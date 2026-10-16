"""Integration tests for the JSON repository against a real temp directory.

The headline test is ``test_edit_is_actually_persisted_to_disk`` — the regression guard
for the prior system's bug, where an edit was *narrated* but never written. Here we mutate,
save, then read back through a brand-new repository instance to prove the bytes on disk
actually changed.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from fitness.adapters.persistence.json_repository import JsonMealRepository
from fitness.domain.value_objects import MealTimeSlot

from _factories import make_food, make_meal


@pytest.fixture
def repo(tmp_path):
    return JsonMealRepository(tmp_path)


class TestRoundTrip:
    def test_save_then_get(self, repo):
        meal = make_meal()
        repo.save(meal)
        loaded = repo.get(meal.id)
        assert loaded == meal  # frozen dataclasses compare by value

    def test_get_unknown_returns_none(self, repo):
        assert repo.get("nope") is None

    def test_upsert_replaces_not_duplicates(self, repo):
        meal = make_meal(foods=(make_food(name="egg", calories=72),))
        repo.save(meal)
        updated = meal.add_food(make_food(name="rice", calories=205))
        repo.save(updated)  # same id
        day_meals = repo.list_by_date(meal.logged_at.date())
        assert len(day_meals) == 1
        assert len(day_meals[0].foods) == 2


class TestListing:
    def test_list_by_date_filters_to_that_day(self, repo):
        repo.save(make_meal(meal_id="a", logged_at=datetime(2026, 6, 4, 8, 0)))
        repo.save(make_meal(meal_id="b", logged_at=datetime(2026, 6, 5, 8, 0)))
        june4 = repo.list_by_date(date(2026, 6, 4))
        assert [m.id for m in june4] == ["a"]

    def test_list_between_is_inclusive(self, repo):
        for d in (3, 4, 5, 6):
            repo.save(make_meal(meal_id=f"m{d}", logged_at=datetime(2026, 6, d, 8, 0)))
        result = repo.list_between(date(2026, 6, 4), date(2026, 6, 5))
        assert {m.id for m in result} == {"m4", "m5"}


class TestDelete:
    def test_delete_removes_and_returns_true(self, repo):
        meal = make_meal()
        repo.save(meal)
        assert repo.delete(meal.id) is True
        assert repo.get(meal.id) is None

    def test_delete_unknown_returns_false(self, repo):
        assert repo.delete("ghost") is False

    def test_deleting_last_meal_removes_day_file(self, repo, tmp_path):
        meal = make_meal()
        repo.save(meal)
        day_file = tmp_path / "meals" / f"{meal.logged_at.date().isoformat()}.json"
        assert day_file.exists()
        repo.delete(meal.id)
        assert not day_file.exists()


class TestPersistenceIsReal:
    """These guard the 'narrated but never saved' failure mode directly."""

    def test_save_writes_parseable_json_to_disk(self, repo, tmp_path):
        meal = make_meal()
        repo.save(meal)
        day_file = tmp_path / "meals" / f"{meal.logged_at.date().isoformat()}.json"
        on_disk = json.loads(day_file.read_text(encoding="utf-8"))
        assert on_disk[0]["id"] == meal.id
        assert on_disk[0]["foods"][0]["name"] == meal.foods[0].name

    def test_edit_is_actually_persisted_to_disk(self, tmp_path):
        # Log a breakfast, then "move it to lunch" and save. A *fresh* repository reading
        # the same directory must see lunch — proving the change hit disk, not just memory.
        writer = JsonMealRepository(tmp_path)
        meal = make_meal(meal_time=MealTimeSlot.BREAKFAST)
        writer.save(meal)

        writer.save(meal.with_meal_time(MealTimeSlot.LUNCH))

        reader = JsonMealRepository(tmp_path)
        reloaded = reader.get(meal.id)
        assert reloaded is not None
        assert reloaded.meal_time is MealTimeSlot.LUNCH
        assert all(f.meal_time is MealTimeSlot.LUNCH for f in reloaded.foods)


class TestExerciseAggregation:
    """Logging the same exercise twice in a day merges rather than duplicating."""

    def _repo(self, tmp_path):
        from fitness.adapters.persistence.json_exercise_repository import JsonExerciseRepository
        return JsonExerciseRepository(tmp_path)

    def _ex(self, name="Bench Press", sets=(), duration=None, day=None):
        from datetime import date as _date
        from fitness.domain.exercise import Exercise, ExerciseType, SetDetail
        return Exercise(
            name=name,
            exercise_type=ExerciseType.STRENGTH,
            day=day or _date(2026, 8, 7),
            set_details=tuple(SetDetail(reps=r, weight=w) for r, w in sets),
            duration_min=duration,
        )

    def test_same_name_merges_into_one_record(self, tmp_path):
        from datetime import date as _date
        repo = self._repo(tmp_path)
        repo.save(self._ex(sets=((10, 185.0),) * 3))
        repo.save(self._ex(sets=((8, 195.0),) * 2))

        stored = repo.list_by_date(_date(2026, 8, 7))
        assert len(stored) == 1
        assert stored[0].sets == 5

    def test_merge_preserves_distinct_weight_groups(self, tmp_path):
        from datetime import date as _date
        repo = self._repo(tmp_path)
        repo.save(self._ex(sets=((10, 185.0),) * 3))
        repo.save(self._ex(sets=((8, 195.0),) * 2))

        groups = repo.list_by_date(_date(2026, 8, 7))[0].grouped_sets()
        assert [(g["count"], g["reps"], g["weight"]) for g in groups] == [
            (3, 10, 185.0),
            (2, 8, 195.0),
        ]

    def test_merge_is_case_and_spacing_insensitive(self, tmp_path):
        from datetime import date as _date
        repo = self._repo(tmp_path)
        repo.save(self._ex(name="Bench Press", sets=((10, 185.0),)))
        repo.save(self._ex(name="bench   press", sets=((10, 185.0),)))
        assert len(repo.list_by_date(_date(2026, 8, 7))) == 1

    def test_different_names_stay_separate(self, tmp_path):
        from datetime import date as _date
        repo = self._repo(tmp_path)
        repo.save(self._ex(name="Bench Press", sets=((10, 185.0),)))
        repo.save(self._ex(name="Squat", sets=((5, 225.0),)))
        assert len(repo.list_by_date(_date(2026, 8, 7))) == 2

    def test_different_days_stay_separate(self, tmp_path):
        from datetime import date as _date
        repo = self._repo(tmp_path)
        repo.save(self._ex(sets=((10, 185.0),), day=_date(2026, 8, 7)))
        repo.save(self._ex(sets=((10, 185.0),), day=_date(2026, 8, 8)))
        assert len(repo.list_by_date(_date(2026, 8, 7))) == 1
        assert len(repo.list_by_date(_date(2026, 8, 8))) == 1

    def test_durations_sum(self, tmp_path):
        from datetime import date as _date
        repo = self._repo(tmp_path)
        repo.save(self._ex(name="Run", duration=20))
        repo.save(self._ex(name="Run", duration=30))
        assert repo.list_by_date(_date(2026, 8, 7))[0].duration_min == 50

    def test_delete_after_merge_removes_everything(self, tmp_path):
        """The old duplicate records made delete/edit behave inconsistently."""
        from datetime import date as _date
        repo = self._repo(tmp_path)
        repo.save(self._ex(sets=((10, 185.0),)))
        repo.save(self._ex(sets=((10, 185.0),)))
        assert repo.delete_by_name(_date(2026, 8, 7), "Bench Press") is True
        assert repo.list_by_date(_date(2026, 8, 7)) == []

    def test_recent_names_dedupes(self, tmp_path):
        repo = self._repo(tmp_path)
        repo.save(self._ex(sets=((10, 185.0),)))
        repo.save(self._ex(sets=((8, 195.0),)))
        names = [n for n, _ in repo.recent_names()]
        assert names.count("Bench Press") == 1
