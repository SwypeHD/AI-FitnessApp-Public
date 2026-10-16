"""The grounding must carry exact logged items, not just totals.

Totals alone ("lunch: 640 kcal") let the model invent plausible items when asked what
was eaten, so these assert the real names reach the prompt.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from fitness.application.use_cases.handle_message import HandleMessageUseCase
from fitness.domain.exercise import Exercise, ExerciseType, SetDetail
from fitness.domain.food import Food
from fitness.domain.meal import Meal, MealTimeSlot
from fitness.domain.value_objects import Macros, Quantity, Unit


class FixedClock:
    def today(self) -> date:
        return date(2026, 8, 8)


class FakeMealRepo:
    def __init__(self, meals=()):
        self._meals = list(meals)

    def list_by_date(self, day):
        return [m for m in self._meals if m.logged_at.date() == day]

    def list_between(self, start, end):
        return list(self._meals)


class FakeExerciseRepo:
    def __init__(self, exercises=()):
        self._exercises = list(exercises)

    def list_by_date(self, day):
        return [e for e in self._exercises if e.day == day]


def _food(name, cals, slot):
    return Food(
        name=name,
        quantity=Quantity(amount=100, unit=Unit.GRAM),
        macros=Macros(protein_g=30, carbs_g=10, fat_g=5),
        calories=cals,
        meal_time=slot,
    )


def _meal(slot, foods):
    return Meal(
        id=f"m-{slot.value}",
        logged_at=datetime(2026, 8, 8, 12, 0),
        meal_time=slot,
        foods=tuple(foods),
    )


def _uc(meals=(), exercises=()):
    return HandleMessageUseCase(
        log_meal=None,
        query=None,
        meal_repo=FakeMealRepo(meals),
        exercise_repo=FakeExerciseRepo(exercises),
        clock=FixedClock(),
    )


class TestFoodDetail:
    def test_named_items_reach_grounding(self):
        uc = _uc(meals=[_meal(MealTimeSlot.LUNCH, [
            _food("chicken breast", 250, MealTimeSlot.LUNCH),
            _food("white rice", 200, MealTimeSlot.LUNCH),
        ])])
        g = uc._build_grounding()
        assert "chicken breast" in g
        assert "white rice" in g

    def test_items_grouped_under_their_slot(self):
        uc = _uc(meals=[
            _meal(MealTimeSlot.BREAKFAST, [_food("oatmeal", 300, MealTimeSlot.BREAKFAST)]),
            _meal(MealTimeSlot.LUNCH, [_food("chicken breast", 250, MealTimeSlot.LUNCH)]),
        ])
        g = uc._build_grounding()
        breakfast_line = next(ln for ln in g.splitlines() if ln.strip().startswith("breakfast:"))
        lunch_line = next(ln for ln in g.splitlines() if ln.strip().startswith("lunch:"))
        assert "oatmeal" in breakfast_line and "chicken" not in breakfast_line
        assert "chicken breast" in lunch_line and "oatmeal" not in lunch_line

    def test_marked_authoritative(self):
        uc = _uc(meals=[_meal(MealTimeSlot.LUNCH, [_food("chicken breast", 250, MealTimeSlot.LUNCH)])])
        assert "only items logged" in uc._build_grounding()

    def test_no_food_section_when_nothing_logged(self):
        g = _uc()._build_grounding() or ""
        assert "EXACT FOOD LOG" not in g


class TestExerciseDetail:
    def test_exercises_reach_grounding_with_sets(self):
        uc = _uc(exercises=[Exercise(
            name="Bench Press",
            exercise_type=ExerciseType.STRENGTH,
            day=date(2026, 8, 8),
            set_details=(SetDetail(reps=10, weight=185.0),) * 3,
        )])
        g = uc._build_grounding()
        assert "Bench Press" in g
        assert "3x10 at 185" in g

    def test_cardio_duration_included(self):
        uc = _uc(exercises=[Exercise(
            name="Run",
            exercise_type=ExerciseType.CARDIO,
            day=date(2026, 8, 8),
            duration_min=30,
        )])
        assert "30 min" in uc._build_grounding()

    def test_says_explicitly_when_nothing_logged(self):
        """An explicit 'nothing logged' beats silence, which invites invention."""
        assert "EXERCISE LOG: nothing logged today." in _uc()._build_grounding()

    def test_other_days_excluded(self):
        uc = _uc(exercises=[Exercise(
            name="Deadlift",
            exercise_type=ExerciseType.STRENGTH,
            day=date(2026, 8, 7),
            set_details=(SetDetail(reps=5, weight=225.0),),
        )])
        assert "Deadlift" not in uc._build_grounding()


class TestNoRepositories:
    def test_grounding_survives_missing_repos(self):
        uc = HandleMessageUseCase(log_meal=None, query=None, clock=FixedClock())
        uc._build_grounding()   # must not raise
