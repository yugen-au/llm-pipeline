"""
Pipeline event persistence models.

Provides the SQLModel table for storing pipeline events emitted
during execution, used by SQLiteEventHandler for durable audit trails.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Column, Field, JSON, SQLModel

from llm_pipeline.state import utc_now


class PipelineEventRecord(SQLModel, table=True):
    """
    Persisted pipeline event record.

    Stores serialised event data for any pipeline event, enabling
    post-hoc analysis, debugging, and audit trails.

    Intentionally duplicates run_id/event_type/timestamp as columns
    (also present inside event_data JSON) for query efficiency.
    """

    __tablename__ = "pipeline_events"

    id: Optional[int] = Field(default=None, primary_key=True)

    run_id: str = Field(
        max_length=36,
        description="UUID identifying the pipeline run",
    )
    event_type: str = Field(
        max_length=100,
        description="Event type name (e.g., 'pipeline_started')",
    )
    pipeline_name: str = Field(
        max_length=100,
        description="Pipeline name in snake_case",
    )
    timestamp: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp of event emission",
    )
    event_data: dict = Field(
        sa_column=Column(JSON),
        description="Full serialised event payload",
    )

    __table_args__ = (
        Index("ix_pipeline_events_run_event", "run_id", "event_type"),
        Index("ix_pipeline_events_type", "event_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<PipelineEventRecord(id={self.id}, "
            f"run={self.run_id}, type={self.event_type})>"
        )


__all__ = ["PipelineEventRecord"]
