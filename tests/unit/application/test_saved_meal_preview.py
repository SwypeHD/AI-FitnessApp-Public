"""Tests for the saved meal preview (create from KB) flow.

Covers:
- Creating a saved meal from KB foods shows a preview with correct macros
- Confirming the preview saves the meal
- Cancelling discards the preview
- Unknown foods are reported gracefully
- Mixed known/unknown foods show partial preview
- Various input phrasings work
"""

from __future__ import annotations

from datetime import datetime

import pytest

from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
from fitness.adapters.extraction.rule_based import RuleBasedExtractor
from fitness.adapters.persistence.json_saved_meal_store import JsonSavedMealStore
from fitness.application.dto import LogStatus, PendingSavedMealState
from fitness.application.use_cases.edit_log import EditLogUseCase
from fitness.application.use_cases.handle_message import HandleMessageUseCase
from fitness.application.use_cases.log_meal import LogMealUseCase
from fitness.application.use_cases.query import QueryUseCase

from _factories import FixedClock, InMemoryMealRepository


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 22, 12, 0))


@pytest.fixture
def repo():
    return InMemoryMealRepository()


@pytest.fixture
def store(tmp_path):
    return JsonSavedMealStore(tmp_path)


@pytest.fixture
def food_kb():
    return StaticFoodKnowledgeBase()


def _build_handler(repo, clock, store, food_kb):
    extractor = RuleBasedExtractor(food_kb)
    log_meal = LogMealUseCase(extractor=extractor, meal_repo=repo, clock=clock, food_kb=food_kb)
    edit_log = EditLogUseCase(meal_repo=repo, clock=clock, food_kb=food_kb)
    query = QueryUseCase(meal_repo=repo, clock=clock)
    return HandleMessageUseCase(
        log_meal=log_meal, query=query, edit_log=edit_log,
        meal_repo=repo, clock=clock, saved_meal_store=store,
        food_kb=food_kb,
    )


