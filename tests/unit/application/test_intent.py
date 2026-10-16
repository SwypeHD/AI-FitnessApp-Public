"""Tests for the deterministic intent router.

The key property: QUERY and EDIT are recognized and NOT misrouted to LOG, even when
their text contains food-adjacent words ("log", "lunch", "had").
"""

import pytest

from fitness.application.intent import classify_intent
from fitness.application.ports.extraction import Intent


@pytest.mark.parametrize(
    "text, expected",
    [
        # QUERY — asking about logged data
        ("show me my log", Intent.QUERY),
        ("what did I eat today", Intent.QUERY),
        ("how much protein so far", Intent.QUERY),
        ("how many calories today", Intent.QUERY),
        ("show me today's meals", Intent.QUERY),
        ("total calories today", Intent.QUERY),
        ("what have I had today", Intent.QUERY),
        ("list my food", Intent.QUERY),

        # EDIT — mutating a log
        ("delete the chicken", Intent.EDIT),
        ("remove my breakfast", Intent.EDIT),
        ("move chicken to lunch", Intent.EDIT),
        ("undo that", Intent.EDIT),

        # CALENDAR — workout calendar management
        ("skip today", Intent.CALENDAR),
        ("skip today's workout", Intent.CALENDAR),
        ("push back today", Intent.CALENDAR),
        ("push back today's workout", Intent.CALENDAR),
        ("mark today complete", Intent.CALENDAR),
        ("I'm done for today", Intent.CALENDAR),
        ("i am finished with today's workout", Intent.CALENDAR),
        ("activate PPL", Intent.CALENDAR),
        ("start push pull legs", Intent.CALENDAR),
        ("skip to today", Intent.CALENDAR),
        ("catch up to today", Intent.CALENDAR),
        ("push back to today", Intent.CALENDAR),
        ("undo skip", Intent.CALENDAR),
        ("undo push back", Intent.CALENDAR),

        # LOG — logging food
        ("I had 3 servings of chicken breast", Intent.LOG),
        ("ate 200g salmon for dinner", Intent.LOG),
        ("2 eggs for breakfast", Intent.LOG),
        ("log 1 cup of rice", Intent.LOG),

        # CHAT — non-food messages (any length, no numbers or LOG signals)
        ("hello", Intent.CHAT),
        ("thanks", Intent.CHAT),
        ("hi there", Intent.CHAT),
        ("what's up with you", Intent.CHAT),
        ("how are you doing today", Intent.CHAT),
        ("tell me about protein bioavailability in plant-based diets", Intent.CHAT),
        ("I'm feeling tired after my workout", Intent.CHAT),
        ("what's a good post-workout snack", Intent.CHAT),
    ],
)
def test_intent_classification(text, expected):
    assert classify_intent(text) is expected


def test_ambiguous_with_number_returns_none():
    # Has a number but no clear LOG verb or unit — genuinely ambiguous.
    result = classify_intent("maybe 300 calories worth of something")
    assert result is None


def test_number_with_food_is_log():
    # Bare "2 eggs" has a number directly followed by a plausible food — LOG.
    assert classify_intent("2 eggs") is Intent.LOG


class TestExerciseQuestionsAreNotLogs:
    """Asking about a lift must not be routed to exercise logging."""

    @pytest.mark.parametrize("text", [
        "should I do overhead press today?",
        "is bench press bad for shoulders",
        "how do I squat properly?",
        "what's a good substitute for deadlift?",
        "can I run on rest days?",
        "why does my shoulder hurt after bench press",
    ])
    def test_questions_do_not_route_to_exercise(self, text):
        assert classify_intent(text) is not Intent.EXERCISE

    @pytest.mark.parametrize("text", [
        "bench press 3 sets of 10 at 185",
        "did 3x10 squats",
        "ran for 30 minutes",
    ])
    def test_actual_logs_still_route_to_exercise(self, text):
        assert classify_intent(text) is Intent.EXERCISE

    def test_question_with_real_set_data_still_logs(self):
        """Trailing '?' shouldn't block a message carrying genuine set data."""
        assert classify_intent("bench 3x10 at 185?") is Intent.EXERCISE


class TestLogQuestionsAreNotCalendarCommands:
    """Asking what was done must not trip the calendar's mark-done command."""

    @pytest.mark.parametrize("text", [
        "what exercises have I done today?",
        "what workouts have I completed today",
        "which exercises did I finish today?",
        "how many workouts have I done today",
    ])
    def test_questions_do_not_route_to_calendar(self, text):
        assert classify_intent(text) is not Intent.CALENDAR

    @pytest.mark.parametrize("text", [
        "mark today done",
        "I'm done with my workout",
        "skip today",
        "push back today",
        "activate push pull legs plan",
    ])
    def test_calendar_commands_still_route_to_calendar(self, text):
        assert classify_intent(text) is Intent.CALENDAR
