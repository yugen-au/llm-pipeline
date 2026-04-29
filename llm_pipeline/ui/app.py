"""FastAPI application factory for llm-pipeline UI."""
from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import logging
import os
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple, Type

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from sqlmodel import create_engine

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.naming import to_snake_case

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from llm_pipeline.graph import Pipeline

logger = logging.getLogger(__name__)


def _discover_pipelines(
    engine: "Engine", default_model: Optional[str]
) -> Tuple[Dict[str, Type["Pipeline"]], Dict[str, Type["Pipeline"]]]:
    """Scan ``llm_pipeline.pipelines`` entry-point group for graph ``Pipeline`` classes.

    Returns ``(pipeline_registry, introspection_registry)``. Both
    map snake-cased pipeline name to the ``Pipeline`` subclass — the
    framework no longer needs separate factory closures because
    ``run_pipeline(pipeline_cls, ...)`` takes the class directly.
    """
    del engine  # _seed_prompts is gone; graph pipelines do their own seed (Phoenix)
    from llm_pipeline.graph import Pipeline

    pipeline_reg: Dict[str, Type[Pipeline]] = {}
    introspection_reg: Dict[str, Type[Pipeline]] = {}

    eps = importlib.metadata.entry_points(group="llm_pipeline.pipelines")
    for ep in eps:
        try:
            cls = ep.load()
            if not (inspect.isclass(cls) and issubclass(cls, Pipeline)):
                logger.warning(
                    "Entry point '%s' does not reference a Pipeline "
                    "(graph) subclass, skipping",
                    ep.name,
                )
                continue
            pipeline_reg[ep.name] = cls
            introspection_reg[ep.name] = cls
        except Exception:
            logger.warning(
                "Failed to load entry point '%s', skipping",
                ep.name,
                exc_info=True,
            )
            continue

    if pipeline_reg:
        logger.info(
            "Discovered %d pipeline(s): %s",
            len(pipeline_reg),
            ", ".join(sorted(pipeline_reg)),
        )

    return pipeline_reg, introspection_reg


def _load_pipeline_modules(
    module_paths: List[str],
    default_model: Optional[str],
    engine: "Engine",
) -> Tuple[Dict[str, Type["Pipeline"]], Dict[str, Type["Pipeline"]]]:
    """Import modules by dotted path, register concrete graph ``Pipeline`` subclasses.

    Raises ``ValueError`` if a module can't be imported or has no
    ``Pipeline`` subclasses.
    """
    del default_model, engine  # not needed for graph pipelines
    from llm_pipeline.graph import Pipeline

    pipeline_reg: Dict[str, Type[Pipeline]] = {}
    introspection_reg: Dict[str, Type[Pipeline]] = {}

    for path in module_paths:
        try:
            mod = importlib.import_module(path)
        except ImportError as e:
            raise ValueError(
                f"Failed to import pipeline module '{path}': {e}"
            ) from e

        members = inspect.getmembers(mod, inspect.isclass)
        found = [
            cls
            for _, cls in members
            if issubclass(cls, Pipeline)
            and cls is not Pipeline
            and not inspect.isabstract(cls)
            and cls.__module__ == mod.__name__
        ]

        if not found:
            raise ValueError(
                f"No Pipeline subclasses found in module '{path}'"
            )

        for cls in found:
            key = to_snake_case(cls.__name__, strip_suffix="Pipeline")
            pipeline_reg[key] = cls
            introspection_reg[key] = cls

    if pipeline_reg:
        logger.info(
            "Loaded %d pipeline(s) from modules: %s",
            len(pipeline_reg),
            ", ".join(sorted(pipeline_reg)),
        )

    return pipeline_reg, introspection_reg


