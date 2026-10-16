"""Pure nutrition scaling math.

Converts a parsed ``Quantity`` into a number of servings of a ``KnownFood`` and scales its
per-serving macros/calories accordingly. Lives in the application layer (not adapters) so
both the rule-based extractor and the use-cases can share it without the dependency rule
being violated. No IO, no parsing — just arithmetic.
"""

from __future__ import annotations

from fitness.application.ports.nutrition import KnownFood
from fitness.domain.value_objects import Macros, Quantity, Unit

GRAMS_PER_OUNCE = 28.3495

#: Units that represent a discrete count equivalent to one serving each.
_COUNT_UNITS = {Unit.SERVING, Unit.PIECE}


def quantity_to_servings(quantity: Quantity, known: KnownFood) -> float | None:
    """Convert ``quantity`` to a number of servings of ``known``, or None if we can't.

    - SERVING/PIECE are treated as a count of servings.
    - GRAM/OUNCE convert via the food's ``serving_grams``.
    - A volumetric unit (CUP/ML) only converts when it matches the food's own
      ``serving_unit`` (e.g. rice measured in cups); otherwise we decline.
    """
    unit = quantity.unit
    amount = quantity.amount

    if unit in _COUNT_UNITS:
        return amount
    if unit == Unit.GRAM:
        return amount / known.serving_grams
    if unit == Unit.OUNCE:
        return (amount * GRAMS_PER_OUNCE) / known.serving_grams
    if unit == known.serving_unit:
        return amount
    return None


def scaled_nutrition(known: KnownFood, servings: float) -> tuple[Macros, float]:
    """Macros and calories for ``servings`` servings of ``known``."""
    return known.macros_per_serving.scaled(servings), known.calories_per_serving * servings
