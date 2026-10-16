"""AI chat plan builder — create and modify workout plans via natural language.

Supports:
- Creating plans from known templates (PPL, upper/lower, bro split, full body)
- Creating custom plans from comma-separated day labels
- Adding, removing, and renaming days in the most recently created custom plan
"""

from __future__ import annotations

import re
import uuid

from fitness.adapters.persistence.json_plan_store import JsonPlanStore
from fitness.application.use_cases.manage_calendar import ManageCalendarUseCase
from fitness.domain.workout_plan import PlanDay, PlannedExercise, WorkoutPlan


def _ex(name: str, sets: int, reps: int) -> PlannedExercise:
    return PlannedExercise(name=name, exercise_type="strength", sets=sets, reps=reps)


_DAY_EXERCISE_TEMPLATES: dict[str, list[PlannedExercise]] = {
    "push": [
        _ex("Bench Press", 4, 8), _ex("Overhead Press", 3, 10),
        _ex("Incline Dumbbell Press", 3, 12), _ex("Lateral Raises", 3, 15),
        _ex("Tricep Pushdowns", 3, 12),
    ],
    "pull": [
        _ex("Deadlift", 3, 5), _ex("Barbell Rows", 4, 8),
        _ex("Lat Pulldowns", 3, 10), _ex("Face Pulls", 3, 15),
        _ex("Barbell Curls", 3, 12),
    ],
    "legs": [
        _ex("Squat", 4, 8), _ex("Romanian Deadlift", 3, 10),
        _ex("Leg Press", 3, 12), _ex("Leg Curls", 3, 12),
        _ex("Calf Raises", 4, 15),
    ],
    "chest": [
        _ex("Bench Press", 4, 8), _ex("Incline Dumbbell Press", 3, 10),
        _ex("Cable Flyes", 3, 12), _ex("Dips", 3, 10),
    ],
    "back": [
        _ex("Deadlift", 3, 5), _ex("Barbell Rows", 4, 8),
        _ex("Lat Pulldowns", 3, 10), _ex("Face Pulls", 3, 15),
    ],
    "shoulders": [
        _ex("Overhead Press", 4, 8), _ex("Lateral Raises", 3, 15),
        _ex("Face Pulls", 3, 15), _ex("Rear Delt Flyes", 3, 12),
    ],
    "arms": [
        _ex("Barbell Curls", 3, 12), _ex("Tricep Pushdowns", 3, 12),
        _ex("Hammer Curls", 3, 12), _ex("Overhead Tricep Extension", 3, 12),
    ],
    "upper": [
        _ex("Bench Press", 4, 8), _ex("Overhead Press", 3, 10),
        _ex("Barbell Rows", 4, 8), _ex("Lat Pulldowns", 3, 10),
        _ex("Barbell Curls", 3, 12), _ex("Tricep Pushdowns", 3, 12),
    ],
    "lower": [
        _ex("Squat", 4, 8), _ex("Romanian Deadlift", 3, 10),
        _ex("Leg Press", 3, 12), _ex("Leg Curls", 3, 12),
        _ex("Calf Raises", 4, 15),
    ],
    "full body": [
        _ex("Squat", 3, 8), _ex("Bench Press", 3, 8),
        _ex("Deadlift", 3, 5), _ex("Overhead Press", 3, 10),
        _ex("Barbell Rows", 3, 8),
    ],
    "rest": [],
}

# Aliases: map common synonyms to canonical template keys.
_DAY_ALIASES: dict[str, str] = {
    "chest and triceps": "push",
    "back and biceps": "pull",
    "leg": "legs",
    "shoulder": "shoulders",
    "arm": "arms",
}

# Known split aliases that map to preset plan IDs.
_SPLIT_ALIASES: dict[str, str] = {
    "ppl": "ppl",
    "push pull legs": "ppl",
    "push/pull/legs": "ppl",
    "pushpulllegs": "ppl",
    "upper lower": "upper_lower",
    "upper/lower": "upper_lower",
    "upperlower": "upper_lower",
    "ppl no rest": "ppl_no_rest",
}


class BuildPlanResult:
    def __init__(self, success: bool, message: str, plan: WorkoutPlan | None = None):
        self.success = success
        self.message = message
        self.plan = plan


