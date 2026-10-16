"""HandleMessageUseCase — the chatbot entry point that routes by intent.

Every inbound message passes through intent classification first. LOG goes to
LogMealUseCase, QUERY to QueryUseCase, CHAT to the LLM (grounded with today's
totals so it talks about real numbers), and EDIT is recognized but deferred.

When the conversation is already mid-clarification (``state`` is not None), we skip
re-classification and continue the LOG flow — the user is answering a question we
asked, not starting a new intent.
"""

from __future__ import annotations

import re

from fitness.application.dto import (
    ConversationState,
    LogMealRequest,
    LogMealResponse,
    LogStatus,
    PendingExerciseState,
    PendingSavedMealItem,
    PendingSavedMealState,
)
from fitness.application.intent import classify_intent
from fitness.application.ports.clock import Clock
from fitness.application.ports.extraction import ChatTurn, Intent, LlmClient, LlmError
from fitness.application.ports.repositories import MealRepository
from fitness.application.use_cases.daily_summary import GetDailySummaryUseCase
from fitness.application.use_cases.edit_log import EditLogUseCase
from fitness.application.use_cases.log_exercise import LogExerciseUseCase
from fitness.application.use_cases.log_meal import LogMealUseCase
from fitness.application.use_cases.query import QueryUseCase
from fitness.application.user_profile import ProfileStore
from fitness.domain.value_objects import MealTimeSlot


