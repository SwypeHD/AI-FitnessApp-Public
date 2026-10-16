"""NullLlmClient — deterministic fallback when no LLM is configured.

Always raises ``LlmError`` for extraction/classification (so the application degrades
to deterministic-only) and returns a canned message for chat. Useful for tests and for
the ``llm_provider=none`` setting.
"""

from __future__ import annotations

from fitness.application.ports.extraction import (
    ChatTurn,
    ExtractionResult,
    Intent,
    LlmError,
)
from fitness.domain.candidate import CandidateMeal


class NullLlmClient:
    def estimate(self, text: str, schema_hint: str) -> ExtractionResult:
        raise LlmError("no LLM configured")

    def classify_intent(self, text: str) -> Intent:
        raise LlmError("no LLM configured")

    def chat(self, history: list[ChatTurn], grounding: str | None) -> str:
        return (
            "I'm a food logging assistant. Chat mode requires an LLM connection. "
            "Try telling me what you ate!"
        )

    def clean_food_name(self, raw_input: str, extracted_name: str) -> str | None:
        return None

    def parse_profile(self, text: str) -> dict | None:
        return None

    def verify_profile(self, profile_data: dict) -> bool:
        return False
