"""Pipeline visibility model for draft/published status control."""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field


class PipelineVisibility(SQLModel, table=True):
    """Controls which pipelines are callable via the external API."""
    __tablename__ = "pipeline_configs"

    id: Optional[int] = Field(default=None, primary_key=True)
    pipeline_name: str = Field(max_length=100, sa_column_kwargs={"unique": True})
    status: str = Field(default="draft", max_length=20)  # draft | published
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["PipelineVisibility"]
