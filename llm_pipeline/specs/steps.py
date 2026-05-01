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

from llm_pipeline.specs.base import ArtifactSpec
from llm_pipeline.specs.blocks import CodeBodySpec, JsonSchemaWithRefs, PromptData
from llm_pipeline.specs.kinds import KIND_STEP


__all__ = ["StepSpec"]


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

    # Names of tools attached via DEFAULT_TOOLS — registry keys
    # into ``registries[KIND_TOOL]``. Resolution to ToolSpec
    # happens at consumer side via the universal resolver.
    tool_names: list[str] = Field(default_factory=list)
