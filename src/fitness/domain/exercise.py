"""The Exercise entity — an immutable, fully-specified logged exercise."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class ExerciseType(str, Enum):
    STRENGTH = "strength"
    CARDIO = "cardio"
    MOBILITY = "mobility"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class SetDetail:
    reps: int
    weight: float | None = None

    def __post_init__(self) -> None:
        if self.reps <= 0:
            raise ValueError(f"reps must be > 0, got {self.reps}")
        if self.weight is not None and self.weight < 0:
            raise ValueError(f"weight must be >= 0, got {self.weight}")


@dataclass(frozen=True, slots=True)
class Exercise:
    name: str
    exercise_type: ExerciseType
    day: date
    set_details: tuple[SetDetail, ...] = ()
    duration_min: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("exercise name must not be blank")
        object.__setattr__(self, "name", self.name.strip().title())
        if self.duration_min is not None and self.duration_min <= 0:
            raise ValueError(f"duration_min must be > 0 when given, got {self.duration_min}")

    @property
    def sets(self) -> int | None:
        return len(self.set_details) if self.set_details else None

    @property
    def reps(self) -> int | None:
        return self.set_details[0].reps if self.set_details else None

    def merged_with(self, other: Exercise) -> Exercise:
        """Combine a later logging of the same exercise on the same day.

        Sets are concatenated rather than summed, so each group keeps its own
        reps/weight — logging 3x10 at 185 and then 2x8 at 195 yields one Bench Press
        with both groups intact. Durations add up.

        The receiver's name and type win, keeping one canonical record per day.
        """
        if other.day != self.day:
            raise ValueError("cannot merge exercises logged on different days")
        duration: float | None = None
        if self.duration_min is not None or other.duration_min is not None:
            duration = (self.duration_min or 0) + (other.duration_min or 0)
        return Exercise(
            name=self.name,
            exercise_type=self.exercise_type,
            day=self.day,
            set_details=self.set_details + other.set_details,
            duration_min=duration,
        )

    def grouped_sets(self) -> list[dict]:
        """Group consecutive identical sets for cleaner display."""
        if not self.set_details:
            return []
        groups: list[dict] = []
        for s in self.set_details:
            key = (s.reps, s.weight)
            if groups and (groups[-1]["reps"], groups[-1]["weight"]) == key:
                groups[-1]["count"] += 1
            else:
                groups.append({"count": 1, "reps": s.reps, "weight": s.weight})
        return groups

    def format_sets(self) -> str:
        groups = self.grouped_sets()
        if not groups:
            return ""
        any_weight = any(g["weight"] for g in groups)
        if not any_weight and len(groups) == 1:
            g = groups[0]
            return f"{g['count']}x{g['reps']}" if g["count"] > 1 else f"{g['reps']} reps"
        parts = []
        for g in groups:
            w = f"{g['weight']:g} x " if g["weight"] else ""
            reps = f"{w}{g['reps']} reps"
            if g["count"] > 1:
                parts.append(f"{g['count']} sets of {reps}")
            else:
                parts.append(reps)
        return ", ".join(parts)
