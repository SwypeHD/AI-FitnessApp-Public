"""ViewLogUseCase — returns a structured, formatted view of a day's meals.

Organized by date header, then meal-time slot headers, with each food showing
name, quantity, calories, and macros. All numbers are deterministic from the repo.
"""

from __future__ import annotations

from datetime import date

from fitness.application.ports.repositories import MealRepository
from fitness.domain.meal import Meal
from fitness.domain.value_objects import Macros, MealTimeSlot


def _qty_label(amount: float, unit_value: str) -> str:
    label = unit_value
    if amount != 1 and unit_value not in ("g", "oz", "ml"):
        label += "s"
    return f"{amount:g} {label}"


class DayLog:
    """Structured log for a single day, suitable for display or serialization."""

    def __init__(self, day: date, meals: list[Meal]) -> None:
        self.day = day
        self.meals = meals
        self.by_slot: dict[MealTimeSlot, list[Meal]] = {}
        for meal in meals:
            self.by_slot.setdefault(meal.meal_time, []).append(meal)

    @property
    def total_calories(self) -> float:
        return sum(m.total_calories for m in self.meals)

    @property
    def is_empty(self) -> bool:
        return len(self.meals) == 0

    def to_text(self) -> str:
        if self.is_empty:
            return f"📋 {self.day.isoformat()} — nothing logged yet."

        lines: list[str] = [f"📋 {self.day.isoformat()}"]

        slot_order = [MealTimeSlot.BREAKFAST, MealTimeSlot.LUNCH,
                      MealTimeSlot.DINNER, MealTimeSlot.SNACK]
        for slot in slot_order:
            meals = self.by_slot.get(slot)
            if not meals:
                continue
            slot_cals = sum(m.total_calories for m in meals)
            lines.append(f"\n  {slot.value.upper()} ({slot_cals:.0f} kcal)")
            for meal in meals:
                for food in meal.foods:
                    m = food.macros
                    qty = _qty_label(food.quantity.amount, food.quantity.unit.value)
                    lines.append(
                        f"    • {food.name} — {qty} — "
                        f"{food.calories:.0f} kcal "
                        f"(P:{m.protein_g:.0f} C:{m.carbs_g:.0f} F:{m.fat_g:.0f})"
                    )

        total_macros = sum(
            (m.total_macros for m in self.meals),
            start=Macros.zero(),
        )
        lines.append(
            f"\n  TOTAL: {self.total_calories:.0f} kcal — "
            f"P:{total_macros.protein_g:.0f}g C:{total_macros.carbs_g:.0f}g F:{total_macros.fat_g:.0f}g"
        )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON-friendly representation for the API."""
        slots = {}
        slot_order = [MealTimeSlot.BREAKFAST, MealTimeSlot.LUNCH,
                      MealTimeSlot.DINNER, MealTimeSlot.SNACK]
        for slot in slot_order:
            meals = self.by_slot.get(slot)
            if not meals:
                continue
            foods = []
            for meal in meals:
                for food in meal.foods:
                    foods.append({
                        "name": food.name,
                        "quantity": _qty_label(food.quantity.amount, food.quantity.unit.value),
                        "quantity_amount": round(food.quantity.amount, 1),
                        "quantity_unit": food.quantity.unit.value,
                        "calories": round(food.calories, 1),
                        "protein_g": round(food.macros.protein_g, 1),
                        "carbs_g": round(food.macros.carbs_g, 1),
                        "fat_g": round(food.macros.fat_g, 1),
                    })
            slots[slot.value] = {
                "foods": foods,
                "calories": round(sum(m.total_calories for m in meals), 1),
            }
        return {
            "day": self.day.isoformat(),
            "slots": slots,
            "total_calories": round(self.total_calories, 1),
        }


class ViewLogUseCase:
    def __init__(self, meal_repo: MealRepository) -> None:
        self._meal_repo = meal_repo

    def handle(self, day: date) -> DayLog:
        meals = self._meal_repo.list_by_date(day)
        return DayLog(day=day, meals=meals)
