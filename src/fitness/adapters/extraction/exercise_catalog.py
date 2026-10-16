"""Static catalog of common exercises, for name autocomplete.

Deliberately separate from ``log_exercise._TYPE_KEYWORDS``: that table exists for
*parsing* and so contains abbreviations ("ohp"), inflections ("squat"/"squats"), and
bare fragments ("press", "row") that would be noise in a picker. This holds canonical
display names only — one entry per exercise, title-cased for the UI.
"""

from __future__ import annotations

from fitness.domain.exercise import ExerciseType

# (canonical name, type, muscle group)
_CATALOG: tuple[tuple[str, ExerciseType, str], ...] = (
    # --- Chest ---
    ("Bench Press", ExerciseType.STRENGTH, "chest"),
    ("Incline Bench Press", ExerciseType.STRENGTH, "chest"),
    ("Decline Bench Press", ExerciseType.STRENGTH, "chest"),
    ("Dumbbell Bench Press", ExerciseType.STRENGTH, "chest"),
    ("Chest Fly", ExerciseType.STRENGTH, "chest"),
    ("Cable Crossover", ExerciseType.STRENGTH, "chest"),
    ("Push-Up", ExerciseType.STRENGTH, "chest"),
    ("Dip", ExerciseType.STRENGTH, "chest"),
    # --- Back ---
    ("Deadlift", ExerciseType.STRENGTH, "back"),
    ("Romanian Deadlift", ExerciseType.STRENGTH, "back"),
    ("Sumo Deadlift", ExerciseType.STRENGTH, "back"),
    ("Barbell Row", ExerciseType.STRENGTH, "back"),
    ("Bent Over Row", ExerciseType.STRENGTH, "back"),
    ("Dumbbell Row", ExerciseType.STRENGTH, "back"),
    ("Cable Row", ExerciseType.STRENGTH, "back"),
    ("Lat Pulldown", ExerciseType.STRENGTH, "back"),
    ("Pull-Up", ExerciseType.STRENGTH, "back"),
    ("Chin-Up", ExerciseType.STRENGTH, "back"),
    ("Face Pull", ExerciseType.STRENGTH, "back"),
    ("Shrug", ExerciseType.STRENGTH, "back"),
    ("Back Extension", ExerciseType.STRENGTH, "back"),
    # --- Legs ---
    ("Squat", ExerciseType.STRENGTH, "legs"),
    ("Front Squat", ExerciseType.STRENGTH, "legs"),
    ("Goblet Squat", ExerciseType.STRENGTH, "legs"),
    ("Leg Press", ExerciseType.STRENGTH, "legs"),
    ("Lunge", ExerciseType.STRENGTH, "legs"),
    ("Bulgarian Split Squat", ExerciseType.STRENGTH, "legs"),
    ("Leg Extension", ExerciseType.STRENGTH, "legs"),
    ("Leg Curl", ExerciseType.STRENGTH, "legs"),
    ("Calf Raise", ExerciseType.STRENGTH, "legs"),
    ("Hip Thrust", ExerciseType.STRENGTH, "legs"),
    ("Glute Bridge", ExerciseType.STRENGTH, "legs"),
    ("Step-Up", ExerciseType.STRENGTH, "legs"),
    # --- Shoulders ---
    ("Overhead Press", ExerciseType.STRENGTH, "shoulders"),
    ("Shoulder Press", ExerciseType.STRENGTH, "shoulders"),
    ("Arnold Press", ExerciseType.STRENGTH, "shoulders"),
    ("Lateral Raise", ExerciseType.STRENGTH, "shoulders"),
    ("Front Raise", ExerciseType.STRENGTH, "shoulders"),
    ("Rear Delt Fly", ExerciseType.STRENGTH, "shoulders"),
    ("Upright Row", ExerciseType.STRENGTH, "shoulders"),
    # --- Arms ---
    ("Bicep Curl", ExerciseType.STRENGTH, "arms"),
    ("Hammer Curl", ExerciseType.STRENGTH, "arms"),
    ("Preacher Curl", ExerciseType.STRENGTH, "arms"),
    ("Concentration Curl", ExerciseType.STRENGTH, "arms"),
    ("Tricep Extension", ExerciseType.STRENGTH, "arms"),
    ("Skull Crusher", ExerciseType.STRENGTH, "arms"),
    ("Tricep Pushdown", ExerciseType.STRENGTH, "arms"),
    ("Close Grip Bench Press", ExerciseType.STRENGTH, "arms"),
    ("Wrist Curl", ExerciseType.STRENGTH, "arms"),
    # --- Core ---
    ("Plank", ExerciseType.STRENGTH, "core"),
    ("Side Plank", ExerciseType.STRENGTH, "core"),
    ("Crunch", ExerciseType.STRENGTH, "core"),
    ("Sit-Up", ExerciseType.STRENGTH, "core"),
    ("Leg Raise", ExerciseType.STRENGTH, "core"),
    ("Russian Twist", ExerciseType.STRENGTH, "core"),
    ("Hanging Knee Raise", ExerciseType.STRENGTH, "core"),
    ("Ab Wheel Rollout", ExerciseType.STRENGTH, "core"),
    ("Mountain Climber", ExerciseType.STRENGTH, "core"),
    # --- Cardio ---
    ("Run", ExerciseType.CARDIO, "cardio"),
    ("Treadmill Run", ExerciseType.CARDIO, "cardio"),
    ("Walk", ExerciseType.CARDIO, "cardio"),
    ("Cycling", ExerciseType.CARDIO, "cardio"),
    ("Stationary Bike", ExerciseType.CARDIO, "cardio"),
    ("Swim", ExerciseType.CARDIO, "cardio"),
    ("Rowing Machine", ExerciseType.CARDIO, "cardio"),
    ("Elliptical", ExerciseType.CARDIO, "cardio"),
    ("Stairmaster", ExerciseType.CARDIO, "cardio"),
    ("Jump Rope", ExerciseType.CARDIO, "cardio"),
    ("HIIT", ExerciseType.CARDIO, "cardio"),
    ("Hike", ExerciseType.CARDIO, "cardio"),
    # --- Mobility ---
    ("Yoga", ExerciseType.MOBILITY, "mobility"),
    ("Stretching", ExerciseType.MOBILITY, "mobility"),
    ("Foam Rolling", ExerciseType.MOBILITY, "mobility"),
    ("Dynamic Warm-Up", ExerciseType.MOBILITY, "mobility"),
)


class StaticExerciseCatalog:
    """In-memory exercise catalog with substring search."""

    def __init__(self) -> None:
        self._entries = _CATALOG

    def all_entries(self) -> tuple[tuple[str, ExerciseType, str], ...]:
        return self._entries

    def search(self, query: str, limit: int = 20) -> list[dict[str, str]]:
        """Match on name substring, ranking prefix matches above interior ones."""
        q = query.lower().strip()
        prefix: list[dict[str, str]] = []
        contains: list[dict[str, str]] = []

        for name, etype, group in self._entries:
            lowered = name.lower()
            if not q:
                prefix.append(_entry(name, etype, group))
            elif lowered.startswith(q):
                prefix.append(_entry(name, etype, group))
            elif q in lowered:
                contains.append(_entry(name, etype, group))

        return (prefix + contains)[:limit]


def _entry(name: str, etype: ExerciseType, group: str) -> dict[str, str]:
    return {"name": name, "exercise_type": etype.value, "muscle_group": group}
