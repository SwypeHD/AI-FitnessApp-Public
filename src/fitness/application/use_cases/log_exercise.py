"""LogExerciseUseCase — parse and persist an exercise from natural language.

Handles patterns like:
  "3 sets of 10 bench press at 185"
  "4 sets of 15 reps of bench press, 2 sets at 165 lb and 2 at 175"
  "bench 3x10 @ 135"
  "ran for 30 minutes"
  "20 min yoga"

Returns a clarification prompt when minimum required info is missing:
  - strength → needs sets + reps + weight
  - cardio   → needs duration
"""

from __future__ import annotations

import re

from fitness.application.dto import PendingExerciseState
from fitness.application.ports.clock import Clock
from fitness.application.ports.repositories import ExerciseRepository
from fitness.domain.exercise import ExerciseType, SetDetail
from fitness.domain.exercise_builder import ExerciseBuilder

# "3 sets of 10 at 185" / "3x10 @ 185" / "3 sets of 10 reps at 185 lbs"
_SET_GROUP_RE = re.compile(
    r"(\d+)\s*(?:sets?\s*(?:of\s*)?)"
    r"(\d+)\s*(?:reps?)?"
    r"(?:\s*(?:at|@|x)\s*(?:about|around|like|~)?\s*(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?)?"
    r"|"
    r"(\d+)\s*x\s*(\d+)"
    r"(?:\s*(?:at|@)\s*(?:about|around|like|~)?\s*(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?)?",
    re.I,
)

# "2 sets at 165 lb and 2 at 175" — sets with weight but reps implied from context
_SETS_AT_WEIGHT_RE = re.compile(
    r"(\d+)\s*(?:sets?\s*)?(?:\bat\b|@)\s*(?:about|around|like|~)?\s*(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?",
    re.I,
)

# Standalone weight: "at 185 lbs" / "@ 225" / "at about 185"
_WEIGHT_RE = re.compile(
    r"(?:\bat\b|@)\s*(?:about|around|like|~)?\s*(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?",
    re.I,
)

# Bare number + optional unit for follow-up answers: "185 lbs", "225", "10 reps"
_BARE_WEIGHT_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)\s*$",
    re.I,
)
_BARE_REPS_RE = re.compile(
    r"^\s*(\d+)\s*(?:reps?)?\s*$",
    re.I,
)
_FOLLOWUP_REPS_WEIGHT_RE = re.compile(
    r"(\d+)\s*(?:reps?)?\s*(?:at|@|x)\s*(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?"
    r"|"
    r"(\d+)\s*reps?\s+(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)",
    re.I,
)

# "10 reps...for 3 sets at 185" — reps-first, sets later
_REPS_FIRST_RE = re.compile(
    r"(\d+)\s*reps?\b.*?(\d+)\s*sets?"
    r"(?:\s*(?:at|@|x)\s*(?:about|around|like|~)?\s*(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?)?",
    re.I,
)

# "4 sets of squats for 8 reps" — exercise name sits between sets and reps
_SETS_NAME_REPS_RE = re.compile(
    r"(\d+)\s*sets?\b.*?(\d+)\s*reps?",
    re.I,
)

# "the weights were 175lb,175lb,185lb,185lb"
_WEIGHTS_LIST_RE = re.compile(
    r"\bweights?\s+(?:were|was|are|is)\s+",
    re.I,
)

# Bare trailing number that looks like a weight: "bench 3x10 185" or "3x10 185lbs"
_TRAILING_WEIGHT_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?\s*$",
    re.I,
)

# "3 sets" / "3 times" without reps — just captures the count
_BARE_SETS_RE = re.compile(
    r"(\d+)\s*(?:sets?|times)(?!\s*(?:of\s*)?\d)",
    re.I,
)

_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:min(?:ute)?s?|hr|hours?)",
    re.I,
)

