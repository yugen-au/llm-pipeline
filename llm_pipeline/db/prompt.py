"""
Prompt model for LLM pipeline prompt storage.
"""
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import Index, text


class Prompt(SQLModel, table=True):
    """Prompt templates and system instructions for LLM operations."""
    __tablename__ = "prompts"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identification
    prompt_key: str = Field(max_length=100, index=True)
    prompt_name: str = Field(max_length=200)
    prompt_type: str = Field(max_length=50)  # system, user

    # Organization
    category: Optional[str] = Field(default=None, max_length=50)
    step_name: Optional[str] = Field(default=None, max_length=50)

    # Content
    content: str

    # Template variables (automatically extracted from {variable_name} in content)
    required_variables: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))

    # Rich variable definitions: {name: {type, description, required, auto_generate}}
    # Editable via UI, merged with code-registered PromptVariables at runtime
    variable_definitions: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # Metadata
    description: Optional[str] = None
    version: str = Field(default="1.0", max_length=20)
    is_active: bool = Field(default=True)
    is_latest: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = Field(default=None, max_length=100)

    # Indexes and constraints
    __table_args__ = (
        Index(
            "uq_prompts_active_latest",
            "prompt_key", "prompt_type",
            unique=True,
            sqlite_where=text("is_active = 1 AND is_latest = 1"),
            postgresql_where=text("is_active = true AND is_latest = true"),
        ),
        Index("ix_prompts_key_type_live",
              "prompt_key", "prompt_type", "is_active", "is_latest"),
        Index("ix_prompts_category_step", "category", "step_name"),
        Index("ix_prompts_key_type_version",
              "prompt_key", "prompt_type", "version"),
    )

    def __repr__(self) -> str:
        return f"<Prompt(id={self.id}, key='{self.prompt_key}', type='{self.prompt_type}')>"


__all__ = ["Prompt"]
