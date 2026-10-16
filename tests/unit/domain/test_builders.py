from datetime import datetime

import pytest

from fitness.domain.builders import FoodBuilder, MealBuilder
from fitness.domain.errors import IncompleteMealError
from fitness.domain.value_objects import (
    FieldValue,
    Macros,
    MealTimeSlot,
    Provenance,
    Quantity,
    Unit,
)


def fv(value, provenance=Provenance.DETERMINISTIC, confidence=1.0):
    return FieldValue(value, provenance, confidence)


def complete_food_builder(meal_time=None):
    fb = FoodBuilder()
    fb.offer("name", fv("chicken breast"))
    fb.offer("quantity", fv(Quantity(1, Unit.SERVING)))
    fb.offer("macros", fv(Macros(31, 0, 3.6)))
    fb.offer("calories", fv(165.0))
    if meal_time is not None:
        fb.offer("meal_time", fv(meal_time))
    return fb


class TestFoodBuilderOffer:
    def test_offer_rejects_unknown_field(self):
        with pytest.raises(ValueError):
            FoodBuilder().offer("bogus", fv("x"))

    def test_fills_empty_field(self):
        fb = FoodBuilder()
        assert fb.offer("name", fv("rice")) is True
        assert fb.name.value == "rice"

    def test_deterministic_does_not_overwrite_user(self):
        fb = FoodBuilder()
        fb.offer("quantity", fv(Quantity(2, Unit.SERVING), Provenance.USER))
        accepted = fb.offer(
            "quantity", fv(Quantity(3, Unit.SERVING), Provenance.DETERMINISTIC)
        )
        assert accepted is False
        assert fb.quantity.value == Quantity(2, Unit.SERVING)

    def test_deterministic_overwrites_llm(self):
        fb = FoodBuilder()
        fb.offer("calories", fv(180.0, Provenance.LLM, 1.0))
        accepted = fb.offer("calories", fv(165.0, Provenance.DETERMINISTIC, 0.9))
        assert accepted is True
        assert fb.calories.value == 165.0


class TestFoodBuilderCompleteness:
    def test_missing_fields_reported(self):
        fb = FoodBuilder()
        fb.offer("name", fv("egg"))
        assert set(fb.missing_fields()) == {"quantity", "macros", "calories", "meal_time"}
        assert not fb.is_complete()

    def test_build_raises_when_incomplete(self):
        fb = FoodBuilder()
        fb.offer("name", fv("egg"))
        with pytest.raises(IncompleteMealError) as exc:
            fb.build()
        assert "quantity" in exc.value.missing

    def test_build_succeeds_when_complete(self):
        fb = complete_food_builder(MealTimeSlot.LUNCH)
        food = fb.build()
        assert food.name == "chicken breast"
        assert food.meal_time is MealTimeSlot.LUNCH


class TestMealBuilder:
    def test_propagates_meal_time_to_foods(self):
        mb = MealBuilder(meal_time=fv(MealTimeSlot.DINNER))
        mb.food_builders.append(complete_food_builder())  # no meal_time yet
        assert mb.is_complete()
        meal = mb.build(meal_id="m1", logged_at=datetime(2026, 6, 4, 19, 0))
        assert meal.meal_time is MealTimeSlot.DINNER
        assert all(f.meal_time is MealTimeSlot.DINNER for f in meal.foods)

    def test_missing_reports_meal_time_and_no_foods(self):
        mb = MealBuilder()
        gaps = mb.missing()
        assert "meal_time" in gaps["meal"]
        assert "foods" in gaps["meal"]

    def test_missing_reports_per_food_gaps(self):
        mb = MealBuilder(meal_time=fv(MealTimeSlot.LUNCH))
        partial = FoodBuilder()
        partial.offer("name", fv("rice"))
        mb.food_builders.append(partial)
        gaps = mb.missing()
        assert "meal" not in gaps  # meal_time provided
        assert set(gaps["food[0]"]) == {"quantity", "macros", "calories"}

    def test_user_meal_time_not_overwritten_by_food_propagation(self):
        # A food already has a USER-set meal_time; meal-level propagation must not override.
        mb = MealBuilder(meal_time=fv(MealTimeSlot.DINNER, Provenance.DETERMINISTIC))
        fb = complete_food_builder()
        fb.offer("meal_time", fv(MealTimeSlot.SNACK, Provenance.USER))
        mb.food_builders.append(fb)
        meal = mb.build(meal_id="m1", logged_at=datetime(2026, 6, 4, 19, 0))
        assert meal.foods[0].meal_time is MealTimeSlot.SNACK

    def test_build_raises_when_incomplete(self):
        mb = MealBuilder()
        with pytest.raises(IncompleteMealError):
            mb.build(meal_id="m1", logged_at=datetime(2026, 6, 4, 19, 0))
