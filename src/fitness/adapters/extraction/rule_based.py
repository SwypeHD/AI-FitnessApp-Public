"""The deterministic, rule-based extractor.

Runs first and is authoritative. Composes the application's parsing/scaling primitives
with food-name cleaning and a knowledge-base lookup to turn free text into a
``CandidateMeal``. It deliberately emits NOTHING it can't justify: a missing quantity or
an unknown food simply leaves fields unset, which later drives a clarification question or
an LLM gap-fill rather than a guess.
"""

from __future__ import annotations

import re

from fitness.application.parsing import (
    parse_meal_time_and_remainder,
    parse_quantity_and_remainder,
)
from fitness.application.ports.extraction import ExtractionResult
from fitness.application.ports.nutrition import FoodKnowledgeBase
from fitness.application.scaling import quantity_to_servings, scaled_nutrition
from fitness.domain.candidate import CandidateFood, CandidateMeal
from fitness.domain.value_objects import FieldValue, Provenance

# Confidence levels for deterministically-derived fields.
_NAME_CONF = 0.95
_QTY_CONF = 0.95
_KB_CONF = 0.95
_MEAL_TIME_CONF = 0.9

# Filler tokens stripped from a food name once quantity/unit have been pulled out.
_STOPWORDS = {
    "i", "had", "ate", "have", "eat", "eating", "having", "of", "the", "a", "an",
    "for", "my", "some", "with", "and", "today", "just", "also",
    "log", "logged", "track", "tracked", "tracking", "add", "added",
    "could", "can", "would", "you", "me", "please", "put", "record",
    "that", "this", "it", "its", "was", "were", "am", "is", "be",
    "?", "!", ".", ",",
}

# Split an utterance into separate food fragments.
_SPLIT_RE = re.compile(r"\s*(?:,|&|\band\b|\bwith\b)\s*", re.IGNORECASE)


class RuleBasedExtractor:
    """Implements the ``Extractor`` port."""

    def __init__(self, knowledge_base: FoodKnowledgeBase) -> None:
        self._kb = knowledge_base

    def extract(
        self, text: str, context: CandidateMeal | None = None
    ) -> ExtractionResult:
        notes: list[str] = []

        foods: list[CandidateFood] = []
        meal_time_fv = None
        last_food_name_fv: FieldValue | None = None

        for fragment in _SPLIT_RE.split(text):
            frag_slot, frag_text = parse_meal_time_and_remainder(fragment)
            if frag_slot is not None and meal_time_fv is None:
                meal_time_fv = FieldValue(
                    frag_slot, Provenance.DETERMINISTIC, _MEAL_TIME_CONF
                )

            candidate = self._parse_fragment(frag_text, notes)

            if candidate is not None:
                if candidate.name is not None:
                    last_food_name_fv = candidate.name
                foods.append(candidate)
            elif last_food_name_fv is not None:
                quantity, _ = parse_quantity_and_remainder(frag_text)
                if quantity is not None:
                    implied = self._make_implied_food(
                        last_food_name_fv, quantity, notes
                    )
                    foods.append(implied)

        meal = CandidateMeal(meal_time=meal_time_fv, foods=foods, raw_turns=[text])
        return ExtractionResult(candidate_meal=meal, notes=notes)

    def _make_implied_food(
        self,
        name_fv: FieldValue,
        quantity: "Quantity",
        notes: list[str],
    ) -> CandidateFood:
        """Build a CandidateFood for a fragment that had a quantity but no food name,
        inheriting the name from a previous fragment (e.g. '3 chicken and 2 for lunch')."""
        from fitness.domain.value_objects import Quantity  # noqa: F811

        candidate = CandidateFood()
        candidate.offer("name", name_fv)
        candidate.offer(
            "quantity", FieldValue(quantity, Provenance.DETERMINISTIC, _QTY_CONF)
        )
        known = self._kb.lookup(name_fv.value)
        if known is not None:
            servings = quantity_to_servings(quantity, known)
            if servings is not None:
                macros, calories = scaled_nutrition(known, servings)
                candidate.offer(
                    "macros", FieldValue(macros, Provenance.KNOWLEDGE_BASE, _KB_CONF)
                )
                candidate.offer(
                    "calories",
                    FieldValue(calories, Provenance.KNOWLEDGE_BASE, _KB_CONF),
                )
            else:
                notes.append(
                    f"can't convert {quantity.unit.value} to servings for '{name_fv.value}'"
                )
        return candidate

    def _parse_fragment(
        self, fragment: str, notes: list[str]
    ) -> CandidateFood | None:
        quantity, name_text = parse_quantity_and_remainder(fragment)
        name = _clean_name(name_text)
        if not name:
            return None

        candidate = CandidateFood()
        candidate.offer("name", FieldValue(name, Provenance.DETERMINISTIC, _NAME_CONF))
        if quantity is not None:
            candidate.offer(
                "quantity", FieldValue(quantity, Provenance.DETERMINISTIC, _QTY_CONF)
            )

        known = self._kb.lookup(name)
        if known is not None and quantity is not None:
            servings = quantity_to_servings(quantity, known)
            if servings is not None:
                macros, calories = scaled_nutrition(known, servings)
                candidate.offer(
                    "macros", FieldValue(macros, Provenance.KNOWLEDGE_BASE, _KB_CONF)
                )
                candidate.offer(
                    "calories", FieldValue(calories, Provenance.KNOWLEDGE_BASE, _KB_CONF)
                )
            else:
                notes.append(
                    f"can't convert {quantity.unit.value} to servings for '{name}'"
                )
        return candidate


def _clean_name(text: str) -> str:
    stripped = re.sub(r"[?.!,]+", " ", text)
    tokens = [t for t in re.split(r"\s+", stripped.strip().lower()) if t]
    kept = [t for t in tokens if t not in _STOPWORDS]
    return " ".join(kept).strip()
