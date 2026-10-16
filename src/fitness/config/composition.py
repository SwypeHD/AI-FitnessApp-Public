"""Composition root — the single place that wires adapters into use-cases.

This is the ONLY module that imports both adapters and the application layer. Swapping
JSON→SQL or Ollama→Anthropic is a local change here, not a core change.
"""

from __future__ import annotations

from fitness.adapters.clock import SystemClock
from fitness.adapters.extraction.exercise_catalog import StaticExerciseCatalog
from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase
from fitness.adapters.extraction.rule_based import RuleBasedExtractor
from fitness.adapters.llm.anthropic_client import AnthropicLlmClient
from fitness.adapters.llm.null_client import NullLlmClient
from fitness.adapters.llm.ollama_client import OllamaLlmClient
from fitness.adapters.persistence.json_exercise_repository import JsonExerciseRepository
from fitness.adapters.persistence.json_plan_store import JsonPlanStore
from fitness.adapters.persistence.json_profile_store import JsonProfileStore
from fitness.adapters.persistence.json_repository import JsonMealRepository
from fitness.adapters.persistence.json_memory_store import JsonMemoryStore
from fitness.adapters.persistence.json_saved_meal_store import JsonSavedMealStore
from fitness.application.use_cases.daily_summary import GetDailySummaryUseCase
from fitness.application.use_cases.edit_exercise import EditExerciseUseCase
from fitness.application.use_cases.edit_log import EditLogUseCase
from fitness.application.use_cases.handle_message import HandleMessageUseCase
from fitness.application.use_cases.log_exercise import LogExerciseUseCase
from fitness.application.use_cases.log_meal import LogMealUseCase
from fitness.application.use_cases.build_plan import BuildPlanUseCase
from fitness.application.use_cases.manage_calendar import ManageCalendarUseCase
from fitness.application.use_cases.query import QueryUseCase
from fitness.application.use_cases.view_log import ViewLogUseCase
from fitness.config.settings import Settings


def _build_llm(settings: Settings):
    if settings.llm_provider == "ollama":
        return OllamaLlmClient(host=settings.ollama_host, model=settings.ollama_model)
    if settings.llm_provider == "anthropic":
        return AnthropicLlmClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    return NullLlmClient()


class Container:
    """Holds the fully-wired use-case instances. Built once at startup."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or Settings()

        self.clock = SystemClock()
        self.food_kb = StaticFoodKnowledgeBase()
        self.exercise_catalog = StaticExerciseCatalog()
        self.extractor = RuleBasedExtractor(self.food_kb)
        self.meal_repo = JsonMealRepository(settings.data_dir)
        self.exercise_repo = JsonExerciseRepository(settings.data_dir)
        self.plan_store = JsonPlanStore(settings.data_dir)
        self.profile_store = JsonProfileStore(settings.data_dir)
        self.saved_meal_store = JsonSavedMealStore(settings.data_dir)
        self.memory_store = JsonMemoryStore(settings.data_dir)
        self.llm = _build_llm(settings)

        self.log_meal = LogMealUseCase(
            extractor=self.extractor,
            meal_repo=self.meal_repo,
            clock=self.clock,
            food_kb=self.food_kb,
            llm=self.llm,
        )
        self.daily_summary = GetDailySummaryUseCase(meal_repo=self.meal_repo)
        self.view_log = ViewLogUseCase(meal_repo=self.meal_repo)
        self.edit_log = EditLogUseCase(meal_repo=self.meal_repo, clock=self.clock, food_kb=self.food_kb)
        self.log_exercise = LogExerciseUseCase(exercise_repo=self.exercise_repo, clock=self.clock)
        self.edit_exercise = EditExerciseUseCase(exercise_repo=self.exercise_repo, clock=self.clock)
        self.manage_calendar = ManageCalendarUseCase(plan_store=self.plan_store, clock=self.clock)
        self.build_plan = BuildPlanUseCase(plan_store=self.plan_store, manage_calendar=self.manage_calendar)
        self.query = QueryUseCase(meal_repo=self.meal_repo, clock=self.clock)
        self.handle_message = HandleMessageUseCase(
            log_meal=self.log_meal,
            query=self.query,
            edit_log=self.edit_log,
            log_exercise=self.log_exercise,
            edit_exercise=self.edit_exercise,
            llm=self.llm,
            meal_repo=self.meal_repo,
            clock=self.clock,
            profile_store=self.profile_store,
            saved_meal_store=self.saved_meal_store,
            memory_store=self.memory_store,
            exercise_repo=self.exercise_repo,
            manage_calendar=self.manage_calendar,
            food_kb=self.food_kb,
            build_plan=self.build_plan,
        )
