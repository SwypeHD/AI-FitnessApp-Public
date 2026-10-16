"""The Food entity — an immutable, fully-specified logged food item."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .value_objects import Macros, MealTimeSlot, Quantity


@dataclass(frozen=True, slots=True)
class Food:
    """A single food as logged.

    ``calories`` is stored explicitly (it may come from a source that doesn't perfectly
    match the Atwater-derived value of ``macros``); ``Macros.calories_from_macros`` is
    available for cross-checking. A fully-built ``Food`` is only ever produced by
    ``FoodBuilder.build()`` after completeness passes.
    """

    name: str
    quantity: Quantity
    macros: Macros
    calories: float
    meal_time: MealTimeSlot

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("food name must not be blank")
        if self.calories < 0:
            raise ValueError(f"calories must be non-negative, got {self.calories}")

    def with_meal_time(self, meal_time: MealTimeSlot) -> "Food":
        """Return a copy reassigned to a different meal-time slot (e.g. move to lunch)."""
        return replace(self, meal_time=meal_time)
