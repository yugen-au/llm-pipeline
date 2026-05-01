"""FastAPI application factory for llm-pipeline UI."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Dict, List, Optional, Type

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from sqlmodel import create_engine

from llm_pipeline.db import init_pipeline_db

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from llm_pipeline.graph import Pipeline

logger = logging.getLogger(__name__)


def _resolve_dir_arg(
    *, arg: Optional[str], env_var: str, default: str,
) -> Optional["Path"]:
    """arg > env > default. Empty string anywhere disables the dir."""
    from pathlib import Path

    raw = arg if arg is not None else os.environ.get(env_var)
    if raw is None:
        raw = default
    raw = raw.strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _wire_phoenix(
    app: "FastAPI",
    *,
    prompts_dir_arg: Optional[str],
    datasets_dir_arg: Optional[str],
    introspection_registry: Optional[dict] = None,
) -> None:
    """Resolve YAML dirs, eagerly construct Phoenix clients, run dry-run validator.

    UI boot is read-only: it never writes to Phoenix. YAML → Phoenix
    push runs only via ``uv run llm-pipeline build`` (the gate
    invoked from CI / pre-commit / pre-deploy). At UI boot we only:

    1. Resolve the YAML directories and store them on ``app.state``
       (route handlers read from there for UI saves).
    2. Eagerly construct the Phoenix prompt + dataset clients and
       store them on ``app.state`` so route handlers reuse them.
       Failure to construct (Phoenix unconfigured / unreachable) is
       logged once and the framework continues.
    3. Run :func:`validate_phoenix_alignment` in ``dry-run`` mode.
       Any code↔YAML↔Phoenix misalignment is logged as a warning
       (no exception) — devs see what's broken but the UI keeps
       booting. Run ``build`` to push fixes and re-validate.
    """
    from pathlib import Path  # noqa: F401 — referenced via _resolve_dir_arg

    prompts_dir = _resolve_dir_arg(
        arg=prompts_dir_arg,
        env_var="LLM_PIPELINE_PROMPTS_DIR",
        default="./llm-pipeline-prompts",
    )
    datasets_dir = _resolve_dir_arg(
        arg=datasets_dir_arg,
        env_var="LLM_PIPELINE_EVALS_DIR",
        default="./llm-pipeline-evals",
    )
    app.state.prompts_dir = prompts_dir
    app.state.datasets_dir = datasets_dir

    if prompts_dir is None and datasets_dir is None:
        return

    prompt_client = None
    if prompts_dir is not None:
        try:
            from llm_pipeline.prompts.phoenix_client import PhoenixPromptClient

            prompt_client = PhoenixPromptClient()
            app.state._phoenix_prompt_client = prompt_client
        except Exception as exc:
            logger.info(
                "Phoenix prompt client unavailable at UI boot: %s "
                "(routes that need Phoenix will surface their own error)",
                exc,
            )
            prompt_client = None
    if datasets_dir is not None:
        try:
            from llm_pipeline.evals.phoenix_client import PhoenixDatasetClient

            app.state._phoenix_dataset_client = PhoenixDatasetClient()
        except Exception as exc:
            logger.info(
                "Phoenix dataset client unavailable at UI boot: %s",
                exc,
            )

    # Offline alignment validator. The validator is now strict (always
    # raises on misalignment) — UI boot stays lenient by catching the
    # raise and logging a warning. Step 7 of the CLI refactor replaces
    # this with a proper dry-run chain (generate / build / pull / push)
    # gated on ``args.dev``.
    if prompts_dir is not None and introspection_registry:
        from llm_pipeline.prompts.phoenix_validator import (
            PhoenixValidationFailed,
            validate_phoenix_alignment,
        )

        try:
            validate_phoenix_alignment(introspection_registry, prompts_dir)
        except PhoenixValidationFailed as exc:
            logger.warning(
                "UI boot found code↔YAML misalignment(s):\n%s\n"
                "Run `uv run llm-pipeline build` to surface and fix.",
                exc,
            )
        except Exception:
            logger.exception(
                "Alignment validator crashed; continuing UI boot",
            )


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
    prompts_dir: Optional[str] = None,
    datasets_dir: Optional[str] = None,
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
    from llm_pipeline.discovery import (
        discover_from_convention,
        discover_from_entry_points,
        discover_from_modules,
    )
    if pipeline_modules:
        module_pipeline, module_introspection = discover_from_modules(
            pipeline_modules,
        )
    else:
        module_pipeline: Dict[str, Type["Pipeline"]] = {}
        module_introspection: Dict[str, Type["Pipeline"]] = {}

    # Demo mode: param > env > False
    resolved_demo = demo_mode or os.environ.get("LLM_PIPELINE_DEMO_MODE", "").lower() in ("1", "true")

    # Convention-based discovery (llm_pipelines/ directories)
    convention_pipeline, convention_introspection = discover_from_convention(
        app.state.engine, resolved_model, include_package=resolved_demo,
    )

    # Entry-point discovery (demo pipelines registered here)
    if auto_discover and resolved_demo:
        discovered_pipeline, discovered_introspection = (
            discover_from_entry_points()
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

    # Per-kind ArtifactRegistration container. Phase C.2.a wires the
    # empty shape so consumers can be migrated incrementally; the
    # per-kind walkers in Phase C.2.b populate it during discovery
    # alongside the legacy ``pipeline_registry`` /
    # ``_AUTO_GENERATE_REGISTRY`` paths above. See
    # ``.claude/plans/per-artifact-architecture.md`` (sections 7-9).
    from llm_pipeline.discovery import init_empty_registries
    app.state.registries = init_empty_registries()

    # Sync pipeline visibility (draft/published) to DB
    _sync_pipeline_visibility(app.state.engine, list(app.state.pipeline_registry.keys()))

    # Phoenix wiring at UI boot. Resolves YAML dirs + Phoenix clients,
    # then runs the validator in dry-run mode (warn-only, no writes).
    # YAML → Phoenix push happens only via `uv run llm-pipeline build`.
    _wire_phoenix(
        app,
        prompts_dir_arg=prompts_dir,
        datasets_dir_arg=datasets_dir,
        introspection_registry=app.state.introspection_registry,
    )

    # auto_generate base path: param > env > None
    from llm_pipeline.prompts.variables import set_auto_generate_base_path
    resolved_base = auto_generate_base_path or os.environ.get(
        "LLM_PIPELINE_AUTO_GENERATE_BASE_PATH"
    )
    if resolved_base:
        set_auto_generate_base_path(resolved_base)

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
