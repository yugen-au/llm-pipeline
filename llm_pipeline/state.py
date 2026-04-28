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
from sqlalchemy import Index, UniqueConstraint


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

    # Token usage and cost are now owned by Langfuse (the trace for run_id).
    # Local DB no longer mirrors them — query Langfuse for those metrics.

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


class PipelineRun(SQLModel, table=True):
    """
    Tracks pipeline run lifecycle (start, complete, fail).

    Dedicated table for fast indexed queries on run history.
    Distinct from PipelineRunInstance which tracks created DB instances.
    step_count reflects unique step classes executed, not total calls.
    """
    __tablename__ = "pipeline_runs"

    id: Optional[int] = Field(default=None, primary_key=True)

    run_id: str = Field(
        max_length=36,
        unique=True,
        description="UUID identifying this pipeline run"
    )
    pipeline_name: str = Field(
        max_length=100,
        description="Pipeline name in snake_case"
    )
    status: str = Field(
        max_length=20,
        default="running",
        description="Run status: running, completed, failed"
    )
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = Field(default=None)
    step_count: Optional[int] = Field(default=None)
    total_time_ms: Optional[int] = Field(default=None)
    error_message: Optional[str] = Field(default=None, description="Error details when status=failed")

    __table_args__ = (
        Index("ix_pipeline_runs_name_started", "pipeline_name", "started_at"),
        Index("ix_pipeline_runs_status", "status"),
    )


class DraftStep(SQLModel, table=True):
    """
    Persists a draft step definition across sessions.

    Stores generated code, test results, and validation state for steps
    created by the pipeline creator UI. Status values: draft, tested,
    accepted, error. Re-generation UPDATEs existing row (unique name).
    """
    __tablename__ = "draft_steps"

    id: Optional[int] = Field(default=None, primary_key=True)

    name: str = Field(max_length=100, description="Unique step name")
    description: Optional[str] = Field(default=None)
    generated_code: dict = Field(
        sa_column=Column(JSON),
        description="Generated step code as structured dict"
    )
    test_results: Optional[dict] = Field(
        default=None, sa_column=Column(JSON)
    )
    validation_errors: Optional[dict] = Field(
        default=None, sa_column=Column(JSON)
    )
    status: str = Field(
        default="draft", max_length=20,
        description="draft, tested, accepted, error"
    )
    run_id: Optional[str] = Field(
        default=None, max_length=36,
        description="Traceability link to creator_generation_records.run_id (no FK)"
    )

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        UniqueConstraint("name", name="uq_draft_steps_name"),
        Index("ix_draft_steps_status", "status"),
    )


class DraftPipeline(SQLModel, table=True):
    """
    Persists a draft pipeline definition across sessions.

    Stores pipeline structure (step references) and compilation state.
    Status values: draft, tested, accepted, error.
    Re-generation UPDATEs existing row (unique name).
    """
    __tablename__ = "draft_pipelines"

    id: Optional[int] = Field(default=None, primary_key=True)

    name: str = Field(max_length=100, description="Unique pipeline name")
    structure: dict = Field(
        sa_column=Column(JSON),
        description="Pipeline structure referencing step names"
    )
    compilation_errors: Optional[dict] = Field(
        default=None, sa_column=Column(JSON)
    )
    status: str = Field(
        default="draft", max_length=20,
        description="draft, tested, accepted, error"
    )

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        UniqueConstraint("name", name="uq_draft_pipelines_name"),
        Index("ix_draft_pipelines_status", "status"),
    )


class PipelineReview(SQLModel, table=True):
    """Human review record for pipeline step review points."""
    __tablename__ = "pipeline_reviews"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(max_length=36, sa_column_kwargs={"unique": True})
    run_id: str = Field(max_length=36)
    pipeline_name: str = Field(max_length=100)
    step_name: str = Field(max_length=100)
    step_number: int
    status: str = Field(default="pending", max_length=20)  # pending, completed, expired
    review_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    input_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    decision: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = Field(default=None)
    resume_from: Optional[str] = Field(default=None, max_length=100)
    user_id: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index("ix_pipeline_reviews_run", "run_id"),
        Index("ix_pipeline_reviews_token", "token"),
        Index("ix_pipeline_reviews_status", "status"),
    )


__all__ = [
    "PipelineStepState",
    "PipelineRunInstance",
    "PipelineRun",
    "DraftStep",
    "DraftPipeline",
    "PipelineReview",
]
