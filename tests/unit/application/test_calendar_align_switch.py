"""Calendar alignment and plan switching.

Covers two reported bugs: aligning did nothing visible once today was completed,
and switching plans discarded work already logged today.
"""

from __future__ import annotations

import tempfile
from datetime import date

import pytest

from fitness.adapters.persistence.json_plan_store import JsonPlanStore
from fitness.application.use_cases.manage_calendar import ManageCalendarUseCase

TODAY = "2026-08-08"


class FixedClock:
    def today(self) -> date:
        return date(2026, 8, 8)


@pytest.fixture
def mc():
    return ManageCalendarUseCase(
        plan_store=JsonPlanStore(tempfile.mkdtemp()), clock=FixedClock()
    )


def entry(view, day=TODAY):
    return next(e for e in view["entries"] if e["date"] == day)


def labels(view, count=4):
    upcoming = sorted(
        (e for e in view["entries"] if e["date"] >= TODAY), key=lambda e: e["date"]
    )
    return [e["label"] for e in upcoming[:count]]


class TestAlign:
    def test_aligns_today_when_planned(self, mc):
        mc.activate_plan("ppl")
        mc.align(1)
        assert entry(mc.get_calendar())["label"] == "Pull"

    def test_completed_today_keeps_its_label(self, mc):
        """A finished day is history: realign around it, don't relabel it."""
        mc.activate_plan("ppl")
        mc.complete_day()
        mc.align(1)
        today = entry(mc.get_calendar())
        assert today["label"] == "Push"
        assert today["status"] == "completed"

    def test_skipped_today_keeps_its_label(self, mc):
        mc.activate_plan("ppl")
        mc.skip_day()
        mc.align(2)
        assert entry(mc.get_calendar())["label"] == "Push"

    def test_future_realigns_around_a_completed_today(self, mc):
        """Aligning to Pull means tomorrow is Legs, even though today stays Push."""
        mc.activate_plan("ppl")
        mc.complete_day()
        mc.align(1)
        assert labels(mc.get_calendar(), 3) == ["Push", "Legs", "Rest"]

    def test_rotation_continues_from_the_aligned_day(self, mc):
        mc.activate_plan("ppl")
        mc.align(1)
        assert labels(mc.get_calendar(), 3) == ["Pull", "Legs", "Rest"]

    def test_align_is_idempotent(self, mc):
        mc.activate_plan("ppl")
        mc.align(1)
        first = labels(mc.get_calendar())
        mc.align(1)
        assert labels(mc.get_calendar()) == first


class TestPlanSwitch:
    def test_keeps_todays_completion(self, mc):
        mc.activate_plan("ppl")
        mc.complete_day()
        mc.activate_plan("upper_lower")
        today = entry(mc.get_calendar())
        assert today["status"] == "completed"
        assert today["label"] == "Push"          # labelled under the plan it was done in

    def test_keeps_todays_skip(self, mc):
        mc.activate_plan("ppl")
        mc.skip_day()
        mc.activate_plan("upper_lower")
        assert entry(mc.get_calendar())["status"] == "skipped"

    def test_does_not_duplicate_today(self, mc):
        mc.activate_plan("ppl")
        mc.complete_day()
        mc.activate_plan("upper_lower")
        dates = [e["date"] for e in mc.get_calendar()["entries"]]
        assert dates.count(TODAY) == 1

    def test_future_follows_the_new_plan(self, mc):
        mc.activate_plan("ppl")
        mc.complete_day()
        mc.activate_plan("upper_lower")
        assert labels(mc.get_calendar(), 3)[1:] == ["Upper", "Lower"]

    def test_unstarted_today_is_replaced(self, mc):
        """Nothing logged today means there's nothing to preserve."""
        mc.activate_plan("ppl")
        mc.activate_plan("upper_lower")
        today = entry(mc.get_calendar())
        assert today["status"] == "planned"
        assert today["label"] == "Upper"

    def test_past_completions_still_preserved(self, mc):
        mc.activate_plan("ppl")
        mc.complete_day()
        mc.activate_plan("upper_lower")
        mc.activate_plan("ppl")
        assert entry(mc.get_calendar())["status"] == "completed"
