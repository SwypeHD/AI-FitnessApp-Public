"""Environment-driven settings (pydantic-settings).

All configurable knobs live here. Reads from env vars and/or a ``.env`` file; the
composition root reads these once at startup to build the adapter graph.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_dir: str = "data"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma4:26b"
    llm_provider: str = "none"  # "none" | "ollama" | "anthropic" (later)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    # Shared secret required on API requests. Empty (the default) disables auth
    # entirely, so local development and the test suite are unaffected.
    auth_token: str = ""

    model_config = {"env_prefix": "FITNESS_", "env_file": ".env", "extra": "ignore"}
