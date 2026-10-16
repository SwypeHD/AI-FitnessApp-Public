"""Extraction and LLM ports, plus the shared extraction result type.

The deterministic ``Extractor`` and the ``LlmClient`` both produce the SAME
``ExtractionResult`` (wrapping a ``CandidateMeal``) — that shared shape is the
precondition that lets reconciliation merge them under one rule set. The ``LlmClient``
is treated as an untrusted advisor: it extracts on gaps, classifies ambiguous intent,
and handles free-form chat, but it never touches persistence and never decides
completeness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from fitness.domain.candidate import CandidateMeal


class Intent(str, Enum):
    """How an inbound message should be routed."""

    LOG = "log"           # logging food
    EXERCISE = "exercise" # logging exercise
    QUERY = "query"       # questions about logged data
    EDIT = "edit"         # mutate an existing log (move/delete/change)
    CALENDAR = "calendar" # workout calendar actions (skip, complete, push back, activate)
    CHAT = "chat"         # casual conversation / general Q&A


@dataclass(frozen=True, slots=True)
class ChatTurn:
    """One turn of conversation history passed to the chat model."""

    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """A candidate meal plus non-authoritative notes from the source."""

    candidate_meal: CandidateMeal
    notes: list[str] = field(default_factory=list)


class LlmError(RuntimeError):
    """Raised when the LLM is unavailable or returns unusable output.

    The application swallows this and degrades to deterministic-only behavior for the
    LOG/QUERY/EDIT paths; CHAT falls back to a canned response.
    """


class Extractor(Protocol):
    """Deterministic, rule-based extraction. Authoritative; runs first."""

    def extract(self, text: str, context: CandidateMeal | None) -> ExtractionResult: ...


class LlmClient(Protocol):
    """The model adapter (Ollama/Gemma now, Anthropic later)."""

    def estimate(self, text: str, schema_hint: str) -> ExtractionResult:
        """Gap-filling structured extraction. Raises ``LlmError`` on failure."""
        ...

    def classify_intent(self, text: str) -> Intent:
        """Fallback intent classification for cases heuristics can't resolve."""
        ...

    def chat(self, history: list[ChatTurn], grounding: str | None) -> str:
        """Free-form reply. ``grounding`` is deterministically-computed facts to anchor
        the response; the model must not do arithmetic over raw data itself."""
        ...

    def clean_food_name(self, raw_input: str, extracted_name: str) -> str | None:
        """Ask the model to verify/correct a regex-extracted food name.

        Returns the corrected name, or None if extraction looks correct.
        Raises ``LlmError`` on failure — caller should keep the regex result."""
        ...

    def parse_profile(self, text: str) -> dict | None:
        """Extract profile fields from a user message. Returns dict or None."""
        ...

    def verify_profile(self, profile_data: dict) -> bool:
        """Verify extracted profile data is realistic via a second model call."""
        ...
