"""Routes — conversation, food log, exercises, summary, and user profile."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from fitness.application.user_profile import UserProfile
from fitness.config.composition import Container
from fitness.web.dependencies import get_container
from fitness.web.interaction_log import log_interaction
from fitness.web.models import DailySummaryResponse, MacrosResponse, MessageRequest, MessageResponse
from fitness.web.state_codec import decode_state, encode_state

router = APIRouter()


class ProfileBody(BaseModel):
    name: str = ""
    age: int = 0
    gender: str = ""
    unit_system: str = "metric"
    height_cm: float = 0
    weight_kg: float = 0
    height_ft: int = 0
    height_in: int = 0
    weight_lbs: float = 0
    fitness_goal: str = ""
    activity_level: str = ""
    experience_level: str = ""
    injuries: str = ""
    calorie_target: int = 2000
    protein_target_g: int = 150
    carbs_target_g: int = 250
    fat_target_g: int = 70


@router.post("/messages", response_model=MessageResponse)
def post_message(
    body: MessageRequest,
    container: Container = Depends(get_container),
):
    state = decode_state(body.context) if body.context else None
    result = container.handle_message.handle(text=body.text, state=state)

    context = encode_state(result.state) if result.state else None
    resp = MessageResponse(
        status=result.status.value,
        message=result.message,
        context=context,
        meal_id=result.meal_id,
        notes=result.notes,
    )
    log_interaction(body.text, body.context is not None, resp.model_dump())
    return resp


@router.get("/log/{day}")
def get_log(
    day: date,
    container: Container = Depends(get_container),
):
    day_log = container.view_log.handle(day)
    return day_log.to_dict()


@router.get("/exercises/{day}")
def get_exercises(
    day: date,
    container: Container = Depends(get_container),
):
    exercises = container.exercise_repo.list_by_date(day)
    return [_exercise_response(e) for e in exercises]


def _exercise_response(e) -> dict:
    return {
        "name": e.name,
        "exercise_type": e.exercise_type.value,
        "set_details": [{"reps": s.reps, "weight": s.weight} for s in e.set_details],
        "set_groups": e.grouped_sets(),
        "sets_display": e.format_sets(),
        "duration_min": e.duration_min,
    }


class SetDetailBody(BaseModel):
    reps: int
    weight: float | None = None


class LogExerciseBody(BaseModel):
    name: str
    exercise_type: str = "strength"
    set_details: list[SetDetailBody] = []
    duration_min: float | None = None
    day: date | None = None


@router.delete("/exercises/{day}/{name}")
def delete_exercise(day: date, name: str, container: Container = Depends(get_container)):
    from fitness.adapters.persistence.json_exercise_repository import _to_dict
    from fitness.domain.naming import normalize_food_name

    target = normalize_food_name(name)
    exercises = container.exercise_repo.list_by_date(day)
    for ex in exercises:
        if normalize_food_name(ex.name) == target:
            restore_data = _to_dict(ex)
            container.exercise_repo.delete_by_name(day, ex.name)
            return {"deleted": True, "name": ex.name, "restore_data": restore_data}
    return {"deleted": False, "error": f"Couldn't find '{name}' on {day.isoformat()}."}


@router.post("/exercises/restore")
def restore_exercise(body: dict, container: Container = Depends(get_container)):
    from fitness.adapters.persistence.json_exercise_repository import _from_dict

    data = body.get("exercise_data")
    if not data:
        return {"error": "No exercise data provided"}
    exercise = _from_dict(data)
    container.exercise_repo.save(exercise)
    return {"restored": True}


@router.post("/exercises")
def create_exercise(
    body: LogExerciseBody,
    container: Container = Depends(get_container),
):
    from fitness.domain.exercise import Exercise, ExerciseType, SetDetail

    try:
        ex_type = ExerciseType(body.exercise_type)
    except ValueError:
        ex_type = ExerciseType.OTHER

    details = tuple(
        SetDetail(reps=s.reps, weight=s.weight) for s in body.set_details
    )
    target_day = body.day if body.day is not None else container.clock.today()
    exercise = Exercise(
        name=body.name,
        exercise_type=ex_type,
        day=target_day,
        set_details=details,
        duration_min=body.duration_min,
    )
    container.exercise_repo.save(exercise)
    # save() merges into an existing same-name entry for the day, so re-read to report
    # what's actually stored rather than only what was submitted.
    from fitness.domain.naming import normalize_food_name

    target = normalize_food_name(exercise.name)
    stored = next(
        (e for e in container.exercise_repo.list_by_date(target_day)
         if normalize_food_name(e.name) == target),
        exercise,
    )
    return _exercise_response(stored)


@router.get("/summary/{day}", response_model=DailySummaryResponse)
def get_summary(
    day: date,
    container: Container = Depends(get_container),
):
    summary = container.daily_summary.handle(day)
    return DailySummaryResponse(
        day=summary.day.isoformat(),
        total_calories=summary.total_calories,
        total_macros=MacrosResponse(
            protein_g=summary.total_macros.protein_g,
            carbs_g=summary.total_macros.carbs_g,
            fat_g=summary.total_macros.fat_g,
        ),
        calories_by_slot={k.value: v for k, v in summary.calories_by_slot.items()},
        meal_count=summary.meal_count,
    )


@router.get("/profile")
def get_profile(container: Container = Depends(get_container)):
    return container.profile_store.load().to_dict()


@router.put("/profile")
def put_profile(body: ProfileBody, container: Container = Depends(get_container)):
    profile = UserProfile(**body.model_dump())
    profile.sync_units()
    container.profile_store.save(profile)
    return profile.to_dict()


# --- Workout Plans & Calendar ---

@router.get("/plans")
def list_plans(container: Container = Depends(get_container)):
    return [p.to_dict() for p in container.plan_store.list_plans()]


class PlannedExerciseBody(BaseModel):
    name: str
    exercise_type: str = "strength"
    sets: int = 3
    reps: int = 10


class PlanDayBody(BaseModel):
    label: str
    is_rest: bool = False
    exercises: list[PlannedExerciseBody] = []


class CreatePlanBody(BaseModel):
    name: str
    rotation: list[PlanDayBody]


@router.post("/plans")
def create_plan(body: CreatePlanBody, container: Container = Depends(get_container)):
    import uuid

    from fitness.domain.workout_plan import PlanDay, PlannedExercise, WorkoutPlan

    if not body.name.strip():
        return {"error": "Plan name is required"}
    if not body.rotation:
        return {"error": "At least one day is required"}

    plan = WorkoutPlan(
        id=uuid.uuid4().hex[:8],
        name=body.name.strip(),
        rotation=tuple(
            PlanDay(
                label=d.label.strip(),
                is_rest=d.is_rest,
                exercises=tuple(
                    PlannedExercise(name=e.name, exercise_type=e.exercise_type,
                                    sets=e.sets, reps=e.reps)
                    for e in d.exercises
                ) if not d.is_rest else (),
            )
            for d in body.rotation
        ),
    )
    container.plan_store.save_plan(plan)
    return plan.to_dict()


@router.put("/plans/{plan_id}")
def update_plan(plan_id: str, body: CreatePlanBody, container: Container = Depends(get_container)):
    from fitness.domain.preset_plans import PRESET_PLANS
    from fitness.domain.workout_plan import PlanDay, PlannedExercise, WorkoutPlan

    if plan_id in PRESET_PLANS:
        return {"error": "Cannot modify a preset plan directly — customize it first"}
    existing = container.plan_store.get_plan(plan_id)
    if existing is None:
        return {"error": "Plan not found"}

    plan = WorkoutPlan(
        id=plan_id,
        name=body.name.strip(),
        rotation=tuple(
            PlanDay(
                label=d.label.strip(),
                is_rest=d.is_rest,
                exercises=tuple(
                    PlannedExercise(name=e.name, exercise_type=e.exercise_type,
                                    sets=e.sets, reps=e.reps)
                    for e in d.exercises
                ) if not d.is_rest else (),
            )
            for d in body.rotation
        ),
    )
    container.plan_store.save_plan(plan)

    cal = container.plan_store.load_calendar()
    if cal and cal.plan_id == plan_id:
        cal.plan_name = plan.name
        container.plan_store.save_calendar(cal)

    return plan.to_dict()


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: str, container: Container = Depends(get_container)):
    from fitness.domain.preset_plans import PRESET_PLANS

    if plan_id in PRESET_PLANS:
        return {"error": "Cannot delete a preset plan"}
    path = container.plan_store._plans_dir / f"{plan_id}.json"
    if not path.exists():
        return {"error": "Plan not found"}
    path.unlink()
    return {"deleted": True}


@router.post("/calendar/activate")
def activate_plan(body: dict, container: Container = Depends(get_container)):
    plan_id = body.get("plan_id", "")
    cal = container.manage_calendar.activate_plan(plan_id)
    if cal is None:
        return {"error": "Plan not found"}
    return container.manage_calendar.get_calendar()


@router.get("/calendar")
def get_calendar(container: Container = Depends(get_container)):
    cal = container.manage_calendar.get_calendar()
    if cal is None:
        return {"active": False}
    return {**cal, "active": True}


@router.post("/calendar/skip")
def skip_day(container: Container = Depends(get_container)):
    result = container.manage_calendar.skip_day()
    if result is None:
        return {"error": "No active calendar"}
    return {**result, "active": True}


@router.post("/calendar/push-back")
def push_back_day(container: Container = Depends(get_container)):
    result = container.manage_calendar.push_back()
    if result is None:
        return {"error": "No active calendar"}
    return {**result, "active": True}


@router.post("/calendar/complete")
def complete_day(container: Container = Depends(get_container)):
    result = container.manage_calendar.complete_day()
    if result is None:
        return {"error": "No active calendar"}
    return {**result, "active": True}


@router.post("/calendar/align")
def align_calendar(body: dict, container: Container = Depends(get_container)):
    day_index = body.get("day_index")
    if day_index is None:
        return {"error": "day_index required"}
    result = container.manage_calendar.align(int(day_index))
    if result is None:
        return {"error": "No active calendar"}
    return {**result, "active": True}


@router.post("/calendar/undo")
def undo_calendar(container: Container = Depends(get_container)):
    result = container.manage_calendar.undo()
    if result is None:
        return {"error": "Nothing to undo"}
    return {**result, "active": True}


@router.post("/calendar/skip-to-today")
def skip_to_today(container: Container = Depends(get_container)):
    result = container.manage_calendar.skip_to_today()
    if result is None:
        return {"error": "No active calendar"}
    view, skipped = result
    return {**view, "active": True, "skipped_count": skipped}


@router.post("/calendar/push-back-to-today")
def push_back_to_today(container: Container = Depends(get_container)):
    result = container.manage_calendar.push_back_to_today()
    if result is None:
        return {"error": "No active calendar"}
    view, pushed = result
    return {**view, "active": True, "pushed_count": pushed}


# --- Saved Meals ---

class SavedMealItemBody(BaseModel):
    food_name: str
    quantity_g: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


class SavedMealBody(BaseModel):
    name: str
    items: list[SavedMealItemBody]


@router.get("/saved-meals")
def list_saved_meals(container: Container = Depends(get_container)):
    return [m.to_dict() for m in container.saved_meal_store.list_meals()]


@router.post("/saved-meals")
def create_saved_meal(body: SavedMealBody, container: Container = Depends(get_container)):
    import uuid
    from fitness.domain.saved_meal import SavedMeal, SavedMealItem

    meal = SavedMeal(
        id=uuid.uuid4().hex[:8],
        name=body.name,
        items=[SavedMealItem(**item.model_dump()) for item in body.items],
    )
    container.saved_meal_store.save_meal(meal)
    return meal.to_dict()


@router.put("/saved-meals/{meal_id}")
def update_saved_meal(
    meal_id: str, body: SavedMealBody, container: Container = Depends(get_container),
):
    from fitness.domain.saved_meal import SavedMeal, SavedMealItem

    existing = container.saved_meal_store.get_meal(meal_id)
    if existing is None:
        return {"error": "Not found"}
    meal = SavedMeal(
        id=meal_id,
        name=body.name,
        items=[SavedMealItem(**item.model_dump()) for item in body.items],
    )
    container.saved_meal_store.save_meal(meal)
    return meal.to_dict()


@router.delete("/saved-meals/{meal_id}")
def delete_saved_meal(meal_id: str, container: Container = Depends(get_container)):
    deleted = container.saved_meal_store.delete_meal(meal_id)
    return {"deleted": deleted}


@router.post("/saved-meals/{meal_id}/log")
def log_saved_meal(
    meal_id: str, body: dict, container: Container = Depends(get_container),
):
    """Quick-log a saved meal to today's food log."""
    import uuid
    from datetime import datetime

    from fitness.domain.food import Food
    from fitness.domain.meal import Meal
    from fitness.domain.value_objects import Macros, MealTimeSlot, Quantity, Unit

    meal_template = container.saved_meal_store.get_meal(meal_id)
    if meal_template is None:
        return {"error": "Saved meal not found"}

    slot_str = body.get("meal_time", "snack")
    try:
        slot = MealTimeSlot(slot_str)
    except ValueError:
        slot = MealTimeSlot.SNACK

    foods = []
    for item in meal_template.items:
        foods.append(Food(
            name=item.food_name,
            quantity=Quantity(item.quantity_g, Unit.GRAM),
            macros=Macros(
                protein_g=item.protein_g,
                carbs_g=item.carbs_g,
                fat_g=item.fat_g,
            ),
            calories=item.calories,
            meal_time=slot,
        ))
    logged_meal = Meal(
        id=uuid.uuid4().hex[:8],
        logged_at=datetime.now(),
        meal_time=slot,
        foods=tuple(foods),
    )
    container.meal_repo.save(logged_meal)
    return {"status": "logged", "meal_name": meal_template.name, "food_count": len(foods)}


