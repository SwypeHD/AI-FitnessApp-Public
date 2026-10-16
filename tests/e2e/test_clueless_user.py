"""Simulate a clueless user interacting with the AI fitness assistant.

This test acts as a realistic user who has never read any docs and just
talks to the app however they feel like.  No knowledge of internal parsing
or routing rules — just natural conversation.

Requires an LLM provider (Ollama or Anthropic).
Run with:  py -3 -B -m pytest tests/e2e/test_clueless_user.py -v
"""

from __future__ import annotations

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


def complete(client, text, context=None, max_turns=5):
    """Drive a multi-turn flow to completion."""
    r = chat(client, text, context=context)
    defaults = {"meal_time": "lunch", "quantity": "1 serving", "macros": "20 10 5"}
    for _ in range(max_turns):
        if r["status"] == "logged":
            return r
        if r.get("context") and r["context"].get("type") == "saved_meal_preview":
            r = chat(client, "yes", context=r["context"])
            continue
        pending = r.get("context") or {}
        field = pending.get("pending", {}).get("field", "")
        answer = defaults.get(field, "1 serving for lunch")
        r = chat(client, answer, context=r["context"])
    return r


# ---------------------------------------------------------------------------
# Scenario 1: First-time user just opening the app and exploring
# ---------------------------------------------------------------------------

class TestFirstTimeUser:
    def test_says_hi(self, client):
        """User opens the app and just says hi."""
        r = chat(client, "hi")
        assert r["status"] == "logged"
        assert len(r["message"]) > 5

    def test_asks_what_app_does(self, client):
        """User has no idea what this app is for."""
        r = chat(client, "what can you do?")
        assert r["status"] == "logged"
        assert len(r["message"]) > 20

    def test_introduces_themselves(self, client):
        """User gives personal info unprompted."""
        r = chat(client, "Hey I'm Mike, I'm 28 and trying to lose some weight")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["name"] == "Mike" or profile["age"] == 28


# ---------------------------------------------------------------------------
# Scenario 2: Logging food in messy, casual ways
# ---------------------------------------------------------------------------

class TestMessyFoodLogging:
    def test_super_casual(self, client):
        """User doesn't specify quantities at all."""
        r = complete(client, "just had a sandwich")
        assert r["status"] == "logged"

    def test_stream_of_consciousness(self, client):
        """User talks like they're texting a friend."""
        r = complete(client, "dude I just crushed like 3 eggs and some toast lol")
        assert r["status"] == "logged"

    def test_uses_brand_names(self, client):
        """User references brands the system won't know."""
        r = complete(client, "Had a Clif bar and a Gatorade after my run")
        assert r["status"] == "logged"

    def test_vague_portions(self, client):
        """User uses imprecise quantities."""
        r = complete(client, "ate a big bowl of oatmeal with some blueberries")
        assert r["status"] == "logged"

    def test_forgets_meal_time(self, client):
        """User doesn't mention when they ate."""
        r = complete(client, "200g chicken breast and rice")
        assert r["status"] == "logged"

    def test_multiple_items_run_on(self, client):
        """User lists foods in a run-on sentence."""
        r = complete(client, "ok so I had eggs toast peanut butter and a banana")
        assert r["status"] == "logged"


# ---------------------------------------------------------------------------
# Scenario 3: Asking questions the way a real person would
# ---------------------------------------------------------------------------

class TestNaturalQuestions:
    def test_am_i_eating_enough(self, client):
        complete(client, "Had 200g chicken for lunch")
        r = chat(client, "am I eating enough protein today?")
        assert r["status"] == "logged"
        assert len(r["message"]) > 20

    def test_what_should_i_eat(self, client):
        r = chat(client, "I'm starving, what should I eat?")
        assert r["status"] == "logged"
        assert len(r["message"]) > 20

    def test_how_many_calories_left(self, client):
        chat(client, "set my calorie target to 2000")
        complete(client, "Had 3 eggs for breakfast")
        r = chat(client, "how many more calories can I have today")
        assert r["status"] == "logged"
        assert len(r["message"]) > 10


# ---------------------------------------------------------------------------
# Scenario 4: Exercise logging without knowing the format
# ---------------------------------------------------------------------------

