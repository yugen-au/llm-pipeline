"""Per-artifact spec primitives.

This package defines the typed contracts used by the code <-> UI
translation layer. Per-kind ``ArtifactSpec`` subclasses carry
everything the UI needs to render an artifact and everything the
libcst hot-swap needs to translate UI edits back into code.

- ``ArtifactSpec`` (base.py): common base for every per-kind subclass.
- Building blocks (blocks.py): ``SymbolRef``, ``CodeBodySpec``,
  ``JsonSchemaWithRefs``, ``PromptData``. Reusable across specs.
- Per-kind subclasses: ``ConstantSpec``, ``EnumSpec``,
  ``SchemaSpec``, ``ToolSpec``, ``StepSpec``, ``ExtractionSpec``,
  ``ReviewSpec``. Each lives in its own module.
- ``ArtifactRegistration`` (registration.py): pairs a spec with its
  runtime object — registry value type.
- Builders (builders.py): per-kind functions that introspect a
  loaded class/value and produce a populated spec.
- Kind constants (kinds.py): ``KIND_*`` strings and ``LEVEL_BY_KIND``
  mapping.

See ``.claude/plans/per-artifact-architecture.md`` for the full
design.
"""
from llm_pipeline.specs.base import (
    ArtifactField,
    ArtifactRef,
    ArtifactSpec,
    ImportArtifact,
    ImportBlock,
    SymbolRef,
)
from llm_pipeline.specs.blocks import (
    CodeBodySpec,
    JsonSchemaWithRefs,
    PromptData,
    PromptDataFields,
    PromptVariableDefs,
)
from llm_pipeline.specs.constants import ConstantSpec
from llm_pipeline.specs.enums import EnumMemberSpec, EnumSpec
from llm_pipeline.specs.extractions import ExtractionFields, ExtractionSpec
from llm_pipeline.specs.kinds import (
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
# ``LEVEL_BY_KIND`` is owned by :data:`llm_pipeline.discovery.manifest`.
# It's NOT re-exported here — re-exporting it would create an import
# cycle (manifest → walkers → specs.X submodules → specs/__init__,
# all hitting partially-initialised modules). Callers that need the
# level index import from the manifest module directly.
from llm_pipeline.specs.issues import flatten_artifact_issues
from llm_pipeline.specs.pipelines import NodeBindingSpec, PipelineSpec
from llm_pipeline.specs.registration import ArtifactRegistration
from llm_pipeline.specs.reviews import ReviewFields, ReviewSpec
from llm_pipeline.specs.schemas import SchemaSpec
from llm_pipeline.specs.steps import StepFields, StepSpec
from llm_pipeline.specs.tables import IndexSpec, TableSpec
from llm_pipeline.specs.tools import ToolSpec

# Note: builders live in ``llm_pipeline.specs.builders`` and are
# imported directly from there (e.g. ``from llm_pipeline.specs.builders
# import build_step_spec``). They depend on
# ``llm_pipeline.cst_analysis`` which itself depends on the
# building-block types here — re-exporting builders from this
# package's ``__init__`` would create a circular import. Phase C.2
# walkers and any other consumers should import them from the
# submodule directly.

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
    # Per-kind subclasses
    "ConstantSpec",
    "EnumMemberSpec",
    "EnumSpec",
    "ExtractionFields",
    "ExtractionSpec",
    "IndexSpec",
    "NodeBindingSpec",
    "PipelineSpec",
    "ReviewFields",
    "ReviewSpec",
    "SchemaSpec",
    "StepFields",
    "StepSpec",
    "TableSpec",
    "ToolSpec",
    # Registration wrapper
    "ArtifactRegistration",
    # Issue-collection helper
    "flatten_artifact_issues",
]
