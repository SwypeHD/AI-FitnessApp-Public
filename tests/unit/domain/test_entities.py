from datetime import datetime

import pytest

from fitness.domain.food import Food
from fitness.domain.meal import Meal
from fitness.domain.value_objects import Macros, MealTimeSlot, Quantity, Unit


def make_food(name="chicken breast", calories=165.0, meal_time=MealTimeSlot.LUNCH):
    return Food(
        name=name,
        quantity=Quantity(1, Unit.SERVING),
        macros=Macros(protein_g=31, carbs_g=0, fat_g=3.6),
        calories=calories,
        meal_time=meal_time,
    )


class TestFood:
    def test_rejects_blank_name(self):
        with pytest.raises(ValueError):
            make_food(name="   ")

    def test_rejects_negative_calories(self):
        with pytest.raises(ValueError):
            make_food(calories=-1)

    def test_with_meal_time_returns_new_immutable_copy(self):
        f = make_food(meal_time=MealTimeSlot.BREAKFAST)
        moved = f.with_meal_time(MealTimeSlot.LUNCH)
        assert moved.meal_time is MealTimeSlot.LUNCH
        assert f.meal_time is MealTimeSlot.BREAKFAST  # original unchanged

    def test_is_immutable(self):
        with pytest.raises(AttributeError):
            make_food().calories = 0  # type: ignore[misc]


class TestMeal:
    def _meal(self, foods):
        return Meal(
            id="m1",
            logged_at=datetime(2026, 6, 4, 12, 0),
            meal_time=MealTimeSlot.LUNCH,
            foods=tuple(foods),
        )

    def test_totals_sum_over_foods(self):
        meal = self._meal([make_food(calories=165), make_food(calories=200)])
        assert meal.total_calories == 365
        assert meal.total_macros == Macros(62, 0, 7.2)

    def test_empty_meal_totals_are_zero(self):
        meal = self._meal([])
        assert meal.total_calories == 0
        assert meal.total_macros == Macros.zero()

    def test_add_food_is_immutable(self):
        meal = self._meal([make_food()])
        bigger = meal.add_food(make_food(name="rice"))
        assert len(bigger.foods) == 2
        assert len(meal.foods) == 1  # original unchanged

    def test_without_food_at_removes_one(self):
        meal = self._meal([make_food(name="a"), make_food(name="b")])
        result = meal.without_food_at(0)
        assert [f.name for f in result.foods] == ["b"]

    def test_without_food_at_rejects_bad_index(self):
        meal = self._meal([make_food()])
        with pytest.raises(IndexError):
            meal.without_food_at(5)

    def test_with_meal_time_moves_meal_and_all_foods(self):
        meal = Meal(
            id="m1",
            logged_at=datetime(2026, 6, 4, 8, 0),
            meal_time=MealTimeSlot.BREAKFAST,
            foods=(make_food(meal_time=MealTimeSlot.BREAKFAST),),
        )
        moved = meal.with_meal_time(MealTimeSlot.LUNCH)
        assert moved.meal_time is MealTimeSlot.LUNCH
        assert all(f.meal_time is MealTimeSlot.LUNCH for f in moved.foods)
        assert meal.meal_time is MealTimeSlot.BREAKFAST  # original unchanged
