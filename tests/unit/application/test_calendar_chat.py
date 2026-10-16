"""Tests for AI chat calendar management (skip, complete, push back, activate, undo)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from fitness.adapters.persistence.json_plan_store import JsonPlanStore
from fitness.application.use_cases.manage_calendar import ManageCalendarUseCase

from _factories import FixedClock


@pytest.fixture
def tmp_store(tmp_path):
    return JsonPlanStore(tmp_path)


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 22, 10, 0))


@pytest.fixture
def uc(tmp_store, clock):
    return ManageCalendarUseCase(plan_store=tmp_store, clock=clock)


def _activate(uc):
    cal = uc.activate_plan("ppl")
    assert cal is not None
    return cal


class TestSkipDay:
    def test_skip_marks_today_as_skipped(self, uc):
        _activate(uc)
        result = uc.skip_day()
        assert result is not None
        today_entry = next(e for e in result["entries"] if e["is_today"])
        assert today_entry["status"] == "skipped"

    def test_skip_no_calendar(self, uc):
        assert uc.skip_day() is None


class TestPushBack:
    def test_push_back_shifts_rotation(self, uc):
        _activate(uc)
        cal_before = uc.get_calendar()
        today_label_before = next(e for e in cal_before["entries"] if e["is_today"])["label"]
        result = uc.push_back()
        assert result is not None
        today_entry = next(e for e in result["entries"] if e["is_today"])
        assert today_entry["status"] == "skipped"

    def test_push_back_no_calendar(self, uc):
        assert uc.push_back() is None


class TestCompleteDay:
    def test_complete_marks_today(self, uc):
        _activate(uc)
        result = uc.complete_day()
        assert result is not None
        today_entry = next(e for e in result["entries"] if e["is_today"])
        assert today_entry["status"] == "completed"


class TestUndo:
    def test_undo_skip(self, uc):
        _activate(uc)
        cal_before = uc.get_calendar()
        uc.skip_day()
        result = uc.undo()
        assert result is not None
        today_entry = next(e for e in result["entries"] if e["is_today"])
        assert today_entry["status"] == "planned"

    def test_undo_push_back(self, uc):
        _activate(uc)
        uc.push_back()
        result = uc.undo()
        assert result is not None
        today_entry = next(e for e in result["entries"] if e["is_today"])
        assert today_entry["status"] == "planned"

    def test_undo_nothing(self, uc):
        assert uc.undo() is None


class TestSkipToToday:
    def test_skip_to_today_skips_missed_days(self, tmp_store, tmp_path):
        """Activate a plan 3 days ago, then skip-to-today should mark those as skipped."""
        three_days_ago = FixedClock(datetime(2026, 6, 19, 10, 0))
        uc_old = ManageCalendarUseCase(plan_store=tmp_store, clock=three_days_ago)
        _activate(uc_old)

        today_clock = FixedClock(datetime(2026, 6, 22, 10, 0))
        uc_now = ManageCalendarUseCase(plan_store=tmp_store, clock=today_clock)
        result = uc_now.skip_to_today()
        assert result is not None
        view, count = result
        assert count == 3

    def test_skip_to_today_no_missed(self, uc):
        _activate(uc)
        result = uc.skip_to_today()
        view, count = result
        assert count == 0

    def test_skip_to_today_no_calendar(self, uc):
        assert uc.skip_to_today() is None


class TestPushBackToToday:
    def test_push_back_to_today_shifts_missed(self, tmp_store):
        three_days_ago = FixedClock(datetime(2026, 6, 19, 10, 0))
        uc_old = ManageCalendarUseCase(plan_store=tmp_store, clock=three_days_ago)
        _activate(uc_old)

        today_clock = FixedClock(datetime(2026, 6, 22, 10, 0))
        uc_now = ManageCalendarUseCase(plan_store=tmp_store, clock=today_clock)
        result = uc_now.push_back_to_today()
        assert result is not None
        view, count = result
        assert count == 3

    def test_push_back_to_today_no_missed(self, uc):
        _activate(uc)
        result = uc.push_back_to_today()
        view, count = result
        assert count == 0

    def test_push_back_to_today_no_calendar(self, uc):
        assert uc.push_back_to_today() is None


class TestChatIntentRouting:
    """Verify calendar phrases route to CALENDAR intent."""

    def test_skip_today(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("skip today") is Intent.CALENDAR

    def test_push_back(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("push back today's workout") is Intent.CALENDAR

    def test_mark_complete(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("mark today complete") is Intent.CALENDAR

    def test_im_done(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("I'm done for today") is Intent.CALENDAR

    def test_activate(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("activate push pull legs") is Intent.CALENDAR

    def test_catch_up(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("catch up to today") is Intent.CALENDAR

    def test_undo_calendar(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("undo skip") is Intent.CALENDAR
