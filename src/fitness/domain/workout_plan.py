"""Workout plan domain — saved templates and active calendar entries.

A WorkoutPlan is a reusable template (e.g., PPL, Upper/Lower). It defines a rotation
of PlanDays that cycle when applied to a calendar. The calendar is a separate concern —
the plan itself is just the template.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlannedExercise:
    name: str
    exercise_type: str
    sets: int
    reps: int

    def to_dict(self) -> dict:
        return {"name": self.name, "exercise_type": self.exercise_type,
                "sets": self.sets, "reps": self.reps}

    @classmethod
    def from_dict(cls, d: dict) -> PlannedExercise:
        return cls(name=d["name"], exercise_type=d["exercise_type"],
                   sets=d["sets"], reps=d["reps"])


@dataclass(frozen=True, slots=True)
class PlanDay:
    label: str
    is_rest: bool
    exercises: tuple[PlannedExercise, ...]

    def to_dict(self) -> dict:
        return {"label": self.label, "is_rest": self.is_rest,
                "exercises": [e.to_dict() for e in self.exercises]}

    @classmethod
    def from_dict(cls, d: dict) -> PlanDay:
        return cls(
            label=d["label"], is_rest=d["is_rest"],
            exercises=tuple(PlannedExercise.from_dict(e) for e in d.get("exercises", [])),
        )


@dataclass(frozen=True, slots=True)
class WorkoutPlan:
    id: str
    name: str
    rotation: tuple[PlanDay, ...]

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "rotation": [d.to_dict() for d in self.rotation]}

    @classmethod
    def from_dict(cls, d: dict) -> WorkoutPlan:
        return cls(
            id=d["id"], name=d["name"],
            rotation=tuple(PlanDay.from_dict(day) for day in d["rotation"]),
        )


@dataclass
class CalendarEntry:
    """One day on the active calendar. Mutable status field."""
    date: str
    day_index: int
    status: str  # "planned" | "completed" | "skipped"
    saved_label: str | None = None

    def to_dict(self) -> dict:
        d = {"date": self.date, "day_index": self.day_index, "status": self.status}
        if self.saved_label is not None:
            d["saved_label"] = self.saved_label
        return d

    @classmethod
    def from_dict(cls, d: dict) -> CalendarEntry:
        return cls(date=d["date"], day_index=d["day_index"], status=d["status"],
                   saved_label=d.get("saved_label"))


@dataclass
class ActiveCalendar:
    """The currently active workout schedule — a plan mapped to real dates."""
    plan_id: str
    plan_name: str
    entries: list[CalendarEntry]

    def to_dict(self) -> dict:
        return {"plan_id": self.plan_id, "plan_name": self.plan_name,
                "entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, d: dict) -> ActiveCalendar:
        return cls(
            plan_id=d["plan_id"], plan_name=d["plan_name"],
            entries=[CalendarEntry.from_dict(e) for e in d["entries"]],
        )
