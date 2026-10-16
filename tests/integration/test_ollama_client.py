"""Integration tests for the Ollama LLM client against a real running instance.

Opt-in: skipped unless ``pytest -m llm`` is used AND a reachable Ollama is configured.
These are contract tests — they verify that real Gemma 4 output parses into our domain
types, not that the model gives "good" answers.

Configure via env vars or .env:
    OLLAMA_HOST=http://localhost:11434
    OLLAMA_MODEL=gemma4:e4B
"""

from __future__ import annotations

import httpx
import pytest

from fitness.adapters.llm.ollama_client import OllamaLlmClient
from fitness.application.ports.extraction import ChatTurn, Intent, LlmError
from fitness.config.settings import Settings


def _settings() -> Settings:
    return Settings()


def _is_ollama_reachable(settings: Settings) -> bool:
    try:
        resp = httpx.get(f"{settings.ollama_host}/api/tags", timeout=3)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
def client():
    settings = _settings()
    if not _is_ollama_reachable(settings):
        pytest.skip(f"Ollama not reachable at {settings.ollama_host}")
    return OllamaLlmClient(host=settings.ollama_host, model=settings.ollama_model)


@pytest.mark.llm
class TestEstimate:
    def test_returns_parseable_extraction_result(self, client):
        result = client.estimate("I had 2 eggs and a banana for breakfast", "")
        assert len(result.candidate_meal.foods) >= 1
        names = [f.name.value.lower() for f in result.candidate_meal.foods if f.name]
        assert any("egg" in n for n in names), f"expected 'egg' in {names}"

    def test_unknown_food_still_returns_name(self, client):
        result = client.estimate("1 slice of cheesecake", "")
        foods = result.candidate_meal.foods
        assert len(foods) >= 1
        assert foods[0].name is not None

    def test_returns_macros_when_confident(self, client):
        result = client.estimate("200g chicken breast", "")
        food = result.candidate_meal.foods[0]
        # The model should at least attempt macros for a common food.
        # We don't assert exact values — just that it parsed into valid types.
        if food.macros is not None:
            assert food.macros.value.protein_g >= 0


@pytest.mark.llm
class TestClassifyIntent:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("I had 3 eggs for breakfast", Intent.LOG),
            ("show me what I ate today", Intent.QUERY),
            ("delete the chicken from lunch", Intent.EDIT),
            ("hey, how's it going?", Intent.CHAT),
        ],
    )
    def test_classifies_clear_intents(self, client, text, expected):
        result = client.classify_intent(text)
        assert result is expected, f"expected {expected} for {text!r}, got {result}"


@pytest.mark.llm
class TestChat:
    def test_returns_nonempty_string(self, client):
        history = [ChatTurn(role="user", content="What's a good post-workout snack?")]
        reply = client.chat(history, grounding=None)
        assert isinstance(reply, str)
        assert len(reply) > 10

    def test_uses_grounding_facts(self, client):
        history = [ChatTurn(role="user", content="How am I doing today?")]
        grounding = "Today: 1200 kcal, 80g protein, 150g carbs, 40g fat across 2 meals."
        reply = client.chat(history, grounding=grounding)
        assert isinstance(reply, str)
        # The model should reference something from the grounding.
        assert any(tok in reply for tok in ("1200", "80", "protein", "2 meal")), \
            f"expected grounding data reflected in reply: {reply[:200]}"
