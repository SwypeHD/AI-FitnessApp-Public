"""JSON file persistence for saved meal templates."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fitness.domain.saved_meal import SavedMeal


class JsonSavedMealStore:
    """Stores saved meals as a JSON array in a single file."""

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._data_dir / "saved_meals.json"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write_all(self, records: list[dict]) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(self._data_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            os.replace(tmp, self._path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_meals(self) -> list[SavedMeal]:
        return [SavedMeal.from_dict(r) for r in self._load_all()]

    def get_meal(self, meal_id: str) -> SavedMeal | None:
        for record in self._load_all():
            if record["id"] == meal_id:
                return SavedMeal.from_dict(record)
        return None

    def save_meal(self, meal: SavedMeal) -> None:
        """Insert or update a saved meal (matched by id)."""
        records = self._load_all()
        for idx, record in enumerate(records):
            if record["id"] == meal.id:
                records[idx] = meal.to_dict()
                self._write_all(records)
                return
        records.append(meal.to_dict())
        self._write_all(records)

    def delete_meal(self, meal_id: str) -> bool:
        """Remove a saved meal by id. Returns True if it existed."""
        records = self._load_all()
        filtered = [r for r in records if r["id"] != meal_id]
        if len(filtered) == len(records):
            return False
        self._write_all(filtered)
        return True

    def find_by_name(self, name: str) -> SavedMeal | None:
        """Case-insensitive fuzzy match: returns the first meal whose name
        contains *name* or whose name is contained within *name*.
        """
        query = name.lower()
        for record in self._load_all():
            meal_name = record["name"].lower()
            if query in meal_name or meal_name in query:
                return SavedMeal.from_dict(record)
        return None
