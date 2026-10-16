"""Comprehensive natural-language tests against the real system.

Tests a wide range of user inputs for exercise logging, food logging,
settings changes, and queries — all phrased as a real user would,
including slang, typos, run-on sentences, and unusual formatting.

Runs through the full stack including LLM inference.

Run with:  py -3 -B -m pytest tests/e2e/test_natural_language.py -v
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


def get_exercises(client):
    from datetime import date
    resp = client.get(f"/exercises/{date.today().isoformat()}")
    assert resp.status_code == 200
    return resp.json()


# ---------- EXERCISE LOGGING: structured formats ----------

class TestExerciseStructured:
    """Exercises with complete set/rep/weight info in one message."""

    def test_standard_format(self, client):
        """Classic gym bro format."""
        r = chat(client, "3 sets of 10 bench press at 185 lbs")
        assert r["status"] == "logged"
        assert "bench press" in r["message"].lower()
        assert "185" in r["message"]

    def test_shorthand_x_notation(self, client):
        """3x10 @ 135 format."""
        r = chat(client, "bench 3x10 @ 135")
        assert r["status"] == "logged"
        assert "135" in r["message"]

    def test_reps_before_sets(self, client):
        """Some people say reps first."""
        r = chat(client, "did 10 reps of bench press for 3 sets at 185")
        assert r["status"] == "logged"

    def test_mixed_weights(self, client):
        """Different weights across sets."""
        r = chat(client, "4 sets of 15 reps of bench press, 2 sets at 165 lb and 2 at 175")
        assert r["status"] == "logged"
        assert "165" in r["message"]
        assert "175" in r["message"]

    def test_with_lbs_unit(self, client):
        """Explicit lbs."""
        r = chat(client, "squat 5 sets of 5 at 315 lbs")
        assert r["status"] == "logged"
        assert "315" in r["message"]

    def test_with_kg_unit(self, client):
        """Metric user."""
        r = chat(client, "deadlift 3 sets of 5 at 140 kg")
        assert r["status"] == "logged"
        assert "140" in r["message"]

    def test_trailing_weight_no_separator(self, client):
        """Weight after sets with no 'at'/@."""
        r = chat(client, "bench 3x10 185")
        assert r["status"] == "logged"
        assert "185" in r["message"]

    def test_ohp_abbreviation(self, client):
        """OHP should map to overhead press."""
        r = chat(client, "ohp 3x8 at 95 lbs")
        assert r["status"] == "logged"
        assert "overhead press" in r["message"].lower()

    def test_inline_comma_weights(self, client):
        """Per-set weights as comma list after the set info."""
        r = chat(client, "4 sets of 10 bench, 135, 155, 175, 185")
        assert r["status"] == "logged"
        assert "135" in r["message"]
        assert "185" in r["message"]

    def test_weights_were_per_set(self, client):
        """Weights section with WEIGHTxCOUNT notation."""
        r = chat(client, "4 sets of 8 squat, weights were 175x2 and 185x2")
        assert r["status"] == "logged"
        assert "175" in r["message"]
        assert "185" in r["message"]


# ---------- EXERCISE LOGGING: bodyweight ----------

class TestBodyweightExercises:
    """Bodyweight exercises that don't require a weight."""

    def test_pushups_no_weight_needed(self, client):
        """Pushups should log without asking for weight."""
        r = chat(client, "3 sets of 15 pushups")
        assert r["status"] == "logged"
        assert "pushup" in r["message"].lower()

    def test_pullups_no_weight_needed(self, client):
        """Pullups should log without asking for weight."""
        r = chat(client, "5 sets of 10 pullups")
        assert r["status"] == "logged"
        assert "pullup" in r["message"].lower() or "pull" in r["message"].lower()

    def test_dips_no_weight_needed(self, client):
        """Dips should log without asking for weight."""
        r = chat(client, "3 sets of 20 dips")
        assert r["status"] == "logged"

    def test_bodyweight_still_asks_for_reps(self, client):
        """Even bodyweight exercises need reps."""
        r = chat(client, "I did pushups today")
        assert r["status"] == "needs_clarification"
        assert "sets" in r["message"].lower() or "reps" in r["message"].lower()


