"""Serialization boundary: domain ``Meal`` <-> plain JSON-ready dicts.

This is the only place that knows the on-disk shape. The domain stays free of any
persistence concern, and a future SQL adapter would have its own mapping — so this format
is a private detail of the JSON adapter. Kept as hand-written (de)serialization rather
than pulling in a validation library: the shapes are small and fully under our control,
and isolating it here means swapping to Pydantic later is a local change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fitness.domain.food import Food
from fitness.domain.meal import Meal
from fitness.domain.value_objects import Macros, MealTimeSlot, Quantity, Unit

SCHEMA_VERSION = 1


def meal_to_dict(meal: Meal) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": meal.id,
        "logged_at": meal.logged_at.isoformat(),
        "meal_time": meal.meal_time.value,
        "foods": [_food_to_dict(f) for f in meal.foods],
    }


def meal_from_dict(data: dict[str, Any]) -> Meal:
    return Meal(
        id=data["id"],
        logged_at=datetime.fromisoformat(data["logged_at"]),
        meal_time=MealTimeSlot(data["meal_time"]),
        foods=tuple(_food_from_dict(f) for f in data["foods"]),
    )


def _food_to_dict(food: Food) -> dict[str, Any]:
    return {
        "name": food.name,
        "quantity": {"amount": food.quantity.amount, "unit": food.quantity.unit.value},
        "macros": {
            "protein_g": food.macros.protein_g,
            "carbs_g": food.macros.carbs_g,
            "fat_g": food.macros.fat_g,
        },
        "calories": food.calories,
        "meal_time": food.meal_time.value,
    }


def _food_from_dict(data: dict[str, Any]) -> Food:
    q = data["quantity"]
    m = data["macros"]
    return Food(
        name=data["name"],
        quantity=Quantity(amount=q["amount"], unit=Unit(q["unit"])),
        macros=Macros(protein_g=m["protein_g"], carbs_g=m["carbs_g"], fat_g=m["fat_g"]),
        calories=data["calories"],
        meal_time=MealTimeSlot(data["meal_time"]),
    )
