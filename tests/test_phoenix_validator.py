"""Tests for ``llm_pipeline.prompts.phoenix_validator``.

Covers every per-step error class. Each negative test creates a
deliberately broken fixture (missing YAML, drifted placeholder,
unknown model, etc.) and asserts the validator raises
``PhoenixValidationFailed`` carrying the right exception type. The
validator is fully offline — Phoenix-side checks moved to
``llm-pipeline pull`` / ``push``.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
import yaml
from pydantic import BaseModel, Field
from pydantic_graph import End, GraphRunContext

from llm_pipeline.graph.nodes import LLMStepNode
from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.inputs import StepInputs
from llm_pipeline.prompts.phoenix_validator import (
    AutoGenerateExpressionError,
    ModelNotRecognisedError,
    PhoenixValidationFailed,
    PhoenixValidationReport,
    PromptMessagesShapeError,
    PromptModelMissingError,
    PromptNameMismatchError,
    PromptVariableDriftError,
    PromptVariablesMissingError,
    PromptVariablesRegistryMismatchError,
    PromptYamlInvalidError,
    PromptYamlMissingError,
    StepValidationResult,
    validate_phoenix_alignment,
)
from llm_pipeline.prompts.variables import (
    PromptVariables,
    clear_auto_generate_registry,
    clear_prompt_variables_registry,
    register_auto_generate,
    register_prompt_variables,
)


# ---------------------------------------------------------------------------
# Module-level fixture classes (strict prepare-validator requires module
# scope so typing.get_type_hints can resolve the annotations).
# ---------------------------------------------------------------------------


class _FixtureInputs(StepInputs):
    text: str


class _FixtureInstructions(BaseModel):
    label: str = ""


class _FixturePrompt(PromptVariables):
    text: str = Field(description="text")


class _MultiVarPrompt(PromptVariables):
    text: str = Field(description="text")
    sentiment: str = Field(description="sentiment")


class _FixtureStepBase(LLMStepNode):
    INPUTS = _FixtureInputs
    INSTRUCTIONS = _FixtureInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _FixtureInputs) -> list[_FixturePrompt]:
        return [_FixturePrompt(text=inputs.text)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


class _MultiVarStepBase(LLMStepNode):
    INPUTS = _FixtureInputs
    INSTRUCTIONS = _FixtureInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _FixtureInputs) -> list[_MultiVarPrompt]:
        return [_MultiVarPrompt(text=inputs.text, sentiment="x")]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


def _make_step(name: str, *, base: type = _FixtureStepBase) -> type:
    """Construct a dynamically-named LLMStepNode subclass."""
    return type(name, (base,), {})


def _make_pipeline(*step_classes: type) -> type:
    """Synthesise a Pipeline-shaped class with bindings."""
    from llm_pipeline.wiring import FromInput, Step

    bindings = [
        Step(cls, inputs_spec=cls.INPUTS.sources(text=FromInput("text")))
        for cls in step_classes
    ]
    return type("Pipeline", (), {"nodes": bindings})


# ---------------------------------------------------------------------------
# Per-test fixture: clean PromptVariables registry, real demo step name
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test owns the registry; clear before and after."""
    clear_prompt_variables_registry()
    clear_auto_generate_registry()
    yield
    clear_prompt_variables_registry()
    clear_auto_generate_registry()


