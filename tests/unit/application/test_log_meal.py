"""LogMealUseCase: the multi-turn, deterministic-first logging flow.

Uses the real rule-based extractor + seed KB (both deterministic, no IO) with an in-memory
repository and a fixed clock. These read like small end-to-end conversations.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
from fitness.adapters.extraction.rule_based import RuleBasedExtractor
from fitness.application.dto import LogMealRequest, LogStatus
from fitness.application.use_cases.log_meal import LogMealUseCase
from fitness.domain.value_objects import MealTimeSlot

from _factories import FixedClock, InMemoryMealRepository


@pytest.fixture
def repo():
    return InMemoryMealRepository()


@pytest.fixture
def use_case(repo):
    kb = StaticFoodKnowledgeBase()
    return LogMealUseCase(
        extractor=RuleBasedExtractor(kb),
        meal_repo=repo,
        clock=FixedClock(datetime(2026, 6, 4, 12, 0)),
        food_kb=kb,
    )


def say(use_case, text, prior=None):
    """Send a message, optionally continuing a prior clarification turn."""
    state = prior.state if prior is not None else None
    return use_case.handle(LogMealRequest(text=text, state=state))


class TestSingleTurn:
    def test_complete_utterance_logs_immediately(self, use_case, repo):
        resp = say(use_case, "I had 3 servings of chicken breast for lunch")
        assert resp.status is LogStatus.LOGGED
        assert resp.meal_id is not None
        stored = repo.get(resp.meal_id)
        assert stored.meal_time is MealTimeSlot.LUNCH
        assert stored.total_calories == pytest.approx(495)
        assert "495 kcal" in resp.message  # confirmation built from stored meal


class TestClarifyMealTime:
    def test_asks_then_logs(self, use_case, repo):
        first = say(use_case, "I had 3 servings of chicken breast")
        assert first.status is LogStatus.NEEDS_CLARIFICATION
        assert "breakfast" in first.message.lower()  # meal-time question
        assert repo.list_by_date(date(2026, 6, 4)) == []  # nothing persisted yet

        second = say(use_case, "lunch", prior=first)
        assert second.status is LogStatus.LOGGED
        assert repo.get(second.meal_id).meal_time is MealTimeSlot.LUNCH


class TestClarifyQuantity:
    def test_asks_quantity_then_kb_fills_macros(self, use_case, repo):
        first = say(use_case, "I had chicken breast for lunch")
        assert first.status is LogStatus.NEEDS_CLARIFICATION
        assert "how much" in first.message.lower()

        second = say(use_case, "200g", prior=first)
        assert second.status is LogStatus.LOGGED
        # 200g / 100g serving = 2 servings -> 330 cal, filled from KB after the answer
        assert repo.get(second.meal_id).total_calories == pytest.approx(330)


class TestUnknownFood:
    def test_unknown_food_asks_for_macros_then_derives_calories(self, use_case, repo):
        first = say(use_case, "I had 1 kangaroo steak for dinner")
        # KB can't fill an unknown food, so it must ask. Macros are asked first; calories
        # are then derived from them, so calories is never asked separately.
        assert first.status is LogStatus.NEEDS_CLARIFICATION

        resp = first
        answers = {"macros": "30 0 12", "calories": "250"}
        for _ in range(4):  # safety bound against an unexpected loop
            if resp.status is LogStatus.LOGGED:
                break
            resp = say(use_case, answers.get(resp.state.pending.field, "stuff"), prior=resp)

        assert resp.status is LogStatus.LOGGED
        stored = repo.get(resp.meal_id)
        assert stored.foods[0].name == "kangaroo steak"
        # 30*4 + 0*4 + 12*9 = 228 kcal, derived from the macros the user gave.
        assert stored.foods[0].calories == pytest.approx(228)


class TestStickiness:
    def test_user_answer_is_not_overwritten(self, use_case):
        # Answer meal-time as lunch; it must persist as lunch even though nothing
        # contradicts it. (Stronger stickiness vs. LLM is covered in reconciliation tests.)
        first = say(use_case, "I had 2 eggs")
        second = say(use_case, "breakfast", prior=first)
        assert second.status is LogStatus.LOGGED
        assert second.message.startswith("Logged breakfast")


class TestNothingPersistedUntilComplete:
    def test_clarification_does_not_persist(self, use_case, repo):
        say(use_case, "I had chicken breast")  # incomplete (no qty, no meal_time)
        assert repo.list_by_date(date(2026, 6, 4)) == []
