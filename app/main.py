"""FastAPI application factory and application-lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI

from app.api.routes import router
from app.config.settings import get_settings
from app.graph.runtime import ReviewRuntime


def create_app(runtime_factory: Callable[[], ReviewRuntime] | None = None) -> FastAPI:
    """Create the API app; tests may inject a runtime using fake graph nodes."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        settings = get_settings()
        runtime = (
            runtime_factory()
            if runtime_factory is not None
            else ReviewRuntime(settings.database_file)
        )
        runtime.start()
        application.state.review_runtime = runtime
        try:
            yield
        finally:
            runtime.close()

    application = FastAPI(
        title="Autonomous Code Review & Refactoring Agent",
        description=(
            "LangGraph-powered Pull Request review with persistent checkpoints "
            "and human approval gates."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
