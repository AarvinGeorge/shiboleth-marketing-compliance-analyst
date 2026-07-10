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


def propagate_env(settings: Settings) -> None:
    """LangChain integrations read secrets and LangSmith config from process
    env, not from our Settings object; export them once here (the ONLY place
    besides config.py that handles secrets). Blank/absent values not written."""
    os.environ["LANGSMITH_TRACING"] = "true" if settings.langsmith_tracing else "false"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    exports = {
        "LANGSMITH_API_KEY": settings.langsmith_api_key,
        "GOOGLE_API_KEY": settings.google_api_key,
        "GROQ_API_KEY": settings.groq_api_key,
        "OPENAI_API_KEY": settings.openai_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    }
    for key, value in exports.items():
        if value:
            os.environ[key] = value


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()  # raises EnvError -> startup aborts, by design
    propagate_env(settings)
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
