import pytest

from fitness.application.parsing import (
    first_quantity,
    meal_time_in,
    parse_number,
    parse_numbers,
    parse_quantity_and_remainder,
    parse_unit,
)
from fitness.domain.value_objects import MealTimeSlot, Unit


@pytest.mark.parametrize(
    "token, unit",
    [
        ("g", Unit.GRAM),
        ("grams", Unit.GRAM),
        ("oz", Unit.OUNCE),
        ("servings", Unit.SERVING),
        ("cup", Unit.CUP),
        ("pieces", Unit.PIECE),
        ("nonsense", None),
        (None, None),
    ],
)
def test_parse_unit(token, unit):
    assert parse_unit(token) is unit


class TestParseQuantity:
    def test_digits_with_attached_unit(self):
        q, remainder = parse_quantity_and_remainder("200g chicken")
        assert q.amount == 200 and q.unit is Unit.GRAM
        assert "chicken" in remainder

    def test_word_number_defaults_to_servings(self):
        assert first_quantity("two eggs").amount == 2
        assert first_quantity("two eggs").unit is Unit.SERVING

    def test_article_a_is_one(self):
        assert first_quantity("a cup of rice").amount == 1
        assert first_quantity("a cup of rice").unit is Unit.CUP

    def test_no_quantity(self):
        assert first_quantity("chicken breast") is None


class TestNumbers:
    def test_parse_number_first(self):
        assert parse_number("about 250 calories") == 250

    def test_parse_number_word(self):
        assert parse_number("three") == 3

    def test_parse_numbers_all(self):
        assert parse_numbers("30 protein 5 carbs 4 fat") == [30, 5, 4]

    def test_parse_number_none(self):
        assert parse_number("no digits here") is None


class TestMealTime:
    @pytest.mark.parametrize(
        "text, slot",
        [
            ("for lunch", MealTimeSlot.LUNCH),
            ("this was breakfast", MealTimeSlot.BREAKFAST),
            ("a dinner plate", MealTimeSlot.DINNER),
            ("an afternoon snack", MealTimeSlot.SNACK),
            ("no meal keyword", None),
        ],
    )
    def test_meal_time_in(self, text, slot):
        assert meal_time_in(text) is slot
