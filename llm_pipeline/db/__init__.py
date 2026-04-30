"""
Database initialization for LLM pipeline.

Provides auto-SQLite functionality when no external engine/session is provided.
"""
import os
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import Engine, event, text
from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, Session, create_engine

from llm_pipeline.db.pipeline_visibility import PipelineVisibility
from llm_pipeline.state import (
    DraftPipeline,
    DraftStep,
    EvaluationAcceptance,
    PipelineNodeSnapshot,
    PipelineReview,
    PipelineRun,
    PipelineRunInstance,
)

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_wal_registered_engines: set = set()
_schema_registered_engines: set = set()


def _migrate_add_columns(engine: Engine) -> None:
    """Add columns introduced after initial schema to existing tables.

    Works with both SQLite and Postgres/other databases. Uses
    information_schema on non-SQLite, PRAGMA on SQLite.
    """
    is_sqlite = engine.url.drivername.startswith("sqlite")

    # (table_name, column_name, column_type)
    _MIGRATIONS = [
        ("pipeline_events", "step_name", "VARCHAR(100)"),
        ("pipeline_runs", "error_message", "TEXT"),
        ("pipeline_runs", "trace_id", "VARCHAR(32)"),
        ("pipeline_runs", "span_id", "VARCHAR(16)"),
        ("pipeline_reviews", "input_data", "TEXT"),
        ("eval_runs", "variant_id", "INTEGER"),
        ("eval_runs", "delta_snapshot", "TEXT"),
        # Versioning-snapshots additions
        ("eval_cases", "version", "VARCHAR(20) DEFAULT '1.0'"),
        ("eval_cases", "is_active", "INTEGER DEFAULT 1"),
        ("eval_cases", "is_latest", "INTEGER DEFAULT 1"),
        ("eval_cases", "updated_at", "TIMESTAMP"),
        ("eval_runs", "case_versions", "TEXT"),
        ("eval_runs", "prompt_versions", "TEXT"),
        ("eval_runs", "model_snapshot", "TEXT"),
        ("eval_runs", "instructions_schema_snapshot", "TEXT"),
    ]

    # Group by table to minimise lookups
    tables: dict[str, list[tuple[str, str]]] = {}
    for tbl, col, typ in _MIGRATIONS:
        tables.setdefault(tbl, []).append((col, typ))

    for tbl, columns in tables.items():
        try:
            with engine.connect() as conn:
                if is_sqlite:
                    result = conn.execute(text(f"PRAGMA table_info({tbl})"))
                    existing = {row[1] for row in result}
                else:
                    schema = _get_schema()
                    if schema:
                        query = (
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = :tbl AND table_schema = :schema"
                        )
                        params = {"tbl": tbl, "schema": schema}
                    else:
                        query = (
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = :tbl"
                        )
                        params = {"tbl": tbl}
                    result = conn.execute(text(query), params)
                    existing = {row[0] for row in result}
                for col_name, col_type in columns:
                    if col_name not in existing:
                        if is_sqlite:
                            stmt = f"ALTER TABLE {tbl} ADD COLUMN {col_name} {col_type}"
                        else:
                            stmt = f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                        conn.execute(text(stmt))
                conn.commit()
        except OperationalError:
            pass  # table doesn't exist yet; create_all will handle it


def _migrate_partial_unique_indexes(engine: Engine) -> None:
    """One-off: retire legacy unique on eval_cases, dedupe rows, install
    partial uniques + supporting indexes. Idempotent."""
    is_sqlite = engine.url.drivername.startswith("sqlite")

    dedupe_sql = [
        # Keep newest by created_at (tiebreak id DESC); mark older duplicates
        # is_latest=0 so partial unique no longer collides.
        """
        UPDATE eval_cases
           SET is_latest = 0
         WHERE id NOT IN (
               SELECT id FROM (
                   SELECT id,
                          ROW_NUMBER() OVER (
                              PARTITION BY dataset_id, name
                              ORDER BY created_at DESC, id DESC
                          ) AS rn
                     FROM eval_cases
               ) t
               WHERE rn = 1
         )
        """,
    ]

    if is_sqlite:
        creates = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_cases_active_latest "
            "ON eval_cases (dataset_id, name) "
            "WHERE is_active = 1 AND is_latest = 1",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_live "
            "ON eval_cases (dataset_id, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_name_version "
            "ON eval_cases (dataset_id, name, version)",
        ]
    else:
        creates = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_cases_active_latest "
            "ON eval_cases (dataset_id, name) "
            "WHERE is_active = true AND is_latest = true",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_live "
            "ON eval_cases (dataset_id, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_name_version "
            "ON eval_cases (dataset_id, name, version)",
        ]

    with engine.connect() as conn:
        for stmt in dedupe_sql:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass  # eval_cases may not exist on fresh DB
        for stmt in creates:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass
        conn.commit()


