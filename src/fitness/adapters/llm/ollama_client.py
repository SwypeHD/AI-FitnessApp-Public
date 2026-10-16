"""Ollama LLM client — calls a local model (Gemma 4 by default) via the Ollama HTTP API.

All outputs are treated as untrusted: JSON is validated, confidence is capped, and failure
at any step raises ``LlmError`` so the application degrades gracefully. The adapter has no
access to any repository — it cannot perform or confirm mutations.
"""

from __future__ import annotations

import logging

import httpx

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
    chat_messages,
    extraction_prompt,
    food_name_prompt,
)

log = logging.getLogger(__name__)


class OllamaLlmClient:
    """Implements the ``LlmClient`` port against a running Ollama instance."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "gemma4:26b") -> None:
        if not host.startswith(("http://", "https://")):
            host = "http://" + host
        self._host = host.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=30.0)

    def estimate(self, text: str, schema_hint: str = "") -> ExtractionResult:
        raw = self._generate(EXTRACTION_SYSTEM, extraction_prompt(text))
        try:
            return parse_extraction_response(raw)
        except LlmError:
            log.debug("first extraction attempt failed, retrying")
            raw = self._generate(
                EXTRACTION_SYSTEM,
                "Your previous output was invalid JSON. Try again. "
                + extraction_prompt(text),
            )
            return parse_extraction_response(raw)

    def classify_intent(self, text: str) -> Intent:
        raw = self._generate(INTENT_SYSTEM, text).strip().lower()
        for intent in Intent:
            if intent.value in raw:
                return intent
        raise LlmError(f"unrecognized intent from LLM: {raw!r}")

    def chat(self, history: list[ChatTurn], grounding: str | None) -> str:
        msgs = chat_messages(
            [(t.role, t.content) for t in history], grounding
        )
        return self._chat(msgs)

    def parse_profile(self, text: str) -> dict | None:
        """Extract profile fields from user message. Returns dict of fields or None."""
        import json
        raw = self._generate(PROFILE_PARSE_SYSTEM, text)
        try:
            data = json.loads(raw.strip().strip("`").removeprefix("json").strip())
            if not isinstance(data, dict) or not data:
                return None
            return data
        except (json.JSONDecodeError, ValueError):
            return None

    def verify_profile(self, profile_data: dict) -> bool:
        """Use a second model call to verify extracted profile data is realistic."""
        import json
        raw = self._generate(PROFILE_VERIFY_SYSTEM, json.dumps(profile_data))
        try:
            result = json.loads(raw.strip().strip("`").removeprefix("json").strip())
            return result.get("valid", False)
        except (json.JSONDecodeError, ValueError):
            return False

    def clean_food_name(self, raw_input: str, extracted_name: str) -> str | None:
        result = self._generate(
            FOOD_NAME_SYSTEM, food_name_prompt(raw_input, extracted_name)
        ).strip().strip('"').strip("'").strip()
        if not result or result.lower() == extracted_name.lower():
            return None
        return result

    # --- Ollama HTTP calls (OpenAI-compatible /v1/ API) ----------------------

    def _generate(self, system: str, prompt: str) -> str:
        return self._chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ])

    def _chat(self, messages: list[dict[str, str]]) -> str:
        try:
            resp = self._client.post(
                f"{self._host}/v1/chat/completions",
                json={
                    "model": self._model,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError) as e:
            raise LlmError(f"Ollama call failed: {e}") from e
