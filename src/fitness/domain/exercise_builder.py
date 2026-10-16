"""ExerciseBuilder — accumulates fields for an Exercise across conversational turns.

Same pattern as FoodBuilder: the builder owns completeness, drives clarification, and
produces an immutable Exercise only when all required fields are present.

Required: name, exercise_type, day.
Optional (but encouraged): set_details, duration_min — these are accepted but not required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .errors import IncompleteMealError
from .exercise import Exercise, ExerciseType, SetDetail


@dataclass
class ExerciseBuilder:
    name: str | None = None
    exercise_type: ExerciseType | None = None
    day: date | None = None
    set_details: list[SetDetail] = field(default_factory=list)
    duration_min: float | None = None

    # Legacy setters for text-parsed "3 sets of 10" (uniform sets)
    sets: int | None = None
    reps: int | None = None

    REQUIRED_FIELDS = ("name", "exercise_type", "day")

    def missing_fields(self) -> list[str]:
        return [f for f in self.REQUIRED_FIELDS if getattr(self, f) is None]

    def is_complete(self) -> bool:
        return not self.missing_fields()

    def build(self) -> Exercise:
        missing = self.missing_fields()
        if missing:
            raise IncompleteMealError(missing)

        details = tuple(self.set_details)
        if not details and self.sets and self.reps:
            details = tuple(SetDetail(reps=self.reps) for _ in range(self.sets))

        return Exercise(
            name=self.name,
            exercise_type=self.exercise_type,
            day=self.day,
            set_details=details,
            duration_min=self.duration_min,
        )
