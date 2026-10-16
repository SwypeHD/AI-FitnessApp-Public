"""GetDailySummaryUseCase — aggregate a day's logged meals.

Pure aggregation over immutable ``Meal`` objects from the repository. All arithmetic is
deterministic here (not delegated to a model), so any chatbot grounding built on top is
anchored to real, correct numbers.
"""

from __future__ import annotations

from datetime import date

from fitness.application.dto import DailySummary
from fitness.application.ports.repositories import MealRepository
from fitness.domain.value_objects import Macros, MealTimeSlot


class GetDailySummaryUseCase:
    def __init__(self, meal_repo: MealRepository) -> None:
        self._meal_repo = meal_repo

    def handle(self, day: date) -> DailySummary:
        meals = self._meal_repo.list_by_date(day)

        total_macros = Macros.zero()
        total_calories = 0.0
        by_slot: dict[MealTimeSlot, float] = {}
        for meal in meals:
            total_macros = total_macros + meal.total_macros
            total_calories += meal.total_calories
            by_slot[meal.meal_time] = by_slot.get(meal.meal_time, 0.0) + meal.total_calories

        return DailySummary(
            day=day,
            total_calories=total_calories,
            total_macros=total_macros,
            calories_by_slot=by_slot,
            meal_count=len(meals),
        )
