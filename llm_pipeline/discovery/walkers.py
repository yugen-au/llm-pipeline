"""Per-kind discovery walkers — populate ``app.state.registries``.

Each walker takes a list of loaded modules, introspects them for
the kind-specific artifact shape, calls the matching builder from
:mod:`llm_pipeline.artifacts.builders`, and inserts the resulting
:class:`ArtifactRegistration` into ``registries[KIND]``.

Walker order MUST match the per-kind level so a walker's resolver
hook can resolve everything below it. Within-level peer references
(e.g. schema -> schema) are handled by the two-pass discovery
pattern: pass 1 populates registries with empty refs; pass 2
rebuilds with a resolver that sees every kind populated.

The :class:`Walker` ABC + shared module-source / locality / naming
helpers live in :mod:`llm_pipeline.artifacts.base.walker`.
"""
from __future__ import annotations

import logging
from types import ModuleType

from llm_pipeline.artifacts.base.kinds import (
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_EXTRACTION,
    KIND_PIPELINE,
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TABLE,
    KIND_TOOL,
)
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _is_table,
    _to_registry_key,
)
from llm_pipeline.artifacts.builders import (
    ConstantBuilder,
    EnumBuilder,
    ExtractionBuilder,
    PipelineBuilder,
    ReviewBuilder,
    SchemaBuilder,
    StepBuilder,
    TableBuilder,
    ToolBuilder,
)


__all__ = [
    "ConstantsWalker",
    "EnumsWalker",
    "ExtractionsWalker",
    "PipelinesWalker",
    "ReviewsWalker",
    "SchemasWalker",
    "StepsWalker",
    "TablesWalker",
    "ToolsWalker",
    "Walker",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Level 1: constants
# ---------------------------------------------------------------------------


class ConstantsWalker(Walker):
    """Register :class:`llm_pipeline.constants.Constant` subclasses from ``constants/``.

    Each constant declares as a ``Constant`` subclass with a
    ``value`` ClassVar — the same class-based discovery shape every
    other kind uses. Type validation lives in
    :meth:`Constant.__init_subclass__`, so malformed declarations
    fail at import time rather than during walk.
    """

    KIND = KIND_CONSTANT
    BUILDER = ConstantBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.constants import Constant

        return _is_locally_defined_class(value, mod, Constant)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)


# ---------------------------------------------------------------------------
# Level 2: enums
# ---------------------------------------------------------------------------


class EnumsWalker(Walker):
    """Register ``Enum`` subclasses from ``enums/``."""

    KIND = KIND_ENUM
    BUILDER = EnumBuilder

    def qualifies(self, value, mod):
        from enum import Enum

        return _is_locally_defined_class(value, mod, Enum)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)


# ---------------------------------------------------------------------------
# Level 3: schemas (BaseModel — peer to tools and tables)
# ---------------------------------------------------------------------------


class SchemasWalker(Walker):
    """Register Pydantic ``BaseModel`` subclasses from ``schemas/``.

    Pure data shapes only. SQLModel-with-table classes belong in
    ``llm_pipelines/tables/`` and are picked up by
    :class:`TablesWalker` — folder layout is the source-of-truth.
    """

    KIND = KIND_SCHEMA
    BUILDER = SchemaBuilder

    def qualifies(self, value, mod):
        from pydantic import BaseModel

        return _is_locally_defined_class(value, mod, BaseModel)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)


# ---------------------------------------------------------------------------
# Level 3: tables (SQLModel-with-table=True)
# ---------------------------------------------------------------------------


class TablesWalker(Walker):
    """Register SQLModel-with-``table=True`` classes from ``tables/``.

    The ``__table__`` presence check stays as a defensive filter —
    only classes SQLModel marks as real tables get registered
    (non-table SQLModel subclasses are silently skipped).
    """

    KIND = KIND_TABLE
    BUILDER = TableBuilder

    def qualifies(self, value, mod):
        from pydantic import BaseModel

        return (
            _is_locally_defined_class(value, mod, BaseModel)
            and _is_table(value)
        )

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)


# ---------------------------------------------------------------------------
# Level 3: tools
# ---------------------------------------------------------------------------


class ToolsWalker(Walker):
    """Register :class:`AgentTool` subclasses from ``tools/``.

    Each subclass declares nested ``Inputs`` (StepInputs) and ``Args``
    (BaseModel) classes plus a ``run`` classmethod. Class-level
    contract violations live on ``cls._init_subclass_errors`` and
    flow into ``ToolSpec`` via :meth:`ArtifactSpec.attach_class_captures`.
    """

    KIND = KIND_TOOL
    BUILDER = ToolBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.agent_tool import AgentTool

        return _is_locally_defined_class(value, mod, AgentTool)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Tool")


# ---------------------------------------------------------------------------
# Level 4: steps
# ---------------------------------------------------------------------------


class StepsWalker(Walker):
    """Register ``LLMStepNode`` subclasses from ``steps/``.

    ``StepSpec.prompt`` is left ``None`` here (the default in
    :class:`StepBuilder`). Building :class:`PromptData` requires
    reading the paired YAML and the per-step ``XPrompt`` class —
    separate orchestration concern. Steps still get
    inputs / instructions / prepare / run / tools populated.
    """

    KIND = KIND_STEP
    BUILDER = StepBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import LLMStepNode

        return _is_locally_defined_class(value, mod, LLMStepNode)

    def name_for(self, attr_name, value):
        return value.step_name()


# ---------------------------------------------------------------------------
# Level 4: extractions
# ---------------------------------------------------------------------------


class ExtractionsWalker(Walker):
    """Register ``ExtractionNode`` subclasses from ``extractions/``."""

    KIND = KIND_EXTRACTION
    BUILDER = ExtractionBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import ExtractionNode

        return _is_locally_defined_class(value, mod, ExtractionNode)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Extraction")


# ---------------------------------------------------------------------------
# Level 4: reviews
# ---------------------------------------------------------------------------


class ReviewsWalker(Walker):
    """Register ``ReviewNode`` subclasses from ``reviews/``."""

    KIND = KIND_REVIEW
    BUILDER = ReviewBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import ReviewNode

        return _is_locally_defined_class(value, mod, ReviewNode)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Review")


# ---------------------------------------------------------------------------
# Level 5: pipelines
# ---------------------------------------------------------------------------


class PipelinesWalker(Walker):
    """Register ``Pipeline`` subclasses from ``pipelines/``.

    Each pipeline class has its legacy
    :class:`llm_pipeline.graph.spec.PipelineSpec` already built and
    validated at ``Pipeline.__init_subclass__`` time. The new
    :class:`llm_pipeline.artifacts.PipelineSpec` is a per-artifact
    translation of that — populated by :class:`PipelineBuilder`.
    Both registries coexist during the migration.
    """

    KIND = KIND_PIPELINE
    BUILDER = PipelineBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.graph.pipeline import Pipeline

        return _is_locally_defined_class(value, mod, Pipeline)

    def name_for(self, attr_name, value):
        return value.pipeline_name()


# Subfolder→walker dispatch lives in
# :data:`llm_pipeline.discovery.manifest.WALKERS_BY_SUBFOLDER`.
# Conventions / consumers import from manifest directly.
#
# Schema vs Table is decided by folder layout: ``schemas/`` holds
# Pydantic-only data shapes (→ KIND_SCHEMA); ``tables/`` holds
# SQLModel-with-``table=True`` classes (→ KIND_TABLE). The
# ``__table__`` presence check inside :class:`TablesWalker` is a
# defensive guard for stray non-table classes; classification
# *intent* lives in the directory layout.