# ---------- EXERCISE LOGGING: name normalization ----------

class TestExerciseNameNormalization:
    """Past-tense and abbreviation normalization."""

    def test_ran_becomes_run(self, client):
        """'ran' should normalize to 'run'."""
        r = chat(client, "ran for 30 minutes")
        assert r["status"] == "logged"
        assert "run" in r["message"].lower()

    def test_rdl_becomes_romanian_deadlift(self, client):
        """RDL abbreviation."""
        r = chat(client, "did rdl 3 sets of 10 at 185")
        assert r["status"] == "logged"
        assert "romanian deadlift" in r["message"].lower()


# ---------- EXERCISE LOGGING: multi-turn state preservation ----------

class TestExerciseMultiTurn:
    """Multi-turn exercise clarification with state preservation."""

    def test_weight_then_sets_reps(self, client):
        """Give weight first, then sets+reps."""
        r1 = chat(client, "I did bench press")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "185 lbs", context=r1.get("context"))
        assert r2["status"] == "needs_clarification"
        assert "185" in r2["message"]
        r3 = chat(client, "3 sets of 10", context=r2.get("context"))
        assert r3["status"] == "logged"
        assert "185" in r3["message"]

    def test_followup_reps_weight_no_separator(self, client):
        """'10 reps 185lbs, 3 times' follow-up format."""
        r1 = chat(client, "did overhead press")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "10 reps 185lbs, 3 times", context=r1.get("context"))
        assert r2["status"] == "logged"
        assert "185" in r2["message"]

    def test_sets_known_then_weight_then_reps(self, client):
        """Sets given initially, then weight, then reps in three turns."""
        r1 = chat(client, "3 sets of squats")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "185 lbs", context=r1.get("context"))
        assert r2["status"] == "needs_clarification"
        assert "185" in r2["message"]
        assert r2.get("context") is not None
        r3 = chat(client, "10 reps", context=r2.get("context"))
        assert r3["status"] == "logged"
        assert "185" in r3["message"]


# ---------- EXERCISE LOGGING: natural/casual formats ----------

class TestExerciseCasual:
    """Casual, conversational exercise inputs."""

    def test_just_did_gym(self, client):
        """Super vague — should ask for details."""
        r = chat(client, "just got back from the gym, hit bench press")
        assert r["status"] == "needs_clarification"
        assert "sets" in r["message"].lower() or "reps" in r["message"].lower()

    def test_casual_sets_no_weight(self, client):
        """Sets and reps but no weight — should ask."""
        r = chat(client, "log 3 sets of squat")
        assert r["status"] == "needs_clarification"
        assert "reps" in r["message"].lower() or "weight" in r["message"].lower()

    def test_follow_up_reps_and_weight(self, client):
        """Multi-turn: give sets first, then reps + weight."""
        r1 = chat(client, "did 4 sets of bench press")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "10 reps at 185 lbs", context=r1.get("context"))
        assert r2["status"] == "logged"
        assert "185" in r2["message"]

    def test_follow_up_just_weight(self, client):
        """Multi-turn: sets+reps first, then just the weight."""
        r1 = chat(client, "3 sets of 10 squat")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "225 lbs", context=r1.get("context"))
        assert r2["status"] == "logged"
        assert "225" in r2["message"]

    def test_exercise_with_filler_words(self, client):
        """Lots of filler around the actual data."""
        r = chat(client, "so today I went to the gym and I did like 3 sets of 10 reps of bench press at about 185")
        assert r["status"] == "logged"
        assert "bench press" in r["message"].lower()

    def test_just_name_asks_for_everything(self, client):
        """Just the exercise name — should ask for sets/reps/weight."""
        r = chat(client, "I did deadlifts today")
        assert r["status"] == "needs_clarification"

    def test_cancel_mid_clarification(self, client):
        """User cancels after being asked for details."""
        r1 = chat(client, "did some squats")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "nevermind", context=r1.get("context"))
        assert r2["status"] == "logged"
        assert "cancel" in r2["message"].lower()


