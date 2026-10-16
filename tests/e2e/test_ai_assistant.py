"""AI assistant end-to-end tests — verify the full AI experience across every feature.

Tests the actual LLM-powered assistant through the HTTP API using natural,
conversational language. Unlike the deterministic tests in test_ai_chat_flows.py
(which test regex routing with exact patterns), these tests use varied phrasing
to verify the AI understands and routes correctly.

Requires FITNESS_LLM_PROVIDER set to "ollama" or "anthropic" (with valid API key).
Run with:  py -3 -B -m pytest tests/e2e/test_ai_assistant.py -v

All tests are auto-skipped when no LLM provider is configured.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from fitness.config.composition import Container
from fitness.config.settings import Settings
from fitness.web.app import create_app
from fitness.web.dependencies import get_container


def _llm_available() -> bool:
    try:
        settings = Settings()
    except Exception:
        return False
    if settings.llm_provider == "ollama":
        return True
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        return True
    return False


llm = pytest.mark.skipif(not _llm_available(), reason="LLM provider not configured")

pytestmark = llm


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=str(tmp_path))
    container = Container(settings)
    app = create_app()
    app.dependency_overrides[get_container] = lambda: container
    with TestClient(app) as c:
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


def complete(client, text, context=None, max_turns=5):
    """Drive a multi-turn flow to completion."""
    r = chat(client, text, context=context)
    defaults = {"meal_time": "lunch", "quantity": "1 serving", "macros": "20 10 5"}
    for _ in range(max_turns):
        if r["status"] == "logged":
            return r
        if r["context"] and r["context"].get("type") == "saved_meal_preview":
            r = chat(client, "yes", context=r["context"])
            continue
        pending = r["context"] or {}
        field = pending.get("pending", {}).get("field", "")
        answer = defaults.get(field, "1 serving for lunch")
        r = chat(client, answer, context=r["context"])
    return r


# ---------------------------------------------------------------------------
# 1. FOOD LOGGING — natural language variations
# ---------------------------------------------------------------------------


class TestAIFoodLogging:
    def test_natural_phrasing(self, client):
        r = complete(client, "Just had some grilled chicken, maybe 200 grams, for lunch")
        assert r["status"] == "logged"
        assert r["meal_id"] is not None

    def test_casual_multi_food(self, client):
        r = complete(client, "Had eggs and toast for breakfast this morning")
        assert r["status"] == "logged"

    def test_informal_phrasing(self, client):
        r = complete(client, "Grabbed a banana on my way out")
        assert r["status"] == "logged"

    def test_servings_phrasing(self, client):
        r = complete(client, "Two scoops of peanut butter before my workout")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# 2. FOOD EDITING — natural language
# ---------------------------------------------------------------------------


class TestAIFoodEditing:
    def _seed(self, client):
        complete(client, "I had 200g chicken breast for lunch")

    def test_natural_delete(self, client):
        self._seed(client)
        r = chat(client, "Actually forget the chicken, I didn't eat it")
        assert r["status"] == "logged"

    def test_natural_quantity_correction(self, client):
        self._seed(client)
        r = chat(client, "Wait, it was actually only 150g of chicken")
        assert r["status"] == "logged"

    def test_move_slot_naturally(self, client):
        self._seed(client)
        r = chat(client, "Oh that chicken was actually dinner not lunch")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# 3. EXERCISE LOGGING — natural language
# ---------------------------------------------------------------------------


class TestAIExerciseLogging:
    def test_strength_natural(self, client):
        r = chat(client, "I did bench press today, 4 sets of 8 at 185 pounds")
        assert r["status"] == "logged"
        assert "bench" in r["message"].lower()

    def test_cardio_natural(self, client):
        r = chat(client, "Went for a jog this morning, about 25 minutes")
        assert r["status"] == "logged"

    def test_compound_exercise_description(self, client):
        r = chat(client, "Hit squats for 3 sets of 5 at 225, felt heavy today")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# 4. EXERCISE EDITING — natural language
# ---------------------------------------------------------------------------


class TestAIExerciseEditing:
    def _seed(self, client):
        client.post("/exercises", json={
            "name": "Bench Press",
            "exercise_type": "strength",
            "set_details": [
                {"reps": 10, "weight": 135},
                {"reps": 10, "weight": 135},
                {"reps": 10, "weight": 135},
            ],
        })

    def test_update_weight_naturally(self, client):
        self._seed(client)
        r = chat(client, "Actually I used 155 on bench today, not 135")
        assert r["status"] == "logged"

    def test_add_set_naturally(self, client):
        self._seed(client)
        r = chat(client, "Oh I forgot I did one more set of bench")
        assert r["status"] == "logged"

    def test_change_reps(self, client):
        self._seed(client)
        r = chat(client, "Can you update my bench press to 12 reps per set?")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# 5. CALENDAR MANAGEMENT — natural language
# ---------------------------------------------------------------------------


class TestAICalendar:
    def _activate(self, client):
        chat(client, "activate PPL")

    def test_activate_naturally(self, client):
        r = chat(client, "I want to start the push pull legs program")
        assert r["status"] == "logged"
        assert "ctivat" in r["message"].lower() or "PPL" in r["message"] or "Push" in r["message"]

    def test_skip_naturally(self, client):
        self._activate(client)
        r = chat(client, "I'm going to skip my workout today, not feeling it")
        assert r["status"] == "logged"

    def test_push_back_naturally(self, client):
        self._activate(client)
        r = chat(client, "Can you push today's workout to tomorrow?")
        assert r["status"] == "logged"

    def test_complete_naturally(self, client):
        self._activate(client)
        r = chat(client, "Just finished my workout, I'm done for today!")
        assert r["status"] == "logged"

    def test_undo_naturally(self, client):
        self._activate(client)
        chat(client, "skip today")
        r = chat(client, "Actually wait, undo that skip")
        assert r["status"] == "logged"
        assert "undo" in r["message"].lower()

    def test_skip_to_today_naturally(self, client):
        self._activate(client)
        r = chat(client, "I've been away for a few days, just skip everything and catch me up to today")
        assert r["status"] == "logged"

    def test_align_naturally(self, client):
        self._activate(client)
        r = chat(client, "Can you align my calendar so today is legs day?")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# 6. SAVED MEAL MANAGEMENT — natural language
# ---------------------------------------------------------------------------


class TestAISavedMeals:
    def test_save_from_slot_naturally(self, client):
        complete(client, "I had 200g chicken and 1 cup rice for lunch")
        r = chat(client, "That was a great lunch, save it as my go-to lunch")
        assert r["status"] == "logged"
        assert "aved" in r["message"].lower()

    def test_delete_saved_meal_naturally(self, client):
        complete(client, "I had 200g chicken for lunch")
        chat(client, "save today's lunch as test meal")
        r = chat(client, "Can you get rid of that saved meal called test meal?")
        assert r["status"] == "logged"

    def test_log_saved_meal_naturally(self, client):
        complete(client, "I had 200g chicken for lunch")
        chat(client, "save today's lunch as quick chicken")
        r = chat(client, "I had my quick chicken for dinner tonight")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# 7. SAVED MEAL PREVIEW — multi-turn with AI
# ---------------------------------------------------------------------------


class TestAISavedMealPreview:
    def test_create_preview_naturally(self, client):
        r = chat(client, "I want to make a saved meal called power bowl with 200g chicken breast and a cup of rice")
        assert r["status"] == "needs_clarification"
        assert "chicken" in r["message"].lower()
        assert "rice" in r["message"].lower()
        assert "Total" in r["message"]

    def test_confirm_naturally(self, client):
        r1 = chat(client, "Create a saved meal called test with 200g chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "Yeah that looks right, save it", context=r1["context"])
        assert r2["status"] == "logged"
        meals = client.get("/saved-meals").json()
        assert len(meals) == 1

    def test_cancel_naturally(self, client):
        r1 = chat(client, "Make a saved meal called test with 100g chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "Nah never mind, I don't want that", context=r1["context"])
        assert r2["status"] == "logged"
        assert len(client.get("/saved-meals").json()) == 0

    def test_modify_before_saving(self, client):
        r1 = chat(client, "Create a saved meal called test with 200g chicken and 1 cup rice")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "Change the chicken to 300g", context=r1["context"])
        assert r2["status"] == "needs_clarification"
        assert "300" in r2["message"]
        r3 = chat(client, "yes", context=r2["context"])
        assert r3["status"] == "logged"

    def test_intent_escape_during_preview(self, client):
        r1 = chat(client, "Create a saved meal called test with 100g chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "Actually how much protein have I had today?", context=r1["context"])
        assert r2["status"] == "logged"
        assert r2["context"] is None


# ---------------------------------------------------------------------------
# 8. PLAN BUILDER — natural language
# ---------------------------------------------------------------------------


class TestAIPlanBuilder:
    def test_create_plan_naturally(self, client):
        r = chat(client, "Can you make me a push pull legs workout plan?")
        assert r["status"] == "logged"
        assert "plan" in r["message"].lower() or "Created" in r["message"]

    def test_create_custom_plan_naturally(self, client):
        r = chat(client, "Build me a workout routine with chest, back, legs, and shoulders")
        assert r["status"] == "logged"
        assert "Created" in r["message"]

    def test_create_nday_plan(self, client):
        r = chat(client, "I want a 4 day upper lower training split")
        assert r["status"] == "logged"

    def test_add_day_naturally(self, client):
        chat(client, "Create a plan with push, pull, legs")
        r = chat(client, "Can you add a rest day to my workout plan?")
        assert r["status"] == "logged"
        assert "Added" in r["message"] or "Rest" in r["message"]

    def test_remove_day_naturally(self, client):
        chat(client, "Create a plan with push, pull, legs, rest")
        r = chat(client, "Take out the rest day from my plan")
        assert r["status"] == "logged"

    def test_rename_day_naturally(self, client):
        chat(client, "Create a plan with push, pull, legs")
        r = chat(client, "Rename the push day to chest and triceps")
        assert r["status"] == "logged"

    def test_create_then_activate_naturally(self, client):
        r1 = chat(client, "Design me a push pull legs program")
        assert r1["status"] == "logged"
        assert "activate" in r1["message"].lower()
        r2 = chat(client, "Yeah go ahead and activate that plan")
        assert r2["status"] == "logged"


# ---------------------------------------------------------------------------
# 9. PROFILE TARGETS — natural language
# ---------------------------------------------------------------------------


class TestAIProfileTargets:
    def test_set_calorie_target_naturally(self, client):
        r = chat(client, "I want to aim for 2500 calories per day")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["calorie_target"] == 2500

    def test_set_protein_target_naturally(self, client):
        r = chat(client, "Set my protein goal to 180 grams")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["protein_target_g"] == 180

    def test_set_all_macros_naturally(self, client):
        r = chat(client, "My daily targets should be 2500 calories, 180g protein, 300g carbs, and 80g fat")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["calorie_target"] == 2500
        assert profile["protein_target_g"] == 180


# ---------------------------------------------------------------------------
# 10. UNIT TOGGLE — natural language
# ---------------------------------------------------------------------------


class TestAIUnitToggle:
    def test_switch_to_metric_naturally(self, client):
        r = chat(client, "I'd prefer to use kilograms and metric units")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["unit_system"] == "metric"

    def test_switch_to_imperial_naturally(self, client):
        r = chat(client, "Switch me over to pounds and imperial")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["unit_system"] == "imperial"


# ---------------------------------------------------------------------------
# 11. GROUNDED QUERIES — AI uses real logged data
# ---------------------------------------------------------------------------


class TestAIGroundedQueries:
    def test_protein_query_after_logging(self, client):
        complete(client, "I had 200g chicken breast for lunch")
        r = chat(client, "How much protein have I eaten today?")
        assert r["status"] == "logged"
        assert "62" in r["message"] or "protein" in r["message"].lower()

    def test_calorie_query_after_logging(self, client):
        complete(client, "I had 200g chicken breast for lunch")
        r = chat(client, "What's my calorie total for the day?")
        assert r["status"] == "logged"
        assert "330" in r["message"] or "calorie" in r["message"].lower()

    def test_remaining_query(self, client):
        chat(client, "set my calorie target to 2500")
        complete(client, "I had 200g chicken breast for lunch")
        r = chat(client, "How many more calories can I eat today?")
        assert r["status"] == "logged"
        assert len(r["message"]) > 20

    def test_recommendation_uses_context(self, client):
        complete(client, "I had 3 eggs for breakfast")
        r = chat(client, "What should I eat for lunch to get more protein?")
        assert r["status"] == "logged"
        assert len(r["message"]) > 30


# ---------------------------------------------------------------------------
# 12. GENERAL CHAT — conversational responses
# ---------------------------------------------------------------------------


class TestAIChat:
    def test_greeting(self, client):
        r = chat(client, "Hey there, how's it going?")
        assert r["status"] == "logged"
        assert len(r["message"]) > 10

    def test_fitness_advice(self, client):
        r = chat(client, "What are some good exercises for building chest muscles?")
        assert r["status"] == "logged"
        assert len(r["message"]) > 50

    def test_nutrition_advice(self, client):
        r = chat(client, "I'm trying to bulk, how much protein should I aim for?")
        assert r["status"] == "logged"
        assert "protein" in r["message"].lower()


# ---------------------------------------------------------------------------
# 13. PROFILE EXTRACTION — AI understands user info
# ---------------------------------------------------------------------------


class TestAIProfileExtraction:
    def test_name_and_age(self, client):
        r = chat(client, "Hey, I'm Alex, 25 years old")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["name"] == "Alex" or profile["age"] == 25

    def test_height_weight_imperial(self, client):
        r = chat(client, "I'm 6'2 and weigh about 185 pounds")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["weight_lbs"] > 0 or profile["height_ft"] > 0


# ---------------------------------------------------------------------------
# 14. INTENT ESCAPE — AI handles mid-flow pivots gracefully
# ---------------------------------------------------------------------------


class TestAIIntentEscape:
    def test_escape_clarification_with_exercise(self, client):
        r1 = chat(client, "I had some chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "Wait actually, what should I do for lifting today?", context=r1["context"])
        assert r2["status"] == "logged"
        assert r2["context"] is None

    def test_escape_preview_with_log(self, client):
        r1 = chat(client, "Create a saved meal called test with 200g chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "Actually I just had 3 eggs for breakfast", context=r1["context"])
        assert r2["status"] in ("logged", "needs_clarification")

    def test_escape_preview_with_exercise(self, client):
        r1 = chat(client, "Make a saved meal called test with 100g chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "I did 3 sets of 10 bench press at 185", context=r1["context"])
        assert r2["status"] == "logged"
        assert "bench" in r2["message"].lower()


# ---------------------------------------------------------------------------
# 15. FULL CONVERSATIONAL WORKFLOWS — realistic multi-step sessions
# ---------------------------------------------------------------------------


class TestAIFullWorkflows:
    def test_morning_routine(self, client):
        """Simulate a morning session: log breakfast, set targets, ask about macros."""
        complete(client, "Had 3 eggs and 2 slices of toast for breakfast")
        chat(client, "Set my protein target to 180g")
        r = chat(client, "How am I doing on protein so far?")
        assert r["status"] == "logged"
        assert len(r["message"]) > 20

    def test_workout_session(self, client):
        """Simulate a gym session: activate plan, log exercises, complete day."""
        chat(client, "activate push pull legs")
        chat(client, "I did bench press, 4 sets of 8 at 185")
        chat(client, "Then overhead press 3 sets of 10 at 95")
        r = chat(client, "I'm done with my workout")
        assert r["status"] == "logged"

    def test_meal_prep_session(self, client):
        """Create a saved meal, log some food, query totals."""
        r1 = chat(client, "Create a saved meal called chicken rice bowl with 200g chicken and 1 cup rice")
        if r1["status"] == "needs_clarification":
            chat(client, "yes", context=r1["context"])
        complete(client, "I had my chicken rice bowl for lunch")
        r = chat(client, "How many calories was lunch?")
        assert r["status"] == "logged"

    def test_plan_build_and_start(self, client):
        """Build a custom plan and start using it."""
        chat(client, "Build me a plan with push, pull, legs, rest")
        plans = client.get("/plans").json()
        custom = [p for p in plans if p["id"] not in ("ppl", "upper_lower", "bro_split", "full_body", "ppl_no_rest")]
        assert len(custom) >= 1
        plan_name = custom[0]["name"]
        chat(client, f"Activate {plan_name}")
        cal = client.get("/calendar").json()
        assert cal["active"] is True
        chat(client, "I'm done for today")
        r = chat(client, "What's my next workout?")
        assert r["status"] == "logged"
