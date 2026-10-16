"""Built-in workout plan templates.

These are starting points — the user can customize them or have the AI generate new
ones based on their profile. Each plan defines a 7-day rotation cycle.
"""

from __future__ import annotations

from .workout_plan import PlannedExercise, PlanDay, WorkoutPlan

_S = "strength"


def _ex(name: str, sets: int, reps: int, typ: str = _S) -> PlannedExercise:
    return PlannedExercise(name=name, exercise_type=typ, sets=sets, reps=reps)


_REST = PlanDay(label="Rest", is_rest=True, exercises=())

PUSH_PULL_LEGS = WorkoutPlan(
    id="ppl",
    name="Push Pull Legs",
    rotation=(
        PlanDay(label="Push", is_rest=False, exercises=(
            _ex("Bench Press", 4, 8),
            _ex("Overhead Press", 3, 10),
            _ex("Incline Dumbbell Press", 3, 12),
            _ex("Lateral Raises", 3, 15),
            _ex("Tricep Pushdowns", 3, 12),
        )),
        PlanDay(label="Pull", is_rest=False, exercises=(
            _ex("Deadlift", 3, 5),
            _ex("Barbell Rows", 4, 8),
            _ex("Lat Pulldowns", 3, 10),
            _ex("Face Pulls", 3, 15),
            _ex("Barbell Curls", 3, 12),
        )),
        PlanDay(label="Legs", is_rest=False, exercises=(
            _ex("Squat", 4, 8),
            _ex("Romanian Deadlift", 3, 10),
            _ex("Leg Press", 3, 12),
            _ex("Leg Curls", 3, 12),
            _ex("Calf Raises", 4, 15),
        )),
        _REST,
        PlanDay(label="Push", is_rest=False, exercises=(
            _ex("Bench Press", 4, 8),
            _ex("Overhead Press", 3, 10),
            _ex("Incline Dumbbell Press", 3, 12),
            _ex("Lateral Raises", 3, 15),
            _ex("Tricep Pushdowns", 3, 12),
        )),
        PlanDay(label="Pull", is_rest=False, exercises=(
            _ex("Deadlift", 3, 5),
            _ex("Barbell Rows", 4, 8),
            _ex("Lat Pulldowns", 3, 10),
            _ex("Face Pulls", 3, 15),
            _ex("Barbell Curls", 3, 12),
        )),
        PlanDay(label="Legs", is_rest=False, exercises=(
            _ex("Squat", 4, 8),
            _ex("Romanian Deadlift", 3, 10),
            _ex("Leg Press", 3, 12),
            _ex("Leg Curls", 3, 12),
            _ex("Calf Raises", 4, 15),
        )),
    ),
)

UPPER_LOWER = WorkoutPlan(
    id="upper_lower",
    name="Upper Lower",
    rotation=(
        PlanDay(label="Upper", is_rest=False, exercises=(
            _ex("Bench Press", 4, 8),
            _ex("Overhead Press", 3, 10),
            _ex("Barbell Rows", 4, 8),
            _ex("Lat Pulldowns", 3, 10),
            _ex("Barbell Curls", 3, 12),
            _ex("Tricep Pushdowns", 3, 12),
        )),
        PlanDay(label="Lower", is_rest=False, exercises=(
            _ex("Squat", 4, 8),
            _ex("Romanian Deadlift", 3, 10),
            _ex("Leg Press", 3, 12),
            _ex("Leg Curls", 3, 12),
            _ex("Calf Raises", 4, 15),
        )),
        _REST,
        PlanDay(label="Upper", is_rest=False, exercises=(
            _ex("Bench Press", 4, 8),
            _ex("Overhead Press", 3, 10),
            _ex("Barbell Rows", 4, 8),
            _ex("Lat Pulldowns", 3, 10),
            _ex("Barbell Curls", 3, 12),
            _ex("Tricep Pushdowns", 3, 12),
        )),
        PlanDay(label="Lower", is_rest=False, exercises=(
            _ex("Squat", 4, 8),
            _ex("Romanian Deadlift", 3, 10),
            _ex("Leg Press", 3, 12),
            _ex("Leg Curls", 3, 12),
            _ex("Calf Raises", 4, 15),
        )),
        _REST,
        _REST,
    ),
)

PPL_NO_REST = WorkoutPlan(
    id="ppl_no_rest",
    name="PPL (No Rest Days)",
    rotation=(
        PlanDay(label="Push", is_rest=False, exercises=(
            _ex("Bench Press", 4, 8),
            _ex("Overhead Press", 3, 10),
            _ex("Incline Dumbbell Press", 3, 12),
            _ex("Lateral Raises", 3, 15),
            _ex("Tricep Pushdowns", 3, 12),
        )),
        PlanDay(label="Pull", is_rest=False, exercises=(
            _ex("Deadlift", 3, 5),
            _ex("Barbell Rows", 4, 8),
            _ex("Lat Pulldowns", 3, 10),
            _ex("Face Pulls", 3, 15),
            _ex("Barbell Curls", 3, 12),
        )),
        PlanDay(label="Legs", is_rest=False, exercises=(
            _ex("Squat", 4, 8),
            _ex("Romanian Deadlift", 3, 10),
            _ex("Leg Press", 3, 12),
            _ex("Leg Curls", 3, 12),
            _ex("Calf Raises", 4, 15),
        )),
    ),
)

PRESET_PLANS: dict[str, WorkoutPlan] = {
    p.id: p for p in [PUSH_PULL_LEGS, UPPER_LOWER, PPL_NO_REST]
}
