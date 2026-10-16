"""JSON file persistence for workout plans and the active calendar."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fitness.domain.preset_plans import PRESET_PLANS
from fitness.domain.workout_plan import ActiveCalendar, WorkoutPlan


class JsonPlanStore:
    """Stores custom workout plans and the active calendar to JSON files."""

    def __init__(self, data_dir: str | Path) -> None:
        self._plans_dir = Path(data_dir) / "plans"
        self._plans_dir.mkdir(parents=True, exist_ok=True)
        self._calendar_path = Path(data_dir) / "calendar.json"
        self._calendar_undo_path = Path(data_dir) / "calendar_undo.json"

    def list_plans(self) -> list[WorkoutPlan]:
        plans = list(PRESET_PLANS.values())
        for path in sorted(self._plans_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as f:
                plan = WorkoutPlan.from_dict(json.load(f))
                if plan.id not in PRESET_PLANS:
                    plans.append(plan)
        return plans

    def get_plan(self, plan_id: str) -> WorkoutPlan | None:
        if plan_id in PRESET_PLANS:
            return PRESET_PLANS[plan_id]
        path = self._plans_dir / f"{plan_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return WorkoutPlan.from_dict(json.load(f))

    def save_plan(self, plan: WorkoutPlan) -> None:
        path = self._plans_dir / f"{plan.id}.json"
        fd, tmp = tempfile.mkstemp(dir=str(self._plans_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(plan.to_dict(), f, indent=2)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def load_calendar(self) -> ActiveCalendar | None:
        if not self._calendar_path.exists():
            return None
        with self._calendar_path.open("r", encoding="utf-8") as f:
            return ActiveCalendar.from_dict(json.load(f))

    def save_calendar(self, calendar: ActiveCalendar) -> None:
        fd, tmp = tempfile.mkstemp(
            dir=str(self._calendar_path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(calendar.to_dict(), f, indent=2)
            os.replace(tmp, self._calendar_path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def save_calendar_snapshot(self) -> None:
        """Copy current calendar.json to calendar_undo.json for undo support."""
        if not self._calendar_path.exists():
            return
        import shutil
        shutil.copy2(self._calendar_path, self._calendar_undo_path)

    def restore_calendar_snapshot(self) -> ActiveCalendar | None:
        """Restore calendar_undo.json to calendar.json and delete the snapshot."""
        if not self._calendar_undo_path.exists():
            return None
        import shutil
        shutil.copy2(self._calendar_undo_path, self._calendar_path)
        self._calendar_undo_path.unlink()
        return self.load_calendar()
