"""Single source of truth for per-kind discovery metadata.

Per-kind metadata used to live in four hand-maintained tables —
:data:`llm_pipeline.specs.kinds.LEVEL_BY_KIND`,
:data:`llm_pipeline.discovery.loading._LOAD_ORDER`,
:data:`llm_pipeline.discovery.walkers.WALKERS_BY_SUBFOLDER`, and
:data:`llm_pipeline.specs.kinds.ALL_KINDS`.
Adding a new kind required editing each one; forgetting any was a
silent bug. This module collapses them into :data:`KIND_MANIFESTS`;
the four tables become derived views.

Adding a new kind = one entry in :data:`KIND_MANIFESTS`. Done.

Every entry in :data:`KIND_MANIFESTS` is a real first-class kind —
no sentinel rows, no side-effect-only folders. The previous
``_variables/`` exception was eliminated by co-locating each
``XPrompt(PromptVariables)`` class with its paired step (same
file).
"""
from __future__ import annotations

from dataclasses import dataclass

from llm_pipeline.discovery.walkers import (
    ConstantsWalker,
    EnumsWalker,
    ExtractionsWalker,
    PipelinesWalker,
    ReviewsWalker,
    SchemasWalker,
    StepsWalker,
    TablesWalker,
    ToolsWalker,
    Walker,
)
from llm_pipeline.specs.constants import ConstantSpec
from llm_pipeline.specs.enums import EnumSpec
from llm_pipeline.specs.extractions import ExtractionFields, ExtractionSpec
from llm_pipeline.specs.kinds import (
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
from llm_pipeline.specs.pipelines import PipelineSpec
from llm_pipeline.specs.reviews import ReviewFields, ReviewSpec
from llm_pipeline.specs.schemas import SchemaSpec
from llm_pipeline.specs.steps import StepFields, StepSpec
from llm_pipeline.specs.tables import TableSpec
from llm_pipeline.specs.tools import ToolSpec


__all__ = [
    "KIND_MANIFESTS",
    "KindManifest",
    "LEVEL_BY_KIND",
    "LOAD_ORDER",
    "WALKERS_BY_SUBFOLDER",
]


@dataclass(frozen=True)
class KindManifest:
    """Per-kind metadata. One entry per first-class artifact kind.

    - ``kind``: the ``KIND_*`` constant — registry key on
      ``app.state.registries`` and dispatch tag on the wire.
    - ``subfolder``: directory under ``llm_pipelines/`` holding
      this kind's files.
    - ``level``: dependency tier. A kind at level N may reference
      kinds at level < N (peer references allowed where there's no
      cycle). Drives both module load order and walker resolver
      visibility.
    - ``spec_cls``: the per-kind :class:`ArtifactSpec` subclass.
    - ``fields_cls``: the per-kind ``Fields`` constants class
      (routing keys for ``__init_subclass__`` captures), or
      ``None`` for kinds without capture sites.
    - ``walker``: the per-kind :class:`Walker` instance —
      ``conventions.discover_from_convention`` calls
      ``walker.walk(modules, registries, resolver)`` for the
      matching subfolder.
    """

    kind: str
    subfolder: str
    level: int
    spec_cls: type
    fields_cls: type | None
    walker: Walker


# Single source of truth. Adding a new kind = one entry here.
KIND_MANIFESTS: dict[str, KindManifest] = {
    KIND_CONSTANT: KindManifest(
        kind=KIND_CONSTANT, subfolder="constants", level=1,
        spec_cls=ConstantSpec, fields_cls=None,
        walker=ConstantsWalker(),
    ),
    KIND_ENUM: KindManifest(
        kind=KIND_ENUM, subfolder="enums", level=2,
        spec_cls=EnumSpec, fields_cls=None,
        walker=EnumsWalker(),
    ),
    KIND_SCHEMA: KindManifest(
        kind=KIND_SCHEMA, subfolder="schemas", level=3,
        spec_cls=SchemaSpec, fields_cls=None,
        walker=SchemasWalker(),
    ),
    KIND_TABLE: KindManifest(
        kind=KIND_TABLE, subfolder="tables", level=3,
        spec_cls=TableSpec, fields_cls=None,
        walker=TablesWalker(),
    ),
    KIND_TOOL: KindManifest(
        kind=KIND_TOOL, subfolder="tools", level=3,
        spec_cls=ToolSpec, fields_cls=None,
        walker=ToolsWalker(),
    ),
    KIND_EXTRACTION: KindManifest(
        kind=KIND_EXTRACTION, subfolder="extractions", level=4,
        spec_cls=ExtractionSpec, fields_cls=ExtractionFields,
        walker=ExtractionsWalker(),
    ),
    KIND_REVIEW: KindManifest(
        kind=KIND_REVIEW, subfolder="reviews", level=4,
        spec_cls=ReviewSpec, fields_cls=ReviewFields,
        walker=ReviewsWalker(),
    ),
    KIND_STEP: KindManifest(
        kind=KIND_STEP, subfolder="steps", level=4,
        spec_cls=StepSpec, fields_cls=StepFields,
        walker=StepsWalker(),
    ),
    KIND_PIPELINE: KindManifest(
        kind=KIND_PIPELINE, subfolder="pipelines", level=5,
        spec_cls=PipelineSpec, fields_cls=None,
        walker=PipelinesWalker(),
    ),
}


# Derived views. These are what the rest of the codebase consumes.

LEVEL_BY_KIND: dict[str, int] = {
    m.kind: m.level for m in KIND_MANIFESTS.values()
}

# Subfolder load order: by level, then by subfolder name within a
# level (deterministic). Module-import dependencies (lower-level
# files referenced at module-load time) are respected because levels
# encode the dependency tier.
LOAD_ORDER: list[str] = [
    m.subfolder
    for m in sorted(
        KIND_MANIFESTS.values(), key=lambda m: (m.level, m.subfolder),
    )
]

WALKERS_BY_SUBFOLDER: dict[str, list[Walker]] = {
    m.subfolder: [m.walker] for m in KIND_MANIFESTS.values()
}


# Module-load-time sanity check: catch drift between the manifest
# and the KIND_* / ALL_KINDS constants. Cheap insurance — fires
# loudly on import if someone adds a kind to one and not the other.
def _check_manifest_consistency() -> None:
    from llm_pipeline.specs.kinds import ALL_KINDS

    manifest_kinds = set(KIND_MANIFESTS)
    declared_kinds = set(ALL_KINDS)
    if manifest_kinds != declared_kinds:
        missing_from_manifest = declared_kinds - manifest_kinds
        missing_from_all = manifest_kinds - declared_kinds
        details: list[str] = []
        if missing_from_manifest:
            details.append(
                f"in ALL_KINDS but not KIND_MANIFESTS: "
                f"{sorted(missing_from_manifest)}"
            )
        if missing_from_all:
            details.append(
                f"in KIND_MANIFESTS but not ALL_KINDS: "
                f"{sorted(missing_from_all)}"
            )
        raise RuntimeError(
            "KIND_MANIFESTS / ALL_KINDS drift detected — "
            + "; ".join(details)
        )


_check_manifest_consistency()
