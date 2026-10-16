import pytest

from fitness.application.ports.nutrition import KnownFood
from fitness.application.scaling import quantity_to_servings, scaled_nutrition
from fitness.domain.value_objects import Macros, Quantity, Unit


def kf(serving_grams=100, serving_unit=Unit.SERVING):
    return KnownFood(
        name="x",
        macros_per_serving=Macros(10, 0, 0),
        calories_per_serving=100,
        serving_grams=serving_grams,
        serving_unit=serving_unit,
    )


class TestQuantityToServings:
    def test_servings_are_a_count(self):
        assert quantity_to_servings(Quantity(3, Unit.SERVING), kf()) == 3

    def test_grams_convert_via_serving_grams(self):
        assert quantity_to_servings(Quantity(200, Unit.GRAM), kf(serving_grams=100)) == 2

    def test_ounces_convert(self):
        result = quantity_to_servings(Quantity(1, Unit.OUNCE), kf(serving_grams=28))
        assert result == pytest.approx(28.3495 / 28)

    def test_cup_matches_food_serving_unit(self):
        assert quantity_to_servings(Quantity(2, Unit.CUP), kf(serving_unit=Unit.CUP)) == 2

    def test_cup_mismatch_returns_none(self):
        assert quantity_to_servings(Quantity(2, Unit.CUP), kf(serving_unit=Unit.SERVING)) is None


class TestScaledNutrition:
    def test_scales_macros_and_calories(self):
        macros, calories = scaled_nutrition(kf(), 3)
        assert macros == Macros(30, 0, 0)
        assert calories == 300