_TYPE_KEYWORDS: dict[str, ExerciseType] = {
    "bench press": ExerciseType.STRENGTH,
    "bench": ExerciseType.STRENGTH,
    "incline bench": ExerciseType.STRENGTH,
    "decline bench": ExerciseType.STRENGTH,
    "squat": ExerciseType.STRENGTH,
    "squats": ExerciseType.STRENGTH,
    "front squat": ExerciseType.STRENGTH,
    "deadlift": ExerciseType.STRENGTH,
    "sumo deadlift": ExerciseType.STRENGTH,
    "romanian deadlift": ExerciseType.STRENGTH,
    "rdl": ExerciseType.STRENGTH,
    "curl": ExerciseType.STRENGTH,
    "curls": ExerciseType.STRENGTH,
    "bicep curl": ExerciseType.STRENGTH,
    "hammer curl": ExerciseType.STRENGTH,
    "press": ExerciseType.STRENGTH,
    "overhead press": ExerciseType.STRENGTH,
    "ohp": ExerciseType.STRENGTH,
    "shoulder press": ExerciseType.STRENGTH,
    "military press": ExerciseType.STRENGTH,
    "row": ExerciseType.STRENGTH,
    "rows": ExerciseType.STRENGTH,
    "barbell row": ExerciseType.STRENGTH,
    "bent over row": ExerciseType.STRENGTH,
    "cable row": ExerciseType.STRENGTH,
    "pullup": ExerciseType.STRENGTH,
    "pull up": ExerciseType.STRENGTH,
    "pull-up": ExerciseType.STRENGTH,
    "chin up": ExerciseType.STRENGTH,
    "chin-up": ExerciseType.STRENGTH,
    "pushup": ExerciseType.STRENGTH,
    "push up": ExerciseType.STRENGTH,
    "push-up": ExerciseType.STRENGTH,
    "lunge": ExerciseType.STRENGTH,
    "lunges": ExerciseType.STRENGTH,
    "plank": ExerciseType.STRENGTH,
    "dip": ExerciseType.STRENGTH,
    "dips": ExerciseType.STRENGTH,
    "fly": ExerciseType.STRENGTH,
    "flye": ExerciseType.STRENGTH,
    "flyes": ExerciseType.STRENGTH,
    "chest fly": ExerciseType.STRENGTH,
    "shrug": ExerciseType.STRENGTH,
    "shrugs": ExerciseType.STRENGTH,
    "extension": ExerciseType.STRENGTH,
    "extensions": ExerciseType.STRENGTH,
    "tricep extension": ExerciseType.STRENGTH,
    "lat pulldown": ExerciseType.STRENGTH,
    "leg press": ExerciseType.STRENGTH,
    "hip thrust": ExerciseType.STRENGTH,
    "calf raise": ExerciseType.STRENGTH,
    "calf raises": ExerciseType.STRENGTH,
    "lateral raise": ExerciseType.STRENGTH,
    "face pull": ExerciseType.STRENGTH,
    "run": ExerciseType.CARDIO,
    "ran": ExerciseType.CARDIO,
    "running": ExerciseType.CARDIO,
    "jog": ExerciseType.CARDIO,
    "jogging": ExerciseType.CARDIO,
    "cycling": ExerciseType.CARDIO,
    "bike": ExerciseType.CARDIO,
    "biking": ExerciseType.CARDIO,
    "swim": ExerciseType.CARDIO,
    "swimming": ExerciseType.CARDIO,
    "walk": ExerciseType.CARDIO,
    "walking": ExerciseType.CARDIO,
    "hiit": ExerciseType.CARDIO,
    "cardio": ExerciseType.CARDIO,
    "elliptical": ExerciseType.CARDIO,
    "stairmaster": ExerciseType.CARDIO,
    "jump rope": ExerciseType.CARDIO,
    "rowing machine": ExerciseType.CARDIO,
    "yoga": ExerciseType.MOBILITY,
    "stretch": ExerciseType.MOBILITY,
    "stretching": ExerciseType.MOBILITY,
    "mobility": ExerciseType.MOBILITY,
    "foam roll": ExerciseType.MOBILITY,
    "foam rolling": ExerciseType.MOBILITY,
}

_NAME_NORMALIZE: dict[str, str] = {
    "ran": "run",
    "ohp": "overhead press",
    "rdl": "romanian deadlift",
}

_BODYWEIGHT_EXERCISES = frozenset({
    "pushup", "push up", "push-up",
    "pullup", "pull up", "pull-up",
    "chin up", "chin-up",
    "dip", "dips",
    "plank",
    "lunge", "lunges",
    "calf raise", "calf raises",
})

