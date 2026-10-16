"""Domain-level exceptions.

These are raised by the pure domain and caught/translated by the application layer.
They never reference frameworks or transport concerns.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain errors."""


class IncompleteMealError(DomainError):
    """Raised when building a Food/Meal that is still missing required fields.

    Carries the structured gaps so callers can turn them into clarification
    questions instead of guessing.
    """

    def __init__(self, missing: object) -> None:
        self.missing = missing
        super().__init__(f"cannot build: missing required fields: {missing}")