def _drop_legacy_prompts_table(engine: Engine) -> None:
    """Phase E one-time DROP: remove the local ``prompts`` table.

    Prompts moved to Phoenix in earlier phases; the local table is now
    inert. Drops associated partial indexes too. Idempotent — silently
    no-ops when the table doesn't exist.
    """
    drops = [
        "DROP INDEX IF EXISTS uq_prompts_active_latest",
        "DROP INDEX IF EXISTS uq_prompts_key_type",
        "DROP INDEX IF EXISTS ix_prompts_active",
        "DROP INDEX IF EXISTS ix_prompts_key_type_live",
        "DROP INDEX IF EXISTS ix_prompts_key_type_version",
        "DROP INDEX IF EXISTS ix_prompts_category_step",
        "DROP TABLE IF EXISTS prompts",
    ]
    with engine.connect() as conn:
        for stmt in drops:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass
        conn.commit()


def _drop_legacy_step_states_table(engine: Engine) -> None:
    """Pydantic-graph migration one-time DROP: remove ``pipeline_step_states``.

    Replaced by ``pipeline_node_snapshots`` (the
    ``SqlmodelStatePersistence`` backend). Idempotent.
    """
    drops = [
        "DROP INDEX IF EXISTS ix_pipeline_step_states_run",
        "DROP INDEX IF EXISTS ix_pipeline_step_states_cache",
        "DROP TABLE IF EXISTS pipeline_step_states",
    ]
    with engine.connect() as conn:
        for stmt in drops:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass
        conn.commit()


def _drop_legacy_step_model_configs_table(engine: Engine) -> None:
    """Phoenix-owned-model migration: drop ``step_model_configs``.

    Per-step model overrides are now a Phoenix concern: the model
    lives on the Phoenix prompt's ``model_provider`` + ``model_name``
    fields (declared in YAML, pushed at ``llm-pipeline build``). The
    legacy ``StepModelConfig`` DB table is inert. Idempotent.
    """
    drops = [
        "DROP TABLE IF EXISTS step_model_configs",
    ]
    with engine.connect() as conn:
        for stmt in drops:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass
        conn.commit()


def _drop_legacy_evals_tables(engine: Engine) -> None:
    """Phase-3 evals migration: drop the 5 retired local eval tables.

    Phoenix is now the source of truth for datasets / cases / experiments
    / runs / case results / variants. The framework keeps only
    ``EvaluationAcceptance`` locally. Idempotent.
    """
    drops = [
        # eval_cases first — has FKs into eval_datasets that older
        # SQLite builds may track via their own constraints.
        "DROP INDEX IF EXISTS uq_eval_cases_active_latest",
        "DROP INDEX IF EXISTS ix_eval_cases_dataset_live",
        "DROP INDEX IF EXISTS ix_eval_cases_dataset_name_version",
        "DROP INDEX IF EXISTS ix_eval_datasets_name",
        "DROP TABLE IF EXISTS eval_case_results",
        "DROP TABLE IF EXISTS eval_runs",
        "DROP TABLE IF EXISTS eval_variants",
        "DROP TABLE IF EXISTS eval_cases",
        "DROP TABLE IF EXISTS eval_datasets",
    ]
    with engine.connect() as conn:
        for stmt in drops:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass
        conn.commit()


def add_missing_indexes(engine: Engine) -> None:
    """Add performance indexes that create_all skips on existing tables.

    Uses CREATE INDEX IF NOT EXISTS matching the SQLiteEventHandler pattern
    (handlers.py L175-188). Supports NFR-004 (<200ms run listing) and
    NFR-005 (<100ms step detail) at 10k+ rows.
    """
    _INDEX_STATEMENTS = [
        # Standalone started_at index for unfiltered ORDER BY started_at DESC
        (
            "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started "
            "ON pipeline_runs (started_at)"
        ),
        # Composite index for status-filtered queries with ORDER BY started_at
        (
            "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_status_started "
            "ON pipeline_runs (status, started_at)"
        ),
        (
            "CREATE INDEX IF NOT EXISTS ix_pipeline_events_run_step "
            "ON pipeline_events (run_id, step_name)"
        ),
    ]
    for stmt in _INDEX_STATEMENTS:
        try:
            with engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
        except OperationalError:
            pass  # index already exists or table doesn't exist yet