def _sync_pipeline_visibility(engine: Engine, pipeline_names: list[str]) -> None:
    """Ensure each discovered pipeline has a PipelineVisibility row in DB."""
    from datetime import datetime, timezone
    from sqlmodel import Session, select
    from llm_pipeline.db.pipeline_visibility import PipelineVisibility

    try:
        with Session(engine) as session:
            existing = {
                row.pipeline_name: row
                for row in session.exec(select(PipelineVisibility)).all()
            }
            inserted = 0
            for name in pipeline_names:
                if name not in existing:
                    session.add(PipelineVisibility(
                        pipeline_name=name,
                        status="draft",
                    ))
                    inserted += 1
            if inserted:
                session.commit()
                logger.info("Created %d pipeline visibility row(s) (default: draft)", inserted)
            all_draft = all(
                (existing.get(n) or PipelineVisibility(status="draft")).status == "draft"
                for n in pipeline_names
            )
            if pipeline_names and all_draft:
                logger.warning(
                    "All %d pipeline(s) are in draft status. "
                    "Use PUT /api/pipelines/{name}/status to publish.",
                    len(pipeline_names),
                )
    except Exception:
        logger.warning("Failed to sync pipeline visibility at startup", exc_info=True)


def create_app(
    db_path: Optional[str] = None,
    database_url: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type["Pipeline"]]] = None,
    auto_discover: bool = True,
    default_model: Optional[str] = None,
    pipeline_modules: Optional[List[str]] = None,
    auto_generate_base_path: Optional[str] = None,
    demo_mode: bool = False,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to SQLite database file. If None, uses
            init_pipeline_db() default (LLM_PIPELINE_DB env var
            or .llm_pipeline/pipeline.db).
        database_url: Full SQLAlchemy database URL (e.g.
            ``'postgresql://user:pass@host:port/db'``). Takes precedence
            over db_path. Falls back to ``LLM_PIPELINE_DATABASE_URL`` env var.
        cors_origins: List of allowed CORS origins. Defaults to ["*"].
        pipeline_registry: Optional mapping of pipeline names to factory
            callables. Each factory has signature
            ``(run_id: str, engine: Engine) -> pipeline`` where the
            returned object exposes ``.execute()`` and ``.save()``.
            Used by POST /api/runs to trigger pipelines.
        introspection_registry: Optional mapping of pipeline names to
            PipelineConfig subclass types for class-level introspection.
            Separate from pipeline_registry which stores factory callables.
            Consumed by introspection endpoints.
        auto_discover: If True (default), scan the ``llm_pipeline.pipelines``
            entry-point group and register discovered PipelineConfig
            subclasses. Explicit *pipeline_registry* / *introspection_registry*
            entries override any discovered entries with the same key.
        default_model: pydantic-ai model string (e.g.
            ``'google-gla:gemini-2.0-flash-lite'``). Falls back to
            ``LLM_PIPELINE_MODEL`` env var. If neither is set, pipeline
            execution will fail at call time (introspection still works).
        pipeline_modules: Optional list of Python dotted module paths to
            import and scan for ``PipelineConfig`` subclasses. Each module
            is loaded via ``importlib.import_module``, concrete subclasses
            are registered with keys derived from
            ``naming.to_snake_case(cls.__name__, strip_suffix="Pipeline")``.
            Raises ``ValueError`` on import failure or if no subclasses
            are found. Merge order: auto-discovered < module-loaded <
            explicit *pipeline_registry*.

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
    resolved_db_url = (
        database_url
        or os.environ.get("LLM_PIPELINE_DATABASE_URL")
    )
    if resolved_db_url is not None:
        engine = create_engine(resolved_db_url)
        app.state.engine = init_pipeline_db(engine)
    elif db_path is not None:
        if db_path == ":memory:":
            from sqlalchemy.pool import StaticPool
            engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            engine = create_engine(f"sqlite:///{db_path}")
        app.state.engine = init_pipeline_db(engine)
    else:
        app.state.engine = init_pipeline_db()

    # Model resolution: param > env > None (strip to catch LLM_PIPELINE_MODEL=)
    resolved_model = default_model or os.environ.get("LLM_PIPELINE_MODEL", "").strip() or None
    if resolved_model is None:
        logger.warning(
            "No default model configured. Set LLM_PIPELINE_MODEL or pass "
            "default_model. Pipeline execution will fail without a model."
        )
    app.state.default_model = resolved_model

    # Module-loaded pipelines (--pipelines flag)
    if pipeline_modules:
        module_pipeline, module_introspection = _load_pipeline_modules(
            pipeline_modules, resolved_model, app.state.engine
        )
    else:
        module_pipeline: Dict[str, Type["Pipeline"]] = {}
        module_introspection: Dict[str, Type["Pipeline"]] = {}

    # Demo mode: param > env > False
    resolved_demo = demo_mode or os.environ.get("LLM_PIPELINE_DEMO_MODE", "").lower() in ("1", "true")

    # Convention-based discovery (llm_pipelines/ directories)
    from llm_pipeline.discovery import discover_from_convention
    convention_pipeline, convention_introspection = discover_from_convention(
        app.state.engine, resolved_model, include_package=resolved_demo,
    )

    # Entry-point discovery (demo pipelines registered here)
    if auto_discover and resolved_demo:
        discovered_pipeline, discovered_introspection = _discover_pipelines(
            app.state.engine, resolved_model
        )
    else:
        discovered_pipeline: Dict[str, Type["Pipeline"]] = {}
        discovered_introspection: Dict[str, Type["Pipeline"]] = {}

    # Registry setup: merge order entry-points < convention < module-loaded < explicit
    app.state.pipeline_registry = {
        **discovered_pipeline,
        **convention_pipeline,
        **module_pipeline,
        **(pipeline_registry or {}),
    }
    app.state.introspection_registry = {
        **discovered_introspection,
        **convention_introspection,
        **module_introspection,
        **(introspection_registry or {}),
    }

    # Sync pipeline visibility (draft/published) to DB
    _sync_pipeline_visibility(app.state.engine, list(app.state.pipeline_registry.keys()))

    # Phase B: push code-derived schemas (response_format / tools /
    # variable types) onto the Phoenix prompt records for every
    # registered step. No-op when Phoenix is unconfigured. Idempotent;
    # only writes when the derived schemas differ.
    try:
        from llm_pipeline.prompts.registration import sync_pipelines_to_phoenix

        sync_pipelines_to_phoenix(app.state.introspection_registry)
    except Exception as exc:  # pragma: no cover - sync should never crash startup
        logger.warning("Phoenix prompt schema sync failed: %s", exc)

    # auto_generate base path: param > env > None
    from llm_pipeline.prompts.variables import set_auto_generate_base_path
    resolved_base = auto_generate_base_path or os.environ.get(
        "LLM_PIPELINE_AUTO_GENERATE_BASE_PATH"
    )
    if resolved_base:
        set_auto_generate_base_path(resolved_base)

    # Phase E (prompts) + Phase 3 (evals): both YAML/local-DB layers
    # retired. Phoenix is the source of truth for prompts AND eval
    # datasets/experiments. ``--prompts-dir``, ``--evals-dir``, and
    # the matching env vars are accepted by the CLI but ignored.

    # Route modules
    from llm_pipeline.ui.routes.runs import router as runs_router
    from llm_pipeline.ui.routes.steps import router as steps_router
    from llm_pipeline.ui.routes.trace import router as trace_router
    from llm_pipeline.ui.routes.prompts import router as prompts_router
    from llm_pipeline.ui.routes.pipelines import router as pipelines_router
    from llm_pipeline.ui.routes.websocket import router as ws_router
    from llm_pipeline.ui.routes.creator import router as creator_router
    from llm_pipeline.ui.routes.editor import router as editor_router
    from llm_pipeline.ui.routes.models import router as models_router
    from llm_pipeline.ui.routes.auto_generate import router as auto_generate_router
    from llm_pipeline.ui.routes.reviews import router as reviews_router
    from llm_pipeline.ui.routes.evals import router as evals_router

    app.include_router(runs_router, prefix="/api")
    app.include_router(steps_router, prefix="/api")
    app.include_router(trace_router, prefix="/api")
    app.include_router(prompts_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")
    app.include_router(creator_router, prefix="/api")
    app.include_router(editor_router, prefix="/api")
    app.include_router(models_router, prefix="/api")
    app.include_router(auto_generate_router, prefix="/api")
    app.include_router(reviews_router, prefix="/api")
    app.include_router(evals_router, prefix="/api")
    app.include_router(ws_router)  # no /api prefix for websocket

    return app
