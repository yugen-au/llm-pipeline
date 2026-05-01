"""``ArtifactSpec`` base — common contract for every first-class artifact.

Every per-kind spec subclass (``ConstantSpec``, ``StepSpec``,
``PipelineSpec``, etc.) inherits from ``ArtifactSpec``. The base
defines the minimum data the system needs to identify an artifact
and surface it to the UI:

- ``kind``: the dispatch key (``KIND_*`` constant).
- ``name``: snake_case registry key.
- ``cls``: fully-qualified Python identifier (class qualname for
  class-based artifacts, dotted module path for module-level values
  like constants).
- ``source_path``: filesystem path to the file containing the
  artifact, used by the UI for navigation and by libcst codegen for
  hot-swap edits.
- ``issues``: localised validation issues for the artifact itself.
  Sub-component issues live on building-block fields (e.g.
  ``CodeBodySpec.issues`` on each editable code body); per-kind
  subclasses define those slots.

This is *only* the base class for Phase A. Per-kind subclasses,
the static analyser, and registry plumbing land in subsequent
phases per ``.claude/plans/per-artifact-architecture.md``.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ValidationIssue must be a runtime import (not under TYPE_CHECKING)
# because Pydantic needs the actual class to validate the ``issues``
# field. Phase C moves the validation types into ``llm_pipeline.specs``
# so this cross-package import goes away.
from llm_pipeline.graph.spec import ValidationIssue


__all__ = ["ArtifactSpec"]


class ArtifactSpec(BaseModel):
    """Common contract for any UI-editable code artifact.

    Subclassed per kind. The base intentionally carries no
    kind-specific data — that lives on each subclass — but every
    artifact, regardless of kind, exposes these fields so the
    generic resolver, list endpoints, and validation surfaces work
    uniformly.

    JSON-serialisable end-to-end (Pydantic v2 ``model_dump(mode="json")``)
    so the spec can travel through the API without bespoke encoders.
    """

    model_config = ConfigDict(extra="forbid")

    # Dispatch key. Per-kind subclasses pin this with ``Literal[KIND_X]``.
    kind: str

    # snake_case identifier — the key under which this artifact is
    # registered in ``app.state.registries[kind][name]``.
    name: str

    # Fully-qualified Python identifier:
    # - Class artifacts (steps, schemas, etc.): the class's
    #   ``__module__.__qualname__``.
    # - Value artifacts (constants): the module path + symbol name,
    #   e.g. ``llm_pipelines.constants.retries.MAX_RETRIES``.
    cls: str

    # Filesystem path to the source file. Used by the UI for "open
    # the file" navigation and by libcst codegen as the hot-swap
    # target.
    source_path: str

    # Localised validation issues attached *directly* to this
    # artifact (i.e. not nested under a building-block field).
    # Per-kind subclasses add their own building-block fields whose
    # ``issues`` lists describe sub-component problems.
    issues: list[ValidationIssue] = Field(default_factory=list)
