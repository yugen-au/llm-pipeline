"""Per-kind discovery walkers — populate ``app.state.registries``.

Each walker takes a list of loaded modules (the output of
:func:`._load_subfolder` for one subfolder), introspects them for
the kind-specific artifact shape, calls the matching builder from
:mod:`llm_pipeline.specs.builders`, and inserts the resulting
:class:`ArtifactRegistration` into ``registries[KIND]``.

Walker order MUST match :data:`LEVEL_BY_KIND` so a walker's
resolver hook can resolve everything below it. Within-level peer
references (e.g. schema -> schema) are handled by the two-pass
discovery pattern: pass 1 populates registries with empty refs;
pass 2 rebuilds with a resolver that sees every kind populated.

Phase C.2.b implements: constants, enums, schemas, steps,
extractions, reviews. Tools and pipelines get skeleton no-op
walkers — both need follow-up work outside this phase scope.
"""
from __future__ import annotations

import inspect
import logging
from pathlib import Path
from types import ModuleType

from llm_pipeline.cst_analysis import ResolverHook
from llm_pipeline.specs import (
    ArtifactRegistration,
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_EXTRACTION,
    KIND_PIPELINE,
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TABLE,
)
from llm_pipeline.specs.builders import (
    build_constant_spec,
    build_enum_spec,
    build_extraction_spec,
    build_pipeline_spec,
    build_review_spec,
    build_schema_spec,
    build_step_spec,
    build_table_spec,
)


