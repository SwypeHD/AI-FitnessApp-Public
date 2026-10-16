"""Nutrition knowledge-base port.

Resolves a known food name to its macros and a sensible default serving size, so the
deterministic path can supply macros/calories without asking the LLM. Implemented now by
a static seed table; the same port can later be backed by the USDA FoodData Central API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fitness.domain.value_objects import Macros, Unit


@dataclass(frozen=True, slots=True)
class KnownFood:
    """Canonical nutrition facts for a known food, per one default serving.

    ``macros_per_serving`` are the macros for a single serving; ``serving_grams`` lets the
    deterministic extractor convert gram-based quantities into servings (and back).
    """

    name: str
    macros_per_serving: Macros
    calories_per_serving: float
    serving_grams: float
    serving_unit: Unit = Unit.SERVING


class FoodKnowledgeBase(Protocol):
    def lookup(self, name: str) -> KnownFood | None:
        """Return facts for ``name`` if known (matching is the adapter's concern)."""
        ...