def _write_valid_yaml(
    prompts_dir: Path,
    step_name: str,
    *,
    name: str | None = None,
    model: str | None = "openai:gpt-4o-mini",
    system: str = "You are a helper.",
    user: str = "Process: {text}",
    extra_messages: list[dict] | None = None,
) -> Path:
    """Write a YAML file matching ``_FixturePrompt`` placeholder shape."""
    payload: dict = {
        "name": name if name is not None else step_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if model is not None:
        payload["model"] = model
    if extra_messages:
        payload["messages"].extend(extra_messages)
    path = prompts_dir / f"{step_name}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_aligned_step_passes(self, tmp_path: Path):
        register_prompt_variables("happy", _FixturePrompt)
        cls = _make_step("HappyStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "happy")

        report = validate_phoenix_alignment(registry, tmp_path)
        assert report.ok
        assert len(report.steps) == 1
        assert report.steps[0].step_name == "happy"


# ---------------------------------------------------------------------------
# Code-side errors (1-10)
# ---------------------------------------------------------------------------


class TestCodeSideErrors:
    def test_prompt_variables_missing(self, tmp_path: Path):
        # No register_prompt_variables call — registry empty for this name.
        register_prompt_variables("other", _FixturePrompt)
        cls = _make_step("MissingStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "missing")

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptVariablesMissingError) for e in errors)

    def test_registry_mismatch(self, tmp_path: Path):
        # Register a DIFFERENT class under the same name; the cached
        # prompt_variables_cls on the step is _FixturePrompt.
        register_prompt_variables("mismatch", _MultiVarPrompt)
        cls = _make_step("MismatchStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "mismatch")

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(
            isinstance(e, PromptVariablesRegistryMismatchError) for e in errors
        )

    def test_yaml_missing(self, tmp_path: Path):
        register_prompt_variables("noyaml", _FixturePrompt)
        cls = _make_step("NoyamlStep")
        registry = {"p": _make_pipeline(cls)}
        # tmp_path stays empty — no YAML written

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptYamlMissingError) for e in errors)

    def test_yaml_invalid(self, tmp_path: Path):
        register_prompt_variables("badyaml", _FixturePrompt)
        cls = _make_step("BadyamlStep")
        registry = {"p": _make_pipeline(cls)}
        # Write garbage YAML — passes yaml.safe_load (returns string) but
        # fails Pydantic validation because root isn't a mapping.
        (tmp_path / "badyaml.yaml").write_text("just-a-string", encoding="utf-8")

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptYamlInvalidError) for e in errors)

    def test_yaml_unparseable(self, tmp_path: Path):
        register_prompt_variables("unparseable", _FixturePrompt)
        cls = _make_step("UnparseableStep")
        registry = {"p": _make_pipeline(cls)}
        # Genuinely malformed YAML.
        (tmp_path / "unparseable.yaml").write_text(
            "key: : :\n  - [ {", encoding="utf-8",
        )

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptYamlInvalidError) for e in errors)

    def test_name_mismatch(self, tmp_path: Path):
        register_prompt_variables("named", _FixturePrompt)
        cls = _make_step("NamedStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "named", name="something_else")

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptNameMismatchError) for e in errors)

    def test_model_missing(self, tmp_path: Path):
        register_prompt_variables("nomodel", _FixturePrompt)
        cls = _make_step("NomodelStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "nomodel", model=None)

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptModelMissingError) for e in errors)

    def test_model_unrecognised(self, tmp_path: Path):
        register_prompt_variables("badmodel", _FixturePrompt)
        cls = _make_step("BadmodelStep")
        registry = {"p": _make_pipeline(cls)}
        # Missing colon — pai format violation.
        _write_valid_yaml(tmp_path, "badmodel", model="not-a-pai-string")

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, ModelNotRecognisedError) for e in errors)

    def test_model_unknown_provider(self, tmp_path: Path):
        register_prompt_variables("ghost", _FixturePrompt)
        cls = _make_step("GhostStep")
        registry = {"p": _make_pipeline(cls)}
        # Format is right, but pydantic-ai doesn't know this provider.
        _write_valid_yaml(tmp_path, "ghost", model="ghostprovider:imaginary")

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, ModelNotRecognisedError) for e in errors)

    def test_messages_shape_extra_message(self, tmp_path: Path):
        register_prompt_variables("extramsg", _FixturePrompt)
        cls = _make_step("ExtramsgStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(
            tmp_path, "extramsg",
            extra_messages=[{"role": "user", "content": "second user"}],
        )

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptMessagesShapeError) for e in errors)

    def test_system_drift_template_uses_unknown_var(self, tmp_path: Path):
        register_prompt_variables("sysdrift", _FixturePrompt)
        cls = _make_step("SysdriftStep")
        registry = {"p": _make_pipeline(cls)}
        # System has {rogue} but _FixturePrompt.system has no fields.
        _write_valid_yaml(
            tmp_path, "sysdrift",
            system="You are a helper. Topic: {rogue}",
        )

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(
            isinstance(e, PromptVariableDriftError) for e in errors
        )

    def test_user_drift_template_missing_declared_field(self, tmp_path: Path):
        # _MultiVarPrompt declares text + sentiment; template only uses text.
        register_prompt_variables("userdrift", _MultiVarPrompt)
        cls = _make_step("UserdriftStep", base=_MultiVarStepBase)
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "userdrift", user="Just text: {text}")

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptVariableDriftError) for e in errors)


# ---------------------------------------------------------------------------
# auto_vars expression validation (Tiers 1-4)
# ---------------------------------------------------------------------------


import enum


