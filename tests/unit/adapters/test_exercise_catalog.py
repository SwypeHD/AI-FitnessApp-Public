"""Tests for the static exercise catalog used by name autocomplete."""

from __future__ import annotations

from fitness.adapters.extraction.exercise_catalog import StaticExerciseCatalog
from fitness.domain.exercise import ExerciseType


def _names(results):
    return [r["name"] for r in results]


class TestSearch:
    def setup_method(self):
        self.cat = StaticExerciseCatalog()

    def test_empty_query_returns_entries(self):
        assert len(self.cat.search("")) == 20

    def test_respects_limit(self):
        assert len(self.cat.search("", limit=5)) == 5

    def test_prefix_match_ranks_before_interior_match(self):
        names = _names(self.cat.search("bench"))
        assert names[0] == "Bench Press"
        # "Close Grip Bench Press" only contains the query, so it must come later.
        assert names.index("Bench Press") < names.index("Close Grip Bench Press")

    def test_case_insensitive(self):
        assert _names(self.cat.search("BENCH PRESS")) == _names(self.cat.search("bench press"))

    def test_no_match_returns_empty(self):
        assert self.cat.search("zzzznotanexercise") == []

    def test_entries_carry_type_and_group(self):
        run = next(r for r in self.cat.search("run") if r["name"] == "Run")
        assert run["exercise_type"] == ExerciseType.CARDIO.value
        assert run["muscle_group"] == "cardio"

    def test_yoga_is_mobility(self):
        yoga = next(r for r in self.cat.search("yoga") if r["name"] == "Yoga")
        assert yoga["exercise_type"] == ExerciseType.MOBILITY.value

    def test_names_are_unique(self):
        names = [n for n, _, _ in self.cat.all_entries()]
        assert len(names) == len(set(names))

    def test_no_parser_style_noise(self):
        """The catalog is for display, so it must not carry abbreviations or fragments."""
        names = {n.lower() for n, _, _ in self.cat.all_entries()}
        for junk in ("ohp", "rdl", "press", "row", "curl", "squats", "fly"):
            assert junk not in names
