"""
Data models for the meta-pipeline step generator.

Defines intermediate Pydantic models for structured step specification
and the GenerationRecord SQLModel for persisting generation history.
"""
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Column, Field, JSON, SQLModel


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


__all__ = ["FieldDefinition", "ExtractionTarget", "GenerationRecord"]
