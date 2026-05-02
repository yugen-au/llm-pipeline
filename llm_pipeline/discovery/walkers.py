"""Per-kind discovery walkers — populate ``app.state.registries``.

Each walker takes a list of loaded modules (the output of
:func:`._load_subfolder` for one subfolder), introspects them for
the kind-specific artifact shape, calls the matching builder from
:mod:`llm_pipeline.artifacts.builders`, and inserts the resulting
:class:`ArtifactRegistration` into ``registries[KIND]``.

Walker order MUST match the per-kind level so a walker's resolver
hook can resolve everything below it. Within-level peer references
(e.g. schema -> schema) are handled by the two-pass discovery
pattern: pass 1 populates registries with empty refs; pass 2
rebuilds with a resolver that sees every kind populated.

Architecture: a small :class:`Walker` ABC owns the iteration
scaffold (per-module source/imports analysis + member enumeration
+ name filtering + registry insertion). Each kind subclasses with
three hooks — ``qualifies``, ``name_for``, ``build_spec`` — and
the rest is inherited. Public ``walk_*`` functions are thin
wrappers around the matching walker instance, registered in
:data:`llm_pipeline.discovery.manifest.KIND_MANIFESTS` for
dispatch.
"""
from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

from llm_pipeline.cst_analysis import ResolverHook, analyze_imports
# Import from submodules (not the ``specs`` package) to keep the
# manifest's import chain acyclic. ``specs/__init__.py`` imports
# from ``discovery.manifest``, which imports this module — going
# through ``llm_pipeline.artifacts`` here would trigger that cycle.
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
from llm_pipeline.artifacts.base.registration import ArtifactRegistration
from llm_pipeline.artifacts.builders import (
    ConstantBuilder,
    EnumBuilder,
    ExtractionBuilder,
    PipelineBuilder,
    ReviewBuilder,
    SchemaBuilder,
    SpecBuilder,
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
# Shared helpers
# ---------------------------------------------------------------------------


def _module_source(mod: ModuleType) -> str:
    """Read ``mod.__file__`` and return its text, or "" if unavailable."""
    path = getattr(mod, "__file__", None)
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _module_path(mod: ModuleType) -> str:
    """Filesystem path of ``mod.__file__`` as a string, or "" if unavailable."""
    path = getattr(mod, "__file__", None)
    return str(path) if path else ""


def _is_locally_defined_class(value: object, mod: ModuleType, base: type) -> bool:
    """``True`` iff ``value`` is a strict subclass of ``base`` defined in ``mod``."""
    return (
        inspect.isclass(value)
        and issubclass(value, base)
        and value is not base
        and getattr(value, "__module__", None) == mod.__name__
    )


def _is_table(cls: type) -> bool:
    """``True`` iff ``cls`` is a SQLModel class with ``table=True``.

    SQLModel only sets ``__table__`` on classes declared with
    ``table=True``; non-table SQLModel subclasses (used as bases
    or pure data shapes) leave it unset. This single check covers
    both "is SQLModel" and "has a real table" without needing a
    SQLModel import here.
    """
    return getattr(cls, "__table__", None) is not None


def _imports_for_module(source_text: str, resolver: ResolverHook) -> list:
    """Analyse imports for a module's source. Empty list when source is unavailable.

    Walked once per module by each walker; the returned list is
    shared across every artifact registered from that module so
    we don't re-parse for each one.
    """
    if not source_text:
        return []
    try:
        return analyze_imports(source=source_text, resolver=resolver)
    except Exception:  # noqa: BLE001 — analysis is best-effort
        return []


def _to_registry_key(identifier: str, *, strip_suffix: str | None = None) -> str:
    """Snake-case the Python identifier into the registry key.

    Defers to :func:`llm_pipeline.naming.to_snake_case`. The strip
    suffix lets us drop the conventional class-name suffix
    (``Step`` / ``Extraction`` / ``Review``).
    """
    from llm_pipeline.naming import to_snake_case

    if strip_suffix is None:
        return to_snake_case(identifier)
    return to_snake_case(identifier, strip_suffix=strip_suffix)


# ---------------------------------------------------------------------------
# Walker base class — owns the per-module iteration scaffold
# ---------------------------------------------------------------------------


class Walker(ABC):
    """Per-kind discovery walker base.

    Encapsulates the iteration shared by every kind:

    1. For each module: read its source text, analyse imports.
    2. For each member of the module: skip ``_``-prefixed names,
       skip members that don't pass :meth:`qualifies`.
    3. Compute the registry key via :meth:`name_for`.
    4. Build the per-kind spec via :meth:`build_spec` (default
       implementation calls ``self.BUILDER(...).build()`` for the
       standard class-based pattern; value-based kinds override).
    5. Stamp ``spec.imports`` with the once-per-module list.
    6. Insert into ``registries[KIND][name]``.

    Subclasses pin :attr:`KIND` and :attr:`BUILDER`, override
    :meth:`qualifies` and :meth:`name_for`, and (when value-based)
    override :meth:`build_spec`. Adding a new kind = a new subclass
    plus an entry in
    :data:`llm_pipeline.discovery.manifest.KIND_MANIFESTS` — the
    iteration scaffold is inherited.
    """

    # The ``KIND_*`` constant for the artifact registry slot this
    # walker populates.
    KIND: ClassVar[str]

    # The :class:`SpecBuilder` subclass this walker dispatches to.
    # The default :meth:`build_spec` instantiates ``BUILDER`` with
    # the standard class-based signature (``name``, ``cls=value``,
    # ``source_path``, ``source_text``, ``resolver``); value-based
    # kinds (constants) override :meth:`build_spec` to pass their
    # own kwargs.
    BUILDER: ClassVar[type[SpecBuilder]]

    @abstractmethod
    def qualifies(self, value: Any, mod: ModuleType) -> bool:
        """Return ``True`` if ``value`` is a member of this kind in ``mod``.

        Called for every non-private member; only members for which
        this returns ``True`` get registered.
        """

    @abstractmethod
    def name_for(self, attr_name: str, value: Any) -> str:
        """Return the registry key for ``value`` (snake_case).

        Most kinds derive from ``attr_name``; node kinds delegate to
        a class method (``cls.step_name()`` etc.).
        """

    def build_spec(
        self,
        *,
        name: str,
        attr_name: str,
        value: Any,
        mod: ModuleType,
        source_text: str,
        resolver: ResolverHook,
    ):
        """Construct the per-kind spec via :attr:`BUILDER`.

        Default implementation: standard class-based call —
        ``self.BUILDER(name=name, cls=value, source_path=...,
        source_text=..., resolver=...).build()``.

        Value-based kinds (constants) override to supply their own
        builder kwargs.

        ``attr_name`` is the original Python identifier (e.g.
        ``MAX_RETRIES``); ``name`` is the snake-cased registry key
        (e.g. ``max_retries``).
        """
        return self.BUILDER(
            name=name,
            cls=value,
            source_path=_module_path(mod),
            source_text=source_text,
            resolver=resolver,
        ).build()

    def walk(
        self,
        modules: list[ModuleType],
        registries: dict[str, dict[str, ArtifactRegistration]],
        resolver: ResolverHook,
    ) -> None:
        for mod in modules:
            source_text = _module_source(mod)
            imports = _imports_for_module(source_text, resolver)
            for attr_name, value in inspect.getmembers(mod):
                if attr_name.startswith("_"):
                    continue
                if not self.qualifies(value, mod):
                    continue
                name = self.name_for(attr_name, value)
                spec = self.build_spec(
                    name=name,
                    attr_name=attr_name,
                    value=value,
                    mod=mod,
                    source_text=source_text,
                    resolver=resolver,
                )
                spec.imports = imports
                registries[self.KIND][name] = ArtifactRegistration(
                    spec=spec, obj=value,
                )


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
