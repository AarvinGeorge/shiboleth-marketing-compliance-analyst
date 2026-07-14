"""
meta:
  purpose: FastAPI application factory for the Shiboleth API. M0 scope: app
           construction, env verification at startup with masked echo,
           LangSmith tracing env propagation, /health. Routes mount here as
           milestones land (M4: checks, products, flags, metrics, SSE).
           CORS origins are env-driven (CORS_ALLOW_ORIGINS) for the
           Vercel-hosted frontend; default stays the dev web app.
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

    from shiboleth.db.engine import get_engine, session_factory

    url = getattr(app.state, "database_url_override", None) or settings.database_url
    engine = get_engine(url)
    app.state.session_factory = session_factory(engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Shiboleth API", version="0.1.0", lifespan=lifespan)

    from fastapi.middleware.cors import CORSMiddleware

    # Origins resolved at construction time (middleware can't wait for the
    # lifespan settings load); CORS_ALLOW_ORIGINS env drives prod, default
    # stays the dev web app.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(Settings.from_env().cors_allow_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from shiboleth.api.routes.flags import router as flags_router
    from shiboleth.api.routes.metrics import router as metrics_router
    from shiboleth.api.routes.preview import router as preview_router
    from shiboleth.api.routes.products import router as products_router
    from shiboleth.api.routes.runs import router as runs_router
    from shiboleth.api.routes.scorecard import router as scorecard_router

    app.include_router(products_router)
    app.include_router(flags_router)
    app.include_router(preview_router)
    app.include_router(runs_router)
    app.include_router(metrics_router)
    app.include_router(scorecard_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        settings: Settings = app.state.settings
        return {"status": "ok", "project": settings.langsmith_project}

    return app


app = create_app()
