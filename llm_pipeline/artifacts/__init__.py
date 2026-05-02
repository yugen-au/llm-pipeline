"""Per-artifact spec primitives + per-kind manifest aggregation.

Each ``llm_pipeline.artifacts.{kind}`` module owns its
:class:`ArtifactSpec` subclass, optional ``Fields`` routing class,
:class:`SpecBuilder` subclass, :class:`Walker` subclass, and a
module-level ``MANIFEST: ArtifactManifest`` constant. This package's
``__init__`` imports each kind's MANIFEST and assembles them into
the framework-wide :data:`ARTIFACT_MANIFESTS` dict + derived views.

Adding a new kind = create the kind file (with spec / fields /
builder / walker / MANIFEST) and add one import line below.

The :class:`ArtifactSpec` ABC + foundation modules live in
:mod:`llm_pipeline.artifacts.base`.
"""
from llm_pipeline.artifacts.base import (
    ArtifactField,
    ArtifactRef,
    ArtifactSpec,
    ImportArtifact,
    ImportBlock,
    SymbolRef,
)
from llm_pipeline.artifacts.base.blocks import (
    CodeBodySpec,
    JsonSchemaWithRefs,
    PromptData,
    PromptDataFields,
    PromptVariableDefs,
)
from llm_pipeline.artifacts.base.issues import flatten_artifact_issues
from llm_pipeline.artifacts.base.kinds import (
    ALL_KINDS,
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
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.registration import ArtifactRegistration
from llm_pipeline.artifacts.base.walker import Walker

# Per-kind imports — each module exports its spec + fields + builder
# + walker + module-level ``MANIFEST`` constant. Listed in dependency-
# tier order for readability; the actual load order is derived from
# ``MANIFEST.level`` in :data:`LOAD_ORDER` below.
from llm_pipeline.artifacts import (
    constants as _constants,
    enums as _enums,
    extractions as _extractions,
    pipelines as _pipelines,
    reviews as _reviews,
    schemas as _schemas,
    steps as _steps,
    tables as _tables,
    tools as _tools,
)
from llm_pipeline.artifacts.constants import ConstantSpec
from llm_pipeline.artifacts.enums import EnumMemberSpec, EnumSpec
from llm_pipeline.artifacts.extractions import ExtractionFields, ExtractionSpec
from llm_pipeline.artifacts.pipelines import (
    EdgeSpec,
    NodeBindingSpec,
    PipelineFields,
    PipelineSpec,
    SourceSpec,
    WiringSpec,
)
from llm_pipeline.artifacts.reviews import ReviewFields, ReviewSpec
from llm_pipeline.artifacts.schemas import SchemaSpec
from llm_pipeline.artifacts.steps import StepFields, StepSpec
from llm_pipeline.artifacts.tables import IndexSpec, TableSpec
from llm_pipeline.artifacts.tools import ToolFields, ToolSpec


# ---------------------------------------------------------------------------
# Manifest aggregation
# ---------------------------------------------------------------------------


_ALL_MANIFESTS = (
    _constants.MANIFEST,
    _enums.MANIFEST,
    _schemas.MANIFEST,
    _tables.MANIFEST,
    _tools.MANIFEST,
    _extractions.MANIFEST,
    _reviews.MANIFEST,
    _steps.MANIFEST,
    _pipelines.MANIFEST,
)


# Single source of truth. Adding a new kind = one entry in the
# tuple above (after creating the kind file with its MANIFEST).
ARTIFACT_MANIFESTS: dict[str, ArtifactManifest] = {
    m.kind: m for m in _ALL_MANIFESTS
}


# Derived views.

LEVEL_BY_KIND: dict[str, int] = {
    m.kind: m.level for m in ARTIFACT_MANIFESTS.values()
}

# Subfolder load order: by level, then by subfolder name within a
# level (deterministic). Module-import dependencies (lower-level
# files referenced at module-load time) are respected because levels
# encode the dependency tier.
LOAD_ORDER: list[str] = [
    m.subfolder
    for m in sorted(
        ARTIFACT_MANIFESTS.values(), key=lambda m: (m.level, m.subfolder),
    )
]

WALKERS_BY_SUBFOLDER: dict[str, list[Walker]] = {
    m.subfolder: [m.walker] for m in ARTIFACT_MANIFESTS.values()
}


# Module-load-time sanity check: catch drift between the manifest
# and the KIND_* / ALL_KINDS constants.
def _check_manifest_consistency() -> None:
    manifest_kinds = set(ARTIFACT_MANIFESTS)
    declared_kinds = set(ALL_KINDS)
    if manifest_kinds != declared_kinds:
        missing_from_manifest = declared_kinds - manifest_kinds
        missing_from_all = manifest_kinds - declared_kinds
        details: list[str] = []
        if missing_from_manifest:
            details.append(
                f"in ALL_KINDS but not ARTIFACT_MANIFESTS: "
                f"{sorted(missing_from_manifest)}"
            )
        if missing_from_all:
            details.append(
                f"in ARTIFACT_MANIFESTS but not ALL_KINDS: "
                f"{sorted(missing_from_all)}"
            )
        raise RuntimeError(
            "ARTIFACT_MANIFESTS / ALL_KINDS drift detected — "
            + "; ".join(details)
        )


_check_manifest_consistency()


__all__ = [
    # Kind constants
    "ALL_KINDS",
    "KIND_CONSTANT",
    "KIND_ENUM",
    "KIND_EXTRACTION",
    "KIND_PIPELINE",
    "KIND_REVIEW",
    "KIND_SCHEMA",
    "KIND_STEP",
    "KIND_TABLE",
    "KIND_TOOL",
    # Base + building blocks
    "ArtifactField",
    "ArtifactRef",
    "ArtifactSpec",
    "CodeBodySpec",
    "ImportArtifact",
    "ImportBlock",
    "JsonSchemaWithRefs",
    "PromptData",
    "PromptDataFields",
    "PromptVariableDefs",
    "SymbolRef",
    "Walker",
    # Per-kind subclasses
    "ConstantSpec",
    "EdgeSpec",
    "EnumMemberSpec",
    "EnumSpec",
    "ExtractionFields",
    "ExtractionSpec",
    "IndexSpec",
    "NodeBindingSpec",
    "PipelineFields",
    "PipelineSpec",
    "ReviewFields",
    "ReviewSpec",
    "SchemaSpec",
    "SourceSpec",
    "StepFields",
    "StepSpec",
    "TableSpec",
    "ToolFields",
    "ToolSpec",
    "WiringSpec",
    # Registration wrapper
    "ArtifactRegistration",
    # Issue-collection helper
    "flatten_artifact_issues",
    # Manifest aggregation + derived views
    "ArtifactManifest",
    "ARTIFACT_MANIFESTS",
    "LEVEL_BY_KIND",
    "LOAD_ORDER",
    "WALKERS_BY_SUBFOLDER",
]
