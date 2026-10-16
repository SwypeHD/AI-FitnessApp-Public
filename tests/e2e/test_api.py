"""End-to-end API tests.

Exercises the full stack through the HTTP surface: FastAPI routes → use-cases → real
rule-based extractor + seed KB → in-memory repository. No LLM. Uses TestClient so
no network is involved.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from fitness.config.composition import Container
from fitness.config.settings import Settings
from fitness.web.app import create_app
from fitness.web.dependencies import get_container


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=str(tmp_path))
    container = Container(settings)

    app = create_app()
    app.dependency_overrides[get_container] = lambda: container
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def post(client, text, context=None):
    body = {"text": text}
    if context is not None:
        body["context"] = context
    resp = client.post("/messages", json=body)
    assert resp.status_code == 200
    return resp.json()


class TestHealthCheck:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}


class TestSingleTurnLog:
    def test_complete_utterance_logs_and_returns_summary(self, client):
        data = post(client, "I had 3 servings of chicken breast for lunch")
        assert data["status"] == "logged"
        assert "495 kcal" in data["message"]
        assert data["meal_id"] is not None
        assert data["context"] is None  # conversation complete

        today = datetime.now().strftime("%Y-%m-%d")
        summary = client.get(f"/summary/{today}").json()
        assert summary["total_calories"] == pytest.approx(495)
        assert summary["meal_count"] == 1


class TestMultiTurnClarification:
    def test_clarify_meal_time_then_log(self, client):
        first = post(client, "I had 3 servings of chicken breast")
        assert first["status"] == "needs_clarification"
        assert first["context"] is not None

        second = post(client, "lunch", context=first["context"])
        assert second["status"] == "logged"
        assert "lunch" in second["message"].lower()

    def test_clarify_quantity_then_log(self, client):
        first = post(client, "I had chicken breast for lunch")
        assert first["status"] == "needs_clarification"

        second = post(client, "200g", context=first["context"])
        assert second["status"] == "logged"
        assert "330 kcal" in second["message"]


class TestSummaryEmpty:
    def test_empty_day(self, client):
        resp = client.get("/summary/2020-01-01").json()
        assert resp["meal_count"] == 0
        assert resp["total_calories"] == 0


class TestEntryPoints:
    """The bare host URL must open the app, not return a JSON 404."""

    def test_root_redirects_to_the_app(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"] == "/static/index.html"

    def test_root_serves_the_page_when_followed(self, client):
        r = client.get("/", follow_redirects=True)
        assert r.status_code == 200
        assert "<!DOCTYPE html>" in r.text

    def test_static_directory_serves_index(self, client):
        r = client.get("/static/", follow_redirects=True)
        assert r.status_code == 200
        assert "<!DOCTYPE html>" in r.text

    def test_api_routes_are_unaffected(self, client):
        assert client.get("/profile").status_code == 200
