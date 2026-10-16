"""Tests for AI chat plan builder — create and modify workout plans via chat."""

from __future__ import annotations

from datetime import datetime

import pytest

from fitness.adapters.persistence.json_plan_store import JsonPlanStore
from fitness.application.use_cases.build_plan import BuildPlanUseCase
from fitness.application.use_cases.manage_calendar import ManageCalendarUseCase

from _factories import FixedClock


@pytest.fixture
def tmp_store(tmp_path):
    return JsonPlanStore(tmp_path)


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 22, 10, 0))


@pytest.fixture
def manage_cal(tmp_store, clock):
    return ManageCalendarUseCase(plan_store=tmp_store, clock=clock)


@pytest.fixture
def uc(tmp_store, manage_cal):
    return BuildPlanUseCase(plan_store=tmp_store, manage_calendar=manage_cal)


class TestCreatePlan:
    def test_create_ppl_plan(self, uc):
        result = uc.handle("create a push pull legs plan")
        assert result is not None
        assert result.success is True
        assert result.plan is not None
        assert len(result.plan.rotation) == 7  # PPL preset has 7 days
        assert "Push Pull Legs" in result.message

    def test_create_upper_lower_plan(self, uc):
        result = uc.handle("make me an upper lower split")
        assert result is not None
        assert result.success is True
        assert result.plan is not None
        labels = [d.label for d in result.plan.rotation]
        assert "Upper" in labels
        assert "Lower" in labels

    def test_create_custom_plan_with_days(self, uc):
        result = uc.handle("create a plan with push, pull, legs, rest")
        assert result is not None
        assert result.success is True
        assert result.plan is not None
        assert len(result.plan.rotation) == 4
        labels = [d.label for d in result.plan.rotation]
        assert labels == ["Push", "Pull", "Legs", "Rest"]

    def test_create_custom_plan_rest_day_is_rest(self, uc):
        result = uc.handle("create a plan with push, rest, pull")
        assert result is not None
        assert result.success is True
        rest_days = [d for d in result.plan.rotation if d.is_rest]
        assert len(rest_days) == 1
        assert rest_days[0].label == "Rest"

    def test_create_custom_plan_has_exercises(self, uc):
        result = uc.handle("create a plan with chest, back, legs")
        assert result is not None
        assert result.success is True
        for day in result.plan.rotation:
            assert len(day.exercises) > 0

    def test_create_4day_upper_lower(self, uc):
        result = uc.handle("create a 4-day upper/lower split")
        assert result is not None
        assert result.success is True
        assert len(result.plan.rotation) == 4
        labels = [d.label for d in result.plan.rotation]
        assert labels == ["Upper", "Lower", "Upper", "Lower"]

    def test_create_plan_saved_to_store(self, uc, tmp_store):
        result = uc.handle("create a plan with push, pull, legs")
        assert result is not None
        assert result.success is True
        # Should be retrievable from the store.
        plan = tmp_store.get_plan(result.plan.id)
        assert plan is not None
        assert plan.name == result.plan.name

    def test_create_plan_message_mentions_activate(self, uc):
        result = uc.handle("create a push pull legs plan")
        assert result is not None
        assert "activate" in result.message.lower()

    def test_create_bro_split(self, uc):
        result = uc.handle("create a 5-day bro split")
        assert result is not None
        assert result.success is True
        assert len(result.plan.rotation) == 5
        labels = [d.label for d in result.plan.rotation]
        assert "Chest" in labels
        assert "Back" in labels
        assert "Legs" in labels

    def test_create_full_body(self, uc):
        result = uc.handle("create a 3-day full body plan")
        assert result is not None
        assert result.success is True
        assert len(result.plan.rotation) == 3
        for day in result.plan.rotation:
            assert day.label == "Full Body"

    def test_non_plan_message_returns_none(self, uc):
        result = uc.handle("I had 200g chicken for lunch")
        assert result is None

    def test_create_plan_with_and_separator(self, uc):
        result = uc.handle("create a plan with push and pull and legs")
        assert result is not None
        assert result.success is True
        assert len(result.plan.rotation) == 3


class TestAddDay:
    def _create_base_plan(self, uc):
        result = uc.handle("create a plan with push, pull, legs")
        assert result is not None and result.success
        return result.plan

    def test_add_rest_day_to_plan(self, uc):
        self._create_base_plan(uc)
        result = uc.handle("add a rest day to my plan")
        assert result is not None
        assert result.success is True
        assert len(result.plan.rotation) == 4
        assert result.plan.rotation[-1].label == "Rest"
        assert result.plan.rotation[-1].is_rest is True

    def test_add_day_after_specific_day(self, uc):
        self._create_base_plan(uc)
        result = uc.handle("add a rest day after legs to my plan")
        assert result is not None
        assert result.success is True
        labels = [d.label for d in result.plan.rotation]
        legs_idx = labels.index("Legs")
        assert labels[legs_idx + 1] == "Rest"

    def test_add_day_no_plan(self, uc):
        result = uc.handle("add a rest day to my plan")
        assert result is not None
        assert result.success is False
        assert "create" in result.message.lower() or "no custom plan" in result.message.lower()


class TestRemoveDay:
    def _create_base_plan(self, uc):
        result = uc.handle("create a plan with push, pull, legs, rest")
        assert result is not None and result.success
        return result.plan

    def test_remove_rest_day(self, uc):
        self._create_base_plan(uc)
        result = uc.handle("remove rest day from my plan")
        assert result is not None
        assert result.success is True
        assert len(result.plan.rotation) == 3
        labels = [d.label for d in result.plan.rotation]
        assert "Rest" not in labels

    def test_remove_second_occurrence(self, uc):
        # Create plan with two push days.
        uc.handle("create a plan with push, pull, push, legs")
        result = uc.handle("remove second push day from my plan")
        assert result is not None
        assert result.success is True
        labels = [d.label for d in result.plan.rotation]
        assert labels.count("Push") == 1
        # First push should remain at position 0.
        assert labels[0] == "Push"

    def test_remove_nonexistent_day(self, uc):
        self._create_base_plan(uc)
        result = uc.handle("remove cardio day from my plan")
        assert result is not None
        assert result.success is False

    def test_remove_day_no_plan(self, uc):
        result = uc.handle("remove rest day from my plan")
        assert result is not None
        assert result.success is False


class TestRenameDay:
    def _create_base_plan(self, uc):
        result = uc.handle("create a plan with push, pull, legs")
        assert result is not None and result.success
        return result.plan

    def test_rename_day(self, uc):
        self._create_base_plan(uc)
        result = uc.handle("rename push to chest and triceps")
        assert result is not None
        assert result.success is True
        labels = [d.label for d in result.plan.rotation]
        assert "Push" not in labels
        assert "Chest And Triceps" in labels

    def test_rename_nonexistent_day(self, uc):
        self._create_base_plan(uc)
        result = uc.handle("rename cardio to hiit")
        assert result is not None
        assert result.success is False

    def test_rename_day_no_plan(self, uc):
        result = uc.handle("rename push to chest")
        assert result is not None
        assert result.success is False


class TestIntentRouting:
    """Verify plan builder phrases route to EDIT intent."""

    def test_create_plan_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("create a push pull legs plan") is Intent.EDIT

    def test_make_plan_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("make me a 4-day upper/lower split") is Intent.EDIT

    def test_build_routine_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("build a workout routine") is Intent.EDIT

    def test_add_day_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("add a rest day to my plan") is Intent.EDIT

    def test_remove_day_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("remove rest day from my plan") is Intent.EDIT

    def test_rename_day_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("rename push to chest and triceps") is Intent.EDIT
