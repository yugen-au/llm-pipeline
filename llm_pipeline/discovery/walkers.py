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

Architecture: a small :class:`Walker` ABC owns the iteration
scaffold (per-module source/imports analysis + member enumeration
+ name filtering + registry insertion). Each kind subclasses with
three hooks — ``qualifies``, ``name_for``, ``build_spec`` — and
the rest is inherited. Public ``walk_*`` functions are thin
wrappers around the matching walker instance (kept for
:data:`WALKERS_BY_SUBFOLDER` and external callers).
"""
from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

from llm_pipeline.cst_analysis import ResolverHook, analyze_imports
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
    4. Build the per-kind spec via :meth:`build_spec`.
    5. Stamp ``spec.imports`` with the once-per-module list.
    6. Insert into ``registries[KIND][name]``.

    Subclasses pin :attr:`KIND` and override the three kind-
    specific hooks. Adding a new kind = a new subclass plus an
    entry in :data:`WALKERS_BY_SUBFOLDER` — the iteration scaffold
    is inherited.
    """

    # The ``KIND_*`` constant for the artifact registry slot this
    # walker populates.
    KIND: ClassVar[str]

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

    @abstractmethod
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
        """Construct the per-kind spec. Subclass calls the matching
        ``build_*_spec`` from :mod:`llm_pipeline.specs.builders`.

        ``attr_name`` is the original Python identifier (e.g.
        ``MAX_RETRIES``); ``name`` is the snake-cased registry key
        (e.g. ``max_retries``). Most subclasses just need ``name``;
        constants need ``attr_name`` to construct the dotted
        ``cls_path`` that the resolver uses for reverse lookup.
        """

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


_CONSTANT_VALUE_TYPES = (str, int, float, bool, list, dict)


class ConstantsWalker(Walker):
    """Register module-level scalar / list / dict values from ``constants/``.

    Limitation (matches legacy behaviour): re-imported names get
    registered too. If ``constants/foo.py`` does
    ``from .other import X``, ``X`` will also appear in the registry
    under foo's module path. Document rather than work around —
    users shouldn't re-import in constants files.
    """

    KIND = KIND_CONSTANT

    def qualifies(self, value, mod):
        # Plain primitive value, NOT a class (Enum subclasses go to
        # walk_enums).
        return (
            isinstance(value, _CONSTANT_VALUE_TYPES)
            and not inspect.isclass(value)
        )

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)

    def build_spec(self, *, name, attr_name, value, mod, source_text, resolver):
        # ``cls_path`` uses the original Python identifier — that's
        # what an importer of this module would write
        # (``from constants import MAX_RETRIES``), and it's what
        # the resolver's reverse index looks up against.
        return build_constant_spec(
            name=name,
            value=value,
            cls_path=f"{mod.__name__}.{attr_name}",
            source_path=_module_path(mod),
        )


def walk_constants(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    ConstantsWalker().walk(modules, registries, resolver)


# ---------------------------------------------------------------------------
# Level 2: enums
# ---------------------------------------------------------------------------


class EnumsWalker(Walker):
    """Register ``Enum`` subclasses from ``enums/``."""

    KIND = KIND_ENUM

    def qualifies(self, value, mod):
        from enum import Enum

        return _is_locally_defined_class(value, mod, Enum)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)

    def build_spec(self, *, name, attr_name, value, mod, source_text, resolver):
        return build_enum_spec(
            name=name,
            enum_cls=value,
            source_path=_module_path(mod),
        )


def walk_enums(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    EnumsWalker().walk(modules, registries, resolver)


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

    def qualifies(self, value, mod):
        from pydantic import BaseModel

        return _is_locally_defined_class(value, mod, BaseModel)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)

    def build_spec(self, *, name, attr_name, value, mod, source_text, resolver):
        return build_schema_spec(
            name=name,
            cls=value,
            source_path=_module_path(mod),
            source_text=source_text,
            resolver=resolver,
        )


def walk_schemas(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    SchemasWalker().walk(modules, registries, resolver)


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

    def qualifies(self, value, mod):
        from pydantic import BaseModel

        return (
            _is_locally_defined_class(value, mod, BaseModel)
            and _is_table(value)
        )

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)

    def build_spec(self, *, name, attr_name, value, mod, source_text, resolver):
        return build_table_spec(
            name=name,
            cls=value,
            source_path=_module_path(mod),
            source_text=source_text,
            resolver=resolver,
        )


