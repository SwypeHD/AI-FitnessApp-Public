"""Deterministic clarification-question generator.

Turns the structured gaps from ``MealBuilder.missing()`` into a single focused question and
a ``PendingClarification`` pointer to the slot being asked about. This is intentionally NOT
the LLM's job — the questions are predictable, and the pointer lets the next user message be
applied to exactly the right field with USER provenance.
"""

from __future__ import annotations

from fitness.domain.candidate import CandidateMeal

from .dto import PendingClarification

_TEMPLATES: dict[str, str] = {
    "meal_time": "Was this breakfast, lunch, dinner, or a snack?",
    "foods": "What did you eat?",
    "name": "What food was that?",
    "quantity": "How much {name} did you have? (e.g. 3 servings, 200g)",
    "calories": "About how many calories was the {name}?",
    "macros": "Do you know the macros for {name}? (protein, carbs, fat in grams)",
}


def next_question(
    missing: dict[str, list[str]], candidate: CandidateMeal
) -> tuple[PendingClarification, str] | None:
    """Pick the first gap to ask about. Meal-level gaps come before per-food gaps, and
    foods are asked in order — so the conversation resolves predictably."""
    if "meal" in missing:
        for field_name in missing["meal"]:
            return PendingClarification("meal", field_name), _TEMPLATES[field_name]

    for key in sorted(
        (k for k in missing if k.startswith("food[")),
        key=_food_index,
    ):
        for field_name in missing[key]:
            name = _food_name(candidate, _food_index(key))
            question = _TEMPLATES[field_name].format(name=name)
            return PendingClarification(key, field_name), question
    return None


def _food_index(key: str) -> int:
    return int(key[len("food[") : -1])


def _food_name(candidate: CandidateMeal, index: int) -> str:
    if 0 <= index < len(candidate.foods):
        name_field = candidate.foods[index].name
        if name_field is not None:
            return name_field.value
    return "that"
