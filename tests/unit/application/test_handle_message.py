"""Tests for HandleMessageUseCase — the intent-routing dispatcher.

Verifies that queries, chat, and edits are recognized and NOT fed to the food extractor.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
from fitness.adapters.extraction.rule_based import RuleBasedExtractor
from fitness.application.dto import LogStatus
from fitness.application.use_cases.edit_log import EditLogUseCase
from fitness.application.use_cases.handle_message import HandleMessageUseCase
from fitness.application.use_cases.log_meal import LogMealUseCase
from fitness.application.use_cases.query import QueryUseCase

from _factories import FixedClock, InMemoryMealRepository, make_meal


@pytest.fixture
def repo():
    return InMemoryMealRepository()


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 4, 12, 0))


@pytest.fixture
def uc(repo, clock):
    kb = StaticFoodKnowledgeBase()
    log_meal = LogMealUseCase(
        extractor=RuleBasedExtractor(kb),
        meal_repo=repo,
        clock=clock,
        food_kb=kb,
    )
    query = QueryUseCase(meal_repo=repo, clock=clock)
    edit_log = EditLogUseCase(meal_repo=repo, clock=clock)
    return HandleMessageUseCase(log_meal=log_meal, query=query, edit_log=edit_log)


class TestQueryRouting:
    def test_show_me_my_log_does_not_extract_food(self, uc, repo):
        result = uc.handle("show me my log")
        assert result.status is LogStatus.LOGGED
        assert "nothing logged" in result.message.lower()

    def test_query_after_logging_shows_totals(self, uc, repo, clock):
        uc.handle("I had 3 servings of chicken breast for lunch")
        result = uc.handle("how much have I had today")
        assert "495" in result.message
        assert result.state is None  # no clarification


class TestChatRouting:
    def test_chat_returns_placeholder(self, uc):
        result = uc.handle("hello")
        assert "food logging" in result.message.lower() or "chat" in result.message.lower()


class TestEditRouting:
    def test_edit_routes_to_edit_handler(self, uc):
        result = uc.handle("delete the chicken")
        # No chicken logged, so it should say "couldn't find"
        assert "couldn't find" in result.message.lower() or "didn't understand" in result.message.lower()


class TestLogStillWorks:
    def test_food_logging_unchanged(self, uc, repo):
        result = uc.handle("I had 2 eggs for breakfast")
        assert result.status is LogStatus.LOGGED
        assert result.meal_id is not None


class TestMidClarification:
    def test_continues_log_flow_when_state_present(self, uc, repo):
        first = uc.handle("I had 3 servings of chicken breast")
        assert first.status is LogStatus.NEEDS_CLARIFICATION
        second = uc.handle("lunch", state=first.state)
        assert second.status is LogStatus.LOGGED
