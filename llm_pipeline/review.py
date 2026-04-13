"""Human-in-the-loop review system for pipeline steps.

Declarative review points that pause pipeline execution, notify
reviewers, and resume based on the review decision.
"""
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict


class DisplayFieldType(str, Enum):
    """Supported display types for review page rendering."""
    text = "text"
    number = "number"
    progress = "progress"  # 0-1 bar
    table = "table"        # list of dicts
    code = "code"          # monospace
    badge = "badge"        # status label


class DisplayField(BaseModel):
    """A single field rendered on the review page."""
    label: str
    value: Any
    type: str = "text"


class ReviewData(BaseModel):
    """What the reviewer sees: human-friendly display + raw JSON."""
    display_data: list[DisplayField] = []
    raw_data: dict | None = None


class ReviewDecision(str, Enum):
    """Possible review outcomes."""
    approved = "approved"
    minor_revision = "minor_revision"
    major_revision = "major_revision"
    restart = "restart"


class StepReview(BaseModel):
    """Base review config. Subclass per step following naming convention.

    Example:
        class ClassifyReview(StepReview):
            pass

        @step_definition(instructions=ClassifyInstructions, review=ClassifyReview)
        class ClassifyStep(LLMStep): ...
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    enabled: bool = True
    condition: Optional[Callable] = None
    default_resume_step: Optional[str] = None
    webhook_url: Optional[str] = None


__all__ = [
    "DisplayField",
    "DisplayFieldType",
    "ReviewData",
    "ReviewDecision",
    "StepReview",
]
