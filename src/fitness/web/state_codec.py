"""Serialize/deserialize ``ConversationState`` to/from a plain dict for the API context.

This is the adapter between the opaque ``context`` dict on the wire and the typed
application DTO. The client treats this as opaque JSON — it echoes it back without
parsing. Keeping this codec here (in the web layer) means the application never knows
about JSON wire shapes.
"""

from __future__ import annotations

from typing import Any

from fitness.application.dto import (
    ConversationState,
    PendingClarification,
    PendingExerciseState,
    PendingSavedMealItem,
    PendingSavedMealState,
)
from fitness.domain.candidate import CandidateFood, CandidateMeal
from fitness.domain.value_objects import (
    FieldValue,
    Macros,
    MealTimeSlot,
    Provenance,
    Quantity,
    Unit,
)


_StateTypes = ConversationState | PendingSavedMealState | PendingExerciseState


def encode_state(state: _StateTypes) -> dict[str, Any]:
    if isinstance(state, PendingExerciseState):
        return {
            "type": "pending_exercise",
            "name": state.name,
            "exercise_type": state.exercise_type,
            "sets": state.sets,
            "reps": state.reps,
            "weight": state.weight,
            "duration_min": state.duration_min,
            "question": state.question,
        }
    if isinstance(state, PendingSavedMealState):
        return {
            "type": "saved_meal_preview",
            "name": state.name,
            "items": [
                {
                    "food_name": item.food_name,
                    "quantity_amount": item.quantity_amount,
                    "quantity_unit": item.quantity_unit,
                    "calories": item.calories,
                    "protein_g": item.protein_g,
                    "carbs_g": item.carbs_g,
                    "fat_g": item.fat_g,
                }
                for item in state.items
            ],
        }
    return {
        "type": "log",
        "candidate": _encode_candidate(state.candidate),
        "pending": _encode_pending(state.pending) if state.pending else None,
    }


def decode_state(data: dict[str, Any]) -> _StateTypes:
    if data.get("type") == "pending_exercise":
        return PendingExerciseState(
            name=data["name"],
            exercise_type=data["exercise_type"],
            sets=data.get("sets"),
            reps=data.get("reps"),
            weight=data.get("weight"),
            duration_min=data.get("duration_min"),
            question=data.get("question", ""),
        )
    if data.get("type") == "saved_meal_preview":
        return PendingSavedMealState(
            name=data["name"],
            items=[
                PendingSavedMealItem(
                    food_name=item["food_name"],
                    quantity_amount=item["quantity_amount"],
                    quantity_unit=item["quantity_unit"],
                    calories=item["calories"],
                    protein_g=item["protein_g"],
                    carbs_g=item["carbs_g"],
                    fat_g=item["fat_g"],
                )
                for item in data["items"]
            ],
        )
    # Default / legacy: "log" type or missing type field
    return ConversationState(
        candidate=_decode_candidate(data["candidate"]),
        pending=_decode_pending(data["pending"]) if data.get("pending") else None,
    )


def _encode_candidate(c: CandidateMeal) -> dict:
    return {
        "meal_time": _encode_fv(c.meal_time, _encode_str) if c.meal_time else None,
        "foods": [_encode_food(f) for f in c.foods],
        "raw_turns": c.raw_turns,
    }


def _decode_candidate(d: dict) -> CandidateMeal:
    return CandidateMeal(
        meal_time=_decode_fv(d["meal_time"], lambda v: MealTimeSlot(v)) if d.get("meal_time") else None,
        foods=[_decode_food(f) for f in d.get("foods", [])],
        raw_turns=d.get("raw_turns", []),
    )


def _encode_food(f: CandidateFood) -> dict:
    return {
        "name": _encode_fv(f.name, _encode_str) if f.name else None,
        "quantity": _encode_fv(f.quantity, _encode_quantity) if f.quantity else None,
        "macros": _encode_fv(f.macros, _encode_macros) if f.macros else None,
        "calories": _encode_fv(f.calories, _encode_str) if f.calories else None,
    }


def _decode_food(d: dict) -> CandidateFood:
    cf = CandidateFood()
    if d.get("name"):
        cf.name = _decode_fv(d["name"], str)
    if d.get("quantity"):
        cf.quantity = _decode_fv(d["quantity"], _decode_quantity)
    if d.get("macros"):
        cf.macros = _decode_fv(d["macros"], _decode_macros)
    if d.get("calories"):
        cf.calories = _decode_fv(d["calories"], float)
    return cf


def _encode_fv(fv: FieldValue, value_fn) -> dict:
    return {"value": value_fn(fv.value), "provenance": fv.provenance.value, "confidence": fv.confidence}


def _decode_fv(d: dict, value_fn) -> FieldValue:
    return FieldValue(value=value_fn(d["value"]), provenance=Provenance(d["provenance"]), confidence=d["confidence"])


def _encode_str(v: Any) -> Any:
    return v


def _encode_quantity(q: Quantity) -> dict:
    return {"amount": q.amount, "unit": q.unit.value}


def _decode_quantity(d: dict) -> Quantity:
    return Quantity(amount=d["amount"], unit=Unit(d["unit"]))


def _encode_macros(m: Macros) -> dict:
    return {"protein_g": m.protein_g, "carbs_g": m.carbs_g, "fat_g": m.fat_g}


def _decode_macros(d: dict) -> Macros:
    return Macros(protein_g=d["protein_g"], carbs_g=d["carbs_g"], fat_g=d["fat_g"])


def _encode_pending(p: PendingClarification) -> dict:
    return {"target": p.target, "field": p.field}


def _decode_pending(d: dict) -> PendingClarification:
    return PendingClarification(target=d["target"], field=d["field"])