__all__ = [
    "WALKERS_BY_SUBFOLDER",
    "walk_constants",
    "walk_enums",
    "walk_extractions",
    "walk_pipelines",
    "walk_reviews",
    "walk_schemas",
    "walk_steps",
    "walk_tables",
    "walk_tools",
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
# Level 1: constants
# ---------------------------------------------------------------------------


_CONSTANT_VALUE_TYPES = (str, int, float, bool, list, dict)


def walk_constants(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Register module-level scalar / list / dict values from ``constants/``.

    ``resolver`` is accepted for interface uniformity but unused —
    constants don't reference other artifacts via cst_analysis at
    spec-build time. (They can reference other artifacts at runtime
    via imports, but there's no field on ConstantSpec for that;
    UI tooling resolves imports separately when displaying a
    constant's source file.)

    Limitation (matches the legacy ``_register_enums_constants``
    behaviour): re-imported names get registered too. If
    ``constants/foo.py`` does ``from .other import X``, ``X`` will
    also appear in the registry under foo's module path. Document
    rather than work around — users shouldn't re-import in
    constants files.
    """
    del resolver  # unused; included for walker uniformity

    for mod in modules:
        for attr_name, value in inspect.getmembers(mod):
            if attr_name.startswith("_"):
                continue
            if not isinstance(value, _CONSTANT_VALUE_TYPES):
                continue
            # Exclude enums (they're caught by ``walk_enums``).
            if inspect.isclass(value):
                continue

            name = _to_registry_key(attr_name)
            cls_path = f"{mod.__name__}.{attr_name}"
            spec = build_constant_spec(
                name=name,
                value=value,
                cls_path=cls_path,
                source_path=_module_path(mod),
            )
            registries[KIND_CONSTANT][name] = ArtifactRegistration(
                spec=spec, obj=value,
            )


# ---------------------------------------------------------------------------
# Level 2: enums
# ---------------------------------------------------------------------------


def walk_enums(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Register ``Enum`` subclasses from ``enums/``.

    ``resolver`` is currently unused — enums declare members
    inline (no source-side cross-artifact refs to capture). When
    the EnumSpec grows ref tracking (e.g. for member values
    referencing constants), this is where the resolver gets used.
    """
    del resolver  # unused for now

    from enum import Enum

    for mod in modules:
        for attr_name, value in inspect.getmembers(mod):
            if attr_name.startswith("_"):
                continue
            if not _is_locally_defined_class(value, mod, Enum):
                continue
            name = _to_registry_key(attr_name)
            spec = build_enum_spec(
                name=name,
                enum_cls=value,
                source_path=_module_path(mod),
            )
            registries[KIND_ENUM][name] = ArtifactRegistration(
                spec=spec, obj=value,
            )


# ---------------------------------------------------------------------------
# Level 3: schemas (BaseModel — peer to tools and tables)
# ---------------------------------------------------------------------------


def walk_schemas(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Register Pydantic ``BaseModel`` subclasses from ``schemas/``.

    Pure data shapes only. SQLModel-with-table classes belong in
    ``llm_pipelines/tables/`` and are picked up by
    :func:`walk_tables`; if a SQLModel-with-table class is found
    here it gets registered as a schema all the same — the
    folder layout is the source-of-truth for the schema/table
    classification.
    """
    from pydantic import BaseModel

    for mod in modules:
        source_text = _module_source(mod)
        for attr_name, value in inspect.getmembers(mod):
            if attr_name.startswith("_"):
                continue
            if not _is_locally_defined_class(value, mod, BaseModel):
                continue
            name = _to_registry_key(attr_name)
            spec = build_schema_spec(
                name=name,
                cls=value,
                source_path=_module_path(mod),
                source_text=source_text,
                resolver=resolver,
            )
            registries[KIND_SCHEMA][name] = ArtifactRegistration(
                spec=spec, obj=value,
            )


def walk_tables(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Register SQLModel-with-``table=True`` classes from ``tables/``.

    The ``__table__`` presence check stays as a defensive filter
    — only classes SQLModel marks as real tables get registered
    (non-table SQLModel subclasses, used as bases or pure data
    shapes, are silently skipped). This guards against a stray
    pure-Pydantic class accidentally landing in ``tables/``.
    """
    from pydantic import BaseModel

    for mod in modules:
        source_text = _module_source(mod)
        for attr_name, value in inspect.getmembers(mod):
            if attr_name.startswith("_"):
                continue
            if not _is_locally_defined_class(value, mod, BaseModel):
                continue
            if not _is_table(value):
                continue
            name = _to_registry_key(attr_name)
            spec = build_table_spec(
                name=name,
                cls=value,
                source_path=_module_path(mod),
                source_text=source_text,
                resolver=resolver,
            )
            registries[KIND_TABLE][name] = ArtifactRegistration(
                spec=spec, obj=value,
            )


# ---------------------------------------------------------------------------
# Level 3: tools (skeleton — no-op until tool convention firms up)
# ---------------------------------------------------------------------------


def walk_tools(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Skeleton walker for ``tools/``.

    The current ``tools/`` convention is "files that call
    ``register_agent``" — there isn't a structurally identifiable
    tool class shape this walker can inspect generically. Future
    work (out of Phase C.2.b scope): pin a tool-class convention
    (e.g. classes subclassing a ``PipelineTool`` base, or a
    ``@tool`` decorator) so this walker has a target.

    For now this is a documented no-op. Tools registered via
    ``register_agent`` continue to live in their existing global
    registry; ``registries[KIND_TOOL]`` stays empty.
    """
    del modules, registries, resolver  # no-op


# ---------------------------------------------------------------------------
# Level 4: steps
# ---------------------------------------------------------------------------


def walk_steps(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Register ``LLMStepNode`` subclasses from ``steps/``.

    Phase C.2.b note: ``StepSpec.prompt`` is left ``None`` here.
    Building :class:`PromptData` requires reading the paired YAML
    and the ``_variables/`` PromptVariables class — that's a
    separate orchestration concern that lands either in C.2.c or
    in a follow-up plan. Steps still get inputs / instructions /
    prepare / run / tool_names populated.
    """
    from llm_pipeline.graph.nodes import LLMStepNode

    for mod in modules:
        source_text = _module_source(mod)
        for attr_name, value in inspect.getmembers(mod):
            if attr_name.startswith("_"):
                continue
            if not _is_locally_defined_class(value, mod, LLMStepNode):
                continue
            name = value.step_name()
            spec = build_step_spec(
                name=name,
                cls=value,
                source_path=_module_path(mod),
                source_text=source_text,
                resolver=resolver,
                prompt=None,
            )
            registries[KIND_STEP][name] = ArtifactRegistration(
                spec=spec, obj=value,
            )


# ---------------------------------------------------------------------------
# Level 4: extractions
# ---------------------------------------------------------------------------


def walk_extractions(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Register ``ExtractionNode`` subclasses from ``extractions/``."""
    from llm_pipeline.graph.nodes import ExtractionNode

    for mod in modules:
        source_text = _module_source(mod)
        for attr_name, value in inspect.getmembers(mod):
            if attr_name.startswith("_"):
                continue
            if not _is_locally_defined_class(value, mod, ExtractionNode):
                continue
            name = _to_registry_key(attr_name, strip_suffix="Extraction")
            spec = build_extraction_spec(
                name=name,
                cls=value,
                source_path=_module_path(mod),
                source_text=source_text,
                resolver=resolver,
            )
            registries[KIND_EXTRACTION][name] = ArtifactRegistration(
                spec=spec, obj=value,
            )


# ---------------------------------------------------------------------------
# Level 4: reviews
# ---------------------------------------------------------------------------


def walk_reviews(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Register ``ReviewNode`` subclasses from ``reviews/``."""
    from llm_pipeline.graph.nodes import ReviewNode

    for mod in modules:
        source_text = _module_source(mod)
        for attr_name, value in inspect.getmembers(mod):
            if attr_name.startswith("_"):
                continue
            if not _is_locally_defined_class(value, mod, ReviewNode):
                continue
            name = _to_registry_key(attr_name, strip_suffix="Review")
            spec = build_review_spec(
                name=name,
                cls=value,
                source_path=_module_path(mod),
                source_text=source_text,
                resolver=resolver,
            )
            registries[KIND_REVIEW][name] = ArtifactRegistration(
                spec=spec, obj=value,
            )


# ---------------------------------------------------------------------------
# Level 5: pipelines (skeleton — old PipelineSpec doesn't subclass ArtifactSpec yet)
# ---------------------------------------------------------------------------


def walk_pipelines(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    """Register ``Pipeline`` subclasses from ``pipelines/``.

    Each pipeline class has its legacy
    :class:`llm_pipeline.graph.spec.PipelineSpec` already built
    and validated at ``Pipeline.__init_subclass__`` time (cached
    on ``cls._spec``). The new
    :class:`llm_pipeline.specs.PipelineSpec` is a per-artifact
    translation of that — populated by
    :func:`llm_pipeline.specs.builders.build_pipeline_spec`.

    Both registries coexist during the migration: the legacy
    ``app.state.pipeline_registry`` powers
    ``/api/pipelines/*``; the new ``registries[KIND_PIPELINE]``
    feeds the kind-uniform ``/api/artifacts/{kind}`` surface.
    """
    from llm_pipeline.graph.pipeline import Pipeline

    for mod in modules:
        source_text = _module_source(mod)
        for attr_name, value in inspect.getmembers(mod):
            if attr_name.startswith("_"):
                continue
            if not _is_locally_defined_class(value, mod, Pipeline):
                continue
            name = value.pipeline_name()
            spec = build_pipeline_spec(
                name=name,
                cls=value,
                source_path=_module_path(mod),
                source_text=source_text,
                resolver=resolver,
            )
            registries[KIND_PIPELINE][name] = ArtifactRegistration(
                spec=spec, obj=value,
            )


# ---------------------------------------------------------------------------
# Subfolder dispatch table
# ---------------------------------------------------------------------------


# Maps each ``llm_pipelines/<subfolder>/`` to its walkers. Used by
# ``conventions.discover_from_convention`` to dispatch each
# subfolder's loaded modules to the right walker(s). Subfolders
# not in this table (e.g. ``_variables``, ``utilities``) are
# walked for import side effects but don't contribute kind
# registrations (intentional per the per-artifact architecture
# plan).
#
# Schema vs Table is decided by folder: ``schemas/`` holds
# Pydantic-only data shapes (-> KIND_SCHEMA); ``tables/`` holds
# SQLModel-with-``table=True`` classes (-> KIND_TABLE). The
# ``__table__`` presence check inside ``walk_tables`` is a
# defensive guard for stray non-table classes; classification
# *intent* lives in the directory layout.
WALKERS_BY_SUBFOLDER: dict[str, list] = {
    "constants": [walk_constants],
    "enums": [walk_enums],
    "schemas": [walk_schemas],
    "tables": [walk_tables],
    "tools": [walk_tools],
    "extractions": [walk_extractions],
    "reviews": [walk_reviews],
    "steps": [walk_steps],
    "pipelines": [walk_pipelines],
}
