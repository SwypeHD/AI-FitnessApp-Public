"""Shared LLM response parsing — used by both Ollama and Anthropic adapters.

Extracts structured ``CandidateFood``s from a JSON string the model returned,
with bracket repair for truncated output. All values get LLM provenance with
capped confidence.
"""

from __future__ import annotations

import json

from fitness.application.ports.extraction import ExtractionResult, LlmError
from fitness.domain.candidate import CandidateFood, CandidateMeal
from fitness.domain.value_objects import (
    FieldValue,
    Macros,
    MealTimeSlot,
    Provenance,
    Quantity,
    Unit,
)

_MAX_LLM_CONFIDENCE = 0.7
_VALID_UNITS = {u.value for u in Unit}
_VALID_MEAL_TIMES = {s.value for s in MealTimeSlot}


def parse_extraction_response(raw: str) -> ExtractionResult:
    """Parse a raw LLM string into an ``ExtractionResult``.

    Handles markdown fencing, truncated JSON (bracket repair), and validates
    each field into domain types. Raises ``LlmError`` if unparseable.
    """
    cleaned = _strip_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = _repair_json(cleaned)
        if repaired is not None:
            data = repaired
        else:
            raise LlmError(f"LLM returned invalid JSON: {raw[:200]}")

    foods_raw = data.get("foods", [])
    if not isinstance(foods_raw, list):
        raise LlmError(f"expected foods array, got {type(foods_raw).__name__}")

    foods: list[CandidateFood] = []
    notes: list[str] = []
    meal_time = None

    for item in foods_raw:
        cf = CandidateFood()

        name = item.get("name")
        if name and isinstance(name, str):
            cf.offer("name", FieldValue(name, Provenance.LLM, _MAX_LLM_CONFIDENCE))

        amount = item.get("amount")
        unit_str = item.get("unit")
        if amount is not None and isinstance(amount, (int, float)) and amount > 0:
            unit = Unit(unit_str) if unit_str in _VALID_UNITS else Unit.SERVING
            cf.offer(
                "quantity",
                FieldValue(Quantity(float(amount), unit), Provenance.LLM, _MAX_LLM_CONFIDENCE),
            )

        p = item.get("protein_g")
        c = item.get("carbs_g")
        f = item.get("fat_g")
        if all(isinstance(v, (int, float)) for v in (p, c, f) if v is not None):
            if p is not None and c is not None and f is not None:
                cf.offer(
                    "macros",
                    FieldValue(Macros(float(p), float(c), float(f)), Provenance.LLM, _MAX_LLM_CONFIDENCE),
                )

        cals = item.get("calories")
        if cals is not None and isinstance(cals, (int, float)):
            cf.offer(
                "calories",
                FieldValue(float(cals), Provenance.LLM, _MAX_LLM_CONFIDENCE),
            )

        if cf.name is not None:
            foods.append(cf)
        else:
            notes.append(f"LLM returned a food without a name: {item!r}")

        mt = item.get("meal_time")
        if mt in _VALID_MEAL_TIMES and meal_time is None:
            meal_time = FieldValue(MealTimeSlot(mt), Provenance.LLM, _MAX_LLM_CONFIDENCE)

    return ExtractionResult(
        candidate_meal=CandidateMeal(meal_time=meal_time, foods=foods, raw_turns=[]),
        notes=notes,
    )


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


def _repair_json(text: str) -> dict | None:
    """Try to fix truncated JSON by closing unmatched brackets/braces."""
    opens = 0
    sq_opens = 0
    for ch in text:
        if ch == "{":
            opens += 1
        elif ch == "}":
            opens -= 1
        elif ch == "[":
            sq_opens += 1
        elif ch == "]":
            sq_opens -= 1
    if opens <= 0 and sq_opens <= 0:
        return None
    repaired = text + ("]" * sq_opens) + ("}" * opens)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None
