"""Table-driven tests for the reconciliation precedence matrix.

This is the highest-value test surface in the app: it pins down exactly how the
deterministic parser, knowledge base, LLM, and prior user answers combine.
"""

import pytest

from fitness.application.reconciliation import reconcile
from fitness.domain.candidate import CandidateFood, CandidateMeal
from fitness.domain.value_objects import (
    FieldValue,
    MealTimeSlot,
    Provenance,
    Quantity,
    Unit,
)

P = Provenance


def fv(value, provenance, confidence=1.0):
    return FieldValue(value, provenance, confidence)


def cfood(name=None, name_prov=P.DETERMINISTIC, calories=None, cal_prov=P.DETERMINISTIC):
    cf = CandidateFood()
    if name is not None:
        cf.name = fv(name, name_prov)
    if calories is not None:
        cf.calories = fv(calories, cal_prov)
    return cf


class TestMealTimePrecedence:
    @pytest.mark.parametrize(
        "a_prov, b_prov, winner_prov",
        [
            (P.DETERMINISTIC, P.LLM, P.DETERMINISTIC),
            (P.LLM, P.DETERMINISTIC, P.DETERMINISTIC),
            (P.USER, P.DETERMINISTIC, P.USER),
            (P.KNOWLEDGE_BASE, P.LLM, P.KNOWLEDGE_BASE),
            (P.DEFAULT, P.LLM, P.LLM),
        ],
    )
    def test_highest_provenance_wins(self, a_prov, b_prov, winner_prov):
        a = CandidateMeal(meal_time=fv(MealTimeSlot.LUNCH, a_prov))
        b = CandidateMeal(meal_time=fv(MealTimeSlot.DINNER, b_prov))
        result = reconcile([a, b])
        assert result.candidate.meal_time.provenance is winner_prov

    def test_same_provenance_keeps_incumbent(self):
        a = CandidateMeal(meal_time=fv(MealTimeSlot.LUNCH, P.LLM, 0.6))
        b = CandidateMeal(meal_time=fv(MealTimeSlot.DINNER, P.LLM, 0.6))
        result = reconcile([a, b])
        assert result.candidate.meal_time.value is MealTimeSlot.LUNCH

    def test_higher_confidence_wins_within_same_provenance(self):
        a = CandidateMeal(meal_time=fv(MealTimeSlot.LUNCH, P.LLM, 0.4))
        b = CandidateMeal(meal_time=fv(MealTimeSlot.DINNER, P.LLM, 0.9))
        result = reconcile([a, b])
        assert result.candidate.meal_time.value is MealTimeSlot.DINNER


class TestPriorStickiness:
    def test_prior_user_value_survives_new_extraction(self):
        prior = CandidateMeal(meal_time=fv(MealTimeSlot.LUNCH, P.USER))
        new = CandidateMeal(meal_time=fv(MealTimeSlot.BREAKFAST, P.LLM))
        result = reconcile([new], prior=prior)
        assert result.candidate.meal_time.value is MealTimeSlot.LUNCH
        assert result.candidate.meal_time.provenance is P.USER


class TestFoodAlignment:
    def test_foods_with_same_normalized_name_merge(self):
        det = CandidateMeal(foods=[cfood(name="Chicken Breasts")])
        llm = CandidateMeal(foods=[cfood(name="chicken breast", calories=165, cal_prov=P.LLM)])
        result = reconcile([det, llm])
        assert len(result.candidate.foods) == 1
        merged = result.candidate.foods[0]
        assert merged.name.value == "Chicken Breasts"  # deterministic name kept
        assert merged.calories.value == 165  # llm filled the gap

    def test_distinct_foods_stay_separate(self):
        meal = CandidateMeal(foods=[cfood(name="rice"), cfood(name="chicken")])
        result = reconcile([meal])
        assert len(result.candidate.foods) == 2

    def test_deterministic_calories_beat_llm_on_same_food(self):
        det = CandidateMeal(foods=[cfood(name="egg", calories=78, cal_prov=P.DETERMINISTIC)])
        llm = CandidateMeal(foods=[cfood(name="egg", calories=90, cal_prov=P.LLM)])
        result = reconcile([det, llm])
        merged = result.candidate.foods[0]
        assert merged.calories.value == 78
        assert merged.calories.provenance is P.DETERMINISTIC


class TestNotes:
    def test_flags_calorie_divergence_beyond_tolerance(self):
        det = CandidateMeal(foods=[cfood(name="egg", calories=78, cal_prov=P.DETERMINISTIC)])
        llm = CandidateMeal(foods=[cfood(name="egg", calories=140, cal_prov=P.LLM)])
        result = reconcile([det, llm])
        assert any("differ" in n and "egg" in n for n in result.notes)

    def test_no_divergence_note_within_tolerance(self):
        det = CandidateMeal(foods=[cfood(name="egg", calories=78, cal_prov=P.DETERMINISTIC)])
        llm = CandidateMeal(foods=[cfood(name="egg", calories=80, cal_prov=P.LLM)])
        result = reconcile([det, llm])
        assert result.notes == []

    def test_flags_llm_only_food_as_unverified(self):
        llm = CandidateMeal(
            foods=[cfood(name="exotic fruit", name_prov=P.LLM, calories=50, cal_prov=P.LLM)]
        )
        result = reconcile([llm])
        assert any("unverified" in n and "exotic fruit" in n for n in result.notes)

    def test_verified_food_not_flagged(self):
        det = CandidateMeal(foods=[cfood(name="egg", name_prov=P.DETERMINISTIC)])
        result = reconcile([det])
        assert result.notes == []


class TestEmptyAndUnnamed:
    def test_empty_sources(self):
        result = reconcile([])
        assert result.candidate.meal_time is None
        assert result.candidate.foods == []

    def test_unnamed_food_passes_through(self):
        unnamed = CandidateFood()
        unnamed.quantity = fv(Quantity(2, Unit.SERVING), P.DETERMINISTIC)
        result = reconcile([CandidateMeal(foods=[unnamed])])
        assert len(result.candidate.foods) == 1
        assert result.candidate.foods[0].name is None
