"""Per-kind spec builders — back-compat re-exports.

Per-kind builders now live alongside their spec in the matching
``llm_pipeline.artifacts.{kind}`` module. This shim keeps the old
import path working until callers migrate.

The :class:`SpecBuilder` ABC + shared helpers live in
:mod:`llm_pipeline.artifacts.base.builder`.
"""
from __future__ import annotations

from llm_pipeline.artifacts.base.builder import (
    SpecBuilder,
    build_code_body,
    json_schema_with_refs,
)
from llm_pipeline.artifacts.constants import ConstantBuilder
from llm_pipeline.artifacts.enums import EnumBuilder
from llm_pipeline.artifacts.extractions import ExtractionBuilder
from llm_pipeline.artifacts.pipelines import PipelineBuilder
from llm_pipeline.artifacts.reviews import ReviewBuilder
from llm_pipeline.artifacts.schemas import SchemaBuilder
from llm_pipeline.artifacts.steps import StepBuilder
from llm_pipeline.artifacts.tables import TableBuilder
from llm_pipeline.artifacts.tools import ToolBuilder


__all__ = [
    "build_code_body",
    "json_schema_with_refs",
    "SpecBuilder",
    "ConstantBuilder",
    "EnumBuilder",
    "ExtractionBuilder",
    "PipelineBuilder",
    "ReviewBuilder",
    "SchemaBuilder",
    "StepBuilder",
    "TableBuilder",
    "ToolBuilder",
]
