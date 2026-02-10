"""
Database initialization for LLM pipeline.

Provides auto-SQLite functionality when no external engine/session is provided.
"""
import os
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine
from sqlmodel import SQLModel, Session, create_engine

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.state import PipelineStepState, PipelineRunInstance

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None


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

    Creates PipelineStepState, PipelineRunInstance, and Prompt tables.

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

    # Create framework tables
    SQLModel.metadata.create_all(
        engine,
        tables=[
            PipelineStepState.__table__,
            PipelineRunInstance.__table__,
            Prompt.__table__,
        ],
    )

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
    "init_pipeline_db",
    "get_engine",
    "get_session",
    "get_default_db_path",
    "Prompt",
]