class TestCreateSavedMealPreview:
    """Test that 'create a saved meal called X with Y' returns a preview."""

    def test_chicken_and_rice_preview(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        result = handler.handle(
            "create a saved meal called my lunch with 200g chicken and 1 cup rice"
        )
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert isinstance(result.state, PendingSavedMealState)
        assert result.state.name == "my lunch"
        assert len(result.state.items) == 2

        # Check chicken item (200g chicken breast: 165 kcal per 100g)
        chicken = result.state.items[0]
        assert chicken.food_name == "chicken breast"
        assert chicken.quantity_amount == 200.0
        assert chicken.calories == 330.0  # 165 * 2

        # Check rice item (1 cup rice: 205 kcal per cup/158g)
        rice = result.state.items[1]
        assert rice.food_name == "white rice"
        assert rice.calories == 205.0

        # Preview message should contain food names and totals
        assert "chicken breast" in result.message
        assert "white rice" in result.message
        assert "my lunch" in result.message
        assert "Save this meal?" in result.message

    def test_eggs_with_servings(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        result = handler.handle(
            "create a meal called breakfast bowl with 3 eggs and 200g oatmeal"
        )
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert result.state.name == "breakfast bowl"
        assert len(result.state.items) == 2

        # 3 eggs: 72 kcal per egg * 3 = 216
        eggs = result.state.items[0]
        assert eggs.food_name == "egg"
        assert eggs.calories == 216.0

    def test_make_verb_works(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        result = handler.handle(
            "make a saved meal called snack plate with 1 banana and 30g almonds"
        )
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert result.state.name == "snack plate"
        assert len(result.state.items) == 2

    def test_preview_shows_total_macros(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        result = handler.handle(
            "create a saved meal called simple with 100g chicken"
        )
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert "Total:" in result.message
        assert "protein" in result.message


class TestConfirmSavedMeal:
    """Test that confirming saves the meal to the store."""

    def test_yes_saves_meal(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        # Step 1: Create preview
        preview = handler.handle(
            "create a saved meal called my lunch with 200g chicken and 1 cup rice"
        )
        assert preview.status == LogStatus.NEEDS_CLARIFICATION

        # Step 2: Confirm
        result = handler.handle("yes", state=preview.state)
        assert result.status == LogStatus.LOGGED
        assert "Saved meal" in result.message
        assert "my lunch" in result.message

        # Verify it was persisted
        meals = store.list_meals()
        assert len(meals) == 1
        assert meals[0].name == "my lunch"
        assert len(meals[0].items) == 2

    def test_save_it_confirms(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("save it", state=preview.state)
        assert result.status == LogStatus.LOGGED
        assert len(store.list_meals()) == 1

    def test_looks_good_confirms(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("looks good", state=preview.state)
        assert result.status == LogStatus.LOGGED
        assert len(store.list_meals()) == 1

    def test_saved_macros_are_correct(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 200g chicken"
        )
        handler.handle("yes", state=preview.state)
        meal = store.list_meals()[0]
        item = meal.items[0]
        # 200g chicken breast: 165 * 2 = 330 cal, 31*2=62 protein
        assert item.calories == 330.0
        assert item.protein_g == 62.0
        assert item.quantity_g == 200.0


class TestCancelSavedMeal:
    """Test that cancelling discards the preview."""

    def test_no_cancels(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("no", state=preview.state)
        assert result.status == LogStatus.LOGGED
        assert "cancelled" in result.message.lower()
        assert len(store.list_meals()) == 0

    def test_cancel_cancels(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("cancel", state=preview.state)
        assert result.status == LogStatus.LOGGED
        assert "cancelled" in result.message.lower()
        assert len(store.list_meals()) == 0

    def test_nevermind_cancels(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("nevermind", state=preview.state)
        assert result.status == LogStatus.LOGGED
        assert "cancelled" in result.message.lower()
        assert len(store.list_meals()) == 0

    def test_unrecognized_reprompts(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("hmm maybe", state=preview.state)
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert isinstance(result.state, PendingSavedMealState)


class TestUnknownFoods:
    """Test graceful handling when foods aren't in the KB."""

    def test_all_unknown_gives_error(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        result = handler.handle(
            "create a saved meal called test with 100g unicorn meat and 50g dragon scales"
        )
        assert result.status == LogStatus.LOGGED
        assert "couldn't find" in result.message.lower() or "Could not find" in result.message

    def test_partial_unknown_shows_warning(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        result = handler.handle(
            "create a saved meal called test with 200g chicken and 100g mystery food"
        )
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert len(result.state.items) == 1  # only chicken
        assert "Could not find" in result.message
        assert "mystery food" in result.message


class TestIntentRouting:
    """Test that create/make saved meal patterns route to EDIT intent."""

    def test_create_saved_meal_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("create a saved meal called breakfast with 3 eggs") is Intent.EDIT

    def test_make_meal_called_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("make a meal called lunch with 200g chicken and rice") is Intent.EDIT

    def test_make_saved_meal_named_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("make a saved meal named dinner with salmon") is Intent.EDIT


class TestIntentEscape:
    """Mid-preview, a clear non-chat intent should break out of the flow."""

    def test_query_escapes_preview(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 200g chicken"
        )
        assert preview.status == LogStatus.NEEDS_CLARIFICATION
        result = handler.handle("how much protein have I had today?", state=preview.state)
        assert result.status == LogStatus.LOGGED
        assert result.state is None
        assert len(store.list_meals()) == 0

    def test_log_escapes_preview(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("I had 200g rice for lunch", state=preview.state)
        assert result.state is None or not isinstance(result.state, PendingSavedMealState)
        assert len(store.list_meals()) == 0


class TestModifyPendingMeal:
    """User can modify items in the preview before confirming."""

    def test_change_quantity(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 200g chicken and 1 cup rice"
        )
        assert preview.state.items[0].calories == 330.0  # 200g chicken

        result = handler.handle("change chicken to 300g", state=preview.state)
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert isinstance(result.state, PendingSavedMealState)
        assert result.state.items[0].quantity_amount == 300.0
        assert result.state.items[0].calories == 495.0  # 300g chicken

    def test_remove_item(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 200g chicken and 1 cup rice"
        )
        assert len(preview.state.items) == 2

        result = handler.handle("remove the rice", state=preview.state)
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert len(result.state.items) == 1
        assert result.state.items[0].food_name == "chicken breast"

    def test_remove_all_items_cancels(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("remove the chicken", state=preview.state)
        assert result.status == LogStatus.LOGGED
        assert "removed" in result.message.lower() or "cancelled" in result.message.lower()

    def test_modify_then_confirm(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 200g chicken"
        )
        modified = handler.handle("change chicken to 300g", state=preview.state)
        result = handler.handle("yes", state=modified.state)
        assert result.status == LogStatus.LOGGED
        meals = store.list_meals()
        assert len(meals) == 1
        assert meals[0].items[0].quantity_g == 300.0
        assert meals[0].items[0].calories == 495.0

    def test_remove_unknown_item_shows_error(self, repo, clock, store, food_kb):
        handler = _build_handler(repo, clock, store, food_kb)
        preview = handler.handle(
            "create a saved meal called test with 100g chicken"
        )
        result = handler.handle("remove the pasta", state=preview.state)
        assert result.status == LogStatus.NEEDS_CLARIFICATION
        assert "Couldn't find" in result.message
        assert isinstance(result.state, PendingSavedMealState)


class TestStateCodecRoundTrip:
    """Test that PendingSavedMealState survives encode/decode."""

    def test_roundtrip(self):
        from fitness.application.dto import PendingSavedMealItem, PendingSavedMealState
        from fitness.web.state_codec import decode_state, encode_state

        state = PendingSavedMealState(
            name="my lunch",
            items=[
                PendingSavedMealItem(
                    food_name="chicken breast",
                    quantity_amount=200.0,
                    quantity_unit="g",
                    calories=330.0,
                    protein_g=62.0,
                    carbs_g=0.0,
                    fat_g=7.2,
                ),
            ],
        )
        encoded = encode_state(state)
        assert encoded["type"] == "saved_meal_preview"

        decoded = decode_state(encoded)
        assert isinstance(decoded, PendingSavedMealState)
        assert decoded.name == "my lunch"
        assert len(decoded.items) == 1
        assert decoded.items[0].food_name == "chicken breast"
        assert decoded.items[0].calories == 330.0
