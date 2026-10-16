"""EditLogUseCase tests including the mutation-integrity regression test.

The key test (test_delete_actually_persists) guards the prior system's bug: edits must
change on-disk state, and the confirmation must reflect what's actually stored — not
what the model narrated.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
from fitness.application.use_cases.edit_log import EditLogUseCase
from fitness.domain.value_objects import MealTimeSlot, Quantity, Unit

from _factories import FixedClock, InMemoryMealRepository, make_food, make_meal


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 10, 12, 0))


@pytest.fixture
def repo():
    return InMemoryMealRepository()


@pytest.fixture
def kb():
    return StaticFoodKnowledgeBase()


@pytest.fixture
def uc(repo, clock, kb):
    return EditLogUseCase(meal_repo=repo, clock=clock, food_kb=kb)


def _seed(repo):
    """Seed a lunch with chicken + rice (KB-accurate macros)."""
    repo.save(make_meal(
        meal_id="m1",
        logged_at=datetime(2026, 6, 10, 12, 0),
        meal_time=MealTimeSlot.LUNCH,
        foods=(
            make_food(name="chicken breast", calories=495, meal_time=MealTimeSlot.LUNCH),
            make_food(name="white rice", amount=3, unit=Unit.SERVING, calories=615, meal_time=MealTimeSlot.LUNCH),
        ),
    ))


class TestDelete:
    def test_deletes_food_by_name(self, uc, repo):
        _seed(repo)
        result = uc.handle("delete the chicken breast")
        assert result.success
        assert "Deleted" in result.message
        remaining = repo.list_by_date(datetime(2026, 6, 10).date())
        food_names = [f.name for m in remaining for f in m.foods]
        assert "chicken breast" not in food_names
        assert "white rice" in food_names

    def test_delete_last_food_removes_meal(self, uc, repo, clock):
        repo.save(make_meal(
            meal_id="m2",
            logged_at=datetime(2026, 6, 10, 8, 0),
            meal_time=MealTimeSlot.BREAKFAST,
            foods=(make_food(name="eggs", calories=144, meal_time=MealTimeSlot.BREAKFAST),),
        ))
        result = uc.handle("delete the eggs")
        assert result.success
        assert repo.get("m2") is None

    def test_delete_unknown_food_fails(self, uc, repo):
        _seed(repo)
        result = uc.handle("delete the pizza")
        assert not result.success
        assert "Couldn't find" in result.message

    def test_delete_actually_persists(self, uc, repo):
        """MUTATION-INTEGRITY REGRESSION: delete must change stored state, and the
        confirmation must reflect the actual post-delete state — not a narration."""
        _seed(repo)
        result = uc.handle("remove chicken breast")
        assert result.success
        # Verify the confirmation contains the ACTUAL remaining log state.
        assert "white rice" in result.message
        # The log portion (after the "Deleted" line) must not list chicken breast.
        log_portion = result.message.split("\n", 1)[1] if "\n" in result.message else ""
        assert "chicken breast" not in log_portion.lower()
        # Verify the repo actually changed.
        day_meals = repo.list_by_date(datetime(2026, 6, 10).date())
        all_foods = [f.name for m in day_meals for f in m.foods]
        assert "chicken breast" not in all_foods


class TestMove:
    def test_moves_food_to_new_slot(self, uc, repo):
        _seed(repo)
        result = uc.handle("move white rice to dinner")
        assert result.success
        assert "dinner" in result.message.lower()
        day_meals = repo.list_by_date(datetime(2026, 6, 10).date())
        rice_meals = [m for m in day_meals for f in m.foods if f.name == "white rice"]
        assert any(m.meal_time is MealTimeSlot.DINNER for m in rice_meals)

    def test_move_unknown_food_fails(self, uc, repo):
        _seed(repo)
        result = uc.handle("move pizza to breakfast")
        assert not result.success

    def test_move_actually_persists(self, uc, repo):
        """MUTATION-INTEGRITY REGRESSION: move must change stored state."""
        _seed(repo)
        uc.handle("move chicken breast to dinner")
        day_meals = repo.list_by_date(datetime(2026, 6, 10).date())
        chicken_slots = [
            m.meal_time for m in day_meals for f in m.foods
            if f.name == "chicken breast"
        ]
        assert MealTimeSlot.DINNER in chicken_slots
        assert MealTimeSlot.LUNCH not in chicken_slots


class TestUpdateQuantity:
    def test_change_to_grams(self, uc, repo):
        _seed(repo)
        result = uc.handle("change the chicken breast to 200g")
        assert result.success
        assert "Updated" in result.message
        foods = [f for m in repo.list_by_date(datetime(2026, 6, 10).date()) for f in m.foods]
        chicken = next(f for f in foods if "chicken" in f.name)
        assert chicken.quantity == Quantity(200, Unit.GRAM)
        assert chicken.calories == pytest.approx(330, rel=0.05)

    def test_change_to_servings(self, uc, repo):
        _seed(repo)
        result = uc.handle("update the white rice to 2 servings")
        assert result.success
        foods = [f for m in repo.list_by_date(datetime(2026, 6, 10).date()) for f in m.foods]
        rice = next(f for f in foods if "rice" in f.name)
        assert rice.quantity == Quantity(2, Unit.SERVING)
        assert rice.calories == pytest.approx(410, rel=0.05)

    def test_correct_quantity(self, uc, repo):
        _seed(repo)
        result = uc.handle("actually only 100g of chicken breast")
        assert result.success
        foods = [f for m in repo.list_by_date(datetime(2026, 6, 10).date()) for f in m.foods]
        chicken = next(f for f in foods if "chicken" in f.name)
        assert chicken.quantity == Quantity(100, Unit.GRAM)
        assert chicken.calories == pytest.approx(165, rel=0.05)

    def test_update_unknown_food_fails(self, uc, repo):
        _seed(repo)
        result = uc.handle("change the pizza to 200g")
        assert not result.success


class TestConvertUnit:
    def test_convert_to_grams(self, uc, repo):
        _seed(repo)
        result = uc.handle("convert the white rice to grams")
        assert result.success
        assert "Converted" in result.message
        foods = [f for m in repo.list_by_date(datetime(2026, 6, 10).date()) for f in m.foods]
        rice = next(f for f in foods if "rice" in f.name)
        assert rice.quantity.unit == Unit.GRAM
        assert rice.quantity.amount == pytest.approx(474, rel=0.05)
        assert rice.calories == pytest.approx(615, rel=0.01)

    def test_convert_to_oz(self, uc, repo):
        _seed(repo)
        result = uc.handle("convert the chicken breast to oz")
        assert result.success
        foods = [f for m in repo.list_by_date(datetime(2026, 6, 10).date()) for f in m.foods]
        chicken = next(f for f in foods if "chicken" in f.name)
        assert chicken.quantity.unit == Unit.OUNCE
        assert chicken.calories == pytest.approx(495, rel=0.01)

    def test_convert_unknown_food_fails(self, uc, repo):
        _seed(repo)
        result = uc.handle("convert the pizza to grams")
        assert not result.success


class TestRename:
    def test_rename_food(self, uc, repo):
        _seed(repo)
        result = uc.handle("rename the white rice to brown rice")
        assert result.success
        assert "Renamed" in result.message
        foods = [f for m in repo.list_by_date(datetime(2026, 6, 10).date()) for f in m.foods]
        names = [f.name for f in foods]
        assert "brown rice" in names
        assert "white rice" not in names

    def test_rename_unknown_food_fails(self, uc, repo):
        _seed(repo)
        result = uc.handle("rename the pizza to calzone")
        assert not result.success


class TestIntentRouting:
    def test_update_quantity_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent

        assert classify_intent("change the rice to 200g") is Intent.EDIT
        assert classify_intent("update my chicken to 2 servings") is Intent.EDIT

    def test_convert_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent

        assert classify_intent("convert the rice to grams") is Intent.EDIT
        assert classify_intent("show my chicken in oz") is Intent.EDIT

    def test_rename_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent

        assert classify_intent("rename the rice to brown rice") is Intent.EDIT

    def test_correction_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent

        assert classify_intent("actually only 200g of rice") is Intent.EDIT


class TestUnparseable:
    def test_gibberish_edit(self, uc, repo):
        _seed(repo)
        result = uc.handle("do the thing with the stuff")
        assert not result.success
