"""Deterministic natural-language parsing primitives.

Pure, rule-based extraction of the small set of structured tokens we care about:
quantities (number + unit), meal-time keywords, and bare numbers. No IO, no LLM. Lives in
the application layer so it's shared by the rule-based extractor (adapter) AND the
use-cases' clarification-answer handling — both need to parse the same things the same way.
"""

from __future__ import annotations

import re

from fitness.domain.value_objects import MealTimeSlot, Quantity, Unit

# --- units -----------------------------------------------------------------

_TOKEN_TO_UNIT: dict[str, Unit] = {
    "serving": Unit.SERVING, "servings": Unit.SERVING,
    "g": Unit.GRAM, "gram": Unit.GRAM, "grams": Unit.GRAM,
    "oz": Unit.OUNCE, "ounce": Unit.OUNCE, "ounces": Unit.OUNCE,
    "cup": Unit.CUP, "cups": Unit.CUP,
    "piece": Unit.PIECE, "pieces": Unit.PIECE,
    "ml": Unit.MILLILITER, "milliliter": Unit.MILLILITER, "milliliters": Unit.MILLILITER,
}

#: Unit tokens ordered longest-first so the regex alternation prefers "grams" over "g".
UNIT_TOKENS: tuple[str, ...] = tuple(sorted(_TOKEN_TO_UNIT, key=len, reverse=True))


def parse_unit(token: str | None) -> Unit | None:
    if token is None:
        return None
    return _TOKEN_TO_UNIT.get(token.strip().lower())


# --- numbers ---------------------------------------------------------------

_WORD_NUMBERS: dict[str, float] = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# digits use a leading boundary only (so "200g" works); word-numbers need both boundaries
# (so "a" doesn't match inside "apple").
_QTY_RE = re.compile(
    r"(?P<num>\b\d+(?:\.\d+)?|\b(?:" + "|".join(_WORD_NUMBERS) + r")\b)"
    r"\s*(?P<unit>" + "|".join(UNIT_TOKENS) + r")?\b",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def word_to_number(token: str) -> float | None:
    token = token.lower()
    if token in _WORD_NUMBERS:
        return float(_WORD_NUMBERS[token])
    try:
        return float(token)
    except ValueError:
        return None


def parse_quantity_and_remainder(text: str) -> tuple[Quantity | None, str]:
    """Find the first quantity in ``text``. Returns (quantity_or_None, text_without_it).

    A bare count with no unit ("2 eggs") defaults to servings; the knowledge base treats
    one piece/serving equivalently for count foods.
    """
    match = _QTY_RE.search(text)
    if match is None:
        return None, text
    amount = word_to_number(match.group("num"))
    if amount is None or amount <= 0:
        return None, text
    unit = parse_unit(match.group("unit")) or Unit.SERVING
    remainder = text[: match.start()] + " " + text[match.end() :]
    return Quantity(amount, unit), remainder


def first_quantity(text: str) -> Quantity | None:
    return parse_quantity_and_remainder(text)[0]


def parse_numbers(text: str) -> list[float]:
    """All bare numbers in order (used for e.g. 'protein/carbs/fat' answers)."""
    return [float(m.group()) for m in _NUMBER_RE.finditer(text)]


def parse_number(text: str) -> float | None:
    numbers = parse_numbers(text)
    if numbers:
        return numbers[0]
    for word, value in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            return float(value)
    return None


# --- meal time -------------------------------------------------------------

def parse_meal_time_and_remainder(text: str) -> tuple[MealTimeSlot | None, str]:
    """Pull the first meal-time keyword out, returning it and text with it removed."""
    for slot in MealTimeSlot:
        pattern = re.compile(rf"\b{slot.value}\b", re.IGNORECASE)
        if pattern.search(text):
            return slot, pattern.sub(" ", text, count=1)
    return None, text


def meal_time_in(text: str) -> MealTimeSlot | None:
    return parse_meal_time_and_remainder(text)[0]
