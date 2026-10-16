"""End-to-end tests for all AI-assisted user flows through the HTTP API.

Exercises every chat-driven action through POST /messages: food editing, exercise
logging/editing, calendar management, saved meal preview, plan builder, profile
targets, unit toggle, and calendar align. All flows use deterministic regex routing
— no LLM required.

Run with:  py -3 -B -m pytest tests/e2e/test_ai_chat_flows.py -v
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
        c._container = container
        yield c
    app.dependency_overrides.clear()


def chat(client, text, context=None):
    body = {"text": text}
    if context is not None:
        body["context"] = context
    resp = client.post("/messages", json=body)
    assert resp.status_code == 200
    return resp.json()


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 1. FOOD LOGGING via chat
# ---------------------------------------------------------------------------


class TestFoodLogging:
    def test_log_known_food(self, client):
        r = chat(client, "I had 200g chicken breast for lunch")
        assert r["status"] == "logged"
        assert "330" in r["message"]
        assert r["meal_id"] is not None

    def test_log_multiple_foods(self, client):
        r = chat(client, "I had chicken and rice for lunch")
        assert r["status"] in ("logged", "needs_clarification")

    def test_clarification_then_log(self, client):
        r1 = chat(client, "I had chicken breast")
        assert r1["status"] == "needs_clarification"
        assert r1["context"] is not None
        r2 = chat(client, "200g for lunch", context=r1["context"])
        if r2["status"] == "needs_clarification":
            r2 = chat(client, "lunch", context=r2["context"])
        assert r2["status"] == "logged"

    def test_cancel_mid_clarification(self, client):
        r1 = chat(client, "I had chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "nevermind", context=r1["context"])
        assert r2["status"] == "logged"
        assert "cancel" in r2["message"].lower()


# ---------------------------------------------------------------------------
# 2. FOOD EDITING via chat
# ---------------------------------------------------------------------------


class TestFoodEditing:
    def _log_food(self, client):
        return chat(client, "I had 200g chicken breast for lunch")

    def test_delete_food(self, client):
        self._log_food(client)
        r = chat(client, "delete the chicken breast")
        assert r["status"] == "logged"
        assert "delet" in r["message"].lower()

    def test_change_quantity(self, client):
        self._log_food(client)
        r = chat(client, "change the chicken to 300g")
        assert r["status"] == "logged"

    def test_rename_food(self, client):
        self._log_food(client)
        r = chat(client, "rename chicken to grilled chicken")
        assert r["status"] == "logged"

    def test_move_food_slot(self, client):
        self._log_food(client)
        r = chat(client, "move the chicken to dinner")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# 3. EXERCISE LOGGING via chat
# ---------------------------------------------------------------------------


class TestExerciseLogging:
    def test_log_strength_exercise(self, client):
        r = chat(client, "I did 3 sets of 10 bench press at 135")
        assert r["status"] == "logged"
        assert "bench press" in r["message"].lower()

    def test_log_cardio_exercise(self, client):
        r = chat(client, "I ran for 30 minutes")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# 4. EXERCISE EDITING via chat
# ---------------------------------------------------------------------------


class TestExerciseEditing:
    def _log_exercise(self, client):
        client.post("/exercises", json={
            "name": "Bench Press",
            "exercise_type": "strength",
            "set_details": [
                {"reps": 10, "weight": 135},
                {"reps": 10, "weight": 135},
                {"reps": 10, "weight": 135},
            ],
        })

    def test_change_sets_reps_weight(self, client):
        self._log_exercise(client)
        r = chat(client, "change bench press to 4 sets of 10 at 185")
        assert r["status"] == "logged"
        assert "185" in r["message"] or "Updated" in r["message"]
        exercises = client.get(f"/exercises/{today_str()}").json()
        bp = next(e for e in exercises if "Bench" in e["name"])
        assert len(bp["set_details"]) == 4
        assert bp["set_details"][0]["weight"] == 185

    def test_change_weight_only(self, client):
        self._log_exercise(client)
        r = chat(client, "set bench press weight to 225")
        assert r["status"] == "logged"
        exercises = client.get(f"/exercises/{today_str()}").json()
        bp = next(e for e in exercises if "Bench" in e["name"])
        assert all(s["weight"] == 225 for s in bp["set_details"])

    def test_add_set(self, client):
        self._log_exercise(client)
        r = chat(client, "add a set to bench press")
        assert r["status"] == "logged"
        exercises = client.get(f"/exercises/{today_str()}").json()
        bp = next(e for e in exercises if "Bench" in e["name"])
        assert len(bp["set_details"]) == 4

    def test_remove_set(self, client):
        self._log_exercise(client)
        r = chat(client, "remove last set of bench press")
        assert r["status"] == "logged"
        exercises = client.get(f"/exercises/{today_str()}").json()
        bp = next(e for e in exercises if "Bench" in e["name"])
        assert len(bp["set_details"]) == 2


# ---------------------------------------------------------------------------
# 5. CALENDAR MANAGEMENT via chat
# ---------------------------------------------------------------------------


class TestCalendarManagement:
    def _activate_plan(self, client):
        r = chat(client, "activate PPL")
        assert r["status"] == "logged"
        assert "Activated" in r["message"]
        return r

    def test_activate_plan(self, client):
        r = self._activate_plan(client)
        cal = client.get("/calendar").json()
        assert cal["active"] is True

    def test_skip_today(self, client):
        self._activate_plan(client)
        r = chat(client, "skip today")
        assert r["status"] == "logged"
        assert "skip" in r["message"].lower()

    def test_push_back_today(self, client):
        self._activate_plan(client)
        r = chat(client, "push back today")
        assert r["status"] == "logged"
        assert "push" in r["message"].lower()

    def test_mark_today_complete(self, client):
        self._activate_plan(client)
        r = chat(client, "mark today complete")
        assert r["status"] == "logged"
        assert "complete" in r["message"].lower() or "Nice work" in r["message"]

    def test_im_done(self, client):
        self._activate_plan(client)
        r = chat(client, "I'm done")
        assert r["status"] == "logged"

    def test_undo_skip(self, client):
        self._activate_plan(client)
        chat(client, "skip today")
        r = chat(client, "undo skip")
        assert r["status"] == "logged"
        assert "undo" in r["message"].lower()

    def test_align_to_day(self, client):
        self._activate_plan(client)
        r = chat(client, "align to Legs")
        assert r["status"] == "logged"
        assert "Legs" in r["message"]


# ---------------------------------------------------------------------------
# 6. SAVED MEAL MANAGEMENT via chat
# ---------------------------------------------------------------------------


class TestSavedMealFromSlot:
    def test_save_lunch_as_meal(self, client):
        chat(client, "I had 200g chicken breast for lunch")
        r = chat(client, "save today's lunch as chicken and rice")
        assert r["status"] == "logged"
        assert "Saved meal" in r["message"]
        meals = client.get("/saved-meals").json()
        assert len(meals) == 1
        assert meals[0]["name"] == "chicken and rice"

    def test_delete_saved_meal(self, client):
        chat(client, "I had 200g chicken breast for lunch")
        save_result = chat(client, "save lunch as my chicken")
        assert "Saved meal" in save_result["message"], f"Save failed: {save_result['message']}"
        meals = client.get("/saved-meals").json()
        assert len(meals) == 1
        r = chat(client, "delete saved meal my chicken")
        assert r["status"] == "logged"
        assert "Deleted" in r["message"]
        assert len(client.get("/saved-meals").json()) == 0


# ---------------------------------------------------------------------------
# 7. SAVED MEAL PREVIEW (multi-turn: create from KB → confirm)
# ---------------------------------------------------------------------------


class TestSavedMealPreview:
    def test_preview_shows_macros(self, client):
        r = chat(client, "create a saved meal called my lunch with 200g chicken and 1 cup rice")
        assert r["status"] == "needs_clarification"
        assert "chicken breast" in r["message"]
        assert "white rice" in r["message"]
        assert "Total:" in r["message"]
        assert r["context"] is not None
        assert r["context"]["type"] == "saved_meal_preview"

    def test_confirm_saves_meal(self, client):
        r1 = chat(client, "create a saved meal called my lunch with 200g chicken and 1 cup rice")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "yes", context=r1["context"])
        assert r2["status"] == "logged"
        assert "Saved meal" in r2["message"]
        meals = client.get("/saved-meals").json()
        assert len(meals) == 1
        assert meals[0]["name"] == "my lunch"

    def test_cancel_discards(self, client):
        r1 = chat(client, "create a saved meal called test with 100g chicken")
        r2 = chat(client, "no", context=r1["context"])
        assert r2["status"] == "logged"
        assert "cancel" in r2["message"].lower()
        assert len(client.get("/saved-meals").json()) == 0

    def test_modify_quantity_then_confirm(self, client):
        r1 = chat(client, "create a saved meal called test with 200g chicken and 1 cup rice")
        r2 = chat(client, "change chicken to 300g", context=r1["context"])
        assert r2["status"] == "needs_clarification"
        assert "300" in r2["message"]
        r3 = chat(client, "yes", context=r2["context"])
        assert r3["status"] == "logged"
        meals = client.get("/saved-meals").json()
        assert len(meals) == 1
        chicken_item = next(i for i in meals[0]["items"] if "chicken" in i["food_name"])
        assert chicken_item["quantity_g"] == 300.0

    def test_remove_item_then_confirm(self, client):
        r1 = chat(client, "create a saved meal called test with 200g chicken and 1 cup rice")
        r2 = chat(client, "remove the rice", context=r1["context"])
        assert r2["status"] == "needs_clarification"
        r3 = chat(client, "yes", context=r2["context"])
        assert r3["status"] == "logged"
        meals = client.get("/saved-meals").json()
        assert len(meals[0]["items"]) == 1

    def test_intent_escape_during_preview(self, client):
        r1 = chat(client, "create a saved meal called test with 100g chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "how much protein have I had today?", context=r1["context"])
        assert r2["status"] == "logged"
        assert r2["context"] is None
        assert len(client.get("/saved-meals").json()) == 0

    def test_unknown_food_error(self, client):
        r = chat(client, "create a saved meal called test with 100g unicorn meat")
        assert r["status"] == "logged"
        assert "couldn't find" in r["message"].lower()


# ---------------------------------------------------------------------------
# 8. PLAN BUILDER via chat
# ---------------------------------------------------------------------------


class TestPlanBuilder:
    def test_create_ppl_plan(self, client):
        r = chat(client, "create a push pull legs plan")
        assert r["status"] == "logged"
        assert "Created plan" in r["message"]
        assert "activate" in r["message"].lower()
        plans = client.get("/plans").json()
        custom = [p for p in plans if p["id"] not in ("ppl", "upper_lower", "bro_split", "full_body", "ppl_no_rest")]
        assert len(custom) >= 1

    def test_create_custom_plan(self, client):
        r = chat(client, "create a plan with push, pull, legs, rest")
        assert r["status"] == "logged"
        assert "4 days" in r["message"]

    def test_create_4day_upper_lower(self, client):
        r = chat(client, "create a 4-day upper/lower split")
        assert r["status"] == "logged"
        assert "4 days" in r["message"]

    def test_add_day_to_plan(self, client):
        chat(client, "create a plan with push, pull, legs")
        r = chat(client, "add a rest day to my plan")
        assert r["status"] == "logged"
        assert "4 days" in r["message"] or "Added" in r["message"]

    def test_remove_day_from_plan(self, client):
        chat(client, "create a plan with push, pull, legs, rest")
        r = chat(client, "remove rest day from my plan")
        assert r["status"] == "logged"
        assert "3 days" in r["message"] or "Removed" in r["message"]

    def test_rename_day(self, client):
        chat(client, "create a plan with push, pull, legs")
        r = chat(client, "rename push to chest and triceps")
        assert r["status"] == "logged"
        assert "Renamed" in r["message"] or "Chest" in r["message"]

    def test_create_then_activate(self, client):
        r1 = chat(client, "create a plan with push, pull, legs")
        assert "activate" in r1["message"].lower()
        plan_name = r1["message"].split('"')[1]
        r2 = chat(client, f"activate {plan_name}")
        assert r2["status"] == "logged"
        assert "Activated" in r2["message"]
        cal = client.get("/calendar").json()
        assert cal["active"] is True


# ---------------------------------------------------------------------------
# 9. PROFILE TARGETS via chat
# ---------------------------------------------------------------------------


class TestProfileTargets:
    def test_set_calorie_target(self, client):
        r = chat(client, "set my calorie target to 2500")
        assert r["status"] == "logged"
        assert "2500" in r["message"]
        profile = client.get("/profile").json()
        assert profile["calorie_target"] == 2500

    def test_set_protein_target(self, client):
        r = chat(client, "set protein target to 180")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["protein_target_g"] == 180

    def test_set_all_targets(self, client):
        r = chat(client, "set my targets to 2500 calories, 180g protein, 300g carbs, 80g fat")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["calorie_target"] == 2500
        assert profile["protein_target_g"] == 180
        assert profile["carbs_target_g"] == 300
        assert profile["fat_target_g"] == 80


# ---------------------------------------------------------------------------
# 10. UNIT TOGGLE via chat
# ---------------------------------------------------------------------------


class TestUnitToggle:
    def test_switch_to_imperial(self, client):
        r = chat(client, "switch to imperial")
        assert r["status"] == "logged"
        assert "imperial" in r["message"]
        profile = client.get("/profile").json()
        assert profile["unit_system"] == "imperial"

    def test_switch_to_metric(self, client):
        chat(client, "use imperial")
        r = chat(client, "switch to metric")
        assert r["status"] == "logged"
        assert "metric" in r["message"]
        profile = client.get("/profile").json()
        assert profile["unit_system"] == "metric"


# ---------------------------------------------------------------------------
# 11. INTENT ESCAPE — mid-flow escape to different intent
# ---------------------------------------------------------------------------


class TestIntentEscape:
    def test_escape_food_clarification_with_query(self, client):
        """Mid-food-logging clarification, a query should escape the flow."""
        r1 = chat(client, "I had chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "how much protein have I had today?", context=r1["context"])
        assert r2["status"] == "logged"
        assert r2["context"] is None

    def test_escape_food_clarification_with_calendar(self, client):
        """Mid-food-logging, a calendar action should escape."""
        chat(client, "activate PPL")
        r1 = chat(client, "I had chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "skip today", context=r1["context"])
        assert r2["status"] == "logged"
        assert "skip" in r2["message"].lower()


# ---------------------------------------------------------------------------
# 12. FULL WORKFLOW — realistic multi-step user sessions
# ---------------------------------------------------------------------------


class TestFullWorkflows:
    def test_log_food_edit_then_query(self, client):
        """Log food, edit it, then query totals."""
        chat(client, "I had 200g chicken breast for lunch")
        chat(client, "change the chicken to 300g")
        summary = client.get(f"/summary/{today_str()}").json()
        assert summary["meal_count"] >= 1

    def test_create_plan_activate_complete(self, client):
        """Build a plan via chat, activate it, complete a day."""
        chat(client, "create a plan with push, pull, legs")
        plans = client.get("/plans").json()
        custom = [p for p in plans if p["id"] not in ("ppl", "upper_lower", "bro_split", "full_body", "ppl_no_rest")]
        plan_name = custom[0]["name"]
        chat(client, f"activate {plan_name}")
        r = chat(client, "mark today complete")
        assert "complete" in r["message"].lower() or "Nice work" in r["message"]

    def test_saved_meal_roundtrip(self, client):
        """Create a saved meal from KB, confirm, then log it via chat."""
        r1 = chat(client, "create a saved meal called quick lunch with 200g chicken and 1 cup rice")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "yes", context=r1["context"])
        assert r2["status"] == "logged"
        r3 = chat(client, "I had my quick lunch for lunch")
        assert r3["status"] == "logged"
        summary = client.get(f"/summary/{today_str()}").json()
        assert summary["total_calories"] > 0

    def test_exercise_log_edit_delete(self, client):
        """Log an exercise via chat, edit it, then delete it."""
        chat(client, "3 sets of 10 bench press at 135")
        exercises = client.get(f"/exercises/{today_str()}").json()
        assert len(exercises) >= 1
        chat(client, "change bench press to 4 sets of 8 at 185")
        exercises = client.get(f"/exercises/{today_str()}").json()
        bp = next(e for e in exercises if "Bench" in e["name"])
        assert len(bp["set_details"]) == 4
        chat(client, "delete bench press exercise")
        exercises = client.get(f"/exercises/{today_str()}").json()
        assert not any("Bench" in e["name"] for e in exercises)
