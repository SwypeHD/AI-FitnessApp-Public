"""Clock port — injectable time, so date-dependent logic is deterministically testable."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...
