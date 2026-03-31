"""
Database initialization for LLM pipeline.

Provides auto-SQLite functionality when no external engine/session is provided.
"""
import os
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, event, text
from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, Session, create_engine

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.db.step_config import StepModelConfig
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun, DraftStep, DraftPipeline
from llm_pipeline.events.models import PipelineEventRecord

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
        ],
    )

    # Migrate existing DBs: add columns introduced after initial schema
    _migrate_add_columns(engine)

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
