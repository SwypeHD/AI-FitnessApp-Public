"""Builders — the mutable accumulators that assemble immutable entities.

These are the *single source of truth for completeness*. The LLM never decides whether
enough information has been gathered; ``missing()`` / ``is_complete()`` do, deterministically.
Builders accumulate ``FieldValue``s across conversational turns and apply provenance-aware
"offer" semantics so a higher-authority source (USER, DETERMINISTIC) is never overwritten
by a lower one (LLM).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from .errors import IncompleteMealError
from .food import Food
from .meal import Meal
from .value_objects import FieldValue, Macros, MealTimeSlot, Quantity, pick


@dataclass
class FoodBuilder:
    """Accumulates the fields needed to build one ``Food``."""

    REQUIRED_FIELDS: ClassVar[tuple[str, ...]] = (
        "name",
        "quantity",
        "macros",
        "calories",
        "meal_time",
    )

    name: FieldValue[str] | None = None
    quantity: FieldValue[Quantity] | None = None
    macros: FieldValue[Macros] | None = None
    calories: FieldValue[float] | None = None
    meal_time: FieldValue[MealTimeSlot] | None = None

    def offer(self, field_name: str, value: FieldValue) -> bool:
        """Offer a candidate value for a field. Accepted only if no current value exists
        or the new value outranks the current one. Returns True if it was accepted."""
        if field_name not in self.REQUIRED_FIELDS:
            raise ValueError(f"unknown food field: {field_name!r}")
        current = getattr(self, field_name)
        winner = pick(current, value)
        setattr(self, field_name, winner)
        return winner is value

    def missing_fields(self) -> list[str]:
        return [f for f in self.REQUIRED_FIELDS if getattr(self, f) is None]

    def is_complete(self) -> bool:
        return not self.missing_fields()

    def build(self) -> Food:
        missing = self.missing_fields()
        if missing:
            raise IncompleteMealError(missing)
        assert self.name and self.quantity and self.macros and self.calories and self.meal_time
        return Food(
            name=self.name.value,
            quantity=self.quantity.value,
            macros=self.macros.value,
            calories=self.calories.value,
            meal_time=self.meal_time.value,
        )


@dataclass
class MealBuilder:
    """Accumulates a meal-time slot plus one or more ``FoodBuilder``s.

    The meal-level ``meal_time`` is propagated down to any food builder that lacks one,
    so the user is never asked twice for the same slot.
    """

    meal_time: FieldValue[MealTimeSlot] | None = None
    food_builders: list[FoodBuilder] = field(default_factory=list)

    def _propagate_meal_time(self) -> None:
        if self.meal_time is None:
            return
        for fb in self.food_builders:
            fb.offer("meal_time", self.meal_time)

    def missing(self) -> dict[str, list[str]]:
        """Structured gaps. Keys: "meal" for meal-level fields, "food[i]" per food."""
        self._propagate_meal_time()
        gaps: dict[str, list[str]] = {}
        meal_gaps: list[str] = []
        if self.meal_time is None:
            meal_gaps.append("meal_time")
        if not self.food_builders:
            meal_gaps.append("foods")
        if meal_gaps:
            gaps["meal"] = meal_gaps
        for i, fb in enumerate(self.food_builders):
            fb_missing = fb.missing_fields()
            if fb_missing:
                gaps[f"food[{i}]"] = fb_missing
        return gaps

    def is_complete(self) -> bool:
        return not self.missing()

    def build(self, *, meal_id: str, logged_at: datetime) -> Meal:
        self._propagate_meal_time()
        gaps = self.missing()
        if gaps:
            raise IncompleteMealError(gaps)
        assert self.meal_time is not None
        foods = tuple(fb.build() for fb in self.food_builders)
        return Meal(
            id=meal_id,
            logged_at=logged_at,
            meal_time=self.meal_time.value,
            foods=foods,
        )