class _Sentiment(enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class _AutoVarsPrompt(PromptVariables):
    text: str = Field(description="text")

    auto_vars: ClassVar[dict[str, str]] = {
        "options": "enum_names(_Sentiment)",
    }


class _AutoVarsStepBase(LLMStepNode):
    INPUTS = _FixtureInputs
    INSTRUCTIONS = _FixtureInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _FixtureInputs) -> list[_AutoVarsPrompt]:
        return [_AutoVarsPrompt(text=inputs.text)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# Module-level fixtures for negative auto_vars tests. The strict
# prepare-validator runs at __init_subclass__ time (calls
# typing.get_type_hints), so the prompt classes referenced in the
# step's prepare signature must live at module top level.


class _BadExprPrompt(PromptVariables):
    text: str = Field(description="text")

    auto_vars: ClassVar[dict[str, str]] = {
        "x": "not_a_function(_Sentiment)",
    }


class _BadExprStepBase(LLMStepNode):
    INPUTS = _FixtureInputs
    INSTRUCTIONS = _FixtureInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _FixtureInputs) -> list[_BadExprPrompt]:
        return [_BadExprPrompt(text=inputs.text)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


class _UnsafePrompt(PromptVariables):
    text: str = Field(description="text")

    auto_vars: ClassVar[dict[str, str]] = {
        "x": "constant({rogue})",
    }


class _UnsafeStepBase(LLMStepNode):
    INPUTS = _FixtureInputs
    INSTRUCTIONS = _FixtureInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _FixtureInputs) -> list[_UnsafePrompt]:
        return [_UnsafePrompt(text=inputs.text)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


class TestAutoVarsValidation:
    def _setup(self, tmp_path: Path, *, register_enum: bool = True):
        register_prompt_variables("auto", _AutoVarsPrompt)
        if register_enum:
            register_auto_generate("_Sentiment", _Sentiment)
        cls = _make_step("AutoStep", base=_AutoVarsStepBase)
        registry = {"p": _make_pipeline(cls)}
        # System message references the auto_var; user references the
        # prepare-supplied field.
        _write_valid_yaml(
            tmp_path, "auto",
            system="Allowed: {options}",
            user="Process: {text}",
        )
        return registry

    def test_valid_enum_names_passes(self, tmp_path: Path):
        registry = self._setup(tmp_path, register_enum=True)
        report = validate_phoenix_alignment(registry, tmp_path)
        assert report.ok

    def test_unresolved_target_raises(self, tmp_path: Path):
        registry = self._setup(tmp_path, register_enum=False)

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, AutoGenerateExpressionError) for e in errors)

    def test_unparseable_expression_raises(self, tmp_path: Path):
        # _BadExprPrompt's auto_vars uses an unrecognised function
        # name; build_auto_generate_factory raises at parse time.
        register_prompt_variables("bad", _BadExprPrompt)
        cls = _make_step("BadStep", base=_BadExprStepBase)
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(
            tmp_path, "bad",
            system="Allowed: {x}",
            user="Process: {text}",
        )

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, AutoGenerateExpressionError) for e in errors)

    def test_target_wrong_shape_raises(self, tmp_path: Path):
        # `enum_names(X)` where X is registered as a constant string,
        # not an enum — factory invocation will iterate over a non-Enum
        # and raise AttributeError on '.name'. The validator catches it.
        # NB: prompt registry key must match step_name() (snake_case);
        # we use "wrongshape" to skip underscore complications.
        register_prompt_variables("wrongshape", _AutoVarsPrompt)
        register_auto_generate("_Sentiment", "just-a-string")  # not Enum
        cls = _make_step("WrongshapeStep", base=_AutoVarsStepBase)
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(
            tmp_path, "wrongshape",
            system="Allowed: {options}",
            user="Process: {text}",
        )

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        assert any(isinstance(e, AutoGenerateExpressionError) for e in errors)

    def test_format_unsafe_output_raises(self, tmp_path: Path):
        # _UnsafePrompt.auto_vars: {"x": "constant({rogue})"} —
        # the factory output contains literal '{' that would corrupt
        # str.format during template rendering.
        register_prompt_variables("unsafe", _UnsafePrompt)
        cls = _make_step("UnsafeStep", base=_UnsafeStepBase)
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(
            tmp_path, "unsafe",
            system="Use: {x}",
            user="Process: {text}",
        )

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)
        errors = exc_info.value.errors
        msgs = [str(e) for e in errors]
        # Format-safety check fires on constant("{rogue}")
        assert any(
            isinstance(e, AutoGenerateExpressionError)
            and "literal '{'" in str(e)
            for e in errors
        ), f"Expected format-safety error; got {msgs!r}"


# ---------------------------------------------------------------------------
# Aggregation: collect every error across every step before raising
# ---------------------------------------------------------------------------


class TestAggregation:
    def test_collects_all_errors_before_raising(self, tmp_path: Path):
        register_prompt_variables("first", _FixturePrompt)
        # Don't register "second" — that step's PromptVariables missing.
        cls_a = _make_step("FirstStep")
        cls_b = _make_step("SecondStep")
        registry = {"p": _make_pipeline(cls_a, cls_b)}
        # First has no YAML; Second has no YAML either + no registry.

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(registry, tmp_path)

        # Errors from both steps surface in one raise.
        steps_with_errors = {e.step_name for e in exc_info.value.errors}
        assert steps_with_errors == {"first", "second"}

    def test_step_seen_only_once_when_shared_across_pipelines(
        self, tmp_path: Path,
    ):
        register_prompt_variables("shared", _FixturePrompt)
        cls = _make_step("SharedStep")
        # Same step in two pipelines.
        registry = {
            "p1": _make_pipeline(cls),
            "p2": _make_pipeline(cls),
        }
        _write_valid_yaml(tmp_path, "shared")

        report = validate_phoenix_alignment(registry, tmp_path)
        # Only validated once despite two pipelines referencing it.
        assert len(report.steps) == 1
