import pytest

from fitness.adapters.llm.null_client import NullLlmClient
from fitness.application.ports.extraction import LlmError


def test_estimate_raises():
    with pytest.raises(LlmError):
        NullLlmClient().estimate("eggs", "")


def test_classify_raises():
    with pytest.raises(LlmError):
        NullLlmClient().classify_intent("hello")


def test_chat_returns_canned():
    result = NullLlmClient().chat([], None)
    assert "food logging" in result.lower()