class LogFoodBody(BaseModel):
    name: str
    meal_time: str = "snack"
    quantity_amount: float = 0
    quantity_unit: str = "g"
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0


@router.post("/log/food")
def log_food_manual(body: LogFoodBody, container: Container = Depends(get_container)):
    """Manually log a single food item to today's food log."""
    import uuid
    from datetime import datetime

    from fitness.domain.food import Food
    from fitness.domain.meal import Meal
    from fitness.domain.value_objects import Macros, MealTimeSlot, Quantity, Unit

    if not body.name.strip():
        return {"error": "Food name is required"}

    try:
        slot = MealTimeSlot(body.meal_time)
    except ValueError:
        slot = MealTimeSlot.SNACK

    try:
        unit = Unit(body.quantity_unit)
    except ValueError:
        unit = Unit.GRAM

    food = Food(
        name=body.name.strip(),
        quantity=Quantity(body.quantity_amount, unit),
        macros=Macros(
            protein_g=body.protein_g,
            carbs_g=body.carbs_g,
            fat_g=body.fat_g,
        ),
        calories=body.calories,
        meal_time=slot,
    )
    meal = Meal(
        id=uuid.uuid4().hex[:8],
        logged_at=datetime.now(),
        meal_time=slot,
        foods=(food,),
    )
    container.meal_repo.save(meal)
    return {"status": "logged", "food_name": food.name}


