from datetime import date, datetime

import pytest

from fitness.application.use_cases.log_exercise import LogExerciseUseCase

from _factories import FixedClock


class InMemoryExerciseRepository:
    def __init__(self):
        self._exercises = []

    def save(self, exercise):
        self._exercises.append(exercise)

    def list_by_date(self, day):
        return [e for e in self._exercises if e.day == day]

    def delete_by_name(self, day, name):
        before = len(self._exercises)
        self._exercises = [e for e in self._exercises if not (e.day == day and e.name == name)]
        return len(self._exercises) < before


@pytest.fixture
def repo():
    return InMemoryExerciseRepository()


@pytest.fixture
def uc(repo):
    return LogExerciseUseCase(exercise_repo=repo, clock=FixedClock(datetime(2026, 6, 10, 12, 0)))


class TestExerciseParsing:
    def test_strength_with_sets_reps_and_weight(self, uc, repo):
        result = uc.handle("I did 3 sets of 10 bench press at 185")
        assert result.success
        assert "Bench Press" in result.message
        exercises = repo.list_by_date(date(2026, 6, 10))
        assert len(exercises) == 1
        assert exercises[0].sets == 3 and exercises[0].reps == 10

    def test_strength_without_weight_asks_for_it(self, uc, repo):
        """A non-bodyweight lift needs a weight before it can be logged."""
        result = uc.handle("I did 3 sets of 10 bench press")
        assert not result.success
        assert "weight" in result.message.lower()
        assert repo.list_by_date(date(2026, 6, 10)) == []

    def test_cardio_with_duration(self, uc, repo):
        result = uc.handle("ran for 30 minutes")
        assert result.success
        assert "30 min" in result.message
        exercises = repo.list_by_date(date(2026, 6, 10))
        assert exercises[0].duration_min == 30

    def test_yoga(self, uc, repo):
        result = uc.handle("20 min yoga")
        assert result.success
        assert "Yoga" in result.message

    def test_unknown_exercise_uses_other_type(self, uc, repo):
        result = uc.handle("I did some jumping jacks")
        assert result.success
        exercises = repo.list_by_date(date(2026, 6, 10))
        assert exercises[0].exercise_type.value == "other"

    def test_empty_text_asks_what(self, uc):
        result = uc.handle("I did something")
        assert result.success or "what exercise" in result.message.lower()

    def test_auto_capitalize(self, uc, repo):
        uc.handle("3 sets of 10 bench press at 185")
        exercises = repo.list_by_date(date(2026, 6, 10))
        assert exercises[0].name == "Bench Press"
