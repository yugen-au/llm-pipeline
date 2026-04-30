"""
Pipeline state tracking models.

The framework persists three orthogonal kinds of pipeline data:

- ``PipelineRun``: run-level pointer (run_id, pipeline_name, status, trace_id).
- ``PipelineNodeSnapshot``: pydantic-graph state-persistence backend rows
  — one per node-execution attempt. Carries the full ``PipelineState``
  JSON at the moment that node was about to run, plus pydantic-graph
  bookkeeping (snapshot id, status, start_ts, duration). The UI's
  run-detail panel reads from these directly.
- ``PipelineRunInstance``: links created SQLModel rows to the run that
  created them (e.g. "which run extracted Topic #42?").
- ``PipelineReview``: human-review records.

``PipelineStepState`` (the legacy audit table) was retired in the
pydantic-graph migration; ``PipelineNodeSnapshot`` is the replacement.
"""
from datetime import datetime, timezone
from typing import Any, Optional
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import Index, UniqueConstraint


def utc_now():
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class PipelineNodeSnapshot(SQLModel, table=True):
    """One pydantic-graph snapshot row, owned by ``SqlmodelStatePersistence``.

    Each row corresponds to either a ``NodeSnapshot`` (the graph is
    about to run a node) or an ``EndSnapshot`` (the graph has finished).
    The full ``PipelineState`` is JSON-encoded in ``state_snapshot`` —
    on resume, the persistence backend reloads the most recent pending
    snapshot, deserialises the state, and continues from that node.

    Phase 2 makes this table the single source of truth for run
    history. The UI's run-detail panel reads from here (no separate
    audit-trail table).
    """

    __tablename__ = "pipeline_node_snapshots"

    # pydantic-graph generates snapshot ids like ``NodeName:uuid_hex``
    # and treats them as opaque opaque strings. We use them as the
    # primary key directly.
    snapshot_id: str = Field(
        max_length=128,
        primary_key=True,
        description="pydantic-graph snapshot id (``{node_id}:{uuid_hex}``).",
    )
    run_id: str = Field(
        max_length=36,
        index=True,
        description="UUID of the owning ``PipelineRun.run_id``.",
    )
    pipeline_name: str = Field(
        max_length=100,
        description="Snake-case pipeline name (mirrors ``PipelineRun``).",
    )

    # Order written. pydantic-graph doesn't carry an inherent sequence,
    # so we autoincrement at write time to give the UI a stable ordering
    # column (resume snapshots can appear out-of-order in time).
    sequence: int = Field(
        index=True,
        description="0-based write order within the run.",
    )

    kind: str = Field(
        max_length=8,
        description="``'node'`` for NodeSnapshot, ``'end'`` for EndSnapshot.",
    )

    # ``node_class_name`` is ``cls.__name__`` of the node about to run
    # (or ``"End"`` for end snapshots). Used by the UI to label each
    # row without having to deserialise ``node_payload`` first.
    node_class_name: str = Field(
        max_length=128,
        description="``BaseNode`` subclass name, or ``'End'``.",
    )

    # Pydantic-dumped payload of the node instance (fields the user
    # set on it) for NodeSnapshot, or the End.data shape for end.
    node_payload: dict = Field(
        sa_column=Column(JSON),
        description="``model_dump`` of the BaseNode instance / End.data.",
    )

    # Full PipelineState dump at the moment this snapshot was taken.
    # Reload + rehydrate to resume the run.
    state_snapshot: dict = Field(
        sa_column=Column(JSON),
        description="``PipelineState.model_dump`` at snapshot time.",
    )

    status: str = Field(
        default="created",
        max_length=10,
        description=(
            "pydantic-graph status: ``created``, ``pending``, "
            "``running``, ``success``, ``error``."
        ),
    )

    # pydantic-graph populates ``start_ts`` when ``record_run`` enters,
    # and ``duration`` (seconds, float) when it exits successfully.
    started_at: Optional[datetime] = Field(default=None)
    duration: Optional[float] = Field(
        default=None,
        description="Wall-clock seconds inside ``record_run`` (float).",
    )

    error: Optional[dict] = Field(
        default=None, sa_column=Column(JSON),
        description="Captured exception summary on ``status='error'``.",
    )

    created_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index("ix_pipeline_node_snapshots_run_seq", "run_id", "sequence"),
        Index("ix_pipeline_node_snapshots_run_kind", "run_id", "kind"),
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

    # Captured from the OTEL context the first time pipeline.execute()
    # opens its root span. Persisted so a paused-and-resumed run can
    # re-attach its resumed spans to the original trace tree (one trace
    # per run, even across review pauses), instead of producing a fresh
    # trace per execute() call.
    trace_id: Optional[str] = Field(
        default=None, max_length=32,
        description="OTEL trace_id of the run's root span (32-char hex)",
    )
    span_id: Optional[str] = Field(
        default=None, max_length=16,
        description="OTEL span_id of the run's root span (16-char hex)",
    )

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


class EvaluationAcceptance(SQLModel, table=True):
    """One row per accepted Phoenix experiment.

    Phase-3 of the evals migration retires the local 5-table eval
    schema (``EvaluationDataset`` / ``Case`` / ``Run`` / ``CaseResult``
    / ``Variant``) — Phoenix is now the source of truth for those.
    The framework still owns one local row: an audit record of which
    experiments have been accepted into production, what the variant
    delta was, and which production surfaces (model config / Phoenix
    prompt / source files) were rewritten.

    Acceptance is append-only; rolling back a previous acceptance
    means accepting a new variant, not deleting a row.
    """

    __tablename__ = "evaluation_acceptances"

    id: Optional[int] = Field(default=None, primary_key=True)

    experiment_id: str = Field(
        max_length=100,
        description="Phoenix experiment id this acceptance was driven from.",
    )
    dataset_id: str = Field(
        max_length=100,
        description="Phoenix dataset id (denormalised for fast filtering).",
    )

    pipeline_name: str = Field(
        max_length=100,
        description="Pipeline whose surfaces were rewritten.",
    )
    step_name: Optional[str] = Field(
        default=None, max_length=100,
        description="Step whose schema/prompt/model was rewritten. "
        "``None`` for pipeline-target acceptances.",
    )

    delta_summary: dict = Field(
        sa_column=Column(JSON),
        description=(
            "Variant delta as JSON: ``{model?, prompt_overrides?, "
            "instructions_delta?}``. Mirrors ``Variant.model_dump()``."
        ),
    )

    accept_paths: dict = Field(
        sa_column=Column(JSON),
        description=(
            "Per-surface result of the accept walk: ``{prompts: [...], "
            "instructions: {...}}``. Each entry records what changed "
            "(Phoenix prompt version, source file path). The ``model`` "
            "key is retired — model variants now propagate through "
            "Phoenix prompt edits, not StepModelConfig rows."
        ),
    )

    notes: Optional[str] = Field(default=None)
    accepted_by: Optional[str] = Field(
        default=None, max_length=100,
        description="Identifier of the user who accepted (free-form).",
    )
    accepted_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index("ix_evaluation_acceptances_experiment", "experiment_id"),
        Index("ix_evaluation_acceptances_dataset", "dataset_id"),
        Index(
            "ix_evaluation_acceptances_pipeline_step",
            "pipeline_name", "step_name",
        ),
    )


__all__ = [
    "PipelineNodeSnapshot",
    "PipelineRunInstance",
    "PipelineRun",
    "DraftStep",
    "DraftPipeline",
    "PipelineReview",
    "EvaluationAcceptance",
]