# ---------- EXERCISE LOGGING: cardio ----------

class TestCardioLogging:
    """Cardio exercises with duration."""

    def test_run_with_time(self, client):
        """Standard cardio log."""
        r = chat(client, "ran for 30 minutes")
        assert r["status"] == "logged"
        assert "30" in r["message"]

    def test_casual_run(self, client):
        """Casual run mention."""
        r = chat(client, "went for a 45 min jog this morning")
        assert r["status"] == "logged"
        assert "45" in r["message"]

    def test_cycling_with_hour(self, client):
        """Hour-based duration."""
        r = chat(client, "biked for 1 hour")
        assert r["status"] == "logged"

    def test_swim_no_time(self, client):
        """Cardio with no duration — should ask."""
        r = chat(client, "I went swimming today")
        assert r["status"] == "needs_clarification"
        assert "long" in r["message"].lower() or "minutes" in r["message"].lower()

    def test_swim_follow_up(self, client):
        """Multi-turn cardio: give duration after being asked."""
        r1 = chat(client, "I went swimming")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "about 45 minutes", context=r1.get("context"))
        assert r2["status"] == "logged"
        assert "45" in r2["message"]


# ---------- EXERCISE LOGGING: mobility ----------

class TestMobilityLogging:
    """Mobility/stretching exercises."""

    def test_yoga_with_time(self, client):
        """Standard mobility log."""
        r = chat(client, "did 20 minutes of yoga")
        assert r["status"] == "logged"
        assert "20" in r["message"]

    def test_stretching_session(self, client):
        """Quick stretch."""
        r = chat(client, "stretched for 15 min after my workout")
        assert r["status"] == "logged"
        assert "15" in r["message"]


# ---------- EXERCISE LOGGING: verification ----------

class TestExerciseVerification:
    """Check that exercises actually end up in the database."""

    def test_logged_exercise_appears(self, client):
        """After logging, the exercise shows up in the API."""
        chat(client, "3 sets of 10 bench press at 185 lbs")
        exercises = get_exercises(client)
        assert len(exercises) >= 1
        bp = [e for e in exercises if "bench" in e["name"].lower()]
        assert len(bp) == 1
        assert bp[0]["set_groups"][0]["reps"] == 10
        assert bp[0]["set_groups"][0]["weight"] == 185.0

    def test_multiple_exercises(self, client):
        """Log multiple exercises in separate messages."""
        chat(client, "3 sets of 10 bench press at 185 lbs")
        chat(client, "4 sets of 8 squat at 225 lbs")
        chat(client, "ran for 30 minutes")
        exercises = get_exercises(client)
        assert len(exercises) == 3

    def test_mixed_weight_groups_stored(self, client):
        """Mixed-weight sets are stored correctly."""
        chat(client, "4 sets of 15 bench, 2 sets at 165 and 2 at 175")
        exercises = get_exercises(client)
        bp = [e for e in exercises if "bench" in e["name"].lower()]
        assert len(bp) == 1
        groups = bp[0]["set_groups"]
        assert len(groups) == 2
        weights = sorted(g["weight"] for g in groups)
        assert weights == [165.0, 175.0]


# ---------- FOOD LOGGING: natural formats ----------

class TestFoodNatural:
    """Natural language food logging."""

    def test_simple_food(self, client):
        """Basic food log."""
        r = chat(client, "I had 2 eggs for breakfast")
        assert r["status"] in ("logged", "needs_clarification")

    def test_multiple_foods(self, client):
        """Multiple foods in one message."""
        r = chat(client, "had chicken breast and rice with some broccoli for lunch")
        assert r["status"] in ("logged", "needs_clarification")

    def test_brand_name(self, client):
        """Brand name food."""
        r = chat(client, "just had a Chobani greek yogurt")
        assert r["status"] in ("logged", "needs_clarification")

    def test_casual_snack(self, client):
        """Ultra casual."""
        r = chat(client, "grabbed a protein bar")
        assert r["status"] in ("logged", "needs_clarification")


# ---------- SETTINGS: natural phrasing ----------

