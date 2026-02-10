"""
Pipeline state tracking models for audit trail and caching.

These models provide generic state tracking for ANY pipeline:
- PipelineStepState: Audit trail of each step's execution
- PipelineRunInstance: Links created database instances to pipeline runs

This enables:
- Traceability: "How was this data created?"
- Caching: "Can we reuse previous results?"
- Partial regeneration: "Re-run from step N onwards"
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import Index


def utc_now():
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class PipelineStepState(SQLModel, table=True):
    """
    Generic audit/state tracking for any pipeline step.
    
    Records what happened at each step of a pipeline execution,
    enabling audit trails, caching, and partial regeneration.
    
    Works for ANY pipeline type - not tied to specific domains.
    """
    __tablename__ = "pipeline_step_states"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Pipeline identification
    pipeline_name: str = Field(
        max_length=100,
        description="Pipeline name in snake_case (e.g., 'rate_card_parser', 'table_config_generator')"
    )
    run_id: str = Field(
        max_length=36,
        index=True,
        description="UUID identifying this specific pipeline run"
    )
    
    # Step identification
    step_name: str = Field(
        max_length=100,
        description="Name of the step (e.g., 'table_type_detection')"
    )
    step_number: int = Field(
        description="Order of execution (1, 2, 3...)"
    )
    
    # State data
    input_hash: str = Field(
        max_length=64,
        description="Hash of step inputs for cache invalidation"
    )
    result_data: dict = Field(
        sa_column=Column(JSON),
        description="The step's result (serialized)"
    )
    context_snapshot: dict = Field(
        sa_column=Column(JSON),
        description="Relevant context at this point"
    )
    
    # Metadata
    prompt_system_key: Optional[str] = Field(
        default=None,
        max_length=200,
        description="System prompt key used (if applicable)"
    )
    prompt_user_key: Optional[str] = Field(
        default=None,
        max_length=200,
        description="User prompt key used (if applicable)"
    )
    prompt_version: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Prompt version used (for cache invalidation)"
    )
    model: Optional[str] = Field(
        default=None,
        max_length=50,
        description="LLM model used (if applicable)"
    )
    
    # Timing
    created_at: datetime = Field(default_factory=utc_now)
    execution_time_ms: Optional[int] = Field(
        default=None,
        description="Execution time in milliseconds"
    )
    
    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_pipeline_step_states_run", "run_id", "step_number"),
        Index("ix_pipeline_step_states_cache", "pipeline_name", "step_name", "input_hash"),
    )


class PipelineRunInstance(SQLModel, table=True):
    """
    Tracks which database instances were created by which pipeline run.
    
    Generic linking table that works for ANY pipeline + ANY model.
    Enables traceability from created data back to the pipeline run.
    
    Example: "Which pipeline run created Rate #456?"
    """
    __tablename__ = "pipeline_run_instances"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Link to pipeline run
    run_id: str = Field(
        max_length=36,
        index=True,
        description="UUID of the pipeline run that created this instance"
    )
    
    # Polymorphic relationship to created instance
    model_type: str = Field(
        max_length=100,
        description="Model class name (e.g., 'Rate', 'Lane', 'ChargeType')"
    )
    model_id: int = Field(
        description="ID of the created instance in its table"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    
    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_pipeline_run_instances_run", "run_id"),
        Index("ix_pipeline_run_instances_model", "model_type", "model_id"),
    )


__all__ = ["PipelineStepState", "PipelineRunInstance"]