def get_default_db_path() -> Path:
    """Get default SQLite database path.

    Uses LLM_PIPELINE_DB env var if set, otherwise .llm_pipeline/pipeline.db
    in the current working directory.
    """
    env_path = os.getenv("LLM_PIPELINE_DB")
    if env_path:
        return Path(env_path)
    db_dir = Path.cwd() / ".llm_pipeline"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "pipeline.db"


def _get_schema() -> Optional[str]:
    """Read LLM_PIPELINE_DB_SCHEMA env var. Returns None for default/public."""
    schema = os.getenv("LLM_PIPELINE_DB_SCHEMA", "").strip()
    return schema or None


def init_pipeline_db(engine: Optional[Engine] = None) -> Engine:
    """Initialize pipeline database tables.

    Creates PipelineStepState, PipelineRunInstance, Prompt,
    DraftStep (draft_steps), and DraftPipeline (draft_pipelines) tables.

    When LLM_PIPELINE_DB_SCHEMA is set, tables are created in that schema
    (Postgres only; SQLite ignores schemas).

    Args:
        engine: Optional SQLAlchemy engine. If None, creates auto-SQLite.

    Returns:
        The engine used (created or provided).
    """
    global _engine

    if engine is None:
        db_path = get_default_db_path()
        db_url = f"sqlite:///{db_path}"
        engine = create_engine(db_url, echo=False)
        logger.info(f"Auto-created SQLite database at {db_path}")

    _engine = engine
    is_sqlite = engine.url.drivername.startswith("sqlite")
    schema = _get_schema()

    # Enable WAL mode for concurrent read/write on SQLite
    if is_sqlite and id(engine) not in _wal_registered_engines:
        _wal_registered_engines.add(id(engine))

        @event.listens_for(engine, "connect")
        def set_sqlite_wal(dbapi_conn, conn_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    # Set search_path for custom schema on Postgres
    if schema and not is_sqlite and id(engine) not in _schema_registered_engines:
        _schema_registered_engines.add(id(engine))

        # Create schema if it doesn't exist
        with engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.commit()

        @event.listens_for(engine, "connect")
        def set_search_path(dbapi_conn, conn_record):
            cursor = dbapi_conn.cursor()
            cursor.execute(f"SET search_path TO {schema},public")
            cursor.close()

    # Create framework tables
    SQLModel.metadata.create_all(
        engine,
        tables=[
            PipelineNodeSnapshot.__table__,
            PipelineRunInstance.__table__,
            PipelineRun.__table__,
            DraftStep.__table__,
            DraftPipeline.__table__,
            PipelineVisibility.__table__,
            PipelineReview.__table__,
            EvaluationAcceptance.__table__,
        ],
    )

    # Migrate existing DBs: add columns introduced after initial schema
    _migrate_add_columns(engine)

    # Retire legacy indexes, dedupe eval_cases, install partial unique indexes
    _migrate_partial_unique_indexes(engine)

    # Phase E: drop the legacy ``prompts`` table on first boot under the
    # Phoenix-backed framework. No-op once dropped.
    _drop_legacy_prompts_table(engine)

    # Pydantic-graph migration: drop the legacy ``pipeline_step_states``
    # table; ``pipeline_node_snapshots`` replaces it.
    _drop_legacy_step_states_table(engine)

    # Phase-3 evals migration: drop the 5 legacy eval tables (datasets,
    # cases, runs, case_results, variants). Phoenix is now the source
    # of truth; only ``EvaluationAcceptance`` survives locally.
    _drop_legacy_evals_tables(engine)

    # Phoenix-owned-model migration: drop step_model_configs. The
    # per-step model lives on the Phoenix prompt now.
    _drop_legacy_step_model_configs_table(engine)

    # Add performance indexes that create_all skips on existing tables
    add_missing_indexes(engine)

    return engine


def get_engine() -> Engine:
    """Get the current engine, initializing if needed."""
    global _engine
    if _engine is None:
        init_pipeline_db()
    return _engine


def get_session() -> Session:
    """Get a new database session."""
    return Session(get_engine())


__all__ = [
    "add_missing_indexes",
    "init_pipeline_db",
    "get_engine",
    "get_session",
    "get_default_db_path",
]