class TestSettingsNatural:
    """Settings changes expressed conversationally."""

    def test_set_targets_with_should(self, client):
        """'I should be eating X' phrasing."""
        r = chat(client, "I think my daily calories should be around 2200")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["calorie_target"] == 2200

    def test_set_protein_target(self, client):
        """Set protein specifically."""
        r = chat(client, "set my protein target to 180g")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["protein_target_g"] == 180

    def test_switch_to_imperial(self, client):
        """Unit preference."""
        r = chat(client, "can you switch me to imperial units")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["unit_system"] == "imperial"

    def test_prefer_kg(self, client):
        """Express preference for metric."""
        r = chat(client, "I prefer kg and cm, use metric please")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["unit_system"] == "metric"

    def test_height_and_weight(self, client):
        """Give body stats."""
        r = chat(client, "I'm 5'10 and 180 lbs")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["height_ft"] == 5
        assert profile["height_in"] == 10
        assert profile["weight_lbs"] == 180

    def test_set_age(self, client):
        """Mention age."""
        r = chat(client, "I'm 25 years old")
        assert r["status"] == "logged"
        profile = client.get("/profile").json()
        assert profile["age"] == 25


# ---------- QUERIES: natural phrasing ----------

class TestQueriesNatural:
    """Natural language questions about nutrition/fitness."""

    def test_how_many_calories(self, client):
        """Basic calorie question."""
        r = chat(client, "how many calories have I had today?")
        assert r["status"] == "logged"

    def test_protein_check(self, client):
        """Protein intake check."""
        r = chat(client, "am I hitting my protein goal?")
        assert r["status"] == "logged"

    def test_what_should_i_eat(self, client):
        """Advice question."""
        r = chat(client, "what should I eat for dinner to hit my macros?")
        assert r["status"] == "logged"

    def test_remaining_calories(self, client):
        """Remaining budget question."""
        r = chat(client, "how much room do I have left for dinner?")
        assert r["status"] == "logged"


# ---------- MIXED SESSIONS ----------

class TestMixedSessions:
    """Realistic sessions combining multiple actions."""

    def test_morning_routine(self, client):
        """User logs food, then exercise, then asks a question."""
        r1 = chat(client, "had 3 eggs and toast for breakfast")
        assert r1["status"] in ("logged", "needs_clarification")

        r2 = chat(client, "then went for a 30 minute run")
        assert r2["status"] == "logged"
        assert "30" in r2["message"]

        r3 = chat(client, "how many calories have I burned?")
        assert r3["status"] == "logged"

    def test_gym_session(self, client):
        """Full gym session with multiple exercises."""
        r1 = chat(client, "3 sets of 10 bench press at 185")
        assert r1["status"] == "logged"

        r2 = chat(client, "then 4 sets of 8 squat at 275")
        assert r2["status"] == "logged"

        r3 = chat(client, "finished with 3 sets of 12 curls at 35 lbs")
        assert r3["status"] == "logged"

        exercises = get_exercises(client)
        assert len(exercises) == 3

    def test_exercise_then_food(self, client):
        """Exercise followed by food logging."""
        r1 = chat(client, "just did 5 sets of 5 deadlift at 315")
        assert r1["status"] == "logged"

        r2 = chat(client, "now eating a protein shake with a banana")
        assert r2["status"] in ("logged", "needs_clarification")

    def test_settings_then_exercise(self, client):
        """Change settings then log exercise."""
        chat(client, "set my calorie target to 2800")
        r = chat(client, "did 3 sets of 10 overhead press at 135")
        assert r["status"] == "logged"
        assert "press" in r["message"].lower()

    def test_multi_turn_exercise_then_food(self, client):
        """Clarification exercise flow, then switch to food."""
        r1 = chat(client, "did some bench press")
        assert r1["status"] == "needs_clarification"
        r2 = chat(client, "3 sets of 10 at 185", context=r1.get("context"))
        assert r2["status"] == "logged"
        r3 = chat(client, "ate a chicken sandwich for lunch")
        assert r3["status"] in ("logged", "needs_clarification")
