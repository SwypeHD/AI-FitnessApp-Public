"""Candidate structures — the shared output type of every extraction source.

Both the deterministic extractor and the LLM emit a ``CandidateMeal``; the knowledge
base contributes another; prior conversational turns carry one forward. Reconciliation
merges them. Every field is an ``Optional[FieldValue]`` so provenance/confidence travel
with each datum and the deterministic-wins rule applies field by field.

These mirror the builders but serve a different role: builders enforce *completeness*
and produce immutable entities; candidates are the *accumulating extraction surface*
that gets projected into a builder once reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from .value_objects import FieldValue, Macros, MealTimeSlot, Quantity, pick


@dataclass
class CandidateFood:
    """A partially-known food from one or more extraction sources."""

    FIELDS: ClassVar[tuple[str, ...]] = ("name", "quantity", "macros", "calories")

    name: FieldValue[str] | None = None
    quantity: FieldValue[Quantity] | None = None
    macros: FieldValue[Macros] | None = None
    calories: FieldValue[float] | None = None

    def offer(self, field_name: str, value: FieldValue | None) -> bool:
        """Merge a candidate value under deterministic-wins rules. Returns True if
        the offered value won (became the current value)."""
        if field_name not in self.FIELDS:
            raise ValueError(f"unknown candidate food field: {field_name!r}")
        if value is None:
            return False
        current = getattr(self, field_name)
        winner = pick(current, value)
        setattr(self, field_name, winner)
        return winner is value

    def provenances(self) -> set:
        """The set of provenances backing this food's present fields."""
        return {
            getattr(self, f).provenance
            for f in self.FIELDS
            if getattr(self, f) is not None
        }


@dataclass
class CandidateMeal:
    """Accumulating extraction surface for a meal across sources and turns."""

    meal_time: FieldValue[MealTimeSlot] | None = None
    foods: list[CandidateFood] = field(default_factory=list)
    raw_turns: list[str] = field(default_factory=list)
