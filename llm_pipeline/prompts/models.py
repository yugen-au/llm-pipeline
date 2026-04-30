"""Canonical prompt wire model.

One record carries every message for a prompt — matches Phoenix's native
shape and what the UI editor renders. Used for both responses and
request bodies (`version_id` is surfaced from Phoenix and ignored on writes,
since Phoenix auto-versions).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PromptMessage(BaseModel):
    role: Literal["system", "user"]
    content: str


class PromptMetadata(BaseModel):
    display_name: str | None = None
    category: str | None = None
    step_name: str | None = None
    variable_definitions: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class Prompt(BaseModel):
    name: str
    description: str | None = None
    metadata: PromptMetadata = Field(default_factory=PromptMetadata)
    messages: list[PromptMessage]
    version_id: str | None = None
