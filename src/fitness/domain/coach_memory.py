"""Durable facts the coach should carry between conversations.

Memories are only ever created from an explicit user instruction ("remember that
..."), never inferred by the LLM. That keeps the same guarantee as the rest of the
app: the model can read this context but can't invent it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Ignored when matching "forget ..." so filler words can't make everything match.
_STOPWORDS = frozenset({
    "a", "an", "the", "my", "me", "i", "is", "are", "was", "were", "about",
    "that", "this", "of", "to", "for", "and", "or", "in", "on", "at", "it",
    "have", "has", "had", "do", "does", "did", "be", "been", "am",
})


@dataclass(frozen=True, slots=True)
class CoachMemory:
    text: str
    created: date

    def __post_init__(self) -> None:
        cleaned = self.text.strip()
        if not cleaned:
            raise ValueError("memory text must not be blank")
        object.__setattr__(self, "text", cleaned)

    def matches(self, term: str) -> bool:
        """Whether ``term`` refers to this memory, for 'forget ...'.

        Plain containment is both too strict and too loose: it misses "my shoulder"
        against "my left shoulder is bad", yet matches "arm" inside "warmups". So
        compare whole words instead — every meaningful word of the term must appear
        in the memory.
        """
        haystack = self.text.lower()
        needle = term.strip().lower()
        if not needle:
            return False

        words = [w for w in re.findall(r"[a-z0-9']+", needle) if w not in _STOPWORDS]
        if not words:
            return False
        present = set(re.findall(r"[a-z0-9']+", haystack))
        return all(w in present for w in words)
