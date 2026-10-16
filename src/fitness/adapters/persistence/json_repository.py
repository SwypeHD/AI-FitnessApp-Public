"""JSON file implementation of ``MealRepository``.

Meals are partitioned one file per day (``<data_dir>/meals/YYYY-MM-DD.json``) so reading
a single day is cheap and files stay small. Writes are atomic (temp file + ``os.replace``)
so a crash mid-write can never corrupt an existing day file.

The day a meal belongs to is derived from ``logged_at`` (date component). Single-user dev
use is assumed; cross-process locking (e.g. filelock) is deferred until it's needed.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fitness.domain.meal import Meal

from .schema import meal_from_dict, meal_to_dict


class JsonMealRepository:
    """Implements the ``MealRepository`` port against per-day JSON files."""

    def __init__(self, data_dir: str | Path) -> None:
        self._meals_dir = Path(data_dir) / "meals"
        self._meals_dir.mkdir(parents=True, exist_ok=True)

    # --- MealRepository port ------------------------------------------------

    def save(self, meal: Meal) -> None:
        day = meal.logged_at.date()
        records = self._load_day(day)
        records = [r for r in records if r["id"] != meal.id]  # upsert by id
        records.append(meal_to_dict(meal))
        self._write_day(day, records)

    def get(self, meal_id: str) -> Meal | None:
        for record in self._iter_all_records():
            if record["id"] == meal_id:
                return meal_from_dict(record)
        return None

    def delete(self, meal_id: str) -> bool:
        for day_file in self._day_files():
            records = self._read_file(day_file)
            kept = [r for r in records if r["id"] != meal_id]
            if len(kept) != len(records):
                if kept:
                    self._atomic_write(day_file, kept)
                else:
                    day_file.unlink()  # no meals left for that day
                return True
        return False

    def list_by_date(self, day: date) -> list[Meal]:
        return [meal_from_dict(r) for r in self._load_day(day)]

    def list_between(self, start: date, end: date) -> list[Meal]:
        meals: list[Meal] = []
        for day_file in self._day_files():
            day = _date_from_filename(day_file)
            if day is None or not (start <= day <= end):
                continue
            meals.extend(meal_from_dict(r) for r in self._read_file(day_file))
        return meals

    # --- internals ----------------------------------------------------------

    def _day_path(self, day: date) -> Path:
        return self._meals_dir / f"{day.isoformat()}.json"

    def _day_files(self) -> list[Path]:
        return sorted(self._meals_dir.glob("*.json"))

    def _load_day(self, day: date) -> list[dict[str, Any]]:
        return self._read_file(self._day_path(day))

    def _read_file(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _iter_all_records(self):
        for day_file in self._day_files():
            yield from self._read_file(day_file)

    def _write_day(self, day: date, records: list[dict[str, Any]]) -> None:
        path = self._day_path(day)
        if records:
            self._atomic_write(path, records)
        elif path.exists():
            path.unlink()

    def _atomic_write(self, path: Path, records: list[dict[str, Any]]) -> None:
        # Write to a temp file in the same directory, then atomically replace.
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(records, fh, indent=2)
            os.replace(tmp_name, path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise


def _date_from_filename(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.stem)
    except ValueError:
        return None
