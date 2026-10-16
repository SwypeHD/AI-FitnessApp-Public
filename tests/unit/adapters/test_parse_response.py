"""Tests for the shared LLM extraction response parser.

These are adapter-agnostic — they prove that both Ollama and Anthropic adapters will
parse the same raw JSON identically, since they both delegate to parse_extraction_response.
"""

import pytest

from fitness.adapters.llm.parse_response import parse_extraction_response, _repair_json
from fitness.application.ports.extraction import LlmError
from fitness.domain.value_objects import Provenance, Unit


class TestValidJSON:
    def test_parses_complete_food(self):
        raw = '{"foods": [{"name": "eggs", "amount": 2, "unit": "piece", "protein_g": 12, "carbs_g": 1, "fat_g": 10, "calories": 144, "meal_time": "breakfast"}]}'
        result = parse_extraction_response(raw)
        assert len(result.candidate_meal.foods) == 1
        food = result.candidate_meal.foods[0]
        assert food.name.value == "eggs"
        assert food.name.provenance is Provenance.LLM
        assert food.quantity.value.amount == 2
        assert food.quantity.value.unit is Unit.PIECE
        assert food.macros.value.protein_g == 12
        assert food.calories.value == 144
        assert result.candidate_meal.meal_time.value.value == "breakfast"

    def test_handles_null_fields(self):
        raw = '{"foods": [{"name": "cheesecake", "amount": 1, "unit": null, "protein_g": null, "carbs_g": null, "fat_g": null, "calories": 320, "meal_time": null}]}'
        result = parse_extraction_response(raw)
        food = result.candidate_meal.foods[0]
        assert food.name.value == "cheesecake"
        assert food.macros is None
        assert food.calories.value == 320

    def test_multiple_foods(self):
        raw = '{"foods": [{"name": "eggs", "amount": 2, "unit": "piece", "protein_g": 12, "carbs_g": 1, "fat_g": 10, "calories": 144, "meal_time": null}, {"name": "toast", "amount": 1, "unit": "piece", "protein_g": 3, "carbs_g": 14, "fat_g": 1, "calories": 75, "meal_time": null}]}'
        result = parse_extraction_response(raw)
        assert len(result.candidate_meal.foods) == 2

    def test_strips_markdown_fences(self):
        raw = '```json\n{"foods": [{"name": "rice", "amount": 1, "unit": "cup", "protein_g": 4, "carbs_g": 45, "fat_g": 0, "calories": 205, "meal_time": null}]}\n```'
        result = parse_extraction_response(raw)
        assert result.candidate_meal.foods[0].name.value == "rice"

    def test_confidence_capped_at_0_7(self):
        raw = '{"foods": [{"name": "egg", "amount": 1, "unit": "piece", "protein_g": 6, "carbs_g": 0, "fat_g": 5, "calories": 72, "meal_time": null}]}'
        food = parse_extraction_response(raw).candidate_meal.foods[0]
        assert food.name.confidence == 0.7
        assert food.calories.confidence == 0.7


class TestBracketRepair:
    def test_repairs_missing_closing_brace(self):
        truncated = '{"foods": [{"name": "chicken", "amount": 300, "unit": "g", "protein_g": null, "carbs_g": null, "fat_g": null, "calories": null, "meal_time": null}'
        result = parse_extraction_response(truncated)
        assert result.candidate_meal.foods[0].name.value == "chicken"

    def test_repair_json_helper_returns_none_for_valid_json(self):
        assert _repair_json('{"a": 1}') is None

    def test_repair_json_helper_closes_brackets(self):
        assert _repair_json('{"a": [1') == {"a": [1]}


class TestInvalidInput:
    def test_raises_on_total_garbage(self):
        with pytest.raises(LlmError):
            parse_extraction_response("I don't know, sorry!")

    def test_food_without_name_noted(self):
        raw = '{"foods": [{"amount": 2, "unit": "piece"}]}'
        result = parse_extraction_response(raw)
        assert len(result.candidate_meal.foods) == 0
        assert any("without a name" in n for n in result.notes)


class TestAdapterSwapability:
    """Prove that both adapters would parse the same response identically by verifying
    they both use parse_extraction_response (import-level check)."""

    def test_ollama_uses_shared_parser(self):
        from fitness.adapters.llm import ollama_client
        assert hasattr(ollama_client, "parse_extraction_response")

    def test_anthropic_uses_shared_parser(self):
        from fitness.adapters.llm import anthropic_client
        assert hasattr(anthropic_client, "parse_extraction_response")
