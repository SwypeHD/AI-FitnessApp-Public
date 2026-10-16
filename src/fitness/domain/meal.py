"""The Meal aggregate — the immutable unit of persistence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from .food import Food
from .value_objects import Macros, MealTimeSlot


@dataclass(frozen=True, slots=True)
class Meal:
    """A meal: a collection of foods logged at a point in time for one meal-time slot.

    ``foods`` is a tuple to preserve immutability. The ``with_*`` helpers return new
    instances and exist to support deterministic EDIT operations (move/add/remove)
    without mutating shared state.
    """

    id: str
    logged_at: datetime
    meal_time: MealTimeSlot
    foods: tuple[Food, ...]

    @property
    def total_macros(self) -> Macros:
        total = Macros.zero()
        for food in self.foods:
            total = total + food.macros
        return total

    @property
    def total_calories(self) -> float:
        return sum(food.calories for food in self.foods)

    def with_foods(self, foods: tuple[Food, ...]) -> "Meal":
        return replace(self, foods=tuple(foods))

    def with_meal_time(self, meal_time: MealTimeSlot) -> "Meal":
        """Reassign the whole meal (and its foods) to a different slot — e.g. move to lunch."""
        return replace(
            self,
            meal_time=meal_time,
            foods=tuple(f.with_meal_time(meal_time) for f in self.foods),
        )

    def add_food(self, food: Food) -> "Meal":
        return replace(self, foods=(*self.foods, food))

    def without_food_at(self, index: int) -> "Meal":
        """Return a copy with the food at ``index`` removed."""
        if not 0 <= index < len(self.foods):
            raise IndexError(f"no food at index {index} (have {len(self.foods)})")
        remaining = self.foods[:index] + self.foods[index + 1 :]
        return replace(self, foods=remaining)
