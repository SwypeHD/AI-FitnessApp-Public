"""Data-transfer objects for use-case inputs and outputs.

These are the contract between the application layer and whatever drives it (web, CLI,
tests). They carry plain data — never repository or LLM handles. Multi-turn state travels
in/out via ``ConversationState`` so the eventual HTTP layer can stay stateless (the client
echoes the state back).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from fitness.domain.candidate import CandidateMeal
from fitness.domain.value_objects import Macros, MealTimeSlot


class LogStatus(str, Enum):
    LOGGED = "logged"
    NEEDS_CLARIFICATION = "needs_clarification"


@dataclass(frozen=True)
class PendingClarification:
    """What the app just asked about, so the next message can be applied to that slot."""

    target: str  # "meal" or "food[i]"
    field: str  # meal_time | quantity | name | macros | calories | foods


@dataclass
class ConversationState:
    """Accumulated, in-flight meal plus any outstanding question. Round-trips with the client."""

    candidate: CandidateMeal
    pending: PendingClarification | None = None


@dataclass(frozen=True)
class PendingSavedMealItem:
    """One resolved food item in a saved-meal preview (pre-confirmation)."""

    food_name: str
    quantity_amount: float
    quantity_unit: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


@dataclass(frozen=True)
class PendingSavedMealState:
    """State for a saved-meal preview awaiting user confirmation."""

    name: str
    items: list[PendingSavedMealItem]


@dataclass(frozen=True)
class PendingExerciseState:
    """Partial exercise awaiting clarification (e.g. missing weight or reps)."""

    name: str
    exercise_type: str
    sets: int | None = None
    reps: int | None = None
    weight: float | None = None
    duration_min: float | None = None
    question: str = ""


@dataclass(frozen=True)
class LogMealRequest:
    text: str
    state: ConversationState | None = None


@dataclass(frozen=True)
class LogMealResponse:
    status: LogStatus
    message: str
    state: ConversationState | PendingSavedMealState | None = None  # present when clarification is needed
    meal_id: str | None = None  # present when logged
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DailySummary:
    day: date
    total_calories: float
    total_macros: Macros
    calories_by_slot: dict[MealTimeSlot, float]
    meal_count: int
