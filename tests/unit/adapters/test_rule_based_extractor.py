import pytest

from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
from fitness.adapters.extraction.rule_based import RuleBasedExtractor
from fitness.domain.value_objects import MealTimeSlot, Provenance, Unit


@pytest.fixture
def extractor():
    return RuleBasedExtractor(StaticFoodKnowledgeBase())


def only_food(result):
    foods = result.candidate_meal.foods
    assert len(foods) == 1
    return foods[0]


class TestSingleFood:
    def test_servings_of_known_food(self, extractor):
        result = extractor.extract("I had 3 servings of chicken breast")
        food = only_food(result)
        assert food.name.value == "chicken breast"
        assert food.name.provenance is Provenance.DETERMINISTIC
        assert food.quantity.value.amount == 3
        assert food.quantity.value.unit is Unit.SERVING
        # macros/calories come from the KB, scaled by 3
        assert food.calories.value == pytest.approx(165 * 3)
        assert food.calories.provenance is Provenance.KNOWLEDGE_BASE
        assert food.macros.value.protein_g == pytest.approx(31 * 3)

    def test_grams_convert_to_servings(self, extractor):
        result = extractor.extract("200g chicken breast for lunch")
        food = only_food(result)
        assert food.quantity.value.unit is Unit.GRAM
        # 200g / 100g per serving = 2 servings -> 330 cal
        assert food.calories.value == pytest.approx(330)
        assert result.candidate_meal.meal_time.value is MealTimeSlot.LUNCH

    def test_meal_time_keyword_removed_from_name(self, extractor):
        result = extractor.extract("2 eggs for breakfast")
        food = only_food(result)
        assert "breakfast" not in food.name.value
        assert result.candidate_meal.meal_time.value is MealTimeSlot.BREAKFAST


class TestMultipleFoods:
    def test_split_on_and(self, extractor):
        result = extractor.extract("2 eggs and 1 cup of rice for breakfast")
        foods = result.candidate_meal.foods
        names = {f.name.value for f in foods}
        assert names == {"eggs", "rice"}
        assert result.candidate_meal.meal_time.value is MealTimeSlot.BREAKFAST
        by_name = {f.name.value: f for f in foods}
        assert by_name["eggs"].calories.value == pytest.approx(72 * 2)
        assert by_name["rice"].calories.value == pytest.approx(205)


class TestLoggingVerbsStripped:
    def test_log_verb_not_in_food_name(self, extractor):
        result = extractor.extract("Log 200g of chicken breast")
        food = only_food(result)
        assert food.name.value == "chicken breast"

    def test_track_verb_not_in_food_name(self, extractor):
        result = extractor.extract("track 2 eggs")
        food = only_food(result)
        assert food.name.value == "eggs"

    def test_add_verb_not_in_food_name(self, extractor):
        result = extractor.extract("add 1 serving of rice for lunch")
        food = only_food(result)
        assert food.name.value == "rice"


class TestGapsAndUnknowns:
    def test_missing_quantity_leaves_macros_unset(self, extractor):
        # "some chicken" -> no number; we don't guess an amount or macros.
        result = extractor.extract("I had some chicken")
        food = only_food(result)
        assert food.name.value == "chicken"
        assert food.quantity is None
        assert food.macros is None
        assert food.calories is None

    def test_unknown_food_has_name_but_no_macros(self, extractor):
        result = extractor.extract("I ate 1 kangaroo steak")
        food = only_food(result)
        assert food.name.value == "kangaroo steak"
        assert food.quantity is not None  # quantity still parsed
        assert food.macros is None  # not in KB -> no guess

    def test_cup_of_weight_food_declines_macros_with_note(self, extractor):
        # almonds are measured by weight; "cups" can't be converted -> note, no macros.
        result = extractor.extract("2 cups of almonds")
        food = only_food(result)
        assert food.quantity.value.unit is Unit.CUP
        assert food.macros is None
        assert any("almond" in n for n in result.notes)

    def test_non_food_text_fabricates_no_nutrition(self, extractor):
        # Even on non-logging text, the extractor must never invent macros/quantities.
        # (Routing such messages away from logging is the router's job, not the extractor's.)
        result = extractor.extract("hello there")
        for food in result.candidate_meal.foods:
            assert food.macros is None
            assert food.calories is None
            assert food.quantity is None