_STOPWORDS = {
    "i", "did", "do", "went", "for", "a", "an", "the", "my", "some", "of",
    "today", "just", "also", "session", "workout", "log", "logged", "record",
    "with", "and", "then", "about", "around",
}


class LogExerciseResult:
    def __init__(
        self,
        success: bool,
        message: str,
        state: PendingExerciseState | None = None,
    ) -> None:
        self.success = success
        self.message = message
        self.state = state


class LogExerciseUseCase:
    def __init__(self, exercise_repo: ExerciseRepository, clock: Clock) -> None:
        self._repo = exercise_repo
        self._clock = clock

    def handle(self, text: str) -> LogExerciseResult:
        builder = ExerciseBuilder(day=self._clock.today())

        duration_match = _DURATION_RE.search(text)
        if duration_match:
            builder.duration_min = float(duration_match.group(1))

        set_details = _parse_sets(text)
        if set_details:
            builder.set_details = list(set_details)
        else:
            bare_sets = _BARE_SETS_RE.search(text)
            if bare_sets:
                builder.sets = int(bare_sets.group(1))

        name, ex_type = _extract_name_and_type(text)
        if name:
            builder.name = name
        if ex_type:
            builder.exercise_type = ex_type

        if not builder.name:
            return LogExerciseResult(False, "What exercise did you do?")
        if not builder.exercise_type:
            builder.exercise_type = ExerciseType.OTHER

        return self._try_finalize(builder)

    def continue_handle(self, text: str, state: PendingExerciseState) -> LogExerciseResult:
        """Handle a follow-up message that fills in missing exercise info."""
        builder = ExerciseBuilder(day=self._clock.today())
        builder.name = state.name
        builder.exercise_type = ExerciseType(state.exercise_type)
        builder.duration_min = state.duration_min

        sets = state.sets
        reps = state.reps
        weight = state.weight

        # Try to parse follow-up for reps + weight: "10 reps at 185" / "10 reps 185lbs"
        m = _FOLLOWUP_REPS_WEIGHT_RE.search(text)
        if m:
            if m.group(1) is not None:
                reps = int(m.group(1))
                weight = float(m.group(2))
            else:
                reps = int(m.group(3))
                weight = float(m.group(4))
            sm = _BARE_SETS_RE.search(text)
            if sm:
                sets = int(sm.group(1))
        else:
            # Try set groups in case they gave full info: "3 sets of 10 at 185"
            new_details = _parse_sets(text)
            if new_details:
                if weight and all(d.weight is None for d in new_details):
                    new_details = [SetDetail(reps=d.reps, weight=weight) for d in new_details]
                builder.set_details = list(new_details)
                return self._try_finalize(builder)

            # Try bare weight: "185 lbs"
            wm = _BARE_WEIGHT_RE.match(text.strip())
            if wm:
                weight = float(wm.group(1))
            else:
                # Try bare reps: "10" or "10 reps"
                rm = _BARE_REPS_RE.match(text.strip())
                if rm:
                    if reps is None:
                        reps = int(rm.group(1))
                    elif weight is None:
                        weight = float(rm.group(1))

            # Try duration for cardio
            dm = _DURATION_RE.search(text)
            if dm:
                builder.duration_min = float(dm.group(1))

            # Try standalone weight
            if weight is None:
                swm = _WEIGHT_RE.search(text)
                if swm:
                    weight = float(swm.group(1))

        if sets and reps:
            builder.set_details = [
                SetDetail(reps=reps, weight=weight) for _ in range(sets)
            ]
        elif reps:
            builder.set_details = [SetDetail(reps=reps, weight=weight)]
        else:
            builder.sets = sets
            builder.reps = reps
            builder._pending_weight = weight

        return self._try_finalize(builder)

    def _try_finalize(self, builder: ExerciseBuilder) -> LogExerciseResult:
        """Try to build and save; re-prompt if still incomplete."""
        clarification = _missing_info(builder)
        if clarification:
            return LogExerciseResult(
                False, clarification, state=_build_pending_state(builder, clarification),
            )

        exercise = builder.build()
        self._repo.save(exercise)

        parts = [f"Logged {exercise.exercise_type.value}: {exercise.name}"]
        if exercise.set_details:
            parts.append(exercise.format_sets())
        if exercise.duration_min:
            parts.append(f"{exercise.duration_min:g} min")
        return LogExerciseResult(True, " — ".join(parts) + ".")


