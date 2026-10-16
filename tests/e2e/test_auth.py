"""Shared-secret API auth.

The default must stay wide open: turning auth on is opt-in, so local development and
the rest of the suite are unaffected.
"""

from __future__ import annotations

import tempfile

import pytest
from fastapi.testclient import TestClient

from fitness.config.composition import Container
from fitness.config.settings import Settings
from fitness.web.app import create_app
from fitness.web.dependencies import get_container

TOKEN = "s3cret-token-value"


def _client(token: str = ""):
    settings = Settings(data_dir=tempfile.mkdtemp(), auth_token=token)
    container = Container(settings)
    app = create_app(settings)
    app.dependency_overrides[get_container] = lambda: container
    return TestClient(app)


class TestDisabledByDefault:
    def test_no_token_configured_allows_everything(self):
        with _client() as c:
            assert c.get("/profile").status_code == 200
            assert c.post("/messages", json={"text": "hi"}).status_code == 200

    def test_settings_default_is_empty(self):
        assert Settings(data_dir=tempfile.mkdtemp()).auth_token == ""


class TestEnabled:
    def test_api_rejected_without_token(self):
        with _client(TOKEN) as c:
            r = c.get("/profile")
            assert r.status_code == 401
            assert "token" in r.json()["detail"].lower()

    def test_api_allowed_with_header(self):
        with _client(TOKEN) as c:
            assert c.get("/profile", headers={"X-Auth-Token": TOKEN}).status_code == 200

    def test_api_allowed_with_query_param(self):
        with _client(TOKEN) as c:
            assert c.get(f"/profile?token={TOKEN}").status_code == 200

    def test_api_allowed_with_cookie(self):
        with _client(TOKEN) as c:
            c.cookies.set("fittrack_token", TOKEN)
            assert c.get("/profile").status_code == 200

    def test_wrong_token_rejected(self):
        with _client(TOKEN) as c:
            assert c.get("/profile", headers={"X-Auth-Token": "nope"}).status_code == 401

    def test_writes_are_protected(self):
        """Reads aren't the only risk — unauthenticated writes would be worse."""
        with _client(TOKEN) as c:
            r = c.post("/messages", json={"text": "I had 3 eggs"})
            assert r.status_code == 401

    def test_token_prefix_is_not_accepted(self):
        with _client(TOKEN) as c:
            assert c.get("/profile", headers={"X-Auth-Token": TOKEN[:-1]}).status_code == 401

    def test_empty_header_rejected(self):
        with _client(TOKEN) as c:
            assert c.get("/profile", headers={"X-Auth-Token": ""}).status_code == 401


class TestOpenPaths:
    def test_app_shell_loads_without_token(self):
        """The page must load so it can prompt for the token."""
        with _client(TOKEN) as c:
            assert c.get("/static/index.html").status_code == 200

    def test_health_open_without_token(self):
        with _client(TOKEN) as c:
            assert c.get("/health").status_code == 200

    @pytest.mark.parametrize("path", ["/static/manifest.json", "/static/sw.js"])
    def test_pwa_assets_open(self, path):
        with _client(TOKEN) as c:
            assert c.get(path).status_code == 200
