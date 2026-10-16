"""FastAPI dependency injection — wires the composition root into route handlers."""

from __future__ import annotations

from functools import lru_cache

from fitness.config.composition import Container
from fitness.config.settings import Settings
from fitness.web.interaction_log import init_interaction_log


@lru_cache(maxsize=1)
def get_container() -> Container:
    container = Container()
    init_interaction_log(Settings().data_dir)
    return container