# --- Food Delete / Restore (clean undo) ---


class DeleteFoodBody(BaseModel):
    name: str
    day: str | None = None


@router.post("/log/delete-food")
def delete_food(body: DeleteFoodBody, container: Container = Depends(get_container)):
    """Delete a food by name from a day's log, returning restore data."""
    from fitness.adapters.persistence.schema import meal_to_dict
    from fitness.domain.naming import normalize_food_name

    target = normalize_food_name(body.name)
    day = date.fromisoformat(body.day) if body.day else container.clock.today()
    meals = container.meal_repo.list_by_date(day)

    for meal in meals:
        for i, food in enumerate(meal.foods):
            if normalize_food_name(food.name) == target:
                restore_data = meal_to_dict(meal)
                if len(meal.foods) == 1:
                    container.meal_repo.delete(meal.id)
                else:
                    container.meal_repo.save(meal.without_food_at(i))
                return {"deleted": True, "food_name": food.name, "restore_data": restore_data}

    return {"deleted": False, "error": f"Couldn't find '{body.name}' in the log."}


@router.post("/log/restore")
def restore_meal(body: dict, container: Container = Depends(get_container)):
    """Restore a previously deleted meal from its serialized data."""
    from fitness.adapters.persistence.schema import meal_from_dict

    meal_data = body.get("meal_data")
    if not meal_data:
        return {"error": "No meal data provided"}
    meal = meal_from_dict(meal_data)
    container.meal_repo.save(meal)
    return {"restored": True}


