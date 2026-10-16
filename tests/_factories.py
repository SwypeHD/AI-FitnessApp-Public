"""Shared test factories and fakes, importable from any test module.

Kept separate from conftest.py so tests can ``from _factories import make_meal`` directly
(``tests`` dir is on the path) without depending on conftest's package import semantics.
"""

from __future__ import annotations

from datetime import date, datetime

from fitness.domain.food import Food
from fitness.domain.meal import Meal
from fitness.domain.value_objects import Macros, MealTimeSlot, Quantity, Unit


class InMemoryMealRepository:
    """A dict-backed ``MealRepository`` for testing the core without touching disk."""

    def __init__(self) -> None:
        self._by_id: dict[str, Meal] = {}

    def save(self, meal: Meal) -> None:
        self._by_id[meal.id] = meal

    def get(self, meal_id: str) -> Meal | None:
        return self._by_id.get(meal_id)

    def delete(self, meal_id: str) -> bool:
        return self._by_id.pop(meal_id, None) is not None

    def list_by_date(self, day: date) -> list[Meal]:
        return [m for m in self._by_id.values() if m.logged_at.date() == day]

    def list_between(self, start: date, end: date) -> list[Meal]:
        return [m for m in self._by_id.values() if start <= m.logged_at.date() <= end]


class FixedClock:
    """A ``Clock`` that always returns the same instant — deterministic time in tests."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def today(self) -> date:
        return self._moment.date()


def make_food(
    name: str = "chicken breast",
    amount: float = 1,
    unit: Unit = Unit.SERVING,
    macros: Macros | None = None,
    calories: float = 165.0,
    meal_time: MealTimeSlot = MealTimeSlot.LUNCH,
) -> Food:
    return Food(
        name=name,
        quantity=Quantity(amount, unit),
        macros=macros or Macros(protein_g=31, carbs_g=0, fat_g=3.6),
        calories=calories,
        meal_time=meal_time,
    )


def make_meal(
    meal_id: str = "m1",
    logged_at: datetime | None = None,
    meal_time: MealTimeSlot = MealTimeSlot.LUNCH,
    foods: tuple[Food, ...] | None = None,
) -> Meal:
    return Meal(
        id=meal_id,
        logged_at=logged_at or datetime(2026, 6, 4, 12, 0),
        meal_time=meal_time,
        foods=foods if foods is not None else (make_food(meal_time=meal_time),),
    )