class TestCasualExerciseLogging:
    def test_just_tells_you_about_gym(self, client):
        """User talks about their workout casually — bench is strength, so asks for details."""
        r = chat(client, "I hit chest today, did bench and some incline stuff")
        assert r["status"] in ("logged", "needs_clarification")

    def test_running_with_details(self, client):
        r = chat(client, "went for a run this morning, maybe like 30 minutes")
        assert r["status"] == "logged"

    def test_home_workout(self, client):
        r = chat(client, "did some pushups and planks at home, maybe 20 minutes total")
        assert r["status"] in ("logged", "needs_clarification")


# ---------------------------------------------------------------------------
# Scenario 5: Settings changes in natural language
# ---------------------------------------------------------------------------

class TestNaturalSettingsChanges:
    def test_calorie_goal_casually(self, client):
        """User mentions a calorie goal in passing."""
        r = chat(client, "I think I should be eating around 2200 calories a day")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["calorie_target"] == 2200

    def test_unit_preference(self, client):
        """User mentions they use pounds."""
        r = chat(client, "I prefer pounds and feet, switch me to imperial")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["unit_system"] == "imperial"

    def test_body_stats(self, client):
        """User gives their stats in conversation."""
        r = chat(client, "I'm 5'10 and about 175 lbs")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["height_ft"] > 0 or profile["weight_lbs"] > 0


# ---------------------------------------------------------------------------
# Scenario 6: Workout planning without knowing the lingo
# ---------------------------------------------------------------------------

class TestCasualPlanBuilding:
    def test_wants_a_workout_schedule(self, client):
        """User asks for a plan without using 'plan' jargon."""
        r = chat(client, "Can you set me up with a workout schedule? I want to do push pull legs")
        assert r["status"] == "logged"
        assert "plan" in r["message"].lower() or "created" in r["message"].lower() or "push" in r["message"].lower()

    def test_simple_plan_request(self, client):
        """User asks plainly."""
        r = chat(client, "make me a 4 day upper lower split")
        assert r["status"] == "logged"

    def test_activate_after_creating(self, client):
        """User creates then wants to start it."""
        r1 = chat(client, "build me a push pull legs plan")
        assert r1["status"] == "logged"
        r2 = chat(client, "ok start that plan")
        assert r2["status"] == "logged"


# ---------------------------------------------------------------------------
# Scenario 7: Mid-conversation pivots (realistic ADHD moments)
# ---------------------------------------------------------------------------

class TestMidConversationPivots:
    def test_starts_logging_then_asks_question(self, client):
        """User starts logging food then pivots to a question."""
        r1 = chat(client, "I had some chicken")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "actually wait, how much protein have I had today?", context=r1["context"])
        assert r2["status"] == "logged"

    def test_logs_food_then_exercise(self, client):
        """User logs food then immediately logs exercise."""
        complete(client, "Had 3 eggs for breakfast")
        r = chat(client, "also I did 3 sets of 10 squats at 185 this morning")
        assert r["status"] == "logged"
        assert "squat" in r["message"].lower()


# ---------------------------------------------------------------------------
# Scenario 8: Realistic full session — morning routine
# ---------------------------------------------------------------------------

class TestRealisticSession:
    def test_full_morning(self, client):
        """Simulate a complete morning interaction."""
        r1 = chat(client, "morning!")
        assert r1["status"] == "logged"

        complete(client, "I had 3 eggs and 2 pieces of toast for breakfast")

        r3 = chat(client, "how's my protein looking so far?")
        assert r3["status"] == "logged"
        assert len(r3["message"]) > 10

    def test_full_gym_day(self, client):
        """Simulate arriving at gym, working out, logging food after."""
        chat(client, "create a push pull legs plan")
        chat(client, "activate push pull legs")

        chat(client, "I did bench press, 4 sets of 8 at 185 pounds")
        chat(client, "then overhead press 3 sets of 10 at 95")

        r = chat(client, "alright I'm done with my workout")
        assert r["status"] == "logged"

        r2 = complete(client, "just had a protein shake, about 30g protein")
        assert r2["status"] == "logged"
