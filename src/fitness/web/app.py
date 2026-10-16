"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from fitness.config.settings import Settings
from fitness.web.auth import SharedSecretAuthMiddleware
from fitness.web.routes import health, meals

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="AI Fitness App", version="0.1.0")

    try:
        resolved = settings or Settings()
        auth_token = resolved.auth_token
    except Exception:
        auth_token = ""   # never let a config problem lock the app open or shut
    if auth_token:
        app.add_middleware(SharedSecretAuthMiddleware, token=auth_token)

    app.include_router(health.router)
    app.include_router(meals.router)

    if _STATIC_DIR.is_dir():
        # The app lived only at /static/index.html, so the obvious URL —
        # http://localhost:8000/ — returned a bare {"detail":"Not Found"}.
        @app.get("/", include_in_schema=False)
        def _root() -> RedirectResponse:
            return RedirectResponse(url="/static/index.html")

        # html=True also serves index.html for /static/ itself.
        app.mount(
            "/static",
            StaticFiles(directory=str(_STATIC_DIR), html=True),
            name="static",
        )
    return app


app = create_app()