_WEIGHTS_SECTION_RE = re.compile(
    r"\bweights?\s+(?:were|was|are|is)\s+.*",
    re.I,
)


def _extract_weight_list(text: str) -> list[float]:
    """Extract per-set weights from 'weights were 175x2 and 185x2' or '175lb,175lb'."""
    wl = _WEIGHTS_LIST_RE.search(text)
    if not wl:
        return []
    rest = text[wl.end():]
    wx = list(re.finditer(
        r"(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?\s*x\s*(\d+)",
        rest, re.I,
    ))
    if wx:
        weights: list[float] = []
        for m in wx:
            weights.extend([float(m.group(1))] * int(m.group(2)))
        return weights
    return [
        float(m.group(1))
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?|kilos?)?", rest, re.I)
    ]


def _extract_inline_weights(text: str, expected_count: int) -> list[float]:
    """Extract comma/and-separated weights like '135, 155, 175, 185' after set info."""
    m = re.search(
        r",\s*(\d+(?:\.\d+)?(?:\s*(?:lbs?|kg))?(?:\s*[,&]\s*(?:and\s+)?\d+(?:\.\d+)?(?:\s*(?:lbs?|kg))?)+)\s*$",
        text, re.I,
    )
    if not m:
        return []
    nums = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)", m.group(0))]
    if len(nums) == expected_count and all(n >= 5 for n in nums):
        return nums
    return []


def _parse_sets(text: str) -> list[SetDetail]:
    """Extract set details from natural language, handling mixed-weight groups."""
    per_set_weights = _extract_weight_list(text)
    clean = _WEIGHTS_SECTION_RE.sub("", text)

    details: list[SetDetail] = []
    last_set_end = 0

    for m in _SET_GROUP_RE.finditer(clean):
        if m.group(1) is not None:
            sets = int(m.group(1))
            reps = int(m.group(2))
            weight = float(m.group(3)) if m.group(3) else None
        else:
            sets = int(m.group(4))
            reps = int(m.group(5))
            weight = float(m.group(6)) if m.group(6) else None
        details.extend(SetDetail(reps=reps, weight=weight) for _ in range(sets))
        last_set_end = m.end()

    if not per_set_weights and details:
        iw = _extract_inline_weights(clean, len(details))
        if iw:
            per_set_weights = iw

    if details:
        base_reps = details[0].reps
        all_no_weight = all(d.weight is None for d in details)
        if all_no_weight and per_set_weights and len(per_set_weights) == len(details):
            details = [
                SetDetail(reps=d.reps, weight=w)
                for d, w in zip(details, per_set_weights)
            ]
        elif all_no_weight:
            weight_groups = list(_SETS_AT_WEIGHT_RE.finditer(clean))
            if weight_groups:
                total_from_weights = sum(int(wg.group(1)) for wg in weight_groups)
                if total_from_weights == len(details):
                    new_details: list[SetDetail] = []
                    for wg in weight_groups:
                        n = int(wg.group(1))
                        w = float(wg.group(2))
                        new_details.extend(
                            SetDetail(reps=base_reps, weight=w) for _ in range(n)
                        )
                    details = new_details
                else:
                    wm = _WEIGHT_RE.search(clean)
                    if wm:
                        w = float(wm.group(1))
                        details = [SetDetail(reps=d.reps, weight=w) for d in details]
            else:
                wm = _WEIGHT_RE.search(clean)
                if not wm:
                    tw = _TRAILING_WEIGHT_RE.search(clean)
                    if tw and tw.start() >= last_set_end:
                        wm = tw
                if wm:
                    w = float(wm.group(1))
                    details = [SetDetail(reps=d.reps, weight=w) for d in details]
        return details

    # "4 sets of squats, 8 reps each. Weights were 175x2 and 185x2"
    snr = _SETS_NAME_REPS_RE.search(clean)
    if snr:
        sets = int(snr.group(1))
        reps = int(snr.group(2))
        if per_set_weights and len(per_set_weights) == sets:
            return [SetDetail(reps=reps, weight=w) for w in per_set_weights]
        wm = _WEIGHT_RE.search(clean)
        if wm:
            return [SetDetail(reps=reps, weight=float(wm.group(1))) for _ in range(sets)]
        return [SetDetail(reps=reps, weight=None) for _ in range(sets)]

    # Fall back to reps-first format: "10 reps of bench for 3 sets at 185"
    rf = _REPS_FIRST_RE.search(clean)
    if rf:
        reps = int(rf.group(1))
        sets = int(rf.group(2))
        weight = float(rf.group(3)) if rf.group(3) else None
        return [SetDetail(reps=reps, weight=weight) for _ in range(sets)]

    return details


