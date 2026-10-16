from datetime import date, datetime

from fitness.application.use_cases.view_log import ViewLogUseCase
from fitness.domain.value_objects import MealTimeSlot

from _factories import InMemoryMealRepository, make_food, make_meal


def test_empty_day():
    log = ViewLogUseCase(InMemoryMealRepository()).handle(date(2026, 6, 4))
    assert log.is_empty
    assert "nothing logged" in log.to_text().lower()


def test_structured_text_format():
    repo = InMemoryMealRepository()
    repo.save(make_meal(
        meal_id="b",
        logged_at=datetime(2026, 6, 4, 8, 0),
        meal_time=MealTimeSlot.BREAKFAST,
        foods=(make_food(name="eggs", calories=144, meal_time=MealTimeSlot.BREAKFAST),),
    ))
    repo.save(make_meal(
        meal_id="l",
        logged_at=datetime(2026, 6, 4, 12, 0),
        meal_time=MealTimeSlot.LUNCH,
        foods=(
            make_food(name="chicken breast", calories=495, meal_time=MealTimeSlot.LUNCH),
            make_food(name="rice", calories=205, meal_time=MealTimeSlot.LUNCH),
        ),
    ))

    log = ViewLogUseCase(repo).handle(date(2026, 6, 4))
    text = log.to_text()

    assert "2026-06-04" in text
    assert "BREAKFAST" in text
    assert "eggs" in text
    assert "144 kcal" in text
    assert "LUNCH" in text
    assert "chicken breast" in text
    assert "rice" in text
    assert "TOTAL" in text
    assert "844 kcal" in text  # 144 + 495 + 205


def test_dict_format_has_slots():
    repo = InMemoryMealRepository()
    repo.save(make_meal(
        meal_id="d",
        logged_at=datetime(2026, 6, 4, 19, 0),
        meal_time=MealTimeSlot.DINNER,
        foods=(make_food(name="salmon", calories=208, meal_time=MealTimeSlot.DINNER),),
    ))

    d = ViewLogUseCase(repo).handle(date(2026, 6, 4)).to_dict()
    assert d["day"] == "2026-06-04"
    assert "dinner" in d["slots"]
    assert d["slots"]["dinner"]["foods"][0]["name"] == "salmon"
    assert d["total_calories"] == 208
