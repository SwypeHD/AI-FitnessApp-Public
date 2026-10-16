"""LogMealUseCase — orchestrates deterministic extraction, KB enrichment, optional LLM
gap-fill, multi-turn clarification, and persistence for logging a meal.

Deterministic-first: the rule-based extractor and knowledge base do the work. The LLM is
called ONLY when fields are still missing after deterministic + KB — it is the fallback,
not the primary. The use-case (not any model) owns the state machine of whether enough
information has been gathered. Clarification answers are applied to the exact slot that was
asked about, with USER provenance, so they stick and are never overwritten by later
extraction. Nothing is persisted until the meal is complete, and the confirmation is built
from the meal that was actually saved.
"""

from __future__ import annotations

import uuid

from fitness.application.dto import (
    ConversationState,
    LogMealRequest,
    LogMealResponse,
    LogStatus,
    PendingClarification,
)
from fitness.application.parsing import (
    first_quantity,
    meal_time_in,
    parse_number,
    parse_numbers,
)
from fitness.application.ports.clock import Clock
from fitness.application.ports.extraction import Extractor, LlmClient, LlmError
from fitness.application.ports.nutrition import FoodKnowledgeBase
from fitness.application.ports.repositories import MealRepository
from fitness.application.questions import next_question
from fitness.application.reconciliation import reconcile
from fitness.application.scaling import quantity_to_servings, scaled_nutrition
from fitness.domain.builders import FoodBuilder, MealBuilder
from fitness.domain.candidate import CandidateFood, CandidateMeal
from fitness.domain.meal import Meal
from fitness.domain.value_objects import FieldValue, Macros, Provenance, pick
import logging

log = logging.getLogger(__name__)


