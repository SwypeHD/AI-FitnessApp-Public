"""Tests for saved meal management via AI chat."""

from __future__ import annotations

from datetime import datetime

import pytest

from fitness.adapters.persistence.json_saved_meal_store import JsonSavedMealStore
from fitness.application.dto import LogStatus
from fitness.application.use_cases.handle_message import HandleMessageUseCase
from fitness.application.use_cases.log_meal import LogMealUseCase

from _factories import FixedClock, InMemoryMealRepository, make_food, make_meal
from fitness.domain.saved_meal import SavedMeal, SavedMealItem
from fitness.domain.value_objects import MealTimeSlot


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 22, 12, 0))


@pytest.fixture
def repo():
    return InMemoryMealRepository()


@pytest.fixture
def store(tmp_path):
    return JsonSavedMealStore(tmp_path)


def _build_handler(repo, clock, store):
    from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
    from fitness.adapters.extraction.rule_based import RuleBasedExtractor
    kb = StaticFoodKnowledgeBase()
    extractor = RuleBasedExtractor(kb)
    log_meal = LogMealUseCase(extractor=extractor, meal_repo=repo, clock=clock, food_kb=kb)
    from fitness.application.use_cases.edit_log import EditLogUseCase
    from fitness.application.use_cases.query import QueryUseCase
    edit_log = EditLogUseCase(meal_repo=repo, clock=clock, food_kb=kb)
    query = QueryUseCase(meal_repo=repo, clock=clock)
    return HandleMessageUseCase(
        log_meal=log_meal, query=query, edit_log=edit_log,
        meal_repo=repo, clock=clock, saved_meal_store=store,
    )


class TestSaveMeal:
    def test_save_lunch_as_named_meal(self, repo, clock, store):
        repo.save(make_meal(
            meal_id="m1", logged_at=datetime(2026, 6, 22, 12, 0),
            meal_time=MealTimeSlot.LUNCH,
            foods=(
                make_food(name="chicken breast", calories=165, meal_time=MealTimeSlot.LUNCH),
                make_food(name="white rice", calories=205, meal_time=MealTimeSlot.LUNCH),
            ),
        ))
        handler = _build_handler(repo, clock, store)
        result = handler.handle("save today's lunch as chicken and rice")
        assert result.status == LogStatus.LOGGED
        assert "Saved meal" in result.message
        assert "chicken and rice" in result.message
        meals = store.list_meals()
        assert len(meals) == 1
        assert meals[0].name == "chicken and rice"
        assert len(meals[0].items) == 2

    def test_save_no_foods_error(self, repo, clock, store):
        """When lunch has foods but breakfast doesn't, saving breakfast gives an error."""
        repo.save(make_meal(
            meal_id="m1", logged_at=datetime(2026, 6, 22, 12, 0),
            meal_time=MealTimeSlot.LUNCH,
            foods=(make_food(name="chicken breast", calories=165, meal_time=MealTimeSlot.LUNCH),),
        ))
        handler = _build_handler(repo, clock, store)
        result = handler.handle("save breakfast as morning meal")
        assert "No foods found" in result.message


class TestDeleteSavedMeal:
    def test_delete_by_name(self, repo, clock, store):
        store.save_meal(SavedMeal(
            id="sm1", name="chicken and rice",
            items=[SavedMealItem("chicken", 165, 165, 31, 0, 3.6)],
        ))
        handler = _build_handler(repo, clock, store)
        result = handler.handle("delete saved meal chicken and rice")
        assert result.status == LogStatus.LOGGED
        assert "Deleted" in result.message
        assert len(store.list_meals()) == 0

    def test_delete_not_found(self, repo, clock, store):
        handler = _build_handler(repo, clock, store)
        result = handler.handle("delete saved meal nonexistent")
        assert "Couldn't find" in result.message


class TestIntentRouting:
    def test_save_as_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("save today's lunch as chicken and rice") is Intent.EDIT

    def test_delete_saved_meal_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("delete saved meal chicken and rice") is Intent.EDIT
