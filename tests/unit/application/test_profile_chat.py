"""Tests for profile targets, unit toggle, and calendar align via AI chat."""

from __future__ import annotations

from datetime import datetime

import pytest

from fitness.adapters.persistence.json_plan_store import JsonPlanStore
from fitness.adapters.persistence.json_profile_store import JsonProfileStore
from fitness.application.dto import LogStatus
from fitness.application.use_cases.handle_message import HandleMessageUseCase
from fitness.application.use_cases.log_meal import LogMealUseCase
from fitness.application.use_cases.manage_calendar import ManageCalendarUseCase

from _factories import FixedClock, InMemoryMealRepository


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 22, 10, 0))


@pytest.fixture
def profile_store(tmp_path):
    return JsonProfileStore(tmp_path)


@pytest.fixture
def plan_store(tmp_path):
    return JsonPlanStore(tmp_path)


def _build_handler(clock, profile_store=None, plan_store=None):
    from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
    from fitness.adapters.extraction.rule_based import RuleBasedExtractor
    kb = StaticFoodKnowledgeBase()
    extractor = RuleBasedExtractor(kb)
    repo = InMemoryMealRepository()
    log_meal = LogMealUseCase(extractor=extractor, meal_repo=repo, clock=clock, food_kb=kb)
    from fitness.application.use_cases.query import QueryUseCase
    query = QueryUseCase(meal_repo=repo, clock=clock)
    manage_cal = ManageCalendarUseCase(plan_store=plan_store, clock=clock) if plan_store else None
    return HandleMessageUseCase(
        log_meal=log_meal, query=query,
        meal_repo=repo, clock=clock,
        profile_store=profile_store,
        manage_calendar=manage_cal,
    )


class TestSetTargets:
    def test_set_calorie_target(self, clock, profile_store):
        handler = _build_handler(clock, profile_store=profile_store)
        result = handler.handle("set my calorie target to 2500")
        assert result.status == LogStatus.LOGGED
        assert "2500" in result.message
        profile = profile_store.load()
        assert profile.calorie_target == 2500

    def test_set_protein_target(self, clock, profile_store):
        handler = _build_handler(clock, profile_store=profile_store)
        result = handler.handle("set protein target to 180")
        assert "180" in result.message
        profile = profile_store.load()
        assert profile.protein_target_g == 180

    def test_set_all_targets(self, clock, profile_store):
        handler = _build_handler(clock, profile_store=profile_store)
        result = handler.handle("set my targets to 2500 calories, 180g protein, 300g carbs, 80g fat")
        assert "2500" in result.message
        profile = profile_store.load()
        assert profile.calorie_target == 2500
        assert profile.protein_target_g == 180
        assert profile.carbs_target_g == 300
        assert profile.fat_target_g == 80


class TestUnitToggle:
    def test_switch_to_metric(self, clock, profile_store):
        profile = profile_store.load()
        profile.unit_system = "imperial"
        profile_store.save(profile)
        handler = _build_handler(clock, profile_store=profile_store)
        result = handler.handle("switch to metric")
        assert "metric" in result.message
        assert profile_store.load().unit_system == "metric"

    def test_switch_to_imperial(self, clock, profile_store):
        handler = _build_handler(clock, profile_store=profile_store)
        result = handler.handle("use imperial")
        assert "imperial" in result.message
        assert profile_store.load().unit_system == "imperial"


class TestAlignCalendar:
    def test_align_to_day(self, clock, plan_store):
        uc = ManageCalendarUseCase(plan_store=plan_store, clock=clock)
        uc.activate_plan("ppl")
        handler = _build_handler(clock, plan_store=plan_store)
        result = handler.handle("align to Legs")
        assert result.status == LogStatus.LOGGED
        assert "Legs" in result.message

    def test_align_unknown_day(self, clock, plan_store):
        uc = ManageCalendarUseCase(plan_store=plan_store, clock=clock)
        uc.activate_plan("ppl")
        handler = _build_handler(clock, plan_store=plan_store)
        result = handler.handle("align to Arms")
        assert "Couldn't find" in result.message

    def test_align_no_calendar(self, clock, plan_store):
        handler = _build_handler(clock, plan_store=plan_store)
        result = handler.handle("align to Push")
        assert "No active calendar" in result.message


class TestIntentRouting:
    def test_calorie_target_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("set my calorie target to 2500") is Intent.EDIT

    def test_protein_target_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("set protein target to 180") is Intent.EDIT

    def test_switch_metric_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("switch to metric") is Intent.EDIT

    def test_use_imperial_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("use imperial") is Intent.EDIT

    def test_align_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("align to Push") is Intent.EDIT
