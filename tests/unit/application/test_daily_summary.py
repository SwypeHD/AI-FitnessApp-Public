from datetime import date, datetime

from fitness.application.use_cases.daily_summary import GetDailySummaryUseCase
from fitness.domain.value_objects import MealTimeSlot

from _factories import InMemoryMealRepository, make_food, make_meal


def test_empty_day_is_all_zero():
    summary = GetDailySummaryUseCase(InMemoryMealRepository()).handle(date(2026, 6, 4))
    assert summary.meal_count == 0
    assert summary.total_calories == 0
    assert summary.calories_by_slot == {}


def test_aggregates_across_meals_and_slots():
    repo = InMemoryMealRepository()
    repo.save(
        make_meal(
            meal_id="b",
            logged_at=datetime(2026, 6, 4, 8, 0),
            meal_time=MealTimeSlot.BREAKFAST,
            foods=(make_food(name="eggs", calories=144, meal_time=MealTimeSlot.BREAKFAST),),
        )
    )
    repo.save(
        make_meal(
            meal_id="l",
            logged_at=datetime(2026, 6, 4, 12, 0),
            meal_time=MealTimeSlot.LUNCH,
            foods=(make_food(name="chicken", calories=495, meal_time=MealTimeSlot.LUNCH),),
        )
    )

    summary = GetDailySummaryUseCase(repo).handle(date(2026, 6, 4))
    assert summary.meal_count == 2
    assert summary.total_calories == 639
    assert summary.calories_by_slot[MealTimeSlot.BREAKFAST] == 144
    assert summary.calories_by_slot[MealTimeSlot.LUNCH] == 495


def test_only_counts_requested_day():
    repo = InMemoryMealRepository()
    repo.save(make_meal(meal_id="x", logged_at=datetime(2026, 6, 4, 8, 0)))
    repo.save(make_meal(meal_id="y", logged_at=datetime(2026, 6, 5, 8, 0)))
    summary = GetDailySummaryUseCase(repo).handle(date(2026, 6, 4))
    assert summary.meal_count == 1
