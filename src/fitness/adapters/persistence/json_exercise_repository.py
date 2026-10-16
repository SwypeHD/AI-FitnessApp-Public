"""JSON file implementation of ``ExerciseRepository``.

Same day-partitioned, atomic-write pattern as JsonMealRepository.
Files live under ``<data_dir>/exercises/YYYY-MM-DD.json``.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from fitness.domain.exercise import Exercise, ExerciseType, SetDetail
from fitness.domain.naming import normalize_food_name


class JsonExerciseRepository:
    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir) / "exercises"
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, exercise: Exercise) -> None:
        """Upsert by name: logging the same exercise twice in a day merges the sets.

        One record per (day, normalized name) is an invariant ``replace_by_name`` and
        ``delete_by_name`` already assume — they match on name, so duplicates made
        editing hit only the first and deleting remove all of them.
        """
        records = self._load_day(exercise.day)
        target = normalize_food_name(exercise.name)
        for i, r in enumerate(records):
            if normalize_food_name(r["name"]) == target:
                records[i] = _to_dict(_from_dict(r).merged_with(exercise))
                self._write_day(exercise.day, records)
                return
        records.append(_to_dict(exercise))
        self._write_day(exercise.day, records)

    def list_by_date(self, day: date) -> list[Exercise]:
        return [_from_dict(r) for r in self._load_day(day)]

    def replace_by_name(self, day: date, name: str, new_exercise: Exercise) -> bool:
        target = normalize_food_name(name)
        records = self._load_day(day)
        for i, r in enumerate(records):
            if normalize_food_name(r["name"]) == target:
                records[i] = _to_dict(new_exercise)
                self._write_day(day, records)
                return True
        return False

    def delete_by_name(self, day: date, name: str) -> bool:
        target = normalize_food_name(name)
        records = self._load_day(day)
        kept = [r for r in records if normalize_food_name(r["name"]) != target]
        if len(kept) == len(records):
            return False
        self._write_day(day, kept)
        return True

    def recent_names(self, limit: int = 50) -> list[tuple[str, str]]:
        """Distinct (name, exercise_type) pairs from stored days, most recent first.

        Powers autocomplete: exercises the user actually does should outrank the
        generic catalog.
        """
        seen: dict[str, tuple[str, str]] = {}   # normalized key -> (display name, type)
        # Filenames are ISO dates, so reverse lexicographic == newest first.
        for path in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    records = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue  # a corrupt day shouldn't break autocomplete
            for r in records:
                name = (r.get("name") or "").strip()
                if not name:
                    continue
                key = normalize_food_name(name)
                if key not in seen:
                    seen[key] = (name, r.get("exercise_type") or "other")
                    if len(seen) >= limit:
                        return list(seen.values())
        return list(seen.values())

    def _day_path(self, day: date) -> Path:
        return self._dir / f"{day.isoformat()}.json"

    def _load_day(self, day: date) -> list[dict[str, Any]]:
        path = self._day_path(day)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write_day(self, day: date, records: list[dict[str, Any]]) -> None:
        path = self._day_path(day)
        if records:
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(records, fh, indent=2)
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        elif path.exists():
            path.unlink()


def _to_dict(e: Exercise) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": e.name,
        "exercise_type": e.exercise_type.value,
        "day": e.day.isoformat(),
        "duration_min": e.duration_min,
    }
    if e.set_details:
        d["set_details"] = [
            {"reps": s.reps, "weight": s.weight} for s in e.set_details
        ]
    return d


def _from_dict(d: dict[str, Any]) -> Exercise:
    set_details: tuple[SetDetail, ...] = ()
    if "set_details" in d:
        set_details = tuple(
            SetDetail(reps=s["reps"], weight=s.get("weight"))
            for s in d["set_details"]
        )
    elif d.get("sets") and d.get("reps"):
        set_details = tuple(
            SetDetail(reps=d["reps"]) for _ in range(d["sets"])
        )
    return Exercise(
        name=d["name"],
        exercise_type=ExerciseType(d["exercise_type"]),
        day=date.fromisoformat(d["day"]),
        set_details=set_details,
        duration_min=d.get("duration_min"),
    )
