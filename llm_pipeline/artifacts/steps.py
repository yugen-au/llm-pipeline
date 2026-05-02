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

from typing import Any, Literal

from pydantic import Field

from llm_pipeline.artifacts.base import ArtifactField, ArtifactRef, ArtifactSpec, SymbolRef
from llm_pipeline.artifacts.base.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.artifacts.base.builder import SpecBuilder, _class_to_artifact_ref
from llm_pipeline.artifacts.base.fields import FieldRef, FieldsBase
from llm_pipeline.artifacts.base.kinds import KIND_STEP
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.walker import Walker, _is_locally_defined_class


__all__ = [
    "MANIFEST",
    "PromptData",
    "PromptDataFields",
    "PromptVariableDefs",
    "StepBuilder",
    "StepFields",
    "StepSpec",
    "StepsWalker",
]


# ---------------------------------------------------------------------------
# Step-paired prompt sub-data
# ---------------------------------------------------------------------------


class PromptVariableDefs(JsonSchemaWithRefs):
    """Unified view of a PromptVariables class's variable definitions.

    Phoenix treats a prompt's variables as one flat dict — every
    placeholder has a ``description``, an optional ``type``, and an
    optional ``auto_generate`` expression. The Python implementation
    splits them across two constructs (Pydantic fields for prepare-
    supplied values; a ``ClassVar[dict[str, str]]`` for
    auto_generate-supplied placeholders). This component is the
    Phoenix-shaped view: both kinds in one place.

    Extends :class:`JsonSchemaWithRefs` (Pydantic-fields portion +
    refs from defaults / type-hints) with the auto_vars portion
    (placeholder → expression + the refs each expression yields).
    PromptVariables-class captures (``missing_field_description``,
    ``auto_vars_*``) all live on the inherited ``issues`` slot.
    """

    # auto_generate expressions, keyed by placeholder name. Values
    # are source-level expressions like ``enum_names(Sentiment)``
    # which are parsed at render time to materialise concrete values.
    auto_vars: dict[str, str] = Field(default_factory=dict)

    # Per-placeholder refs derived from the auto_vars expressions —
    # e.g. the placeholder ``"sentiment_options"`` mapping to a
    # ``SymbolRef(kind=KIND_ENUM, name="sentiment", ...)``.
    auto_vars_refs: dict[str, list[SymbolRef]] = Field(default_factory=dict)


class PromptData(ArtifactField):
    """Sub-data of a step: variables + YAML-resolved templates.

    *Not* a first-class artifact. ``PromptData`` is embedded inside
    ``StepSpec.prompt`` and rendered by the existing ``PromptEditor``
    component as a child of ``StepEditor``. This matches Phoenix's
    data model where a "prompt" *is* a step's LLM-call contract,
    not a separately-editable thing.

    The save flow when the user edits this section updates both the
    YAML prompt file AND regenerates the paired per-step ``XPrompt``
    class (existing ``llm-pipeline generate`` flow).

    Prompt-variable-class issues (auto_vars shape, missing field
    descriptions, etc.) live on ``self.variables.issues`` —
    :class:`PromptVariableDefs` is the unified home for everything
    about the variable declarations.
    """

    # Unified variable definitions — Pydantic-fields shape AND
    # auto_generate expressions in one ArtifactField. Captures from
    # PromptVariables.__pydantic_init_subclass__ route here via
    # ``PromptDataFields.VARIABLES``.
    variables: PromptVariableDefs

    # Filesystem path of the paired YAML prompt file (e.g.
    # ``llm-pipeline-prompts/sentiment_analysis.yaml``).
    yaml_path: str

    # Phoenix-resolved fields. ``None`` until the discovery-time
    # Phoenix validator runs; populated thereafter from whichever
    # source (YAML or Phoenix) wins per the existing sync rules.
    system_template: str | None = None
    user_template: str | None = None
    model: str | None = None


class PromptDataFields(FieldsBase):
    """Routing-key vocabulary for :class:`PromptData` issue captures.

    Captures from :class:`llm_pipeline.prompts.PromptVariables` all
    route to ``PromptData.variables`` (a :class:`PromptVariableDefs`).
    Other PromptData fields are primitives (yaml_path, templates,
    model) — captures about them leave ``location.path`` unset and
    land on top-level ``PromptData.issues``.
    """

    SPEC_CLS = PromptData

    VARIABLES = FieldRef("variables")


# ---------------------------------------------------------------------------
# Step spec
# ---------------------------------------------------------------------------


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


class StepBuilder(SpecBuilder):
    """Build a :class:`StepSpec` from an ``LLMStepNode`` subclass.

    The ``prompt`` argument is provided by the walker — it constructs
    :class:`PromptData` from the paired YAML + per-step ``XPrompt``
    class outside this builder. Builders stay pure (no YAML reading,
    no Phoenix calls).
    """

    KIND = KIND_STEP
    SPEC_CLS = StepSpec

    def __init__(
        self,
        *,
        prompt: PromptData | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.prompt = prompt

    def kind_fields(self) -> dict[str, Any]:
        cls = self.cls
        inputs_cls = getattr(cls, "INPUTS", None)
        instructions_cls = getattr(cls, "INSTRUCTIONS", None)
        default_tools = getattr(cls, "DEFAULT_TOOLS", None) or []

        # One ArtifactRef per DEFAULT_TOOLS entry. Source-side name
        # is the tool's Python class name; ``ref`` is populated when
        # the resolver maps that to a registered tool.
        tools = [
            ref for ref in (
                _class_to_artifact_ref(tool, self.resolver)
                for tool in default_tools
            ) if ref is not None
        ]

        return {
            "inputs": self.json_schema(inputs_cls),
            "instructions": self.json_schema(instructions_cls),
            "prepare": self.code_body("prepare"),
            "run": self.code_body("run"),
            "prompt": self.prompt,
            "tools": tools,
        }


class StepsWalker(Walker):
    """Register ``LLMStepNode`` subclasses from ``steps/``.

    ``StepSpec.prompt`` is left ``None`` here. Building :class:`PromptData`
    requires reading the paired YAML and the per-step ``XPrompt`` class
    — separate orchestration concern. Steps still get inputs / instructions
    / prepare / run / tools populated.
    """

    KIND = KIND_STEP
    BUILDER = StepBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import LLMStepNode

        return _is_locally_defined_class(value, mod, LLMStepNode)

    def name_for(self, attr_name, value):
        return value.step_name()


MANIFEST = ArtifactManifest(
    kind=KIND_STEP,
    subfolder="steps",
    level=4,
    spec_cls=StepSpec,
    fields_cls=StepFields,
    walker=StepsWalker(),
)
