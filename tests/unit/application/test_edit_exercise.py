"""Tests for exercise editing via AI chat."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from fitness.adapters.persistence.json_exercise_repository import JsonExerciseRepository
from fitness.application.use_cases.edit_exercise import EditExerciseUseCase
from fitness.domain.exercise import Exercise, ExerciseType, SetDetail

from _factories import FixedClock


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 22, 10, 0))


@pytest.fixture
def repo(tmp_path):
    return JsonExerciseRepository(tmp_path)


@pytest.fixture
def uc(repo, clock):
    return EditExerciseUseCase(exercise_repo=repo, clock=clock)


def _seed(repo, clock):
    repo.save(Exercise(
        name="Bench Press", exercise_type=ExerciseType.STRENGTH,
        day=clock.today(),
        set_details=(SetDetail(reps=10, weight=135), SetDetail(reps=10, weight=135), SetDetail(reps=10, weight=135)),
    ))
    repo.save(Exercise(
        name="Squat", exercise_type=ExerciseType.STRENGTH,
        day=clock.today(),
        set_details=(SetDetail(reps=8, weight=225), SetDetail(reps=8, weight=225)),
    ))


class TestUpdateExercise:
    def test_change_sets_reps_weight(self, uc, repo, clock):
        _seed(repo, clock)
        result = uc.handle("change bench press to 4 sets of 10 at 185")
        assert result.success
        exercises = repo.list_by_date(clock.today())
        bp = next(e for e in exercises if "Bench" in e.name)
        assert len(bp.set_details) == 4
        assert bp.set_details[0].reps == 10
        assert bp.set_details[0].weight == 185

    def test_change_weight_only(self, uc, repo, clock):
        _seed(repo, clock)
        result = uc.handle("set bench press weight to 225")
        assert result.success
        exercises = repo.list_by_date(clock.today())
        bp = next(e for e in exercises if "Bench" in e.name)
        assert all(s.weight == 225 for s in bp.set_details)
        assert len(bp.set_details) == 3

    def test_change_reps_only(self, uc, repo, clock):
        _seed(repo, clock)
        result = uc.handle("change squat reps to 12")
        assert result.success
        exercises = repo.list_by_date(clock.today())
        sq = next(e for e in exercises if "Squat" in e.name)
        assert all(s.reps == 12 for s in sq.set_details)

    def test_change_sets_count(self, uc, repo, clock):
        _seed(repo, clock)
        result = uc.handle("set squat to 5 sets")
        assert result.success
        exercises = repo.list_by_date(clock.today())
        sq = next(e for e in exercises if "Squat" in e.name)
        assert len(sq.set_details) == 5

    def test_unknown_exercise_fails(self, uc, repo, clock):
        _seed(repo, clock)
        result = uc.handle("change overhead press to 3 sets of 10")
        assert not result.success


class TestAddRemoveSet:
    def test_add_set(self, uc, repo, clock):
        _seed(repo, clock)
        result = uc.handle("add a set to bench press")
        assert result.success
        exercises = repo.list_by_date(clock.today())
        bp = next(e for e in exercises if "Bench" in e.name)
        assert len(bp.set_details) == 4

    def test_remove_set(self, uc, repo, clock):
        _seed(repo, clock)
        result = uc.handle("remove last set of bench press")
        assert result.success
        exercises = repo.list_by_date(clock.today())
        bp = next(e for e in exercises if "Bench" in e.name)
        assert len(bp.set_details) == 2

    def test_remove_set_minimum(self, uc, repo, clock):
        """Can't remove the last remaining set."""
        repo.save(Exercise(
            name="Curl", exercise_type=ExerciseType.STRENGTH,
            day=clock.today(),
            set_details=(SetDetail(reps=10),),
        ))
        result = uc.handle("remove set from curl")
        assert not result.success

    def test_add_set_unknown_exercise(self, uc, repo, clock):
        _seed(repo, clock)
        result = uc.handle("add a set to overhead press")
        assert not result.success


class TestIntentRouting:
    def test_add_set_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("add a set to bench press") is Intent.EDIT

    def test_remove_set_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("remove last set of squats") is Intent.EDIT

    def test_change_exercise_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("change bench press to 4 sets of 10 at 185") is Intent.EDIT

    def test_set_weight_routes_to_edit(self):
        from fitness.application.intent import classify_intent
        from fitness.application.ports.extraction import Intent
        assert classify_intent("set squat weight to 315") is Intent.EDIT