def walk_tables(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    TablesWalker().walk(modules, registries, resolver)


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
    tool class shape this walker can inspect generically. Kept as
    a function (rather than a :class:`Walker` subclass) because
    there's nothing to walk yet.

    For now this is a documented no-op. Tools registered via
    ``register_agent`` continue to live in their existing global
    registry; ``registries[KIND_TOOL]`` stays empty.
    """
    del modules, registries, resolver  # no-op


# ---------------------------------------------------------------------------
# Level 4: steps
# ---------------------------------------------------------------------------


class StepsWalker(Walker):
    """Register ``LLMStepNode`` subclasses from ``steps/``.

    ``StepSpec.prompt`` is left ``None`` here. Building
    :class:`PromptData` requires reading the paired YAML and the
    ``_variables/`` PromptVariables class — separate orchestration
    concern. Steps still get inputs / instructions / prepare /
    run / tool_names populated.
    """

    KIND = KIND_STEP

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import LLMStepNode

        return _is_locally_defined_class(value, mod, LLMStepNode)

    def name_for(self, attr_name, value):
        return value.step_name()

    def build_spec(self, *, name, attr_name, value, mod, source_text, resolver):
        return build_step_spec(
            name=name,
            cls=value,
            source_path=_module_path(mod),
            source_text=source_text,
            resolver=resolver,
            prompt=None,
        )


def walk_steps(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    StepsWalker().walk(modules, registries, resolver)


# ---------------------------------------------------------------------------
# Level 4: extractions
# ---------------------------------------------------------------------------


class ExtractionsWalker(Walker):
    """Register ``ExtractionNode`` subclasses from ``extractions/``."""

    KIND = KIND_EXTRACTION

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import ExtractionNode

        return _is_locally_defined_class(value, mod, ExtractionNode)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Extraction")

    def build_spec(self, *, name, attr_name, value, mod, source_text, resolver):
        return build_extraction_spec(
            name=name,
            cls=value,
            source_path=_module_path(mod),
            source_text=source_text,
            resolver=resolver,
        )


def walk_extractions(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    ExtractionsWalker().walk(modules, registries, resolver)


# ---------------------------------------------------------------------------
# Level 4: reviews
# ---------------------------------------------------------------------------


class ReviewsWalker(Walker):
    """Register ``ReviewNode`` subclasses from ``reviews/``."""

    KIND = KIND_REVIEW

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import ReviewNode

        return _is_locally_defined_class(value, mod, ReviewNode)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Review")

    def build_spec(self, *, name, attr_name, value, mod, source_text, resolver):
        return build_review_spec(
            name=name,
            cls=value,
            source_path=_module_path(mod),
            source_text=source_text,
            resolver=resolver,
        )


def walk_reviews(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    ReviewsWalker().walk(modules, registries, resolver)


# ---------------------------------------------------------------------------
# Level 5: pipelines
# ---------------------------------------------------------------------------


class PipelinesWalker(Walker):
    """Register ``Pipeline`` subclasses from ``pipelines/``.

    Each pipeline class has its legacy
    :class:`llm_pipeline.graph.spec.PipelineSpec` already built
    and validated at ``Pipeline.__init_subclass__`` time. The new
    :class:`llm_pipeline.specs.PipelineSpec` is a per-artifact
    translation of that — populated by
    :func:`llm_pipeline.specs.builders.build_pipeline_spec`. Both
    registries coexist during the migration.
    """

    KIND = KIND_PIPELINE

    def qualifies(self, value, mod):
        from llm_pipeline.graph.pipeline import Pipeline

        return _is_locally_defined_class(value, mod, Pipeline)

    def name_for(self, attr_name, value):
        return value.pipeline_name()

    def build_spec(self, *, name, attr_name, value, mod, source_text, resolver):
        return build_pipeline_spec(
            name=name,
            cls=value,
            source_path=_module_path(mod),
            source_text=source_text,
            resolver=resolver,
        )


def walk_pipelines(
    modules: list[ModuleType],
    registries: dict[str, dict[str, ArtifactRegistration]],
    resolver: ResolverHook,
) -> None:
    PipelinesWalker().walk(modules, registries, resolver)


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
