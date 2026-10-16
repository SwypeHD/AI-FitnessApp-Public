"""Tests that the LLM gap-fill path in LogMealUseCase actually fires and merges correctly.

Uses a scripted FakeLlmClient to simulate the model without network. Verifies:
1. When KB can't fill an unknown food, the LLM's macros are accepted (at LLM provenance).
2. When the LLM is down (raises LlmError), the use-case degrades gracefully.
3. The LLM cannot override deterministic/KB values.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
from fitness.adapters.extraction.rule_based import RuleBasedExtractor
from fitness.application.dto import LogMealRequest, LogStatus
from fitness.application.ports.extraction import ExtractionResult, LlmError
from fitness.application.use_cases.log_meal import LogMealUseCase
from fitness.domain.candidate import CandidateFood, CandidateMeal
from fitness.domain.value_objects import FieldValue, Macros, MealTimeSlot, Provenance, Quantity, Unit

from _factories import FixedClock, InMemoryMealRepository


class FakeLlmClient:
    """Returns scripted extraction results. Simulates the Ollama adapter without network."""

    def __init__(self, foods: list[CandidateFood] | None = None, should_fail: bool = False):
        self._foods = foods or []
        self._should_fail = should_fail

    def estimate(self, text: str, schema_hint: str) -> ExtractionResult:
        if self._should_fail:
            raise LlmError("fake LLM error")
        return ExtractionResult(
            candidate_meal=CandidateMeal(foods=list(self._foods)),
        )

    def classify_intent(self, text):
        raise LlmError("not implemented")

    def chat(self, history, grounding):
        return "fake chat"

    def clean_food_name(self, raw_input, extracted_name):
        return None


def _llm_food(name, calories, protein=0, carbs=0, fat=0):
    cf = CandidateFood()
    cf.offer("name", FieldValue(name, Provenance.LLM, 0.7))
    cf.offer("quantity", FieldValue(Quantity(1, Unit.SERVING), Provenance.LLM, 0.7))
    cf.offer("macros", FieldValue(Macros(protein, carbs, fat), Provenance.LLM, 0.7))
    cf.offer("calories", FieldValue(calories, Provenance.LLM, 0.7))
    return cf


def _make_uc(repo, llm):
    kb = StaticFoodKnowledgeBase()
    return LogMealUseCase(
        extractor=RuleBasedExtractor(kb),
        meal_repo=repo,
        clock=FixedClock(datetime(2026, 6, 4, 12, 0)),
        food_kb=kb,
        llm=llm,
    )


class TestLlmFillsGaps:
    def test_unknown_food_gets_llm_macros(self):
        repo = InMemoryMealRepository()
        llm = FakeLlmClient(foods=[_llm_food("cheesecake", 320, 5, 26, 23)])
        uc = _make_uc(repo, llm)

        resp = uc.handle(LogMealRequest(text="I had 1 serving of cheesecake for lunch"))
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal is not None
        assert meal.foods[0].name == "cheesecake"
        assert meal.foods[0].calories == pytest.approx(320)

    def test_known_food_kb_not_overridden_by_llm(self):
        repo = InMemoryMealRepository()
        # LLM says chicken is 999 cal — but KB says 165. KB wins (higher provenance).
        llm = FakeLlmClient(foods=[_llm_food("chicken breast", 999, 99, 0, 0)])
        uc = _make_uc(repo, llm)

        resp = uc.handle(LogMealRequest(text="I had 1 serving of chicken breast for lunch"))
        assert resp.status is LogStatus.LOGGED
        meal = repo.get(resp.meal_id)
        assert meal.foods[0].calories == pytest.approx(165)  # KB value, not LLM


class TestLlmDown:
    def test_degrades_gracefully_when_llm_fails(self):
        repo = InMemoryMealRepository()
        llm = FakeLlmClient(should_fail=True)
        uc = _make_uc(repo, llm)

        # Known food: still logs fine. The LLM is never even called because the builder
        # is already complete after deterministic + KB — that's the "skip LLM when no
        # gaps" optimization working correctly.
        resp = uc.handle(LogMealRequest(text="I had 2 eggs for breakfast"))
        assert resp.status is LogStatus.LOGGED

    def test_unknown_food_asks_clarification_when_llm_down(self):
        repo = InMemoryMealRepository()
        llm = FakeLlmClient(should_fail=True)
        uc = _make_uc(repo, llm)

        resp = uc.handle(LogMealRequest(text="I had 1 cheesecake for dinner"))
        # LLM failed, KB doesn't know cheesecake -> falls to clarification.
        assert resp.status is LogStatus.NEEDS_CLARIFICATION