class HandleMessageUseCase:
    def __init__(
        self,
        log_meal: LogMealUseCase,
        query: QueryUseCase,
        edit_log: EditLogUseCase | None = None,
        log_exercise: LogExerciseUseCase | None = None,
        edit_exercise=None,
        llm: LlmClient | None = None,
        meal_repo: MealRepository | None = None,
        clock: Clock | None = None,
        profile_store: ProfileStore | None = None,
        saved_meal_store=None,
        exercise_repo=None,
        manage_calendar=None,
        food_kb=None,
        build_plan=None,
        memory_store=None,
    ) -> None:
        self._log_meal = log_meal
        self._query = query
        self._edit_log = edit_log
        self._log_exercise = log_exercise
        self._edit_exercise = edit_exercise
        self._llm = llm
        self._meal_repo = meal_repo
        self._clock = clock
        self._profile_store = profile_store
        self._saved_meal_store = saved_meal_store
        self._exercise_repo = exercise_repo
        self._manage_calendar = manage_calendar
        self._food_kb = food_kb
        self._build_plan = build_plan
        self._memory_store = memory_store

    _CANCEL_WORDS = frozenset({
        "cancel", "nevermind", "never mind", "stop", "abort", "skip", "quit",
        "no", "nah", "nope",
    })

    _CONFIRM_WORDS = frozenset({
        "yes", "y", "yep", "yeah", "sure", "ok", "okay", "confirm",
        "save", "save it", "looks good", "looks great", "do it", "go ahead",
    })

    @classmethod
    def _has_any(cls, text: str, words: frozenset[str]) -> bool:
        lower = text.strip().lower()
        for w in words:
            if " " in w:
                if w in lower:
                    return True
            else:
                if re.search(rf"\b{re.escape(w)}\b", lower):
                    return True
        return False

    def handle(
        self, text: str, state: ConversationState | PendingSavedMealState | None = None
    ) -> LogMealResponse:
        if isinstance(state, PendingExerciseState):
            return self._handle_exercise_clarification(text, state)

        if isinstance(state, PendingSavedMealState):
            result = self._handle_saved_meal_confirmation(text, state)
            if result is not None:
                return result
            state = None

        if state is not None:
            if text.strip().lower() in self._CANCEL_WORDS:
                return LogMealResponse(
                    status=LogStatus.LOGGED,
                    message="No problem, cancelled the pending log.",
                )
            intent = classify_intent(text)
            if intent is not None and intent is not Intent.LOG:
                state = None
            else:
                return self._log_meal.handle(LogMealRequest(text=text, state=state))

        # Memory commands are explicit instructions, so handle them deterministically
        # before any intent guessing — "remember my shoulder is bad" must never be
        # misread as a food log.
        memory_reply = self._try_memory_command(text)
        if memory_reply is not None:
            return LogMealResponse(status=LogStatus.LOGGED, message=memory_reply)

        intent = classify_intent(text)

        if intent is Intent.QUERY:
            return LogMealResponse(
                status=LogStatus.LOGGED, message=self._answer_query(text)
            )

        if intent is Intent.EDIT:
            for handler in (
                self._try_build_plan,
                self._try_exercise_edit,
                self._try_exercise_delete,
                self._try_create_saved_meal,
                self._try_save_meal,
                self._try_delete_saved_meal,
                self._try_set_targets,
                self._try_toggle_units,
                self._try_align_calendar,
            ):
                result = handler(text)
                if result is not None:
                    return result
            if self._edit_log is not None:
                result = self._edit_log.handle(text)
                return LogMealResponse(status=LogStatus.LOGGED, message=result.message)
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message="Editing logs is not available yet.",
            )

        if intent is Intent.CALENDAR:
            return self._handle_calendar(text)

        if intent is Intent.EXERCISE:
            if self._log_exercise is not None:
                result = self._log_exercise.handle(text)
                if result.state:
                    return LogMealResponse(
                        status=LogStatus.NEEDS_CLARIFICATION,
                        message=result.message,
                        state=result.state,
                    )
                return LogMealResponse(status=LogStatus.LOGGED, message=result.message)
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message="Exercise logging is not available yet.",
            )

        if intent is Intent.CHAT:
            return LogMealResponse(
                status=LogStatus.LOGGED, message=self._chat(text)
            )

        if intent is None:
            for handler in (
                self._try_set_targets,
                self._try_toggle_units,
            ):
                result = handler(text)
                if result is not None:
                    return result
            profile_update = self._try_parse_profile(text)
            if profile_update:
                return LogMealResponse(status=LogStatus.LOGGED, message=profile_update)

        if intent is None and self._llm is not None:
            try:
                intent = self._llm.classify_intent(text)
            except LlmError:
                intent = Intent.LOG  # LLM down — safest default

        if intent is None:
            intent = Intent.LOG

        if intent is Intent.QUERY:
            return LogMealResponse(
                status=LogStatus.LOGGED, message=self._answer_query(text)
            )
        if intent is Intent.EXERCISE and self._log_exercise is not None:
            result = self._log_exercise.handle(text)
            if result.state:
                return LogMealResponse(
                    status=LogStatus.NEEDS_CLARIFICATION,
                    message=result.message,
                    state=result.state,
                )
            return LogMealResponse(status=LogStatus.LOGGED, message=result.message)
        if intent is Intent.CHAT:
            return LogMealResponse(
                status=LogStatus.LOGGED, message=self._chat(text)
            )

        saved = self._try_log_saved_meal(text)
        if saved is not None:
            return saved

        return self._log_meal.handle(LogMealRequest(text=text))

    def _try_log_saved_meal(self, text: str) -> LogMealResponse | None:
        if self._saved_meal_store is None or self._meal_repo is None or self._clock is None:
            return None

        import re
        import uuid
        from datetime import datetime

        from fitness.domain.food import Food
        from fitness.domain.meal import Meal
        from fitness.domain.value_objects import Macros, Quantity, Unit

        cleaned = re.sub(
            r"^(i\s+)?(had|ate|eaten|log|just had)\s+", "", text.strip(), flags=re.IGNORECASE,
        ).strip()

        match = self._saved_meal_store.find_by_name(cleaned)
        if match is None:
            return None

        slot = self._parse_meal_time(text) or MealTimeSlot.SNACK
        foods = []
        for item in match.items:
            foods.append(Food(
                name=item.food_name,
                quantity=Quantity(item.quantity_g, Unit.GRAM),
                macros=Macros(protein_g=item.protein_g, carbs_g=item.carbs_g, fat_g=item.fat_g),
                calories=item.calories,
                meal_time=slot,
            ))
        meal = Meal(
            id=uuid.uuid4().hex[:8],
            logged_at=datetime.now(),
            meal_time=slot,
            foods=tuple(foods),
        )
        self._meal_repo.save(meal)
        items_str = ", ".join(f"{i.food_name} ({i.quantity_g}g)" for i in match.items)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=f"Logged your saved meal \"{match.name}\" for {slot.value}: {items_str}.",
            meal_id=meal.id,
        )

    @staticmethod
    def _parse_meal_time(text: str) -> MealTimeSlot | None:
        lower = text.lower()
        for slot in MealTimeSlot:
            if slot.value in lower:
                return slot
        return None

    _PLAN_KEYWORDS_RE = re.compile(
        r"\b(?:plan|routine|split|program|schedule)\b", re.I,
    )

    def _try_build_plan(self, text: str) -> LogMealResponse | None:
        """Try to handle the message as a plan builder action."""
        if self._build_plan is None:
            return None
        result = self._build_plan.handle(text)
        if result is None:
            return None
        if result.success:
            return LogMealResponse(status=LogStatus.LOGGED, message=result.message)
        if self._PLAN_KEYWORDS_RE.search(text):
            return LogMealResponse(status=LogStatus.LOGGED, message=result.message)
        return None

    def _try_exercise_delete(self, text: str) -> LogMealResponse | None:
        """Try to delete an exercise by name from today's log."""
        if self._exercise_repo is None or self._clock is None:
            return None
        import re
        from fitness.domain.naming import normalize_food_name

        match = re.search(
            r"\b(?:delete|remove|undo|cancel)\b\s+(?:the\s+|my\s+)?(?:exercise\s+)?(.+?)(?:\s+exercise)?$",
            text.strip(), re.I,
        )
        if not match:
            return None
        name = match.group(1).strip()
        target = normalize_food_name(name)
        day = self._clock.today()
        exercises = self._exercise_repo.list_by_date(day)
        for ex in exercises:
            if normalize_food_name(ex.name) == target:
                self._exercise_repo.delete_by_name(day, ex.name)
                return LogMealResponse(
                    status=LogStatus.LOGGED,
                    message=f"Deleted exercise: {ex.name}.",
                )
        return None

    _EXERCISE_EDIT_RE = re.compile(
        r"\b(?:change|update|set|edit|add|remove|actually|used)\b.*\b(?:set|reps?|weight|bench|squat|deadlift|curl|press|row|pullup|push\s*up|lunge)\b",
        re.I,
    )

    def _try_exercise_edit(self, text: str) -> LogMealResponse | None:
        if self._edit_exercise is None:
            return None
        if not self._EXERCISE_EDIT_RE.search(text):
            return None
        result = self._edit_exercise.handle(text)
        if result.success:
            return LogMealResponse(status=LogStatus.LOGGED, message=result.message)
        return None

    # --- Saved meal creation from KB (preview → confirm flow) ---

    _CREATE_SAVED_MEAL_RE = re.compile(
        r"\b(?:create|make)\b\s+(?:a\s+)?(?:saved\s+)?meal\s+(?:called|named)\s+"
        r"(.+?)\s+with\s+(.+)",
        re.I,
    )
    _CREATE_SAVED_MEAL_RE2 = re.compile(
        r"\b(?:create|make)\b\s+(?:a\s+)?(?:saved\s+)?meal\s+with\s+(.+?)\s+(?:called|named)\s+(.+)",
        re.I,
    )

    _MODIFY_QUANTITY_RE = re.compile(
        r"\b(?:change|update|set|make)\b\s+(?:the\s+)?(.+?)\s+to\s+(\d+(?:\.\d+)?)\s*g",
        re.I,
    )
    _REMOVE_ITEM_RE = re.compile(
        r"\b(?:remove|drop|delete)\b\s+(?:the\s+)?(.+)",
        re.I,
    )

    def _handle_exercise_clarification(
        self, text: str, state: PendingExerciseState
    ) -> LogMealResponse:
        lower = text.strip().lower()
        if lower in self._CANCEL_WORDS:
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message="No problem, cancelled the exercise log.",
            )
        if self._log_exercise is not None:
            result = self._log_exercise.continue_handle(text, state)
            if result.state:
                return LogMealResponse(
                    status=LogStatus.NEEDS_CLARIFICATION,
                    message=result.message,
                    state=result.state,
                )
            return LogMealResponse(status=LogStatus.LOGGED, message=result.message)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message="Exercise logging is not available.",
        )

    def _handle_saved_meal_confirmation(
        self, text: str, state: PendingSavedMealState
    ) -> LogMealResponse | None:
        lower = text.strip().lower()
        is_cancel = self._has_any(lower, self._CANCEL_WORDS)
        is_confirm = self._has_any(lower, self._CONFIRM_WORDS)
        if is_cancel and not is_confirm:
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message="No problem, cancelled the saved meal.",
            )
        if is_confirm and not is_cancel:
            return self._save_pending_meal(state)

        modified = self._try_modify_pending_meal(text, state)
        if modified is not None:
            return modified

        intent = classify_intent(text)
        if intent is not None and intent is not Intent.CHAT:
            return None

        return LogMealResponse(
            status=LogStatus.NEEDS_CLARIFICATION,
            message="Would you like to save this meal? You can also:\n"
            "• Change an item: \"change chicken to 300g\"\n"
            "• Remove an item: \"remove the rice\"\n"
            "• Say \"yes\" to save or \"no\" to cancel.",
            state=state,
        )

    @staticmethod
    def _match_pending_item(target: str, food_name: str) -> bool:
        from fitness.domain.naming import normalize_food_name
        t = normalize_food_name(target)
        f = normalize_food_name(food_name)
        return t == f or t in f or f in t

    def _try_modify_pending_meal(
        self, text: str, state: PendingSavedMealState
    ) -> LogMealResponse | None:
        remove = self._REMOVE_ITEM_RE.search(text)
        if remove:
            target = remove.group(1).strip()
            new_items = [i for i in state.items if not self._match_pending_item(target, i.food_name)]
            if len(new_items) == len(state.items):
                return LogMealResponse(
                    status=LogStatus.NEEDS_CLARIFICATION,
                    message=f"Couldn't find '{remove.group(1).strip()}' in the preview. "
                    f"Items: {', '.join(i.food_name for i in state.items)}.",
                    state=state,
                )
            if not new_items:
                return LogMealResponse(
                    status=LogStatus.LOGGED,
                    message="All items removed — cancelled the saved meal.",
                )
            new_state = PendingSavedMealState(name=state.name, items=new_items)
            return self._rebuild_preview(new_state)

        modify = self._MODIFY_QUANTITY_RE.search(text)
        if modify and self._food_kb is not None:
            target = modify.group(1).strip()
            new_grams = float(modify.group(2))
            new_items = []
            found = False
            for item in state.items:
                if self._match_pending_item(target, item.food_name) and not found:
                    found = True
                    known = self._food_kb.lookup(item.food_name)
                    if known is not None and known.serving_grams > 0:
                        servings = new_grams / known.serving_grams
                        m = known.macros_per_serving
                        new_items.append(PendingSavedMealItem(
                            food_name=item.food_name,
                            quantity_amount=round(new_grams, 1),
                            quantity_unit="g",
                            calories=round(known.calories_per_serving * servings, 1),
                            protein_g=round(m.protein_g * servings, 1),
                            carbs_g=round(m.carbs_g * servings, 1),
                            fat_g=round(m.fat_g * servings, 1),
                        ))
                    else:
                        new_items.append(item)
                else:
                    new_items.append(item)
            if not found:
                return LogMealResponse(
                    status=LogStatus.NEEDS_CLARIFICATION,
                    message=f"Couldn't find '{target}' in the preview. "
                    f"Items: {', '.join(i.food_name for i in state.items)}.",
                    state=state,
                )
            new_state = PendingSavedMealState(name=state.name, items=new_items)
            return self._rebuild_preview(new_state)

        return None

    def _rebuild_preview(self, state: PendingSavedMealState) -> LogMealResponse:
        lines = [f"Updated preview of \"{state.name}\":"]
        total_cal = total_p = total_c = total_f = 0.0
        for item in state.items:
            lines.append(
                f"  • {item.food_name} ({item.quantity_amount}g) — "
                f"{item.calories} kcal, {item.protein_g}g P / {item.carbs_g}g C / {item.fat_g}g F"
            )
            total_cal += item.calories
            total_p += item.protein_g
            total_c += item.carbs_g
            total_f += item.fat_g
        lines.append(
            f"Total: {round(total_cal, 1)} kcal, "
            f"{round(total_p, 1)}g protein / {round(total_c, 1)}g carbs / {round(total_f, 1)}g fat"
        )
        lines.append("Save this meal? (yes/no)")
        return LogMealResponse(
            status=LogStatus.NEEDS_CLARIFICATION,
            message="\n".join(lines),
            state=state,
        )

    def _save_pending_meal(self, state: PendingSavedMealState) -> LogMealResponse:
        if self._saved_meal_store is None:
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message="Saved meal storage is not available.",
            )
        import uuid
        from fitness.domain.saved_meal import SavedMeal, SavedMealItem

        items = [
            SavedMealItem(
                food_name=item.food_name,
                quantity_g=item.quantity_amount,
                calories=item.calories,
                protein_g=item.protein_g,
                carbs_g=item.carbs_g,
                fat_g=item.fat_g,
            )
            for item in state.items
        ]
        saved = SavedMeal(id=uuid.uuid4().hex[:8], name=state.name, items=items)
        self._saved_meal_store.save_meal(saved)
        food_list = ", ".join(i.food_name for i in items)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=f"Saved meal \"{state.name}\" with {len(items)} item(s): {food_list}.",
        )

    def _try_create_saved_meal(self, text: str) -> LogMealResponse | None:
        """Parse 'create a saved meal called X with Y' and return a preview for confirmation."""
        if self._food_kb is None or self._saved_meal_store is None:
            return None

        # Try "meal called X with foods" first, then "meal with foods called X"
        match = self._CREATE_SAVED_MEAL_RE.search(text)
        if match:
            meal_name = match.group(1).strip().strip('"\'')
            foods_text = match.group(2).strip()
        else:
            match = self._CREATE_SAVED_MEAL_RE2.search(text)
            if not match:
                return None
            foods_text = match.group(1).strip()
            meal_name = match.group(2).strip().strip('"\'')

        from fitness.application.parsing import parse_quantity_and_remainder
        from fitness.application.scaling import quantity_to_servings, scaled_nutrition

        # Split on comma and/or "and"
        raw_items = re.split(r"\s*,\s*|\s+and\s+", foods_text)
        items: list[PendingSavedMealItem] = []
        unknown: list[str] = []

        for raw in raw_items:
            raw = raw.strip()
            if not raw:
                continue
            quantity, remainder = parse_quantity_and_remainder(raw)
            food_name = remainder.strip()
            if not food_name:
                continue

            known = self._food_kb.lookup(food_name)
            if known is None:
                unknown.append(food_name)
                continue

            if quantity is None:
                # Default to 1 serving
                from fitness.domain.value_objects import Quantity, Unit
                quantity = Quantity(1, Unit.SERVING)

            servings = quantity_to_servings(quantity, known)
            if servings is None:
                unknown.append(food_name)
                continue

            macros, calories = scaled_nutrition(known, servings)
            # Convert to grams for storage
            quantity_g = quantity.amount
            if quantity.unit.value == "g":
                quantity_g = quantity.amount
            elif quantity.unit.value == "oz":
                from fitness.application.scaling import GRAMS_PER_OUNCE
                quantity_g = quantity.amount * GRAMS_PER_OUNCE
            else:
                quantity_g = servings * known.serving_grams

            items.append(PendingSavedMealItem(
                food_name=known.name,
                quantity_amount=round(quantity_g, 1),
                quantity_unit="g",
                calories=round(calories, 1),
                protein_g=round(macros.protein_g, 1),
                carbs_g=round(macros.carbs_g, 1),
                fat_g=round(macros.fat_g, 1),
            ))

        if not items and unknown:
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message=f"I couldn't find these foods in the knowledge base: {', '.join(unknown)}. "
                "Try using common food names like 'chicken breast', 'rice', 'eggs', etc.",
            )
        if not items:
            return None

        # Build preview message
        lines = [f"Here's a preview of \"{meal_name}\":"]
        total_cal = 0.0
        total_p = 0.0
        total_c = 0.0
        total_f = 0.0
        for item in items:
            lines.append(
                f"  • {item.food_name} ({item.quantity_amount}g) — "
                f"{item.calories} kcal, {item.protein_g}g P / {item.carbs_g}g C / {item.fat_g}g F"
            )
            total_cal += item.calories
            total_p += item.protein_g
            total_c += item.carbs_g
            total_f += item.fat_g
        lines.append(
            f"Total: {round(total_cal, 1)} kcal, "
            f"{round(total_p, 1)}g protein / {round(total_c, 1)}g carbs / {round(total_f, 1)}g fat"
        )
        if unknown:
            lines.append(f"(Could not find: {', '.join(unknown)})")
        lines.append("Save this meal? (yes/no)")

        state = PendingSavedMealState(name=meal_name, items=items)
        return LogMealResponse(
            status=LogStatus.NEEDS_CLARIFICATION,
            message="\n".join(lines),
            state=state,
        )

    _SAVE_MEAL_RE = re.compile(
        r"\bsave\b.*?\b(?:today'?s?\s+)?(breakfast|lunch|dinner|snack)?\s*(?:as|called)\s+(.+)",
        re.I,
    )
    _DELETE_SAVED_MEAL_RE = re.compile(
        r"\b(?:delete|remove)\b\s+(?:the\s+)?(?:saved\s+)?meal\s+(.+)",
        re.I,
    )

    def _try_save_meal(self, text: str) -> LogMealResponse | None:
        if self._saved_meal_store is None or self._meal_repo is None or self._clock is None:
            return None
        match = self._SAVE_MEAL_RE.search(text)
        if not match:
            return None
        import uuid
        from fitness.domain.saved_meal import SavedMeal, SavedMealItem
        slot_word = match.group(1)
        meal_name = match.group(2).strip().strip('"\'')
        day = self._clock.today()
        meals = self._meal_repo.list_by_date(day)
        if slot_word:
            slot = MealTimeSlot(slot_word.lower())
            foods = [f for m in meals if m.meal_time == slot for f in m.foods]
        else:
            foods = [f for m in meals for f in m.foods]
        if not foods:
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message=f"No foods found in {'today' if not slot_word else slot_word} to save.",
            )
        items = [
            SavedMealItem(
                food_name=f.name,
                quantity_g=f.quantity.amount,
                calories=f.calories,
                protein_g=f.macros.protein_g,
                carbs_g=f.macros.carbs_g,
                fat_g=f.macros.fat_g,
            )
            for f in foods
        ]
        saved = SavedMeal(id=uuid.uuid4().hex[:8], name=meal_name, items=items)
        self._saved_meal_store.save_meal(saved)
        food_list = ", ".join(i.food_name for i in items)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=f"Saved meal \"{meal_name}\" with {len(items)} item(s): {food_list}.",
        )

    def _try_delete_saved_meal(self, text: str) -> LogMealResponse | None:
        if self._saved_meal_store is None:
            return None
        match = self._DELETE_SAVED_MEAL_RE.search(text)
        if not match:
            return None
        name = match.group(1).strip().strip('"\'')
        meal = self._saved_meal_store.find_by_name(name)
        if meal is None:
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message=f"Couldn't find a saved meal matching '{name}'.",
            )
        self._saved_meal_store.delete_meal(meal.id)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=f"Deleted saved meal \"{meal.name}\".",
        )

    _TARGET_RE = re.compile(
        r"(?:set|change|update)?\s*(?:my\s+)?(?:daily\s+)?"
        r"(calorie|protein|carb|fat)\s*(?:target|goal)?\s*(?:to\s+)?(\d+)",
        re.I,
    )
    _TARGET_REVERSE_RE = re.compile(
        r"(\d+)\s*(?:kcal|cal|calories?)\s*(?:per\s+day|daily|a\s+day)?",
        re.I,
    )
    _TARGET_SHOULD_RE = re.compile(
        r"\b(?:calories?|protein|carbs?|fat)\b.*\b(?:should|around|about|be)\b.*?(\d+)",
        re.I,
    )
    _TARGET_BULK_RE = re.compile(
        r"(\d+)\s*(?:kcal|cal|calories?)\b.*?"
        r"(\d+)\s*g?\s*protein\b.*?"
        r"(\d+)\s*g?\s*carbs?\b.*?"
        r"(\d+)\s*g?\s*fat\b",
        re.I,
    )

    def _try_set_targets(self, text: str) -> LogMealResponse | None:
        if self._profile_store is None:
            return None
        profile = self._profile_store.load()
        updated = []
        bulk = self._TARGET_BULK_RE.search(text)
        if bulk:
            profile.calorie_target = int(bulk.group(1))
            profile.protein_target_g = int(bulk.group(2))
            profile.carbs_target_g = int(bulk.group(3))
            profile.fat_target_g = int(bulk.group(4))
            updated = ["calorie target", "protein target", "carbs target", "fat target"]
        else:
            for m in self._TARGET_RE.finditer(text):
                field = m.group(1).lower()
                val = int(m.group(2))
                if field == "calorie":
                    profile.calorie_target = val
                    updated.append("calorie target")
                elif field == "protein":
                    profile.protein_target_g = val
                    updated.append("protein target")
                elif field == "carb":
                    profile.carbs_target_g = val
                    updated.append("carbs target")
                elif field == "fat":
                    profile.fat_target_g = val
                    updated.append("fat target")
            if not updated:
                m = self._TARGET_REVERSE_RE.search(text)
                if not m:
                    m = self._TARGET_SHOULD_RE.search(text)
                if m:
                    profile.calorie_target = int(m.group(1))
                    updated.append("calorie target")
        if not updated:
            return None
        self._profile_store.save(profile)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=f"Updated {', '.join(updated)}: "
            f"{profile.calorie_target} kcal, "
            f"{profile.protein_target_g}g protein, "
            f"{profile.carbs_target_g}g carbs, "
            f"{profile.fat_target_g}g fat.",
        )

    _UNIT_TOGGLE_RE = re.compile(
        r"\b(?:switch|change|use|set|convert|prefer)\b.*\b(metric|imperial|kg|lbs|pounds?|kilos?|kilometers?|miles?)\b",
        re.I,
    )

    def _try_toggle_units(self, text: str) -> LogMealResponse | None:
        if self._profile_store is None:
            return None
        match = self._UNIT_TOGGLE_RE.search(text)
        if not match:
            return None
        val = match.group(1).lower()
        profile = self._profile_store.load()
        if val in ("metric", "kg", "kilos", "kilometers"):
            profile.unit_system = "metric"
        elif val in ("imperial", "lbs", "pounds", "miles"):
            profile.unit_system = "imperial"
        else:
            return None
        profile.sync_units()
        self._profile_store.save(profile)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=f"Switched to {profile.unit_system} units.",
        )

    _ALIGN_RE = re.compile(
        r"\balign\b\s+(?:to\s+|calendar\s+to\s+)?(.+)",
        re.I,
    )

    def _try_align_calendar(self, text: str) -> LogMealResponse | None:
        if self._manage_calendar is None:
            return None
        match = self._ALIGN_RE.search(text)
        if not match:
            return None
        from fitness.domain.naming import normalize_food_name
        target_label = match.group(1).strip().rstrip(".")
        target_norm = normalize_food_name(target_label)
        cal = self._manage_calendar.get_calendar()
        if cal is None:
            return LogMealResponse(status=LogStatus.LOGGED, message="No active calendar.")
        for opt in cal.get("rotation", []):
            if normalize_food_name(opt["label"]) == target_norm:
                result = self._manage_calendar.align(opt["index"])
                if result is None:
                    return LogMealResponse(status=LogStatus.LOGGED, message="Couldn't align calendar.")
                return LogMealResponse(
                    status=LogStatus.LOGGED,
                    message=f"Aligned calendar to {opt['label']} day.",
                )
        labels = ", ".join(o["label"] for o in cal.get("rotation", []))
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=f"Couldn't find '{target_label}' in your rotation. Available: {labels}.",
        )

    _SKIP_RE = re.compile(r"\bskip\b.*\b(?:today|workout|day)\b", re.I)
    _SKIP_TO_TODAY_RE = re.compile(r"\b(?:skip|catch\s*up)\b.*\bto\s*today\b", re.I)
    _PUSH_BACK_RE = re.compile(r"\bpush\s*back\b.*\b(?:today|workout|day)\b", re.I)
    _PUSH_BACK_TO_TODAY_RE = re.compile(r"\b(?:push\s*back|shift)\b.*\bto\s*today\b", re.I)
    _COMPLETE_RE = re.compile(
        r"\b(?:mark|done|complete|finished)\b.*\b(?:today|workout|day)\b"
        r"|\b(?:i'?m|i\s+am)\b\s+(?:done|finished)\b",
        re.I,
    )
    _ACTIVATE_RE = re.compile(
        r"\b(?:activate|start|switch\s+to|use)\b\s+(?:the\s+)?(.+?)(?:\s+plan)?$",
        re.I,
    )
    _UNDO_CAL_RE = re.compile(r"\bundo\b", re.I)

    def _handle_calendar(self, text: str) -> LogMealResponse:
        if self._manage_calendar is None:
            return LogMealResponse(
                status=LogStatus.LOGGED,
                message="Calendar management is not available.",
            )

        if self._SKIP_TO_TODAY_RE.search(text):
            result = self._manage_calendar.skip_to_today()
            if result is None:
                return LogMealResponse(status=LogStatus.LOGGED, message="No active calendar. Activate a plan first.")
            view, count = result
            msg = f"Skipped {count} missed day{'s' if count != 1 else ''} and caught up to today." if count else "No missed days to skip — you're up to date!"
            today_entry = next((e for e in view["entries"] if e["is_today"]), None)
            if today_entry:
                msg += f"\nToday: {today_entry['label']}."
            return LogMealResponse(status=LogStatus.LOGGED, message=msg)

        if self._PUSH_BACK_TO_TODAY_RE.search(text):
            result = self._manage_calendar.push_back_to_today()
            if result is None:
                return LogMealResponse(status=LogStatus.LOGGED, message="No active calendar. Activate a plan first.")
            view, count = result
            msg = f"Pushed back {count} missed day{'s' if count != 1 else ''} to today." if count else "No missed days to push back — you're up to date!"
            today_entry = next((e for e in view["entries"] if e["is_today"]), None)
            if today_entry:
                msg += f"\nToday: {today_entry['label']}."
            return LogMealResponse(status=LogStatus.LOGGED, message=msg)

        if self._SKIP_RE.search(text):
            result = self._manage_calendar.skip_day()
            if result is None:
                return LogMealResponse(status=LogStatus.LOGGED, message="No active calendar. Activate a plan first.")
            today_entry = next((e for e in result["entries"] if e.get("date") == result["today"]), None)
            msg = "Skipped today's workout."
            if today_entry:
                msg += f" Tomorrow: {today_entry['label']}." if not today_entry["is_today"] else ""
            return LogMealResponse(status=LogStatus.LOGGED, message=msg)

        if self._PUSH_BACK_RE.search(text):
            result = self._manage_calendar.push_back()
            if result is None:
                return LogMealResponse(status=LogStatus.LOGGED, message="No active calendar. Activate a plan first.")
            msg = "Pushed back today's workout — it'll be next in your rotation."
            today_entry = next((e for e in result["entries"] if e["is_today"]), None)
            if today_entry:
                msg += f"\nToday is now: {today_entry['label']}."
            return LogMealResponse(status=LogStatus.LOGGED, message=msg)

        if self._COMPLETE_RE.search(text):
            result = self._manage_calendar.complete_day()
            if result is None:
                return LogMealResponse(status=LogStatus.LOGGED, message="No active calendar. Activate a plan first.")
            today_entry = next((e for e in result["entries"] if e["is_today"]), None)
            label = today_entry["label"] if today_entry else "today"
            return LogMealResponse(status=LogStatus.LOGGED, message=f"Marked {label} as complete. Nice work!")

        if self._UNDO_CAL_RE.search(text):
            result = self._manage_calendar.undo()
            if result is None:
                return LogMealResponse(status=LogStatus.LOGGED, message="Nothing to undo.")
            return LogMealResponse(status=LogStatus.LOGGED, message="Undone! Calendar restored to previous state.")

        activate = self._ACTIVATE_RE.search(text)
        if activate:
            return self._activate_plan(activate.group(1).strip())

        return LogMealResponse(
            status=LogStatus.LOGGED,
            message="I didn't understand that calendar action. Try:\n"
            "• 'skip today'\n"
            "• 'push back today'\n"
            "• 'mark today complete' / 'I'm done'\n"
            "• 'skip to today' (catch up missed days)\n"
            "• 'push back to today'\n"
            "• 'activate PPL'\n"
            "• 'undo skip/push back'",
        )

    def _activate_plan(self, plan_text: str) -> LogMealResponse:
        from fitness.domain.naming import normalize_food_name
        plans = self._manage_calendar._store.list_plans()
        target = normalize_food_name(plan_text)
        for plan in plans:
            if normalize_food_name(plan.name) == target or normalize_food_name(plan.id) == target:
                result = self._manage_calendar.activate_plan(plan.id)
                if result is None:
                    return LogMealResponse(status=LogStatus.LOGGED, message=f"Couldn't activate '{plan.name}'.")
                view = self._manage_calendar.get_calendar()
                return LogMealResponse(
                    status=LogStatus.LOGGED,
                    message=f"Activated {plan.name}! Your schedule is set.",
                )
        plan_names = ", ".join(p.name for p in plans)
        return LogMealResponse(
            status=LogStatus.LOGGED,
            message=f"Couldn't find a plan matching '{plan_text}'. Available plans: {plan_names}.",
        )

    def _answer_query(self, text: str) -> str:
        """Answer a data question. Uses the LLM with grounding for natural language;
        falls back to the deterministic summary when no LLM is available."""
        if self._llm is not None:
            return self._chat(text)
        return self._query.handle(text)

    def _chat(self, text: str) -> str:
        if self._llm is None:
            return (
                "I'm a food logging assistant. Try telling me what you ate! "
                "(Chat mode requires an LLM connection.)"
            )

        profile_update = self._try_parse_profile(text)
        if profile_update:
            return profile_update

        grounding = self._build_grounding()
        try:
            return self._llm.chat(
                [ChatTurn(role="user", content=text)], grounding=grounding
            )
        except LlmError:
            return "Sorry, I couldn't reach the AI right now. Try logging some food instead!"

    _PROFILE_PATTERNS: list[tuple[str, str, type]] = [
        (r"(?:i'?m|i am|my name is|name:?)\s+([A-Z][a-z]+)", "name", str),
        (r"(\d{1,3})\s*(?:years?\s*old|yo|y/?o)", "age", int),
        (r"(?:i'?m|i am)\s+(\d{1,3})\b", "age", int),
        (r"\b(male|female|man|woman|guy|girl)\b", "gender", str),
        (r"(\d{2,3})\s*(?:cm|centimeters?)\b", "height_cm", float),
        (r"(\d)'(\d{1,2})\"?", "_height_imperial", str),
        (r"(\d)\s*(?:ft|feet)\s*(\d{1,2})\s*(?:in|inches?)?", "_height_imperial", str),
        (r"(\d{2,3})\s*(?:lbs?|pounds?)\b", "weight_lbs", float),
        (r"(\d{2,3})\s*(?:kg|kilos?|kilograms?)\b", "weight_kg", float),
        (r"(?:goal|trying to|want to)\s+(lose\s*(?:weight|fat)|build\s*muscle|bulk|cut|maintain|recomp)", "fitness_goal", str),
        (r"\b(sedentary|lightly\s*active|moderately?\s*active|very\s*active|athlete)\b", "activity_level", str),
        (r"\b(beginner|intermediate|advanced|novice)\b", "experience_level", str),
    ]

    def _try_parse_profile(self, text: str) -> str | None:
        """Regex-first profile extraction, verified by a single model call."""
        import re

        if self._profile_store is None:
            return None

        is_question = "?" in text and re.search(
            r"\b(?:how|what|should|can|do|does|would|is|are)\b", text, re.I,
        )

        parsed: dict = {}
        lower = text.lower()
        for pattern, field, typ in self._PROFILE_PATTERNS:
            if is_question and field == "fitness_goal":
                continue
            m = re.search(pattern, text if typ is str and field == "name" else lower)
            if not m:
                continue
            if field == "_height_imperial":
                parsed["height_ft"] = int(m.group(1))
                parsed["height_in"] = int(m.group(2))
            elif field == "gender":
                val = m.group(1).lower()
                parsed["gender"] = "male" if val in ("male", "man", "guy") else "female" if val in ("female", "woman", "girl") else val
            else:
                parsed[field] = typ(m.group(1))

        if not parsed:
            return None

        _UNIT_FIELDS = {"height_ft", "height_in", "height_cm", "weight_lbs", "weight_kg", "age"}
        if self._llm is not None:
            try:
                verified = self._llm.verify_profile(parsed)
            except LlmError:
                verified = True
            if not verified:
                if parsed.keys() <= _UNIT_FIELDS:
                    verified = True
                else:
                    return None

        profile = self._profile_store.load()
        _VALID_FIELDS = {f for f in profile.__dataclass_fields__}
        updated_fields = []
        for key, val in parsed.items():
            if key not in _VALID_FIELDS:
                continue
            if val is None or val == "" or val == 0:
                continue
            setattr(profile, key, val)
            updated_fields.append(key)

        if not updated_fields:
            return None

        if any(f in updated_fields for f in ("height_ft", "height_in", "weight_lbs")):
            profile.unit_system = "imperial"
        profile.sync_units()
        self._profile_store.save(profile)

        friendly = [f.replace("_", " ").replace(" g", "g").replace(" cm", "cm")
                     for f in updated_fields if not f.startswith("unit_")]
        return f"Got it! I've updated your profile: {', '.join(friendly)}."

    # "remember that X" / "don't forget X" / "keep in mind X" / "note that X"
    _MEMORY_ADD_RE = re.compile(
        r"^\s*(?:please\s+)?(?:remember|note|keep\s+in\s+mind|don'?t\s+forget)"
        r"(?:\s+(?:that|this)\b)?[:,]?\s+(.+?)\s*[.!]?\s*$",
        re.I,
    )
    _MEMORY_FORGET_RE = re.compile(
        r"^\s*(?:please\s+)?forget(?:\s+(?:about|that))?[:,]?\s+(.+?)\s*[.!]?\s*$",
        re.I,
    )
    _MEMORY_FORGET_ALL_RE = re.compile(
        r"^\s*(?:please\s+)?forget\s+everything(?:\s+about\s+me)?\s*[.!]?\s*$", re.I
    )
    _MEMORY_RECALL_RE = re.compile(
        r"^\s*what\s+(?:do\s+you\s+(?:remember|know)"
        r"|have\s+i\s+told\s+you)"
        r"(?:\s+about\s+me)?\s*\??\s*$",
        re.I,
    )

    def _try_memory_command(self, text: str) -> str | None:
        """Handle explicit memory instructions. Returns None if this isn't one."""
        if self._memory_store is None:
            return None

        if self._MEMORY_RECALL_RE.match(text):
            memories = self._memory_store.list_all()
            if not memories:
                return (
                    "Nothing saved yet. Tell me something like "
                    "\"remember my left shoulder is bad\" and I'll hang onto it."
                )
            lines = "\n".join(f"- {m.text}" for m in memories)
            return f"Here's what I'm holding onto:\n{lines}"

        if self._MEMORY_FORGET_ALL_RE.match(text):
            count = self._memory_store.clear()
            if not count:
                return "There wasn't anything saved."
            return f"Cleared all {count} note(s)."

        forget = self._MEMORY_FORGET_RE.match(text)
        if forget:
            term = forget.group(1).strip()
            removed = self._memory_store.remove_matching(term)
            if not removed:
                return f"I don't have anything saved about \"{term}\"."
            if len(removed) == 1:
                return f"Forgotten: {removed[0].text}"
            return f"Forgot {len(removed)} notes about \"{term}\"."

        add = self._MEMORY_ADD_RE.match(text)
        if add:
            fact = add.group(1).strip()
            if not fact:
                return None
            from fitness.domain.coach_memory import CoachMemory

            from datetime import date

            today = self._clock.today() if self._clock is not None else date.today()
            stored = self._memory_store.add(CoachMemory(text=fact, created=today))
            if not stored:
                return f"Already had that one: {fact}"
            return f"Got it — I'll remember that {fact.rstrip('.')}."

        return None

    @staticmethod
    def _format_food_line(food) -> str:
        qty = getattr(food, "quantity", None)
        qty_text = f" ({qty})" if qty else ""
        return f"{food.name}{qty_text} — {food.calories:.0f} kcal, {food.macros.protein_g:.0f}p/{food.macros.carbs_g:.0f}c/{food.macros.fat_g:.0f}f"

    def _food_detail(self, day) -> str | None:
        """Every item logged on ``day``, grouped by slot.

        Totals alone let the model invent plausible-sounding items when asked "what
        did I eat for lunch?", so the actual names have to be in the grounding.
        """
        if self._meal_repo is None:
            return None
        meals = self._meal_repo.list_by_date(day)
        if not meals:
            return None

        by_slot: dict[str, list[str]] = {}
        for meal in meals:
            for food in meal.foods:
                by_slot.setdefault(meal.meal_time.value, []).append(
                    self._format_food_line(food)
                )
        lines = []
        for slot in ("breakfast", "lunch", "dinner", "snack"):
            if by_slot.get(slot):
                items = "; ".join(by_slot[slot])
                lines.append(f"  {slot}: {items}")
        if not lines:
            return None
        return "EXACT FOOD LOG (these are the only items logged):\n" + "\n".join(lines)

    def _exercise_detail(self, day) -> str:
        """Exercises logged on ``day``, or an explicit statement that there were none."""
        if self._exercise_repo is None:
            return ""
        exercises = self._exercise_repo.list_by_date(day)
        if not exercises:
            return "EXERCISE LOG: nothing logged today."
        lines = []
        for e in exercises:
            bits = []
            if e.set_details:
                for g in e.grouped_sets():
                    w = f" at {g['weight']:g}" if g["weight"] else ""
                    bits.append(f"{g['count']}x{g['reps']}{w}")
            if e.duration_min:
                bits.append(f"{e.duration_min:g} min")
            detail = ", ".join(bits) if bits else "no details"
            lines.append(f"  {e.name} ({e.exercise_type.value}): {detail}")
        return "EXACT EXERCISE LOG (these are the only exercises logged):\n" + "\n".join(lines)

    def _build_grounding(self) -> str | None:
        """Deterministically compute today's totals + user profile to anchor the chat."""
        parts: list[str] = []

        if self._profile_store is not None:
            profile = self._profile_store.load()
            parts.append(profile.grounding_text())

        if self._meal_repo is not None and self._clock is not None:
            summary = GetDailySummaryUseCase(self._meal_repo).handle(self._clock.today())
            if summary.meal_count == 0:
                parts.append("The user has not logged any food today yet.")
            else:
                m = summary.total_macros
                slots = ", ".join(
                    f"{slot.value}: {cals:.0f} kcal"
                    for slot, cals in summary.calories_by_slot.items()
                )
                parts.append(
                    f"Today: {summary.total_calories:.0f} kcal total across {summary.meal_count} meal(s). "
                    f"Macros: {m.protein_g:.0f}g protein, {m.carbs_g:.0f}g carbs, {m.fat_g:.0f}g fat. "
                    f"By slot: {slots}."
                )

        if self._clock is not None:
            today = self._clock.today()
            detail = self._food_detail(today)
            if detail:
                parts.append(detail)
            exercise_detail = self._exercise_detail(today)
            if exercise_detail:
                parts.append(exercise_detail)

        if self._memory_store is not None:
            memories = self._memory_store.list_all()
            if memories:
                remembered = "\n".join(f"- {m.text}" for m in memories)
                parts.append(f"MEMORY (things the user asked you to remember):\n{remembered}")

        return "\n".join(parts) if parts else None
