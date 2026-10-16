"""EditExerciseUseCase — deterministic mutation of logged exercises.

Supports:
- UPDATE sets/reps/weight ("change bench press to 4 sets of 10 at 185")
- ADD a set ("add a set to bench press")
- REMOVE a set ("remove last set of squats")
"""

from __future__ import annotations

import re

from fitness.application.ports.clock import Clock
from fitness.application.ports.repositories import ExerciseRepository
from fitness.domain.exercise import Exercise, SetDetail
from fitness.domain.naming import normalize_food_name


class EditExerciseResult:
    def __init__(self, success: bool, message: str) -> None:
        self.success = success
        self.message = message


_UPDATE_RE = re.compile(
    r"\b(?:change|update|set|make|edit)\b\s+(?:the\s+|my\s+)?(.+?)\s+to\s+"
    r"(\d+)\s*(?:sets?\s*(?:of\s*)?)?(\d+)?\s*(?:reps?)?(?:\s*(?:at|@|x)\s*(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?)?",
    re.I,
)

_SET_WEIGHT_RE = re.compile(
    r"\b(?:change|update|set)\b\s+(?:the\s+|my\s+)?(.+?)\s+weight\s+to\s+(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?",
    re.I,
)

_SET_REPS_RE = re.compile(
    r"\b(?:change|update|set)\b\s+(?:the\s+|my\s+)?(.+?)\s+reps?\s+to\s+(\d+)",
    re.I,
)

_SET_SETS_RE = re.compile(
    r"\b(?:change|update|set)\b\s+(?:the\s+|my\s+)?(.+?)\s+(?:to\s+)?(\d+)\s+sets?",
    re.I,
)

_ADD_SET_RE = re.compile(
    r"\badd\b\s+(?:a\s+)?set\s+(?:to\s+)?(?:the\s+|my\s+)?(.+)",
    re.I,
)

_REMOVE_SET_RE = re.compile(
    r"\b(?:remove|delete)\b\s+(?:a\s+|last\s+)?set\s+(?:from\s+|of\s+)?(?:the\s+|my\s+)?(.+)",
    re.I,
)

_CORRECTION_RE = re.compile(
    r"\b(?:actually|used)\b.*?(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?"
    r".*\b(?:on|for|bench|squat|deadlift|curl|press|row|pullup|push\s*up|lunge)",
    re.I,
)

_EXERCISE_NAMES_RE = re.compile(
    r"\b(bench\s*press|bench|squat|deadlift|curl|overhead\s*press|press|"
    r"barbell\s*row|row|pullup|pull\s*up|pushup|push\s*up|lunge|plank|"
    r"lat\s*pulldown|face\s*pull|dip|fly|flye|raise|extension|shrug)\b",
    re.I,
)


