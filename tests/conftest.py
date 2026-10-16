"""Shared pytest fixtures.

Reusable factories/fakes live in ``_factories`` (importable directly); this module wires
the common ones up as fixtures.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from _factories import FixedClock, make_food, make_meal  # noqa: F401 (re-exported)


@pytest.fixture
def fixed_clock() -> FixedClock:
    return FixedClock(datetime(2026, 6, 4, 12, 0))
