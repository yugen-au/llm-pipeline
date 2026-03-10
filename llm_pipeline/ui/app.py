"""FastAPI application factory for llm-pipeline UI."""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Type

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from sqlmodel import create_engine

from llm_pipeline.db import init_pipeline_db

if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig


def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to SQLite database file. If None, uses
            init_pipeline_db() default (LLM_PIPELINE_DB env var
            or .llm_pipeline/pipeline.db).
        cors_origins: List of allowed CORS origins. Defaults to ["*"].
        pipeline_registry: Optional mapping of pipeline names to factory
            callables. Each factory has signature
            ``(run_id: str, engine: Engine) -> pipeline`` where the
            returned object exposes ``.execute()`` and ``.save()``.
            Used by POST /api/runs to trigger pipelines.
        introspection_registry: Optional mapping of pipeline names to
            PipelineConfig subclass types for class-level introspection.
            Separate from pipeline_registry which stores factory callables.
            Consumed by introspection endpoints (task 24).

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(title="llm-pipeline UI")

    # CORS
    origins = cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # GZip compression for API responses
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Database engine
    # NOTE: init_pipeline_db() sets the module-level _engine global in
    # llm_pipeline.db as a side-effect. Multiple create_app() calls will
    # overwrite that global with the last-created engine.
    if db_path is not None:
        engine = create_engine(f"sqlite:///{db_path}")
        app.state.engine = init_pipeline_db(engine)
    else:
        app.state.engine = init_pipeline_db()

    app.state.pipeline_registry = pipeline_registry or {}
    app.state.introspection_registry = introspection_registry or {}

    # Route modules
    from llm_pipeline.ui.routes.runs import router as runs_router
    from llm_pipeline.ui.routes.steps import router as steps_router
    from llm_pipeline.ui.routes.events import router as events_router
    from llm_pipeline.ui.routes.prompts import router as prompts_router
    from llm_pipeline.ui.routes.pipelines import router as pipelines_router
    from llm_pipeline.ui.routes.websocket import router as ws_router

    app.include_router(runs_router, prefix="/api")
    app.include_router(steps_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(prompts_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")
    app.include_router(ws_router)  # no /api prefix for websocket

    return app
