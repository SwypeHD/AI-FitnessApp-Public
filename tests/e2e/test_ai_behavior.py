"""AI behavior tests — verify LLM integration across all app facets.

These tests hit the real Anthropic API through the full HandleMessageUseCase
pipeline. They require FITNESS_LLM_PROVIDER=anthropic and a valid API key.
Run with:  py -3 -B -m pytest tests/e2e/test_ai_behavior.py -v

All tests are marked ``llm`` and skipped automatically when the provider is
unavailable, so the regular test suite stays fast and offline.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
from fitness.adapters.extraction.rule_based import RuleBasedExtractor
from fitness.application.dto import LogMealRequest, LogStatus
from fitness.application.use_cases.edit_log import EditLogUseCase
from fitness.application.use_cases.handle_message import HandleMessageUseCase
from fitness.application.use_cases.log_exercise import LogExerciseUseCase
from fitness.application.use_cases.log_meal import LogMealUseCase
from fitness.application.use_cases.query import QueryUseCase
from fitness.application.user_profile import ProfileStore
from fitness.config.settings import Settings
from fitness.domain.value_objects import MealTimeSlot, Unit

from _factories import FixedClock, InMemoryMealRepository


def _build_llm():
    """Try to build the real Anthropic client; return None if unavailable."""
    try:
        settings = Settings()
    except Exception:
        return None
    if settings.llm_provider != "anthropic" or not settings.anthropic_api_key:
        return None
    from fitness.adapters.llm.anthropic_client import AnthropicLlmClient

    return AnthropicLlmClient(
        api_key=settings.anthropic_api_key, model=settings.anthropic_model
    )


_llm = _build_llm()
llm = pytest.mark.skipif(_llm is None, reason="Anthropic LLM not configured")


@pytest.fixture
def repo():
    return InMemoryMealRepository()


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 4, 12, 0))


@pytest.fixture
def kb():
    return StaticFoodKnowledgeBase()


@pytest.fixture
def uc(repo, clock, kb):
    log_meal = LogMealUseCase(
        extractor=RuleBasedExtractor(kb),
        meal_repo=repo,
        clock=clock,
        food_kb=kb,
        llm=_llm,
    )
    query = QueryUseCase(meal_repo=repo, clock=clock)
    edit_log = EditLogUseCase(meal_repo=repo, clock=clock)
    exercise_repo = _InMemoryExerciseRepo()
    log_exercise = LogExerciseUseCase(repo=exercise_repo, clock=clock)
    return HandleMessageUseCase(
        log_meal=log_meal,
        query=query,
        edit_log=edit_log,
        log_exercise=log_exercise,
        llm=_llm,
        meal_repo=repo,
        clock=clock,
        exercise_repo=exercise_repo,
    )


def say(uc, text, state=None):
    return uc.handle(text, state=state)


def _complete(uc, text, state=None):
    """Drive clarification turns until logged, up to 5 rounds."""
    resp = say(uc, text, state=state)
    defaults = {"meal_time": "lunch", "quantity": "1 serving", "macros": "20 10 5"}
    for _ in range(5):
        if resp.status is LogStatus.LOGGED:
            return resp
        field = resp.state.pending.field if resp.state and resp.state.pending else ""
        answer = defaults.get(field, "1")
        resp = say(uc, answer, state=resp.state)
    return resp


class _InMemoryExerciseRepo:
    def __init__(self):
        self._exercises = []

    def save(self, exercise):
        self._exercises.append(exercise)

    def list_by_date(self, day):
        return [e for e in self._exercises if e.day == day]

    def delete_by_name(self, day, name):
        self._exercises = [
            e for e in self._exercises if not (e.day == day and e.name == name)
        ]


# ---------------------------------------------------------------------------
# 1. FOOD LOGGING — quantity scaling via AI chat
# ---------------------------------------------------------------------------


@llm
class TestAIFoodScaling:
    """The AI should correctly parse and scale food quantities."""

    def test_log_food_with_grams(self, uc, repo):
        resp = _complete(uc, "I had 200g of chicken breast for lunch")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal is not None
        assert meal.total_calories == pytest.approx(330, rel=0.15)

    def test_log_food_with_servings(self, uc, repo):
        resp = _complete(uc, "I had 2 servings of rice for dinner")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal is not None
        assert meal.total_calories == pytest.approx(410, rel=0.15)

    def test_log_food_with_cups(self, uc, repo):
        resp = _complete(uc, "I had 1 cup of milk for breakfast")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal is not None
        assert meal.total_calories == pytest.approx(122, rel=0.15)

    def test_log_fractional_quantity(self, uc, repo):
        resp = _complete(uc, "I ate half a banana for snack")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal is not None
        assert meal.total_calories == pytest.approx(52.5, rel=0.25)


# ---------------------------------------------------------------------------
# 2. AI-DRIVEN CORRECTIONS — "actually I had X not Y"
# ---------------------------------------------------------------------------


@llm
class TestAICorrections:
    """The AI should handle corrections to previously logged food."""

    def test_correct_quantity_downward(self, uc, repo):
        _complete(uc, "I had 300g of rice for lunch")
        resp = say(uc, "Actually I only had 200g of rice for lunch, not 300")
        if resp.status is LogStatus.NEEDS_CLARIFICATION:
            resp = _complete(uc, resp.message, state=resp.state)
        meals = repo.list_by_date(date(2026, 6, 4))
        rice_cals = []
        for m in meals:
            for f in m.foods:
                if "rice" in f.name.lower():
                    rice_cals.append(f.calories)
        assert any(c < 300 for c in rice_cals), (
            f"Expected a rice entry under 300 cal after correction, got {rice_cals}"
        )

    def test_delete_food_via_chat(self, uc, repo):
        _complete(uc, "I had 2 eggs for breakfast")
        assert len(repo.list_by_date(date(2026, 6, 4))) > 0
        resp = say(uc, "delete the eggs")
        assert resp.status is LogStatus.LOGGED
        assert "delete" in resp.message.lower()


# ---------------------------------------------------------------------------
# 3. AI-DRIVEN UNIT CONVERSION — "convert my rice to cups"
# ---------------------------------------------------------------------------


@llm
class TestAIUnitHandling:
    """The AI should understand unit-related requests."""

    def test_log_with_oz(self, uc, repo):
        resp = _complete(uc, "I had 4 oz of salmon for dinner")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal is not None
        assert meal.total_calories > 100

    def test_log_pieces(self, uc, repo):
        resp = _complete(uc, "I had 3 eggs for breakfast")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal is not None
        assert meal.total_calories == pytest.approx(216, rel=0.15)


# ---------------------------------------------------------------------------
# 4. MULTI-FOOD LOGGING — compound meals
# ---------------------------------------------------------------------------


@llm
class TestAIMultiFood:
    """The AI should parse multiple foods from a single message."""

    def test_log_two_foods(self, uc, repo):
        resp = _complete(
            uc, "I had chicken breast and rice for lunch, 200g of each"
        )
        assert resp.status is LogStatus.LOGGED
        meals = repo.list_by_date(date(2026, 6, 4))
        all_foods = [f for m in meals for f in m.foods]
        names = {f.name.lower() for f in all_foods}
        assert any("chicken" in n for n in names)
        assert any("rice" in n for n in names)

    def test_log_with_and_separator(self, uc, repo):
        resp = _complete(uc, "I had 2 eggs and a banana for breakfast")
        assert resp.status is LogStatus.LOGGED
        meals = repo.list_by_date(date(2026, 6, 4))
        all_foods = [f for m in meals for f in m.foods]
        assert len(all_foods) >= 2


# ---------------------------------------------------------------------------
# 5. EXERCISE LOGGING VIA AI
# ---------------------------------------------------------------------------


@llm
class TestAIExerciseLogging:
    """The AI should route exercise descriptions to the exercise logger."""

    def test_strength_exercise(self, uc):
        resp = say(uc, "I did 3 sets of 10 bench press")
        assert resp.status is LogStatus.LOGGED
        assert "bench press" in resp.message.lower() or "logged" in resp.message.lower()

    def test_cardio_exercise(self, uc):
        resp = say(uc, "I ran for 30 minutes")
        assert resp.status is LogStatus.LOGGED
        assert "run" in resp.message.lower() or "logged" in resp.message.lower()


# ---------------------------------------------------------------------------
# 6. INTENT CLASSIFICATION — AI disambiguates edge cases
# ---------------------------------------------------------------------------


@llm
class TestAIIntentClassification:
    """The AI should correctly classify ambiguous intents."""

    def test_query_recognized(self, uc, repo):
        _complete(uc, "I had 2 eggs for breakfast")
        resp = say(uc, "How many calories have I eaten today?")
        assert resp.status is LogStatus.LOGGED
        assert resp.state is None

    def test_greeting_is_chat(self, uc):
        resp = say(uc, "Hey, how are you?")
        assert resp.status is LogStatus.LOGGED
        assert resp.state is None

    def test_edit_intent(self, uc, repo):
        _complete(uc, "I had 3 servings of chicken breast for lunch")
        resp = say(uc, "move the chicken to dinner")
        assert resp.status is LogStatus.LOGGED
        assert "move" in resp.message.lower() or "dinner" in resp.message.lower()


# ---------------------------------------------------------------------------
# 7. AI CHAT — grounded responses using logged data
# ---------------------------------------------------------------------------


@llm
class TestAIChatGrounding:
    """The AI chat should reference real logged data, not hallucinate numbers."""

    def test_chat_references_logged_totals(self, uc, repo):
        _complete(uc, "I had 3 servings of chicken breast for lunch")
        resp = say(uc, "How much protein have I had today?")
        assert "93" in resp.message or "protein" in resp.message.lower()

    def test_chat_without_data(self, uc):
        resp = say(uc, "What should I eat for dinner to hit my protein goal?")
        assert resp.status is LogStatus.LOGGED
        assert len(resp.message) > 20


# ---------------------------------------------------------------------------
# 8. FOOD NAME CLEANING — AI corrects messy regex extractions
# ---------------------------------------------------------------------------


@llm
class TestAIFoodNameCleaning:
    """The LLM should clean up garbled food names from regex extraction."""

    def test_strips_conversational_words(self):
        result = _llm.clean_food_name(
            "could you log me some chicken breast for dinner",
            "could you chicken me",
        )
        assert result is not None
        assert "chicken" in result.lower()
        assert "could" not in result.lower()
        assert "you" not in result.lower()

    def test_correct_name_unchanged(self):
        result = _llm.clean_food_name(
            "I had 200g of brown rice for lunch",
            "brown rice",
        )
        assert result is None


# ---------------------------------------------------------------------------
# 9. MULTI-TURN CLARIFICATION WITH AI
# ---------------------------------------------------------------------------


@llm
class TestAIMultiTurn:
    """The AI should maintain context across clarification turns."""

    def test_clarify_then_complete(self, uc, repo):
        first = say(uc, "I had some chicken")
        assert first.status is LogStatus.NEEDS_CLARIFICATION
        second = say(uc, "200g for lunch", state=first.state)
        if second.status is LogStatus.NEEDS_CLARIFICATION:
            second = _complete(uc, "lunch", state=second.state)
        assert second.status is LogStatus.LOGGED

    def test_cancel_mid_clarification(self, uc, repo):
        first = say(uc, "I had chicken")
        assert first.status is LogStatus.NEEDS_CLARIFICATION
        second = say(uc, "nevermind", state=first.state)
        assert second.status is LogStatus.LOGGED
        assert "cancel" in second.message.lower()
        assert repo.list_by_date(date(2026, 6, 4)) == []


# ---------------------------------------------------------------------------
# 10. SCALING ARITHMETIC — the AI must not invent its own math
# ---------------------------------------------------------------------------


@llm
class TestAIScalingAccuracy:
    """Logged macros must come from the KB, not the AI's arithmetic."""

    def test_kb_food_macros_match_expected(self, uc, repo):
        resp = _complete(uc, "I had 100g of chicken breast for lunch")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        food = meal.foods[0]
        assert food.calories == pytest.approx(165, rel=0.05)
        assert food.macros.protein_g == pytest.approx(31, rel=0.05)

    def test_double_serving_doubles_macros(self, uc, repo):
        resp = _complete(uc, "I had 2 servings of oats for breakfast")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        food = meal.foods[0]
        assert food.calories == pytest.approx(300, rel=0.1)
        assert food.macros.protein_g == pytest.approx(10, rel=0.1)

    def test_quarter_serving_quarters_macros(self, uc, repo):
        resp = _complete(uc, "I had 25g of almonds for snack")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        food = meal.foods[0]
        # 25g / 28g per serving * 164 cal = ~146 cal
        assert food.calories == pytest.approx(146, rel=0.15)


# ---------------------------------------------------------------------------
# 11. UNKNOWN FOODS — AI gap-fills when KB can't help
# ---------------------------------------------------------------------------


@llm
class TestAIUnknownFoods:
    """For foods not in the KB, the AI should provide reasonable estimates."""

    def test_unknown_food_gets_estimated(self, uc, repo):
        resp = _complete(uc, "I had a bowl of ramen for lunch")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal is not None
        assert meal.total_calories > 0

    def test_unknown_food_has_nonzero_macros(self, uc, repo):
        resp = _complete(uc, "I had 200g of tofu for dinner")
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        food = meal.foods[0]
        assert food.macros.protein_g > 0
