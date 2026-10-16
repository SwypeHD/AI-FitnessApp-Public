"""Static, in-memory food knowledge base — the dev/offline ``FoodKnowledgeBase``.

A small curated seed table of common foods with per-serving macros. Matching is by
normalized name with longest-phrase preference, so "grilled chicken breast" resolves to
"chicken breast" rather than "chicken". The same port can later be backed by the USDA
FoodData Central API without touching the core. Values are approximate and intended for
a believable dev experience, not clinical accuracy.
"""

from __future__ import annotations

from fitness.application.ports.nutrition import KnownFood
from fitness.domain.naming import normalize_food_name
from fitness.domain.value_objects import Macros, Unit


def _food(name, p, c, f, cals, grams, unit=Unit.SERVING) -> KnownFood:
    return KnownFood(
        name=name,
        macros_per_serving=Macros(protein_g=p, carbs_g=c, fat_g=f),
        calories_per_serving=cals,
        serving_grams=grams,
        serving_unit=unit,
    )


# Canonical foods. The first alias in each tuple is the canonical display name.
_SEED: list[tuple[list[str], KnownFood]] = [
    (["chicken breast", "chicken"], _food("chicken breast", 31, 0, 3.6, 165, 100)),
    (["egg"], _food("egg", 6.3, 0.4, 5.3, 72, 50, Unit.PIECE)),
    (["white rice", "rice"], _food("white rice", 4.3, 44.5, 0.4, 205, 158, Unit.CUP)),
    (["banana"], _food("banana", 1.3, 27, 0.4, 105, 118, Unit.PIECE)),
    (["oats", "oatmeal"], _food("oats", 5, 27, 3, 150, 40)),
    (["apple"], _food("apple", 0.5, 25, 0.3, 95, 182, Unit.PIECE)),
    (["milk"], _food("milk", 8, 12, 5, 122, 244, Unit.CUP)),
    (["almonds", "almond"], _food("almonds", 6, 6, 14, 164, 28)),
    (["broccoli"], _food("broccoli", 2.6, 6, 0.3, 31, 91, Unit.CUP)),
    (["greek yogurt", "yogurt"], _food("greek yogurt", 17, 6, 0.7, 100, 170)),
    (["peanut butter"], _food("peanut butter", 7, 7, 16, 188, 32)),
    (["salmon"], _food("salmon", 20, 0, 13, 208, 100)),
]


class StaticFoodKnowledgeBase:
    """In-memory implementation of the ``FoodKnowledgeBase`` port."""

    def __init__(self) -> None:
        # normalized alias -> KnownFood
        self._by_alias: dict[str, KnownFood] = {}
        for aliases, food in _SEED:
            for alias in aliases:
                self._by_alias[normalize_food_name(alias)] = food
        # alias phrases as token lists, longest first (for sub-phrase matching)
        self._phrases: list[tuple[list[str], KnownFood]] = sorted(
            (
                (alias.split(), food)
                for alias, food in self._by_alias.items()
            ),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )

    def all_entries(self):
        """Yield (display_name, KnownFood) for every unique food."""
        seen = set()
        for food in self._by_alias.values():
            if food.name not in seen:
                seen.add(food.name)
                yield food.name, food

    def lookup(self, name: str) -> KnownFood | None:
        normalized = normalize_food_name(name)
        exact = self._by_alias.get(normalized)
        if exact is not None:
            return exact
        tokens = normalized.split()
        for phrase_tokens, food in self._phrases:
            if _contains_phrase(tokens, phrase_tokens):
                return food
        return None


def _contains_phrase(tokens: list[str], phrase: list[str]) -> bool:
    """True if ``phrase`` appears as a contiguous run of whole tokens within ``tokens``.

    Token-level (not substring) matching avoids false hits like "egg" in "eggplant".
    """
    n, m = len(tokens), len(phrase)
    if m == 0 or m > n:
        return False
    for i in range(n - m + 1):
        if tokens[i : i + m] == phrase:
            return True
    return False