class EditFoodBody(BaseModel):
    original_name: str
    day: str | None = None
    name: str
    meal_time: str = "snack"
    quantity_amount: float = 0
    quantity_unit: str = "g"
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0


@router.post("/log/edit-food")
def edit_food(body: EditFoodBody, container: Container = Depends(get_container)):
    from fitness.domain.food import Food
    from fitness.domain.naming import normalize_food_name
    from fitness.domain.value_objects import Macros, MealTimeSlot, Quantity, Unit

    target = normalize_food_name(body.original_name)
    day = date.fromisoformat(body.day) if body.day else container.clock.today()
    meals = container.meal_repo.list_by_date(day)

    try:
        new_slot = MealTimeSlot(body.meal_time)
    except ValueError:
        new_slot = MealTimeSlot.SNACK

    try:
        unit = Unit(body.quantity_unit)
    except ValueError:
        unit = Unit.GRAM

    for meal in meals:
        for i, food in enumerate(meal.foods):
            if normalize_food_name(food.name) == target:
                new_food = Food(
                    name=body.name.strip(),
                    quantity=Quantity(body.quantity_amount, unit),
                    macros=Macros(protein_g=body.protein_g, carbs_g=body.carbs_g, fat_g=body.fat_g),
                    calories=body.calories,
                    meal_time=new_slot,
                )
                new_foods = list(meal.foods)
                new_foods[i] = new_food
                updated = meal.with_foods(tuple(new_foods))
                if new_slot != meal.meal_time:
                    updated = updated.with_meal_time(new_slot)
                container.meal_repo.save(updated)
                return {"edited": True, "food_name": new_food.name}

    return {"edited": False, "error": f"Couldn't find '{body.original_name}' in the log."}


