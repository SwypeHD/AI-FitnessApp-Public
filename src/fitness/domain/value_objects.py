"""Immutable value objects shared across the domain.

Includes the provenance/confidence machinery that makes the "deterministic-wins"
reconciliation rule enforceable at the level of individual fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar


class Unit(str, Enum):
    """Units a quantity can be expressed in.

    ``SERVING`` is symbolic: how many grams a serving is depends on the food and is
    resolved later by the knowledge base, not here.
    """

    GRAM = "g"
    OUNCE = "oz"
    SERVING = "serving"
    CUP = "cup"
    PIECE = "piece"
    MILLILITER = "ml"


class MealTimeSlot(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class Provenance(str, Enum):
    """Where a field's value came from.

    Precedence (highest wins on conflict): USER > DETERMINISTIC > KNOWLEDGE_BASE >
    LLM > DEFAULT. The LLM can never override a user-confirmed or deterministically
    parsed value — this is the structural core of the anti-hallucination design.
    """

    USER = "user"
    DETERMINISTIC = "deterministic"
    KNOWLEDGE_BASE = "knowledge_base"
    LLM = "llm"
    DEFAULT = "default"

    @property
    def rank(self) -> int:
        return _PROVENANCE_RANK[self]


_PROVENANCE_RANK: dict[Provenance, int] = {
    Provenance.USER: 4,
    Provenance.DETERMINISTIC: 3,
    Provenance.KNOWLEDGE_BASE: 2,
    Provenance.LLM: 1,
    Provenance.DEFAULT: 0,
}


@dataclass(frozen=True, slots=True)
class Macros:
    """Macronutrients in grams. Calories are derived via the Atwater 4/4/9 rule."""

    protein_g: float
    carbs_g: float
    fat_g: float

    def __post_init__(self) -> None:
        for name in ("protein_g", "carbs_g", "fat_g"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

    @property
    def calories_from_macros(self) -> float:
        return self.protein_g * 4 + self.carbs_g * 4 + self.fat_g * 9

    def scaled(self, factor: float) -> "Macros":
        if factor < 0:
            raise ValueError(f"scale factor must be non-negative, got {factor}")
        return Macros(self.protein_g * factor, self.carbs_g * factor, self.fat_g * factor)

    def __add__(self, other: "Macros") -> "Macros":
        if not isinstance(other, Macros):
            return NotImplemented
        return Macros(
            self.protein_g + other.protein_g,
            self.carbs_g + other.carbs_g,
            self.fat_g + other.fat_g,
        )

    @classmethod
    def zero(cls) -> "Macros":
        return cls(0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class Quantity:
    """An amount expressed in a unit. Must be strictly positive."""

    amount: float
    unit: Unit

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError(f"quantity amount must be > 0, got {self.amount}")


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class FieldValue(Generic[T]):
    """A value tagged with where it came from and how confident we are.

    ``outranks`` encodes conflict resolution: higher provenance wins; on a tie,
    higher confidence wins. This is consumed by builders and the reconciliation step.
    """

    value: T
    provenance: Provenance
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    def outranks(self, other: "FieldValue[T]") -> bool:
        if self.provenance.rank != other.provenance.rank:
            return self.provenance.rank > other.provenance.rank
        return self.confidence > other.confidence


def pick(
    current: "FieldValue[T] | None", incoming: "FieldValue[T] | None"
) -> "FieldValue[T] | None":
    """Choose the winning field value under deterministic-wins rules.

    Returns ``incoming`` only if there is no current value or it outranks the current
    one; otherwise keeps ``current``. Shared by builders and reconciliation so the
    conflict semantics live in exactly one place.
    """
    if incoming is None:
        return current
    if current is None:
        return incoming
    return incoming if incoming.outranks(current) else current
