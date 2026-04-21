"""Evaluation system database models."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Index, text
from sqlmodel import SQLModel, Field, Column, JSON


def utc_now():
    return datetime.now(timezone.utc)


class EvaluationDataset(SQLModel, table=True):
    """Dataset grouping evaluation cases for a step or pipeline."""
    __tablename__ = "eval_datasets"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=200, sa_column_kwargs={"unique": True})
    target_type: str = Field(max_length=20)  # "step" | "pipeline"
    target_name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index("ix_eval_datasets_name", "name"),
    )


class EvaluationCase(SQLModel, table=True):
    """Single test case within an evaluation dataset."""
    __tablename__ = "eval_cases"

    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: int = Field(foreign_key="eval_datasets.id", index=True)
    name: str = Field(max_length=200)
    inputs: dict = Field(sa_column=Column(JSON))
    expected_output: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    metadata_: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    version: str = Field(default="1.0", max_length=20)
    is_active: bool = Field(default=True)
    is_latest: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index(
            "uq_eval_cases_active_latest",
            "dataset_id", "name",
            unique=True,
            sqlite_where=text("is_active = 1 AND is_latest = 1"),
            postgresql_where=text("is_active = true AND is_latest = true"),
        ),
        Index("ix_eval_cases_dataset", "dataset_id"),
        Index("ix_eval_cases_dataset_live",
              "dataset_id", "is_active", "is_latest"),
        Index("ix_eval_cases_dataset_name_version",
              "dataset_id", "name", "version"),
    )


class EvaluationRun(SQLModel, table=True):
    """Single execution of an evaluation dataset."""
    __tablename__ = "eval_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: int = Field(foreign_key="eval_datasets.id", index=True)
    status: str = Field(default="pending", max_length=20)  # pending|running|completed|failed
    total_cases: int = Field(default=0)
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    errored: int = Field(default=0)
    report_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error_message: Optional[str] = Field(default=None)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = Field(default=None)
    variant_id: Optional[int] = Field(default=None, foreign_key="eval_variants.id")
    delta_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    case_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    prompt_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    model_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    instructions_schema_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    __table_args__ = (
        Index("ix_eval_runs_dataset", "dataset_id"),
    )


class EvaluationCaseResult(SQLModel, table=True):
    """Result of evaluating a single case within a run."""
    __tablename__ = "eval_case_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="eval_runs.id", index=True)
    case_id: int = Field(foreign_key="eval_cases.id", index=True)
    case_name: str = Field(max_length=200)
    passed: bool = Field(default=False)
    evaluator_scores: dict = Field(sa_column=Column(JSON))
    output_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error_message: Optional[str] = Field(default=None)

    __table_args__ = (
        Index("ix_eval_case_results_run", "run_id"),
        Index("ix_eval_case_results_case", "case_id"),
    )


class EvaluationVariant(SQLModel, table=True):
    """Delta-based override for a step definition, scoped to a dataset.

    The `delta` field stores JSON with keys: `model`, `system_prompt`,
    `user_prompt`, `instructions_delta`. Applied by the runner before
    sandbox execution and evaluator resolution.
    """
    __tablename__ = "eval_variants"

    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: int = Field(foreign_key="eval_datasets.id", index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    delta: dict = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index("ix_eval_variants_dataset", "dataset_id"),
    )


__all__ = [
    "EvaluationDataset",
    "EvaluationCase",
    "EvaluationRun",
    "EvaluationCaseResult",
    "EvaluationVariant",
]
