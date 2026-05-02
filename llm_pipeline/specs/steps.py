"""``StepSpec`` — ``LLMStepNode`` subclasses (Level 4).

A step is a self-contained unit: declares its INPUTS class (what
the LLM call needs), INSTRUCTIONS class (the structured output
shape), ``prepare()`` body (how to turn inputs into prompt
variables), ``run()`` body (graph wiring + LLM dispatch), paired
prompt config (system + user templates + variable definitions),
and the tools the agent gets bound to.

The Phoenix model treats a step's prompt + variables + model as
ONE record — not a separate kind. Hence ``prompt`` is embedded as
:class:`PromptData` rather than referenced as its own kind. The
StepEditor on the frontend renders all of this in one composite
view; cross-artifact refs (e.g. a tool reference, a constant
reference inside ``prepare``) dispatch to the relevant kind via
the universal ``(kind, name)`` resolver.

Phase C.1 declares the spec shape. Phase C.2's walker populates
it: INPUTS / INSTRUCTIONS schemas via :func:`build_schema_spec`-
style introspection (Pydantic ``model_json_schema()``); ``prepare``
/ ``run`` bodies via :func:`analyze_code_body`; ``prompt`` from
the paired YAML + ``_variables/`` PromptVariables class.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from llm_pipeline.specs.base import ArtifactRef, ArtifactSpec
from llm_pipeline.specs.blocks import CodeBodySpec, JsonSchemaWithRefs, PromptData
from llm_pipeline.specs.fields import FieldRef, FieldsBase
from llm_pipeline.specs.kinds import KIND_STEP


__all__ = ["StepFields", "StepSpec"]


class StepSpec(ArtifactSpec):
    """An ``LLMStepNode`` subclass declared in ``llm_pipelines/steps/``."""

    kind: Literal[KIND_STEP] = KIND_STEP  # type: ignore[assignment]

    # The step's INPUTS class shape — what ``prepare`` receives.
    # ``None`` when INPUTS isn't set on the class (a captured issue
    # surfaces on ``self.issues``).
    inputs: JsonSchemaWithRefs | None = None

    # The step's INSTRUCTIONS class shape — the structured LLM
    # output shape that pydantic-ai validates the response into.
    instructions: JsonSchemaWithRefs | None = None

    # The body of ``prepare(self, inputs)``. ``None`` for steps
    # that haven't overridden the base. The body's refs include
    # constants/enums/tools/etc. used inline.
    prepare: CodeBodySpec | None = None

    # The body of ``run(self, ctx)``. ``None`` for abstract steps
    # (rare). Includes refs to sibling node classes (graph edges)
    # plus any ad-hoc helpers used in dispatch logic.
    run: CodeBodySpec | None = None

    # Paired prompt data — variables, auto_vars, YAML-resolved
    # templates, model. Embedded (not a separate kind) because
    # Phoenix treats a step's prompt as part of the same record.
    prompt: PromptData | None = None

    # Tools attached via DEFAULT_TOOLS — one :class:`ArtifactRef`
    # per entry, carrying the source-side Python class name plus a
    # resolved ref into ``registries[KIND_TOOL]`` when the resolver
    # matches. Per-tool issues (e.g. unresolved tool reference)
    # land on ``self.tools[i].issues``.
    tools: list[ArtifactRef] = Field(default_factory=list)


class StepFields(FieldsBase):
    """Routing-key vocabulary for :class:`StepSpec` issue captures.

    Capture sites in :class:`LLMStepNode.__init_subclass__` (and the
    ``prepare()`` resolver in :mod:`llm_pipeline.graph.nodes`) tag
    each :class:`ValidationIssue` with one of these :class:`FieldRef`
    constants on ``location.path``. The
    :meth:`ArtifactField.attach_class_captures` walker resolves the
    path to the matching sub-component.

    Constants list ONLY the fields a capture site references — no
    orphan constants for spec fields nobody routes to. Adding a new
    capture site that targets a different StepSpec field is the
    trigger for adding a new constant here. Path validity is checked
    at class-load time against :class:`StepSpec`.
    """

    SPEC_CLS = StepSpec

    INPUTS = FieldRef("inputs")
    INSTRUCTIONS = FieldRef("instructions")
    PREPARE = FieldRef("prepare")
