"""
meta:
  purpose: FastAPI application factory for the Shiboleth API. M0 scope: app
           construction, env verification at startup with masked echo,
           LangSmith tracing env propagation, /health. Routes mount here as
           milestones land (M4: checks, products, flags, metrics, SSE).
  contract: create_app() -> FastAPI. Startup fails fast (EnvError) if
            code/.env is incomplete. GET /health -> {status, project}.
  deps: fastapi, shiboleth.config.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shiboleth.config import Settings, load_settings

logger = logging.getLogger("shiboleth")


def _propagate_langsmith(settings: Settings) -> None:
    """LangChain reads LangSmith config from process env; set it once here."""
    os.environ["LANGSMITH_TRACING"] = "true" if settings.langsmith_tracing else "false"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()  # raises EnvError -> startup aborts, by design
    _propagate_langsmith(settings)
    logger.info("Shiboleth env verified:\n%s", settings.masked_echo())
    app.state.settings = settings
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Shiboleth API", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        settings: Settings = app.state.settings
        return {"status": "ok", "project": settings.langsmith_project}

    return app


app = create_app()
