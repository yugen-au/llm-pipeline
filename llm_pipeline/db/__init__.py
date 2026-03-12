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
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun
from llm_pipeline.events.models import PipelineEventRecord

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_wal_registered_engines: set = set()


def _migrate_step_state_token_columns(engine: Engine) -> None:
    """Add token usage columns to pipeline_step_states if missing.

    Uses PRAGMA table_info to check column existence before ALTER TABLE,
    consistent with SQLiteEventHandler.__init__ migration style.
    """
    _TOKEN_COLUMNS = [
        ("input_tokens", "INTEGER"),
        ("output_tokens", "INTEGER"),
        ("total_tokens", "INTEGER"),
        ("total_requests", "INTEGER"),
    ]
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("PRAGMA table_info(pipeline_step_states)")
            )
            existing = {row[1] for row in result}
            for col_name, col_type in _TOKEN_COLUMNS:
                if col_name not in existing:
                    conn.execute(
                        text(
                            f"ALTER TABLE pipeline_step_states "
                            f"ADD COLUMN {col_name} {col_type}"
                        )
                    )
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


def init_pipeline_db(engine: Optional[Engine] = None) -> Engine:
    """Initialize pipeline database tables.

    Creates PipelineStepState, PipelineRunInstance, Prompt, and
    PipelineEventRecord (pipeline_events) tables.

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

    # Enable WAL mode for concurrent read/write on SQLite
    if engine.url.drivername.startswith("sqlite") and id(engine) not in _wal_registered_engines:
        _wal_registered_engines.add(id(engine))

        @event.listens_for(engine, "connect")
        def set_sqlite_wal(dbapi_conn, conn_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
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
        ],
    )

    # Migrate existing DBs: add token columns to pipeline_step_states
    _migrate_step_state_token_columns(engine)

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
