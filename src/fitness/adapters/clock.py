"""Real implementations of the ``Clock`` port."""

from __future__ import annotations

from datetime import date, datetime, timezone, tzinfo


class SystemClock:
    """Wall-clock time. ``tz`` controls which local day a ``today()`` falls in, so meals
    bucket into the user's day rather than UTC's (configured via settings later)."""

    def __init__(self, tz: tzinfo | None = None) -> None:
        self._tz = tz

    def now(self) -> datetime:
        return datetime.now(self._tz)

    def today(self) -> date:
        return self.now().date()
