"""EditLogUseCase — deterministic mutation of existing logged meals.

Supports:
- DELETE a food by name from today's log ("delete the chicken")
- MOVE a food to a different meal slot ("move chicken to dinner")
- UPDATE quantity ("change the rice to 200g", "update chicken to 2 servings")
- CONVERT unit ("convert the rice to grams", "show chicken in oz")
- RENAME food ("rename the rice to brown rice")

The LLM has NO access here. Mutations are executed against the repository, and the
confirmation message is built from a RE-READ of the actual persisted state — never
from the model's narration. This structurally prevents the "narrated but never saved"
failure mode.
"""

from __future__ import annotations

import re
from dataclasses import replace

from fitness.application.parsing import UNIT_TOKENS, parse_quantity_and_remainder, parse_unit
from fitness.application.ports.clock import Clock
from fitness.application.ports.nutrition import FoodKnowledgeBase
from fitness.application.ports.repositories import MealRepository
from fitness.application.scaling import GRAMS_PER_OUNCE, quantity_to_servings, scaled_nutrition
from fitness.application.use_cases.view_log import ViewLogUseCase, _qty_label
from fitness.domain.food import Food
from fitness.domain.naming import normalize_food_name
from fitness.domain.value_objects import Macros, MealTimeSlot, Quantity, Unit


class EditResult:
    def __init__(self, success: bool, message: str) -> None:
        self.success = success
        self.message = message


_MEAL_TIME_WORDS: dict[str, MealTimeSlot] = {
    "breakfast": MealTimeSlot.BREAKFAST,
    "lunch": MealTimeSlot.LUNCH,
    "dinner": MealTimeSlot.DINNER,
    "snack": MealTimeSlot.SNACK,
}

_DELETE_RE = re.compile(
    r"\b(?:delete|remove|undo|cancel)\b\s+(?:the\s+|my\s+)?(.+)",
    re.I,
)

_MOVE_FROM_TO_RE = re.compile(
    r"\b(?:move|change|switch)\b\s+(?:the\s+|my\s+)?(.+?)\s+from\s+"
    r"(?:breakfast|lunch|dinner|snack)\s+to\s+(breakfast|lunch|dinner|snack)\b",
    re.I,
)

_MOVE_RE = re.compile(
    r"\b(?:move|change|switch)\b\s+(?:the\s+|my\s+)?(.+?)\s+to\s+"
    r"(breakfast|lunch|dinner|snack)\b",
    re.I,
)

_UNIT_PAT = "|".join(UNIT_TOKENS)

_UPDATE_QTY_RE = re.compile(
    r"\b(?:change|update|set|make)\b\s+(?:the\s+|my\s+)?(.+?)\s+to\s+"
    r"(\d+(?:\.\d+)?)\s*(" + _UNIT_PAT + r")\b",
    re.I,
)

_CORRECT_RE = re.compile(
    r"\b(?:actually|only)\b.*?(\d+(?:\.\d+)?)\s*(" + _UNIT_PAT + r")"
    r"\s+(?:of\s+)?(.+?)(?:\s*(?:,|not)\s+.+)?$",
    re.I,
)

_CONVERT_RE = re.compile(
    r"\b(?:convert|show|display)\b\s+(?:the\s+|my\s+)?(.+?)\s+(?:to|in|as)\s+"
    r"(" + _UNIT_PAT + r")\b",
    re.I,
)

_RENAME_RE = re.compile(
    r"\brename\b\s+(?:the\s+|my\s+)?(.+?)\s+to\s+(.+)",
    re.I,
)