# Regex patterns for plan builder intents.
_CREATE_RE = re.compile(
    r"\b(?:create|make|build|generate|design)\b"
    r".*\b(?:plan|split|routine|program|schedule)\b",
    re.I,
)
_CREATE_WITH_RE = re.compile(
    r"\b(?:create|make|build)\b\s+.*?\bwith\s+(.+)",
    re.I,
)
_CREATE_NDAY_RE = re.compile(
    r"\b(\d)\s*[-\s]?\s*day\b",
    re.I,
)
_ADD_DAY_RE = re.compile(
    r"\badd\b\s+(?:a\s+)?(.+?)\s+(?:day\s+)?(?:after\s+(\w+)\s+)?(?:to\s+(?:my\s+)?(?:\w+\s+)?(?:plan|routine|split|program))",
    re.I,
)
_ADD_DAY_AFTER_RE = re.compile(
    r"\badd\b\s+(?:a\s+)?(.+?)\s+(?:day\s+)?after\s+(\w+)",
    re.I,
)
_REMOVE_DAY_RE = re.compile(
    r"\b(?:remove|delete)\b\s+(?:the\s+)?(?:(first|second|third|last|\d+)\w*\s+)?(.+?)\s*(?:\bday\b)?\s*(?:from\s+(?:my\s+)?(?:plan|routine|split))?$",
    re.I,
)
_RENAME_DAY_RE = re.compile(
    r"\brename\b\s+(?:the\s+)?(.+?)\s+(?:day\s+)?(?:to|as)\s+(.+?)(?:\s+day)?$",
    re.I,
)

_ORDINALS = {"first": 1, "second": 2, "third": 3, "last": -1}


