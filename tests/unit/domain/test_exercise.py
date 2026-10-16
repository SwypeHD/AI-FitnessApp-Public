from datetime import date

import pytest

from fitness.domain.exercise import Exercise, ExerciseType, SetDetail
from fitness.domain.exercise_builder import ExerciseBuilder
from fitness.domain.errors import IncompleteMealError


class TestSetDetail:
    def test_basic(self):
        s = SetDetail(reps=10, weight=135)
        assert s.reps == 10 and s.weight == 135

    def test_no_weight(self):
        s = SetDetail(reps=10)
        assert s.weight is None

    def test_invalid_reps(self):
        with pytest.raises(ValueError):
            SetDetail(reps=0)

    def test_negative_weight(self):
        with pytest.raises(ValueError):
            SetDetail(reps=10, weight=-5)


class TestExercise:
    def test_auto_capitalize(self):
        ex = Exercise(name="bench press", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10))
        assert ex.name == "Bench Press"

    def test_sets_property(self):
        ex = Exercise(
            name="squat", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10),
            set_details=(SetDetail(10), SetDetail(8), SetDetail(6)),
        )
        assert ex.sets == 3
        assert ex.reps == 10

    def test_format_sets_with_weight_varying(self):
        ex = Exercise(
            name="bench", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10),
            set_details=(SetDetail(10, 135), SetDetail(8, 155), SetDetail(6, 175)),
        )
        assert ex.format_sets() == "135 x 10 reps, 155 x 8 reps, 175 x 6 reps"

    def test_format_sets_with_weight_repeated(self):
        ex = Exercise(
            name="bench", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10),
            set_details=(SetDetail(8, 185), SetDetail(8, 185), SetDetail(8, 185)),
        )
        assert ex.format_sets() == "3 sets of 185 x 8 reps"

    def test_format_sets_without_weight_uniform(self):
        ex = Exercise(
            name="pushups", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10),
            set_details=(SetDetail(20), SetDetail(20), SetDetail(20)),
        )
        assert ex.format_sets() == "3x20"

    def test_format_sets_without_weight_varying(self):
        ex = Exercise(
            name="pushups", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10),
            set_details=(SetDetail(20), SetDetail(15), SetDetail(10)),
        )
        assert ex.format_sets() == "20 reps, 15 reps, 10 reps"

    def test_grouped_sets(self):
        ex = Exercise(
            name="bench", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10),
            set_details=(SetDetail(10, 135), SetDetail(10, 135), SetDetail(8, 155)),
        )
        groups = ex.grouped_sets()
        assert len(groups) == 2
        assert groups[0] == {"count": 2, "reps": 10, "weight": 135}
        assert groups[1] == {"count": 1, "reps": 8, "weight": 155}

    def test_empty_set_details(self):
        ex = Exercise(name="yoga", exercise_type=ExerciseType.MOBILITY, day=date(2026, 6, 10))
        assert ex.sets is None
        assert ex.reps is None
        assert ex.format_sets() == ""


class TestExerciseBuilder:
    def test_complete_build_with_legacy_sets_reps(self):
        b = ExerciseBuilder(name="bench press", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10))
        b.sets = 3
        b.reps = 10
        ex = b.build()
        assert ex.name == "Bench Press"
        assert ex.sets == 3 and ex.reps == 10
        assert len(ex.set_details) == 3

    def test_build_with_set_details(self):
        b = ExerciseBuilder(name="squat", exercise_type=ExerciseType.STRENGTH, day=date(2026, 6, 10))
        b.set_details = [SetDetail(10, 135), SetDetail(8, 155)]
        ex = b.build()
        assert len(ex.set_details) == 2
        assert ex.set_details[0].weight == 135

    def test_missing_name_raises(self):
        b = ExerciseBuilder(exercise_type=ExerciseType.CARDIO, day=date(2026, 6, 10))
        with pytest.raises(IncompleteMealError):
            b.build()

    def test_optional_fields_can_be_none(self):
        b = ExerciseBuilder(name="yoga", exercise_type=ExerciseType.MOBILITY, day=date(2026, 6, 10))
        ex = b.build()
        assert ex.sets is None
        assert ex.duration_min is None