class EditLogUseCase:
    def __init__(
        self,
        meal_repo: MealRepository,
        clock: Clock,
        food_kb: FoodKnowledgeBase | None = None,
    ) -> None:
        self._meal_repo = meal_repo
        self._clock = clock
        self._food_kb = food_kb
        self._view_log = ViewLogUseCase(meal_repo)

    def handle(self, text: str) -> EditResult:
        rename = _RENAME_RE.search(text)
        if rename:
            return self._rename(rename.group(1).strip(), rename.group(2).strip())

        update = _UPDATE_QTY_RE.search(text)
        if update:
            return self._update_quantity(
                update.group(1).strip(),
                float(update.group(2)),
                parse_unit(update.group(3)) or Unit.GRAM,
            )

        correct = _CORRECT_RE.search(text)
        if correct:
            return self._update_quantity(
                correct.group(3).strip(),
                float(correct.group(1)),
                parse_unit(correct.group(2)) or Unit.GRAM,
            )

        convert = _CONVERT_RE.search(text)
        if convert:
            return self._convert_unit(
                convert.group(1).strip(),
                parse_unit(convert.group(2)) or Unit.GRAM,
            )

        move = _MOVE_FROM_TO_RE.search(text) or _MOVE_RE.search(text)
        if move:
            return self._move(move.group(1).strip(), move.group(2).strip().lower())

        delete = _DELETE_RE.search(text)
        if delete:
            return self._delete(delete.group(1).strip())

        return EditResult(
            False,
            "I didn't understand that edit. Try:\n"
            "• 'delete the chicken'\n"
            "• 'move chicken to dinner'\n"
            "• 'change the rice to 200g'\n"
            "• 'convert the chicken to oz'\n"
            "• 'rename the rice to brown rice'",
        )

    def _delete(self, food_name: str) -> EditResult:
        target = normalize_food_name(food_name)
        day = self._clock.today()
        meals = self._meal_repo.list_by_date(day)

        for meal in meals:
            for i, food in enumerate(meal.foods):
                if normalize_food_name(food.name) == target:
                    if len(meal.foods) == 1:
                        self._meal_repo.delete(meal.id)
                    else:
                        self._meal_repo.save(meal.without_food_at(i))
                    return self._confirm_delete(food.name, day)

        return EditResult(False, f"Couldn't find '{food_name}' in today's log.")

    def _move(self, food_name: str, slot_word: str) -> EditResult:
        target = normalize_food_name(food_name)
        new_slot = _MEAL_TIME_WORDS.get(slot_word)
        if new_slot is None:
            return EditResult(False, f"Unknown meal time: '{slot_word}'.")

        day = self._clock.today()
        meals = self._meal_repo.list_by_date(day)

        for meal in meals:
            for i, food in enumerate(meal.foods):
                if normalize_food_name(food.name) == target:
                    moved_food = food.with_meal_time(new_slot)
                    updated = meal.without_food_at(i)
                    if updated.foods:
                        self._meal_repo.save(updated)
                    else:
                        self._meal_repo.delete(meal.id)
                    new_meal = meal.add_food(moved_food).with_meal_time(new_slot)
                    new_meal = new_meal.with_foods((moved_food,))
                    self._meal_repo.save(new_meal.__class__(
                        id=meal.id + "_moved",
                        logged_at=meal.logged_at,
                        meal_time=new_slot,
                        foods=(moved_food,),
                    ))
                    return self._confirm_move(food.name, new_slot, day)

        return EditResult(False, f"Couldn't find '{food_name}' in today's log.")

    def _confirm_delete(self, food_name: str, day) -> EditResult:
        """Build confirmation from the ACTUAL post-mutation state on disk."""
        log = self._view_log.handle(day)
        return EditResult(
            True,
            f"Deleted {food_name}.\n\n{log.to_text()}"
        )

    def _confirm_move(self, food_name: str, new_slot: MealTimeSlot, day) -> EditResult:
        log = self._view_log.handle(day)
        return EditResult(
            True,
            f"Moved {food_name} to {new_slot.value}.\n\n{log.to_text()}"
        )

    def _find_food(self, food_name: str):
        target = normalize_food_name(food_name)
        day = self._clock.today()
        meals = self._meal_repo.list_by_date(day)
        for meal in meals:
            for i, food in enumerate(meal.foods):
                if normalize_food_name(food.name) == target:
                    return meal, i, food, day
        return None, None, None, day

    def _replace_food(self, meal, idx, new_food):
        new_foods = list(meal.foods)
        new_foods[idx] = new_food
        self._meal_repo.save(meal.with_foods(tuple(new_foods)))

    def _scale_food(self, food: Food, new_qty: Quantity) -> Food:
        """Create a new Food with the given quantity and KB-scaled macros."""
        known = self._food_kb.lookup(food.name) if self._food_kb else None
        if known:
            servings = quantity_to_servings(new_qty, known)
            if servings is not None:
                macros, cals = scaled_nutrition(known, servings)
                return replace(food, quantity=new_qty, macros=macros, calories=cals)
        old_servings = quantity_to_servings(food.quantity, known) if known else None
        new_servings = quantity_to_servings(new_qty, known) if known else None
        if old_servings and new_servings:
            ratio = new_servings / old_servings
        else:
            ratio = 0
        return replace(
            food,
            quantity=new_qty,
            macros=food.macros.scaled(ratio),
            calories=food.calories * ratio,
        )

    def _update_quantity(self, food_name: str, amount: float, unit: Unit) -> EditResult:
        meal, idx, food, day = self._find_food(food_name)
        if food is None:
            return EditResult(False, f"Couldn't find '{food_name}' in today's log.")
        new_qty = Quantity(amount, unit)
        new_food = self._scale_food(food, new_qty)
        self._replace_food(meal, idx, new_food)
        log = self._view_log.handle(day)
        label = _qty_label(amount, unit.value)
        return EditResult(True, f"Updated {food.name} to {label}.\n\n{log.to_text()}")

    def _convert_unit(self, food_name: str, new_unit: Unit) -> EditResult:
        meal, idx, food, day = self._find_food(food_name)
        if food is None:
            return EditResult(False, f"Couldn't find '{food_name}' in today's log.")
        known = self._food_kb.lookup(food.name) if self._food_kb else None
        old_grams = self._to_grams(food.quantity, known)
        if old_grams is None:
            return EditResult(False, f"Can't convert {food.name} to {new_unit.value}.")
        new_amount = self._from_grams(old_grams, new_unit, known)
        if new_amount is None:
            return EditResult(False, f"Can't convert {food.name} to {new_unit.value}.")
        rounded = round(new_amount)
        if abs(new_amount - rounded) < 0.1:
            new_amount = float(rounded)
        else:
            new_amount = round(new_amount, 2)
        new_food = replace(food, quantity=Quantity(new_amount, new_unit))
        self._replace_food(meal, idx, new_food)
        log = self._view_log.handle(day)
        label = _qty_label(new_amount, new_unit.value)
        return EditResult(True, f"Converted {food.name} to {label}.\n\n{log.to_text()}")

    def _rename(self, old_name: str, new_name: str) -> EditResult:
        meal, idx, food, day = self._find_food(old_name)
        if food is None:
            return EditResult(False, f"Couldn't find '{old_name}' in today's log.")
        new_food = replace(food, name=new_name)
        self._replace_food(meal, idx, new_food)
        log = self._view_log.handle(day)
        return EditResult(True, f"Renamed {food.name} to {new_name}.\n\n{log.to_text()}")

    @staticmethod
    def _to_grams(qty: Quantity, known) -> float | None:
        if qty.unit == Unit.GRAM:
            return qty.amount
        if qty.unit == Unit.OUNCE:
            return qty.amount * GRAMS_PER_OUNCE
        if qty.unit in (Unit.SERVING, Unit.PIECE):
            return qty.amount * known.serving_grams if known else None
        if known and qty.unit == known.serving_unit:
            return qty.amount * known.serving_grams
        return None

    @staticmethod
    def _from_grams(grams: float, unit: Unit, known) -> float | None:
        if unit == Unit.GRAM:
            return grams
        if unit == Unit.OUNCE:
            return grams / GRAMS_PER_OUNCE
        if unit in (Unit.SERVING, Unit.PIECE):
            return grams / known.serving_grams if known else None
        if known and unit == known.serving_unit:
            return grams / known.serving_grams
        return None
