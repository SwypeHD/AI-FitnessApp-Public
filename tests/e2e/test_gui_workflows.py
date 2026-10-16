"""End-to-end tests for GUI-driven workflows.

These reproduce the exact sequences a user performs in the browser: log food
across different meal slots, delete items, move items, and verify that the
GET /log response (which drives all UI rendering) returns the correct slot
assignments at every step.
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


def get_log(client):
    today = datetime.now().strftime("%Y-%m-%d")
    resp = client.get(f"/log/{today}")
    assert resp.status_code == 200
    return resp.json()


def food_names_in_slot(log, slot):
    """Return the list of food names under a given slot in the log response."""
    slot_data = log.get("slots", {}).get(slot)
    if not slot_data:
        return []
    return [f["name"] for f in slot_data["foods"]]


def all_food_names(log):
    """Return a flat list of (slot, name) pairs from the log response."""
    result = []
    for slot, data in log.get("slots", {}).items():
        for f in data["foods"]:
            result.append((slot, f["name"]))
    return result


class TestDeletePreservesSlotAssignment:
    """Regression: deleting a food from one slot must NOT move foods from other slots."""

    def test_delete_breakfast_leaves_lunch_in_lunch(self, client):
        """Log breakfast + lunch, delete breakfast food, verify lunch stays in lunch."""
        r1 = post(client, "200g chicken breast for lunch")
        assert r1["status"] == "logged"

        r2 = post(client, "2 eggs for breakfast")
        assert r2["status"] == "logged"

        log_before = get_log(client)
        assert "chicken breast" in food_names_in_slot(log_before, "lunch")
        assert "eggs" in food_names_in_slot(log_before, "breakfast")

        post(client, "delete eggs")

        log_after = get_log(client)
        assert food_names_in_slot(log_after, "breakfast") == [], \
            f"Breakfast should be empty after deleting eggs, got {food_names_in_slot(log_after, 'breakfast')}"
        assert "chicken breast" in food_names_in_slot(log_after, "lunch"), \
            f"Chicken should still be in lunch, got slots: {all_food_names(log_after)}"

    def test_delete_lunch_leaves_breakfast_in_breakfast(self, client):
        """Reverse direction: delete lunch, breakfast stays."""
        post(client, "2 eggs for breakfast")
        post(client, "200g chicken breast for lunch")

        post(client, "delete chicken breast")

        log = get_log(client)
        assert food_names_in_slot(log, "lunch") == []
        assert "eggs" in food_names_in_slot(log, "breakfast")

    def test_delete_one_of_two_in_same_slot(self, client):
        """Delete one food from a slot that has two, the other stays."""
        post(client, "200g chicken breast for lunch")
        post(client, "200g rice for lunch")

        post(client, "delete chicken breast")

        log = get_log(client)
        lunch_names = food_names_in_slot(log, "lunch")
        assert "chicken breast" not in lunch_names
        assert "rice" in lunch_names


class TestDeleteThenLog:
    """After deleting, newly logged food should go to its correct slot."""

    def test_log_after_delete_goes_to_correct_slot(self, client):
        post(client, "2 eggs for breakfast")
        post(client, "delete eggs")
        post(client, "200g chicken breast for lunch")

        log = get_log(client)
        assert food_names_in_slot(log, "breakfast") == []
        assert "chicken breast" in food_names_in_slot(log, "lunch")


class TestMovePreservesOtherSlots:
    """Moving a food to a different slot must not affect other foods."""

    def test_move_does_not_affect_other_foods(self, client):
        post(client, "200g chicken breast for lunch")
        post(client, "2 eggs for breakfast")

        post(client, "move eggs to dinner")

        log = get_log(client)
        assert "chicken breast" in food_names_in_slot(log, "lunch"), \
            f"Chicken should remain in lunch, got: {all_food_names(log)}"
        assert "eggs" in food_names_in_slot(log, "dinner"), \
            f"Eggs should be in dinner after move, got: {all_food_names(log)}"
        assert food_names_in_slot(log, "breakfast") == []


class TestMultiSlotIntegrity:
    """Full workflow: log across all slots, delete from middle, verify integrity."""

    def test_four_slot_delete_middle(self, client):
        post(client, "2 eggs for breakfast")
        post(client, "200g chicken breast for lunch")
        post(client, "200g rice for dinner")
        post(client, "1 serving almonds for snack")

        log_full = get_log(client)
        assert len(log_full["slots"]) == 4

        post(client, "delete chicken breast")

        log_after = get_log(client)
        assert "eggs" in food_names_in_slot(log_after, "breakfast")
        assert food_names_in_slot(log_after, "lunch") == []
        assert "rice" in food_names_in_slot(log_after, "dinner")
        assert "almonds" in food_names_in_slot(log_after, "snack")

    def test_delete_all_then_relog(self, client):
        post(client, "2 eggs for breakfast")
        post(client, "200g chicken breast for lunch")

        post(client, "delete eggs")
        post(client, "delete chicken breast")

        log_empty = get_log(client)
        assert log_empty["slots"] == {} or all(
            len(data["foods"]) == 0 for data in log_empty["slots"].values()
        )

        post(client, "200g rice for dinner")
        log_final = get_log(client)
        assert "rice" in food_names_in_slot(log_final, "dinner")
        assert food_names_in_slot(log_final, "breakfast") == []
        assert food_names_in_slot(log_final, "lunch") == []
