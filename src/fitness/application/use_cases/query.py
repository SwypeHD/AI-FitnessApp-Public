"""QueryUseCase — answers questions about logged data deterministically.

Routes between a structured log view ("show me my log") and a summary view ("how much
protein today"). All numbers come from the repository; the LLM never does arithmetic.
"""

from __future__ import annotations

import re

from fitness.application.ports.clock import Clock
from fitness.application.ports.repositories import MealRepository
from fitness.application.use_cases.daily_summary import GetDailySummaryUseCase
from fitness.application.use_cases.view_log import ViewLogUseCase

_LOG_VIEW_PATTERNS = [
    re.compile(r"\b(?:show|list|view|display|see|get)\b.*\b(?:log|meals?|food|eaten)\b", re.I),
    re.compile(r"\bwhat (?:did|have) I\b.*\b(?:eat|ate|had|have|log)\b", re.I),
]


class QueryUseCase:
    def __init__(self, meal_repo: MealRepository, clock: Clock) -> None:
        self._summary_uc = GetDailySummaryUseCase(meal_repo)
        self._view_log_uc = ViewLogUseCase(meal_repo)
        self._clock = clock

    def handle(self, text: str) -> str:
        day = self._clock.today()

        if any(p.search(text) for p in _LOG_VIEW_PATTERNS):
            return self._view_log_uc.handle(day).to_text()

        summary = self._summary_uc.handle(day)
        if summary.meal_count == 0:
            return f"Nothing logged yet for {day.isoformat()}."

        slots = ", ".join(
            f"{slot.value}: {cals:.0f} kcal"
            for slot, cals in summary.calories_by_slot.items()
        )
        m = summary.total_macros
        return (
            f"Today ({day.isoformat()}): {summary.total_calories:.0f} kcal across "
            f"{summary.meal_count} meal(s). "
            f"Macros: {m.protein_g:.0f}g protein, {m.carbs_g:.0f}g carbs, {m.fat_g:.0f}g fat. "
            f"By slot: {slots}."
        )
