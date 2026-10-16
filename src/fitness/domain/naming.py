"""Food-name normalization, used to align foods across extraction sources.

Kept deliberately simple and deterministic. Shared by reconciliation (to match the
same food coming from the deterministic parser and the LLM) and, later, by the
knowledge-base lookup and the rule-based extractor.
"""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_food_name(name: str) -> str:
    """Lowercase, collapse whitespace, and strip a simple trailing plural 's'.

    >>> normalize_food_name("  Chicken  Breasts ")
    'chicken breast'
    """
    normalized = _WHITESPACE.sub(" ", name.strip().lower())
    if len(normalized) > 3 and normalized.endswith("s") and not normalized.endswith("ss"):
        normalized = normalized[:-1]
    return normalized
