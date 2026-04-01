"""DB-backed per-step configuration (model overrides, etc)."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field


class StepModelConfig(SQLModel, table=True):
    """UI-configurable model override per pipeline step."""

    __tablename__ = "step_model_configs"
    __table_args__ = (
        UniqueConstraint("pipeline_name", "step_name"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    pipeline_name: str = Field(max_length=100)
    step_name: str = Field(max_length=100)
    model: str = Field(max_length=100)
    request_limit: Optional[int] = Field(default=None, description="Max LLM requests per step run (None = pydantic-ai default)")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
