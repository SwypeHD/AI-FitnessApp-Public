"""Anthropic LLM client — calls Claude (Haiku/Sonnet) via the Anthropic SDK.

Implements the same ``LlmClient`` port as the Ollama adapter, proving the hexagonal
boundary swaps cleanly. Uses the shared ``parse_extraction_response`` so both adapters
validate LLM output identically.
"""

from __future__ import annotations

import logging

import anthropic

from fitness.application.ports.extraction import (
    ChatTurn,
    ExtractionResult,
    Intent,
    LlmError,
)

from .parse_response import parse_extraction_response
from .prompts import (
    EXTRACTION_SYSTEM,
    FOOD_NAME_SYSTEM,
    INTENT_SYSTEM,
    PROFILE_PARSE_SYSTEM,
    PROFILE_VERIFY_SYSTEM,
    extraction_prompt,
    food_name_prompt,
)

log = logging.getLogger(__name__)


class AnthropicLlmClient:
    """Implements the ``LlmClient`` port against the Anthropic API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def estimate(self, text: str, schema_hint: str = "") -> ExtractionResult:
        raw = self._message(EXTRACTION_SYSTEM, extraction_prompt(text))
        try:
            return parse_extraction_response(raw)
        except LlmError:
            log.debug("first extraction attempt failed, retrying")
            raw = self._message(
                EXTRACTION_SYSTEM,
                "Your previous output was invalid JSON. Try again. "
                + extraction_prompt(text),
            )
            return parse_extraction_response(raw)

    def classify_intent(self, text: str) -> Intent:
        raw = self._message(INTENT_SYSTEM, text).strip().lower()
        for intent in Intent:
            if intent.value in raw:
                return intent
        raise LlmError(f"unrecognized intent from LLM: {raw!r}")

    def chat(self, history: list[ChatTurn], grounding: str | None) -> str:
        from .prompts import chat_messages
        msgs = chat_messages(
            [(t.role, t.content) for t in history], grounding
        )
        system = msgs[0]["content"]
        messages = [{"role": m["role"], "content": m["content"]} for m in msgs[1:]]
        return self._message(system, messages=messages)

    def clean_food_name(self, raw_input: str, extracted_name: str) -> str | None:
        result = self._message(
            FOOD_NAME_SYSTEM, food_name_prompt(raw_input, extracted_name)
        ).strip().strip('"').strip("'").strip()
        if not result or result.lower() == extracted_name.lower():
            return None
        return result

    def parse_profile(self, text: str) -> dict | None:
        import json
        raw = self._message(PROFILE_PARSE_SYSTEM, text)
        try:
            data = json.loads(raw.strip().strip("`").removeprefix("json").strip())
            if not isinstance(data, dict) or not data:
                return None
            return data
        except (json.JSONDecodeError, ValueError):
            return None

    def verify_profile(self, profile_data: dict) -> bool:
        import json
        raw = self._message(PROFILE_VERIFY_SYSTEM, json.dumps(profile_data))
        try:
            result = json.loads(raw.strip().strip("`").removeprefix("json").strip())
            return result.get("valid", False)
        except (json.JSONDecodeError, ValueError):
            return False

    # --- Anthropic API call -------------------------------------------------

    def _message(
        self,
        system: str,
        user_text: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        if messages is None:
            messages = [{"role": "user", "content": user_text}]
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=messages,
            )
            return resp.content[0].text
        except (anthropic.APIError, IndexError, KeyError) as e:
            raise LlmError(f"Anthropic API call failed: {e}") from e