class BuildPlanUseCase:
    def __init__(self, plan_store: JsonPlanStore, manage_calendar: ManageCalendarUseCase) -> None:
        self._store = plan_store
        self._manage_calendar = manage_calendar

    def handle(self, text: str) -> BuildPlanResult | None:
        """Try to handle the text as a plan builder action. Returns None if not matched."""
        for handler in (self._rename_day, self._add_day, self._remove_day, self._create_plan):
            result = handler(text)
            if result is not None:
                return result
        return None

    def _create_plan(self, text: str) -> BuildPlanResult | None:
        if not _CREATE_RE.search(text):
            return None

        lower = text.lower()

        # Try parsing "with push, pull, legs, rest, ..." syntax first (most explicit).
        with_match = _CREATE_WITH_RE.search(text)
        if with_match:
            days_text = with_match.group(1)
            days = self._parse_day_list(days_text)
            if days:
                return self._build_custom_plan(days, text)

        # Try parsing N-day + split keyword (e.g. "4-day upper/lower").
        n_match = _CREATE_NDAY_RE.search(text)
        if n_match:
            n = int(n_match.group(1))
            days = self._infer_days_for_count(n, lower)
            if days:
                return self._build_custom_plan(days, text)

        # Check for known split aliases (e.g. "PPL plan", "upper lower split").
        for alias, plan_id in _SPLIT_ALIASES.items():
            if alias in lower:
                from fitness.domain.preset_plans import PRESET_PLANS
                preset = PRESET_PLANS.get(plan_id)
                if preset is not None:
                    new_id = uuid.uuid4().hex[:8]
                    plan = WorkoutPlan(
                        id=new_id, name=preset.name, rotation=preset.rotation,
                    )
                    self._store.save_plan(plan)
                    day_labels = ", ".join(d.label for d in plan.rotation)
                    return BuildPlanResult(
                        success=True,
                        message=f"Created plan \"{plan.name}\" ({len(plan.rotation)} days: {day_labels}). "
                                f"Say \"activate {plan.name}\" to start using it.",
                        plan=plan,
                    )

        # Last resort: look for comma-separated day labels anywhere.
        days = self._parse_day_list(lower)
        if days:
            return self._build_custom_plan(days, text)

        return BuildPlanResult(
            success=False,
            message="I couldn't figure out what days to include. "
                    "Try something like \"create a plan with push, pull, legs, rest\" "
                    "or \"make a PPL plan\".",
        )

    def _parse_day_list(self, text: str) -> list[str]:
        """Extract day labels from comma/and-separated text."""
        # Clean up common filler words.
        cleaned = re.sub(r"\b(?:and|then|followed\s+by|day)\b", ",", text, flags=re.I)
        cleaned = re.sub(r"\b(?:create|make|build|generate|me|a|my|plan|split|routine|program|schedule|with)\b",
                         "", cleaned, flags=re.I)
        parts = [p.strip().strip(",").strip() for p in cleaned.split(",")]
        parts = [p for p in parts if p]

        days = []
        for part in parts:
            label = part.lower().strip()
            if not label:
                continue
            # Check aliases.
            canonical = _DAY_ALIASES.get(label, label)
            if canonical in _DAY_EXERCISE_TEMPLATES:
                days.append(canonical)
            elif label:
                # Accept unknown labels as custom days with no exercises.
                days.append(label)
        return days

    def _infer_days_for_count(self, n: int, text: str) -> list[str]:
        """Infer day labels based on a day count and split description."""
        if "upper" in text and "lower" in text:
            if n == 4:
                return ["upper", "lower", "upper", "lower"]
            if n == 6:
                return ["upper", "lower", "upper", "lower", "upper", "lower"]
            return ["upper", "lower"] * (n // 2) + (["upper"] if n % 2 else [])

        if "push" in text or "pull" in text or "ppl" in text:
            if n == 3:
                return ["push", "pull", "legs"]
            if n == 6:
                return ["push", "pull", "legs", "push", "pull", "legs"]

        if "full body" in text or "full-body" in text:
            return ["full body"] * n

        if "bro" in text:
            bro = ["chest", "back", "shoulders", "arms", "legs"]
            return bro[:n]

        return []

    def _build_custom_plan(self, day_labels: list[str], original_text: str) -> BuildPlanResult:
        """Build a plan from a list of day labels."""
        rotation = []
        for label in day_labels:
            canonical = _DAY_ALIASES.get(label, label)
            is_rest = canonical == "rest"
            exercises = _DAY_EXERCISE_TEMPLATES.get(canonical, [])
            display_label = label.title()
            rotation.append(PlanDay(
                label=display_label,
                is_rest=is_rest,
                exercises=tuple(exercises),
            ))

        plan_name = self._generate_plan_name(day_labels)
        plan_id = uuid.uuid4().hex[:8]
        plan = WorkoutPlan(id=plan_id, name=plan_name, rotation=tuple(rotation))
        self._store.save_plan(plan)
        day_summary = ", ".join(d.label for d in plan.rotation)
        return BuildPlanResult(
            success=True,
            message=f"Created plan \"{plan.name}\" ({len(plan.rotation)} days: {day_summary}). "
                    f"Say \"activate {plan.name}\" to start using it.",
            plan=plan,
        )

    def _generate_plan_name(self, day_labels: list[str]) -> str:
        """Generate a sensible plan name from day labels."""
        unique = []
        for label in day_labels:
            if label not in unique:
                unique.append(label)
        if unique == ["push", "pull", "legs"]:
            return "Push Pull Legs"
        if unique == ["upper", "lower"]:
            return "Upper Lower"
        if unique == ["full body"]:
            return "Full Body"
        if set(unique) <= {"chest", "back", "shoulders", "arms", "legs"}:
            return "Bro Split"
        return " / ".join(l.title() for l in unique)

    def _add_day(self, text: str) -> BuildPlanResult | None:
        match = _ADD_DAY_RE.search(text)
        if not match:
            match = _ADD_DAY_AFTER_RE.search(text)
        if not match:
            return None

        new_label = match.group(1).strip().lower()
        after_label = match.group(2).strip().lower() if match.lastindex >= 2 and match.group(2) else None

        # Find the most recent custom plan.
        plan = self._find_latest_custom_plan()
        if plan is None:
            return BuildPlanResult(
                success=False,
                message="No custom plan found to modify. Create one first!",
            )

        canonical = _DAY_ALIASES.get(new_label, new_label)
        is_rest = canonical == "rest"
        exercises = _DAY_EXERCISE_TEMPLATES.get(canonical, [])
        new_day = PlanDay(
            label=new_label.title(),
            is_rest=is_rest,
            exercises=tuple(exercises),
        )

        rotation = list(plan.rotation)
        if after_label:
            after_norm = after_label.strip().lower()
            insert_idx = None
            for i, d in enumerate(rotation):
                if d.label.lower() == after_norm:
                    insert_idx = i + 1
            if insert_idx is not None:
                rotation.insert(insert_idx, new_day)
            else:
                rotation.append(new_day)
        else:
            rotation.append(new_day)

        updated = WorkoutPlan(id=plan.id, name=plan.name, rotation=tuple(rotation))
        self._store.save_plan(updated)
        day_summary = ", ".join(d.label for d in updated.rotation)
        return BuildPlanResult(
            success=True,
            message=f"Added {new_day.label} day to \"{updated.name}\". "
                    f"Now {len(updated.rotation)} days: {day_summary}.",
            plan=updated,
        )

    def _remove_day(self, text: str) -> BuildPlanResult | None:
        match = _REMOVE_DAY_RE.search(text)
        if not match:
            return None

        ordinal_str = match.group(1)
        target_label = match.group(2).strip().lower()

        plan = self._find_latest_custom_plan()
        if plan is None:
            return BuildPlanResult(
                success=False,
                message="No custom plan found to modify. Create one first!",
            )

        rotation = list(plan.rotation)

        # Find matching days by label.
        target_norm = _DAY_ALIASES.get(target_label, target_label)
        matches = [(i, d) for i, d in enumerate(rotation) if d.label.lower() == target_norm or d.label.lower() == target_label]

        if not matches:
            # Try "day N" syntax.
            day_num_match = re.search(r"day\s*(\d+)", text, re.I)
            if day_num_match:
                idx = int(day_num_match.group(1)) - 1
                if 0 <= idx < len(rotation):
                    removed = rotation.pop(idx)
                    updated = WorkoutPlan(id=plan.id, name=plan.name, rotation=tuple(rotation))
                    self._store.save_plan(updated)
                    day_summary = ", ".join(d.label for d in updated.rotation)
                    return BuildPlanResult(
                        success=True,
                        message=f"Removed {removed.label} (day {idx + 1}) from \"{updated.name}\". "
                                f"Now {len(updated.rotation)} days: {day_summary}.",
                        plan=updated,
                    )
            return BuildPlanResult(
                success=False,
                message=f"Couldn't find a '{target_label}' day in your plan.",
            )

        # Determine which occurrence to remove.
        if ordinal_str:
            ordinal_str_lower = ordinal_str.lower()
            if ordinal_str_lower in _ORDINALS:
                which = _ORDINALS[ordinal_str_lower]
            else:
                try:
                    which = int(ordinal_str)
                except ValueError:
                    which = 1
        else:
            which = 1 if len(matches) == 1 else 1

        if which == -1:
            remove_idx = matches[-1][0]
        elif 1 <= which <= len(matches):
            remove_idx = matches[which - 1][0]
        else:
            remove_idx = matches[0][0]

        removed = rotation.pop(remove_idx)
        updated = WorkoutPlan(id=plan.id, name=plan.name, rotation=tuple(rotation))
        self._store.save_plan(updated)
        day_summary = ", ".join(d.label for d in updated.rotation)
        return BuildPlanResult(
            success=True,
            message=f"Removed {removed.label} day from \"{updated.name}\". "
                    f"Now {len(updated.rotation)} days: {day_summary}.",
            plan=updated,
        )

    def _rename_day(self, text: str) -> BuildPlanResult | None:
        match = _RENAME_DAY_RE.search(text)
        if not match:
            return None

        old_label = match.group(1).strip().lower()
        new_label = match.group(2).strip()

        plan = self._find_latest_custom_plan()
        if plan is None:
            return BuildPlanResult(
                success=False,
                message="No custom plan found to modify. Create one first!",
            )

        rotation = list(plan.rotation)
        new_display = new_label.title() if new_label.islower() else new_label
        renamed = False
        for i, d in enumerate(rotation):
            if d.label.lower() == old_label:
                # Determine if the new label implies rest or exercises.
                new_canonical = _DAY_ALIASES.get(new_label.lower(), new_label.lower())
                is_rest = new_canonical == "rest"
                new_exercises = d.exercises
                if new_canonical in _DAY_EXERCISE_TEMPLATES and not d.exercises:
                    new_exercises = tuple(_DAY_EXERCISE_TEMPLATES[new_canonical])
                rotation[i] = PlanDay(
                    label=new_display,
                    is_rest=is_rest,
                    exercises=new_exercises,
                )
                renamed = True
                break

        if not renamed:
            return BuildPlanResult(
                success=False,
                message=f"Couldn't find a '{old_label}' day in your plan.",
            )

        updated = WorkoutPlan(id=plan.id, name=plan.name, rotation=tuple(rotation))
        self._store.save_plan(updated)
        day_summary = ", ".join(d.label for d in updated.rotation)
        return BuildPlanResult(
            success=True,
            message=f"Renamed {old_label.title()} to {new_display} in \"{updated.name}\". "
                    f"Days: {day_summary}.",
            plan=updated,
        )

    def _find_latest_custom_plan(self) -> WorkoutPlan | None:
        """Find the most recently saved custom plan (non-preset)."""
        from fitness.domain.preset_plans import PRESET_PLANS
        plans = self._store.list_plans()
        custom = [p for p in plans if p.id not in PRESET_PLANS]
        return custom[-1] if custom else None