class LogMealUseCase:
    def __init__(
        self,
        extractor: Extractor,
        meal_repo: MealRepository,
        clock: Clock,
        food_kb: FoodKnowledgeBase,
        llm: LlmClient | None = None,
    ) -> None:
        self._extractor = extractor
        self._meal_repo = meal_repo
        self._clock = clock
        self._food_kb = food_kb
        self._llm = llm

    def handle(self, request: LogMealRequest) -> LogMealResponse:
        notes: list[str] = []
        state = request.state
        candidate = state.candidate if state is not None else CandidateMeal()
        pending = state.pending if state is not None else None

        if pending is not None:
            if not self._apply_answer(candidate, pending, request.text, notes):
                notes.append("Sorry, I didn't catch that.")
        else:
            extraction = self._extractor.extract(request.text, candidate)
            notes.extend(extraction.notes)
            merged = reconcile([extraction.candidate_meal], prior=candidate)
            notes.extend(merged.notes)
            candidate = merged.candidate

        self._validate_food_names(candidate, request.text, notes)
        self._fill_from_kb(candidate)
        self._fill_from_llm(candidate, request.text, notes)

        builder = _to_builder(candidate)
        missing = builder.missing()
        if missing:
            question = next_question(missing, candidate)
            assert question is not None  # missing is non-empty
            pend, text = question
            return LogMealResponse(
                status=LogStatus.NEEDS_CLARIFICATION,
                message=text,
                state=ConversationState(candidate=candidate, pending=pend),
                notes=_dedup(notes),
            )

        meal = builder.build(meal_id=uuid.uuid4().hex, logged_at=self._clock.now())
        self._meal_repo.save(meal)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=_confirmation(meal),
            meal_id=meal.id,
            notes=_dedup(notes),
        )

    # --- applying a clarification answer to the asked-about slot -------------

    def _apply_answer(
        self,
        candidate: CandidateMeal,
        pending: PendingClarification,
        text: str,
        notes: list[str],
    ) -> bool:
        field = pending.field

        if field == "meal_time":
            slot = meal_time_in(text)
            if slot is None:
                return False
            candidate.meal_time = pick(
                candidate.meal_time, FieldValue(slot, Provenance.USER, 1.0)
            )
            return True

        if field == "foods":
            extraction = self._extractor.extract(text, candidate)
            notes.extend(extraction.notes)
            merged = reconcile([extraction.candidate_meal], prior=candidate).candidate
            candidate.meal_time = merged.meal_time
            candidate.foods = merged.foods
            candidate.raw_turns = merged.raw_turns
            return bool(candidate.foods)

        index = _food_index(pending.target)
        if not (0 <= index < len(candidate.foods)):
            return False
        food = candidate.foods[index]

        if field == "quantity":
            quantity = first_quantity(text)
            if quantity is None:
                return False
            food.offer("quantity", FieldValue(quantity, Provenance.USER, 1.0))
            return True
        if field == "name":
            name = text.strip()
            if not name:
                return False
            food.offer("name", FieldValue(name, Provenance.USER, 1.0))
            return True
        if field == "calories":
            calories = parse_number(text)
            if calories is None:
                return False
            food.offer("calories", FieldValue(calories, Provenance.USER, 1.0))
            return True
        if field == "macros":
            numbers = parse_numbers(text)
            if len(numbers) < 3:
                return False
            macros = Macros(numbers[0], numbers[1], numbers[2])
            food.offer("macros", FieldValue(macros, Provenance.USER, 1.0))
            if food.calories is None:
                # derive calories from the macros the user just gave
                food.offer(
                    "calories",
                    FieldValue(macros.calories_from_macros, Provenance.DEFAULT, 1.0),
                )
            return True
        return False

    # --- LLM food-name validation (safety net for regex misses) -------------

    def _validate_food_names(
        self, candidate: CandidateMeal, raw_input: str, notes: list[str]
    ) -> None:
        if self._llm is None:
            return
        for food in candidate.foods:
            if food.name is None:
                continue
            if food.name.provenance in (Provenance.USER, Provenance.KNOWLEDGE_BASE):
                continue
            if food.macros is not None and food.macros.provenance == Provenance.KNOWLEDGE_BASE:
                continue
            try:
                corrected = self._llm.clean_food_name(raw_input, food.name.value)
            except LlmError:
                continue
            if corrected:
                log.debug("LLM corrected food name %r -> %r", food.name.value, corrected)
                food.name = FieldValue(corrected, Provenance.LLM, 0.8)

    # --- knowledge-base enrichment ------------------------------------------

    def _fill_from_kb(self, candidate: CandidateMeal) -> None:
        """Fill macros/calories for foods that now have a known name + quantity but no
        nutrition yet (e.g. the user supplied a quantity in a clarification turn)."""
        for food in candidate.foods:
            if food.name is None or food.quantity is None or food.macros is not None:
                continue
            known = self._food_kb.lookup(food.name.value)
            if known is None:
                continue
            servings = quantity_to_servings(food.quantity.value, known)
            if servings is None:
                continue
            macros, calories = scaled_nutrition(known, servings)
            food.offer("macros", FieldValue(macros, Provenance.KNOWLEDGE_BASE, 0.9))
            if food.calories is None:
                food.offer(
                    "calories", FieldValue(calories, Provenance.KNOWLEDGE_BASE, 0.9)
                )


    # --- LLM gap-fill (deterministic-first: only called when gaps remain) -----

    def _fill_from_llm(
        self, candidate: CandidateMeal, text: str, notes: list[str]
    ) -> None:
        """Call the LLM only if there are still missing fields after deterministic + KB.

        Swallows ``LlmError`` — the app must work LLM-down. Results are reconciled with
        deterministic-wins (LLM provenance is lower than DETERMINISTIC/KB).
        """
        if self._llm is None:
            return
        builder = _to_builder(candidate)
        if builder.is_complete():
            return  # no gaps — skip the LLM entirely
        try:
            llm_result = self._llm.estimate(text, schema_hint="")
            merged = reconcile([llm_result.candidate_meal], prior=candidate)
            notes.extend(merged.notes)
            # Apply merged fields back into the candidate.
            for i, merged_food in enumerate(merged.candidate.foods):
                if i < len(candidate.foods):
                    for field_name in CandidateFood.FIELDS:
                        candidate.foods[i].offer(field_name, getattr(merged_food, field_name))
                else:
                    candidate.foods.append(merged_food)
            if merged.candidate.meal_time is not None:
                candidate.meal_time = pick(candidate.meal_time, merged.candidate.meal_time)
        except LlmError as e:
            notes.append(f"LLM unavailable: {e}")


def _to_builder(candidate: CandidateMeal) -> MealBuilder:
    builder = MealBuilder(meal_time=candidate.meal_time)
    for food in candidate.foods:
        builder.food_builders.append(
            FoodBuilder(
                name=food.name,
                quantity=food.quantity,
                macros=food.macros,
                calories=food.calories,
            )
        )
    return builder


def _confirmation(meal: Meal) -> str:
    names = ", ".join(f.name for f in meal.foods)
    macros = meal.total_macros
    return (
        f"Logged {meal.meal_time.value}: {names} "
        f"({meal.total_calories:.0f} kcal, {macros.protein_g:.0f}g protein, "
        f"{macros.carbs_g:.0f}g carbs, {macros.fat_g:.0f}g fat)."
    )


def _food_index(target: str) -> int:
    return int(target[len("food[") : -1])


def _dedup(notes: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for note in notes:
        if note not in seen:
            seen.add(note)
            result.append(note)
    return result
