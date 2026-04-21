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

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.db.step_config import StepModelConfig
from llm_pipeline.db.pipeline_visibility import PipelineVisibility
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun, DraftStep, DraftPipeline, PipelineReview
from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.evals.models import EvaluationDataset, EvaluationCase, EvaluationRun, EvaluationCaseResult, EvaluationVariant

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
        ("pipeline_step_states", "input_tokens", "INTEGER"),
        ("pipeline_step_states", "output_tokens", "INTEGER"),
        ("pipeline_step_states", "total_tokens", "INTEGER"),
        ("pipeline_step_states", "total_requests", "INTEGER"),
        ("pipeline_events", "step_name", "VARCHAR(100)"),
        ("prompts", "variable_definitions", "TEXT"),
        ("step_model_configs", "request_limit", "INTEGER"),
        ("pipeline_runs", "error_message", "TEXT"),
        ("pipeline_reviews", "input_data", "TEXT"),
        ("eval_runs", "variant_id", "INTEGER"),
        ("eval_runs", "delta_snapshot", "TEXT"),
        # Versioning-snapshots additions
        ("prompts", "is_latest", "INTEGER DEFAULT 1"),
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
    """One-off: retire legacy unique, dedupe eval_cases, install partial
    uniques + supporting indexes. Idempotent."""
    is_sqlite = engine.url.drivername.startswith("sqlite")

    drops = [
        "DROP INDEX IF EXISTS uq_prompts_key_type",   # legacy unique
        "DROP INDEX IF EXISTS ix_prompts_active",     # per A7
    ]

    dedupe_sql = [
        # Keep newest by created_at (tiebreak id DESC); mark older duplicates
        # is_latest=0 so partial unique no longer collides. is_active kept as-is.
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
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompts_active_latest "
            "ON prompts (prompt_key, prompt_type) "
            "WHERE is_active = 1 AND is_latest = 1",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_cases_active_latest "
            "ON eval_cases (dataset_id, name) "
            "WHERE is_active = 1 AND is_latest = 1",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_live "
            "ON prompts (prompt_key, prompt_type, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_version "
            "ON prompts (prompt_key, prompt_type, version)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_live "
            "ON eval_cases (dataset_id, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_name_version "
            "ON eval_cases (dataset_id, name, version)",
        ]
    else:
        creates = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompts_active_latest "
            "ON prompts (prompt_key, prompt_type) "
            "WHERE is_active = true AND is_latest = true",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_cases_active_latest "
            "ON eval_cases (dataset_id, name) "
            "WHERE is_active = true AND is_latest = true",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_live "
            "ON prompts (prompt_key, prompt_type, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_version "
            "ON prompts (prompt_key, prompt_type, version)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_live "
            "ON eval_cases (dataset_id, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_name_version "
            "ON eval_cases (dataset_id, name, version)",
        ]

    with engine.connect() as conn:
        for stmt in drops:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass
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
    PipelineEventRecord (pipeline_events), DraftStep (draft_steps),
    and DraftPipeline (draft_pipelines) tables.

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
            PipelineStepState.__table__,
            PipelineRunInstance.__table__,
            PipelineRun.__table__,
            Prompt.__table__,
            PipelineEventRecord.__table__,
            DraftStep.__table__,
            DraftPipeline.__table__,
            StepModelConfig.__table__,
            PipelineVisibility.__table__,
            PipelineReview.__table__,
            EvaluationDataset.__table__,
            EvaluationCase.__table__,
            EvaluationRun.__table__,
            EvaluationCaseResult.__table__,
            EvaluationVariant.__table__,
        ],
    )

    # Migrate existing DBs: add columns introduced after initial schema
    _migrate_add_columns(engine)

    # Retire legacy indexes, dedupe eval_cases, install partial unique indexes
    _migrate_partial_unique_indexes(engine)

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
    "Prompt",
]
