"""Persistence ports.

Use-cases depend only on these Protocols and on domain entities — never on a concrete
store, file path, or ORM model. A JSON adapter implements them now; a SQL adapter can
implement the identical interface later and be swapped in the composition root with no
change to the core.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from fitness.domain.exercise import Exercise
from fitness.domain.food import Food
from fitness.domain.meal import Meal


class MealRepository(Protocol):
    def save(self, meal: Meal) -> None:
        """Insert or replace the meal with ``meal.id`` (upsert)."""
        ...

    def get(self, meal_id: str) -> Meal | None: ...

    def delete(self, meal_id: str) -> bool:
        """Remove the meal. Returns True iff a meal was actually removed."""
        ...

    def list_by_date(self, day: date) -> list[Meal]: ...

    def list_between(self, start: date, end: date) -> list[Meal]: ...


class ExerciseRepository(Protocol):
    def save(self, exercise: Exercise) -> None: ...

    def list_by_date(self, day: date) -> list[Exercise]: ...

    def replace_by_name(self, day: date, name: str, new_exercise: Exercise) -> bool: ...

    def delete_by_name(self, day: date, name: str) -> bool: ...
