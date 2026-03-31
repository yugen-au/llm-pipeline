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
    from llm_pipeline.pipeline import PipelineConfig

logger = logging.getLogger(__name__)


def _make_pipeline_factory(
    cls: Type[PipelineConfig], model: Optional[str]
) -> Callable:
    """Return a factory closure that instantiates *cls* with captured *model*.

    The returned callable matches the signature expected by trigger_run:
    ``(run_id, engine, event_emitter, **kwargs) -> PipelineConfig``.
    """

    def factory(
        run_id: str,
        engine: Engine,
        event_emitter: object = None,
        **kwargs: object,
    ) -> PipelineConfig:
        return cls(
            model=model,
            run_id=run_id,
            engine=engine,
            event_emitter=event_emitter,
        )

    return factory


def _discover_pipelines(
    engine: Engine, default_model: Optional[str]
) -> Tuple[Dict[str, Callable], Dict[str, Type[PipelineConfig]]]:
    """Scan ``llm_pipeline.pipelines`` entry-point group and build registries.

    Returns:
        Tuple of (pipeline_registry, introspection_registry) dicts keyed by
        ``ep.name``.
    """
    from llm_pipeline.pipeline import PipelineConfig

    pipeline_reg: Dict[str, Callable] = {}
    introspection_reg: Dict[str, Type[PipelineConfig]] = {}

    eps = importlib.metadata.entry_points(group="llm_pipeline.pipelines")
    for ep in eps:
        try:
            cls = ep.load()
            if not inspect.isclass(cls) or not issubclass(cls, PipelineConfig):
                logger.warning(
                    "Entry point '%s' does not reference a PipelineConfig "
                    "subclass, skipping",
                    ep.name,
                )
                continue
            pipeline_reg[ep.name] = _make_pipeline_factory(cls, default_model)
            introspection_reg[ep.name] = cls
        except Exception:
            logger.warning(
                "Failed to load entry point '%s', skipping",
                ep.name,
                exc_info=True,
            )
            continue

        # _seed_prompts is optional; failure must not unregister the pipeline
        try:
            if hasattr(cls, "_seed_prompts") and callable(cls._seed_prompts):
                cls._seed_prompts(engine)
        except Exception:
            logger.warning(
                "_seed_prompts failed for '%s', pipeline still registered",
                ep.name,
                exc_info=True,
            )

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
    engine: Engine,
) -> Tuple[Dict[str, Callable], Dict[str, Type[PipelineConfig]]]:
    """Import modules by dotted path, scan for PipelineConfig subclasses, and build registries.

    Raises:
        ValueError: If a module cannot be imported or contains no
            PipelineConfig subclasses.
    """
    from llm_pipeline.pipeline import PipelineConfig

    pipeline_reg: Dict[str, Callable] = {}
    introspection_reg: Dict[str, Type[PipelineConfig]] = {}

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
            if issubclass(cls, PipelineConfig)
            and cls is not PipelineConfig
            and not inspect.isabstract(cls)
            and cls.__module__ == mod.__name__
        ]

        if not found:
            raise ValueError(
                f"No PipelineConfig subclasses found in module '{path}'"
            )

        for cls in found:
            key = to_snake_case(cls.__name__, strip_suffix="Pipeline")
            pipeline_reg[key] = _make_pipeline_factory(cls, default_model)
            introspection_reg[key] = cls

            # _seed_prompts is optional; failure must not unregister the pipeline
            try:
                if hasattr(cls, "_seed_prompts") and callable(cls._seed_prompts):
                    cls._seed_prompts(engine)
            except Exception:
                logger.warning(
                    "_seed_prompts failed for '%s', pipeline still registered",
                    key,
                    exc_info=True,
                )

    if pipeline_reg:
        logger.info(
            "Loaded %d pipeline(s) from modules: %s",
            len(pipeline_reg),
            ", ".join(sorted(pipeline_reg)),
        )

    return pipeline_reg, introspection_reg


def _sync_variable_definitions(engine: Engine) -> None:
    """Rebuild runtime PromptVariables classes from DB-stored variable_definitions."""
    from sqlmodel import Session, select
    from llm_pipeline.db.prompt import Prompt
    from llm_pipeline.prompts.variables import rebuild_from_db

    try:
        with Session(engine) as session:
            stmt = select(Prompt).where(Prompt.variable_definitions.isnot(None))
            prompts = session.exec(stmt).all()
            for p in prompts:
                rebuild_from_db(p.prompt_key, p.prompt_type, p.variable_definitions)
            if prompts:
                logger.info("Synced variable_definitions for %d prompt(s)", len(prompts))
    except Exception:
        logger.warning("Failed to sync variable_definitions at startup", exc_info=True)


def create_app(
    db_path: Optional[str] = None,
    database_url: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None,
    auto_discover: bool = True,
    default_model: Optional[str] = None,
    pipeline_modules: Optional[List[str]] = None,
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

    # Model resolution: param > env > None
    resolved_model = default_model or os.environ.get("LLM_PIPELINE_MODEL")
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
        module_pipeline: Dict[str, Callable] = {}
        module_introspection: Dict[str, Type[PipelineConfig]] = {}

    # Registry setup: merge order auto-discovered < module-loaded < explicit
    if auto_discover:
        discovered_pipeline, discovered_introspection = _discover_pipelines(
            app.state.engine, resolved_model
        )
        app.state.pipeline_registry = {
            **discovered_pipeline,
            **module_pipeline,
            **(pipeline_registry or {}),
        }
        app.state.introspection_registry = {
            **discovered_introspection,
            **module_introspection,
            **(introspection_registry or {}),
        }
    else:
        app.state.pipeline_registry = {
            **module_pipeline,
            **(pipeline_registry or {}),
        }
        app.state.introspection_registry = {
            **module_introspection,
            **(introspection_registry or {}),
        }

    # Sync DB-stored variable_definitions into runtime registry
    _sync_variable_definitions(app.state.engine)

    # Route modules
    from llm_pipeline.ui.routes.runs import router as runs_router
    from llm_pipeline.ui.routes.steps import router as steps_router
    from llm_pipeline.ui.routes.events import router as events_router
    from llm_pipeline.ui.routes.prompts import router as prompts_router
    from llm_pipeline.ui.routes.pipelines import router as pipelines_router
    from llm_pipeline.ui.routes.websocket import router as ws_router
    from llm_pipeline.ui.routes.creator import router as creator_router
    from llm_pipeline.ui.routes.editor import router as editor_router
    from llm_pipeline.ui.routes.models import router as models_router

    app.include_router(runs_router, prefix="/api")
    app.include_router(steps_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(prompts_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")
    app.include_router(creator_router, prefix="/api")
    app.include_router(editor_router, prefix="/api")
    app.include_router(models_router, prefix="/api")
    app.include_router(ws_router)  # no /api prefix for websocket

    return app