class EditExerciseUseCase:
    def __init__(self, exercise_repo: ExerciseRepository, clock: Clock) -> None:
        self._repo = exercise_repo
        self._clock = clock

    def handle(self, text: str) -> EditExerciseResult:
        add = _ADD_SET_RE.search(text)
        if add:
            return self._add_set(add.group(1).strip())

        remove = _REMOVE_SET_RE.search(text)
        if remove:
            return self._remove_set(remove.group(1).strip())

        weight = _SET_WEIGHT_RE.search(text)
        if weight:
            return self._update_field(weight.group(1).strip(), weight_val=float(weight.group(2)))

        reps = _SET_REPS_RE.search(text)
        if reps:
            return self._update_field(reps.group(1).strip(), reps_val=int(reps.group(2)))

        update = _UPDATE_RE.search(text)
        if update:
            name = update.group(1).strip()
            num1 = int(update.group(2))
            reps_val = int(update.group(3)) if update.group(3) else None
            weight_val = float(update.group(4)) if update.group(4) else None
            if reps_val is None:
                after = text[update.end(2):].strip()
                if re.match(r"\s*sets?\b", after, re.I):
                    return self._update_field(name, sets_val=num1)
                return self._update_field(name, reps_val=num1)
            return self._update_field(name, sets_val=num1, reps_val=reps_val, weight_val=weight_val)

        correction = _CORRECTION_RE.search(text)
        if correction:
            new_weight = float(correction.group(1))
            ex_match = _EXERCISE_NAMES_RE.search(text)
            if ex_match:
                return self._update_field(ex_match.group(1).strip(), weight_val=new_weight)

        return EditExerciseResult(
            False,
            "I didn't understand that exercise edit. Try:\n"
            "• 'change bench press to 4 sets of 10 at 185'\n"
            "• 'set squat weight to 225'\n"
            "• 'add a set to bench press'\n"
            "• 'remove last set of squats'",
        )

    def _find_exercise(self, name: str) -> Exercise | None:
        target = normalize_food_name(name)
        day = self._clock.today()
        exercises = self._repo.list_by_date(day)
        for ex in exercises:
            if normalize_food_name(ex.name) == target:
                return ex
        return None

    def _update_field(
        self,
        name: str,
        sets_val: int | None = None,
        reps_val: int | None = None,
        weight_val: float | None = None,
    ) -> EditExerciseResult:
        ex = self._find_exercise(name)
        if ex is None:
            return EditExerciseResult(False, f"Couldn't find '{name}' in today's exercises.")

        old_details = ex.set_details or ()
        if sets_val is not None:
            base_reps = reps_val or (old_details[0].reps if old_details else 10)
            base_weight = weight_val if weight_val is not None else (old_details[0].weight if old_details else None)
            new_details = tuple(SetDetail(reps=base_reps, weight=base_weight) for _ in range(sets_val))
        elif reps_val is not None or weight_val is not None:
            new_details = tuple(
                SetDetail(
                    reps=reps_val if reps_val is not None else s.reps,
                    weight=weight_val if weight_val is not None else s.weight,
                )
                for s in old_details
            ) if old_details else (
                SetDetail(reps=reps_val or 10, weight=weight_val),
            )
        else:
            new_details = old_details

        new_ex = Exercise(
            name=ex.name,
            exercise_type=ex.exercise_type,
            day=ex.day,
            set_details=new_details,
            duration_min=ex.duration_min,
        )
        self._repo.replace_by_name(ex.day, ex.name, new_ex)
        return EditExerciseResult(True, f"Updated {ex.name}: {new_ex.format_sets()}.")

    def _add_set(self, name: str) -> EditExerciseResult:
        ex = self._find_exercise(name)
        if ex is None:
            return EditExerciseResult(False, f"Couldn't find '{name}' in today's exercises.")
        if not ex.set_details:
            return EditExerciseResult(False, f"{ex.name} has no sets to duplicate.")
        last = ex.set_details[-1]
        new_details = ex.set_details + (SetDetail(reps=last.reps, weight=last.weight),)
        new_ex = Exercise(
            name=ex.name, exercise_type=ex.exercise_type, day=ex.day,
            set_details=new_details, duration_min=ex.duration_min,
        )
        self._repo.replace_by_name(ex.day, ex.name, new_ex)
        return EditExerciseResult(True, f"Added a set to {ex.name}: {new_ex.format_sets()}.")

    def _remove_set(self, name: str) -> EditExerciseResult:
        ex = self._find_exercise(name)
        if ex is None:
            return EditExerciseResult(False, f"Couldn't find '{name}' in today's exercises.")
        if not ex.set_details or len(ex.set_details) <= 1:
            return EditExerciseResult(False, f"{ex.name} only has {len(ex.set_details or ())} set(s) — can't remove.")
        new_details = ex.set_details[:-1]
        new_ex = Exercise(
            name=ex.name, exercise_type=ex.exercise_type, day=ex.day,
            set_details=new_details, duration_min=ex.duration_min,
        )
        self._repo.replace_by_name(ex.day, ex.name, new_ex)
        return EditExerciseResult(True, f"Removed a set from {ex.name}: {new_ex.format_sets()}.")