# --- Food KB Search ---

@router.get("/food-search")
def search_food_kb(q: str = "", container: Container = Depends(get_container)):
    """Search the food knowledge base by name prefix. Returns first 20 if query is empty."""
    query = q.lower().strip()
    results = []
    for name, food in container.food_kb.all_entries():
        if not query or query in name.lower():
            results.append({
                "name": name,
                "calories": food.calories_per_serving,
                "protein_g": food.macros_per_serving.protein_g,
                "carbs_g": food.macros_per_serving.carbs_g,
                "fat_g": food.macros_per_serving.fat_g,
                "serving_grams": food.serving_grams,
                "serving_unit": food.serving_unit.value,
            })
            if len(results) >= 20:
                break
    return results


@router.get("/exercise-search")
def search_exercises(q: str = "", container: Container = Depends(get_container)):
    """Autocomplete exercise names.

    Exercises the user has already logged rank first (they're the likely repeat), then
    the static catalog. Duplicates are collapsed by normalized name.
    """
    from fitness.domain.naming import normalize_food_name

    query = q.lower().strip()
    results: list[dict] = []
    seen: set[str] = set()

    for name, etype in container.exercise_repo.recent_names():
        if query and query not in name.lower():
            continue
        key = normalize_food_name(name)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "name": name,
            "exercise_type": etype,
            "muscle_group": "",
            "recent": True,
        })
        if len(results) >= 20:
            return results

    for entry in container.exercise_catalog.search(query, limit=20):
        key = normalize_food_name(entry["name"])
        if key in seen:
            continue
        seen.add(key)
        results.append({**entry, "recent": False})
        if len(results) >= 20:
            break

    return results