def _missing_info(builder: ExerciseBuilder) -> str | None:
    """Return a clarification prompt if minimum info is missing."""
    etype = builder.exercise_type
    has_sets = bool(builder.set_details) or (builder.sets and builder.reps)

    if etype is ExerciseType.STRENGTH:
        is_bw = builder.name and builder.name.lower() in _BODYWEIGHT_EXERCISES
        if not has_sets and not builder.sets:
            pw = getattr(builder, "_pending_weight", None)
            if pw:
                return (
                    f"Got {builder.name} at {pw:g} lbs. "
                    "How many sets and reps? (e.g. \"3 sets of 10\")"
                )
            if is_bw:
                return (
                    f"How many sets and reps did you do for {builder.name}? "
                    "(e.g. \"3 sets of 10\")"
                )
            return (
                f"How many sets and reps did you do for {builder.name}? "
                "And at what weight? (e.g. \"3 sets of 10 at 185 lbs\")"
            )
        if builder.sets and not has_sets:
            pw = getattr(builder, "_pending_weight", None)
            if pw:
                return (
                    f"Got {builder.sets} sets at {pw:g} lbs for {builder.name}. "
                    "How many reps per set? (e.g. \"10 reps\")"
                )
            return (
                f"Got {builder.sets} sets of {builder.name}. "
                "How many reps per set? (e.g. \"10 reps\")"
            )
        has_weight = any(
            s.weight is not None
            for s in (builder.set_details or [])
        )
        if not has_weight and builder.set_details and not is_bw:
            reps_info = builder.set_details[0].reps
            n_sets = len(builder.set_details)
            return (
                f"Got {n_sets} sets of {reps_info} reps for {builder.name}. "
                "What weight did you use? (e.g. \"185 lbs\")"
            )
    elif etype is ExerciseType.CARDIO:
        if not builder.duration_min and not has_sets:
            return (
                f"How long did you do {builder.name}? "
                "(e.g. \"30 minutes\")"
            )

    return None


def _build_pending_state(builder: ExerciseBuilder, question: str) -> PendingExerciseState:
    return PendingExerciseState(
        name=builder.name,
        exercise_type=builder.exercise_type.value,
        sets=len(builder.set_details) if builder.set_details else builder.sets,
        reps=builder.set_details[0].reps if builder.set_details else builder.reps,
        weight=(
            builder.set_details[0].weight
            if builder.set_details and builder.set_details[0].weight
            else getattr(builder, "_pending_weight", None)
        ),
        duration_min=builder.duration_min,
        question=question,
    )


def _extract_name_and_type(text: str) -> tuple[str | None, ExerciseType | None]:
    lower = text.lower()
    best_kw = None
    best_type = None
    for kw, etype in _TYPE_KEYWORDS.items():
        if kw in lower and (best_kw is None or len(kw) > len(best_kw)):
            best_kw = kw
            best_type = etype

    if best_kw:
        return _NAME_NORMALIZE.get(best_kw, best_kw), best_type

    cleaned = _clean(text)
    if cleaned:
        return cleaned, None
    return None, None


def _clean(text: str) -> str:
    text = _WEIGHTS_SECTION_RE.sub("", text)
    text = _SET_GROUP_RE.sub("", text)
    text = _DURATION_RE.sub("", text)
    text = _WEIGHT_RE.sub("", text)
    tokens = [t for t in re.split(r"\s+", text.strip().lower()) if t and t not in _STOPWORDS]
    return " ".join(tokens).strip()
