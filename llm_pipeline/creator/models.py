"""
Data models for the meta-pipeline step generator.

Defines intermediate Pydantic models for structured step specification,
the GenerationRecord SQLModel for persisting generation history,
and the GeneratedStep adapter for typed access to generated artifacts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel
from sqlmodel import Column, Field, JSON, SQLModel

if TYPE_CHECKING:
    from llm_pipeline.state import DraftStep


def _to_pascal_case(snake: str) -> str:
    """Convert snake_case to PascalCase. e.g. 'sentiment_analysis' -> 'SentimentAnalysis'."""
    return snake.title().replace("_", "")


class FieldDefinition(BaseModel):
    """Definition of a single field on a generated Instructions or Context class."""

    name: str
    type_annotation: str
    description: str
    default: str | None = None
    is_required: bool = True


class ExtractionTarget(BaseModel):
    """Specification for a PipelineExtraction target model to be generated."""

    model_name: str
    fields: list[FieldDefinition]
    source_field_mapping: dict[str, str]


class GeneratedStep(BaseModel):
    """Typed adapter over DraftStep.generated_code dict.

    Extracts individual artifact file contents and derives class names
    from the step name. Used as the typed boundary between the untyped
    generated_code JSON dict and StepIntegrator.integrate().
    """

    step_name: str
    step_class_name: str
    instructions_class_name: str
    step_code: str
    instructions_code: str
    prompts_code: str
    extraction_code: str | None = None
    all_artifacts: dict[str, str]

    @classmethod
    def from_draft(cls, draft: DraftStep) -> GeneratedStep:
        """Build GeneratedStep from a DraftStep's generated_code dict.

        Derives PascalCase class names from draft.name and extracts
        file contents using the naming convention {step_name}_step.py etc.
        """
        name = draft.name
        gc = draft.generated_code
        pascal = _to_pascal_case(name)

        return cls(
            step_name=name,
            step_class_name=f"{pascal}Step",
            instructions_class_name=f"{pascal}Instructions",
            step_code=gc[f"{name}_step.py"],
            instructions_code=gc[f"{name}_instructions.py"],
            prompts_code=gc[f"{name}_prompts.py"],
            extraction_code=gc.get(f"{name}_extraction.py"),
            all_artifacts=dict(gc),
        )


class IntegrationResult(BaseModel):
    """Result returned by StepIntegrator.integrate()."""

    files_written: list[str]
    prompts_registered: int
    pipeline_file_updated: bool
    target_dir: str


class GenerationRecord(SQLModel, table=True):
    """
    Tracks each code generation run for audit and downstream consumption.

    Used by StepCreatorRegistry for DB persistence and queried by
    Task 47 (StepIntegrator) to locate generated artifacts.
    """

    __tablename__ = "creator_generation_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(description="UUID identifying the pipeline run")
    step_name_generated: str = Field(
        description="Name of the step that was generated"
    )
    files_generated: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="List of file paths produced by this generation",
    )
    is_valid: bool = Field(
        default=False,
        description="Whether generated code passed validation",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of generation",
    )


__all__ = [
    "FieldDefinition",
    "ExtractionTarget",
    "GeneratedStep",
    "IntegrationResult",
    "GenerationRecord",
]
