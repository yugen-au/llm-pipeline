"""Tests for ``llm_pipeline.prompts.phoenix_validator``.

Covers every per-step error class plus the build/dry-run mode split.
Each negative test creates a deliberately broken fixture (missing YAML,
drifted placeholder, unknown model, etc.) and asserts the validator
records the right exception type.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, Field
from pydantic_graph import End, GraphRunContext

from llm_pipeline.graph.nodes import LLMStepNode
from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.inputs import StepInputs
from llm_pipeline.prompts.phoenix_client import (
    PhoenixError,
    PromptNotFoundError,
)
from llm_pipeline.prompts.phoenix_validator import (
    ModelNotRecognisedError,
    PhoenixPromptMissingError,
    PhoenixValidationFailed,
    PhoenixValidationReport,
    PromptMessagesShapeError,
    PromptModelMissingError,
    PromptNameMismatchError,
    PromptSystemVariableDriftError,
    PromptUserVariableDriftError,
    PromptVariablesMissingError,
    PromptVariablesRegistryMismatchError,
    PromptYamlInvalidError,
    PromptYamlMissingError,
    StepValidationResult,
    validate_phoenix_alignment,
)
from llm_pipeline.prompts.variables import (
    PromptVariables,
    clear_prompt_variables_registry,
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
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class _MultiVarPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")
        sentiment: str = Field(description="sentiment")


class _FixtureStepBase(LLMStepNode):
    INPUTS = _FixtureInputs
    INSTRUCTIONS = _FixtureInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _FixtureInputs) -> list[_FixturePrompt]:
        return [_FixturePrompt(
            system=_FixturePrompt.system(),
            user=_FixturePrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


class _MultiVarStepBase(LLMStepNode):
    INPUTS = _FixtureInputs
    INSTRUCTIONS = _FixtureInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _FixtureInputs) -> list[_MultiVarPrompt]:
        return [_MultiVarPrompt(
            system=_MultiVarPrompt.system(),
            user=_MultiVarPrompt.user(text=inputs.text, sentiment="x"),
        )]

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
# Fake Phoenix client
# ---------------------------------------------------------------------------


class _FakePromptClient:
    def __init__(self, *, present: set[str] | None = None) -> None:
        # Names Phoenix knows about. Anything not in this set raises
        # PromptNotFoundError on get_latest.
        self._present = present if present is not None else set()
        self._raise_phoenix_error = False

    def add(self, name: str) -> None:
        self._present.add(name)

    def fail_with_phoenix_error(self) -> None:
        self._raise_phoenix_error = True

    def get_latest(self, name: str):
        if self._raise_phoenix_error:
            raise PhoenixError("simulated Phoenix outage")
        if name not in self._present:
            raise PromptNotFoundError(name)
        return {
            "id": f"v_{name}",
            "template": {"type": "chat", "messages": []},
            "model_provider": "OPENAI",
            "model_name": "gpt-4o-mini",
        }


# ---------------------------------------------------------------------------
# Per-test fixture: clean PromptVariables registry, real demo step name
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test owns the registry; clear before and after."""
    clear_prompt_variables_registry()
    yield
    clear_prompt_variables_registry()


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
        client = _FakePromptClient(present={"happy"})

        report = validate_phoenix_alignment(
            registry, tmp_path, prompt_client=client, mode="build",
        )
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
        client = _FakePromptClient(present={"missing"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptVariablesMissingError) for e in errors)

    def test_registry_mismatch(self, tmp_path: Path):
        # Register a DIFFERENT class under the same name; the cached
        # prompt_variables_cls on the step is _FixturePrompt.
        register_prompt_variables("mismatch", _MultiVarPrompt)
        cls = _make_step("MismatchStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "mismatch")
        client = _FakePromptClient(present={"mismatch"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(
            isinstance(e, PromptVariablesRegistryMismatchError) for e in errors
        )

    def test_yaml_missing(self, tmp_path: Path):
        register_prompt_variables("noyaml", _FixturePrompt)
        cls = _make_step("NoyamlStep")
        registry = {"p": _make_pipeline(cls)}
        # tmp_path stays empty — no YAML written
        client = _FakePromptClient(present={"noyaml"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptYamlMissingError) for e in errors)

    def test_yaml_invalid(self, tmp_path: Path):
        register_prompt_variables("badyaml", _FixturePrompt)
        cls = _make_step("BadyamlStep")
        registry = {"p": _make_pipeline(cls)}
        # Write garbage YAML — passes yaml.safe_load (returns string) but
        # fails Pydantic validation because root isn't a mapping.
        (tmp_path / "badyaml.yaml").write_text("just-a-string", encoding="utf-8")
        client = _FakePromptClient(present={"badyaml"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
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
        client = _FakePromptClient(present={"unparseable"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptYamlInvalidError) for e in errors)

    def test_name_mismatch(self, tmp_path: Path):
        register_prompt_variables("named", _FixturePrompt)
        cls = _make_step("NamedStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "named", name="something_else")
        client = _FakePromptClient(present={"named"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptNameMismatchError) for e in errors)

    def test_model_missing(self, tmp_path: Path):
        register_prompt_variables("nomodel", _FixturePrompt)
        cls = _make_step("NomodelStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "nomodel", model=None)
        client = _FakePromptClient(present={"nomodel"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptModelMissingError) for e in errors)

    def test_model_unrecognised(self, tmp_path: Path):
        register_prompt_variables("badmodel", _FixturePrompt)
        cls = _make_step("BadmodelStep")
        registry = {"p": _make_pipeline(cls)}
        # Missing colon — pai format violation.
        _write_valid_yaml(tmp_path, "badmodel", model="not-a-pai-string")
        client = _FakePromptClient(present={"badmodel"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, ModelNotRecognisedError) for e in errors)

    def test_model_unknown_provider(self, tmp_path: Path):
        register_prompt_variables("ghost", _FixturePrompt)
        cls = _make_step("GhostStep")
        registry = {"p": _make_pipeline(cls)}
        # Format is right, but pydantic-ai doesn't know this provider.
        _write_valid_yaml(tmp_path, "ghost", model="ghostprovider:imaginary")
        client = _FakePromptClient(present={"ghost"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
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
        client = _FakePromptClient(present={"extramsg"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
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
        client = _FakePromptClient(present={"sysdrift"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(
            isinstance(e, PromptSystemVariableDriftError) for e in errors
        )

    def test_user_drift_template_missing_declared_field(self, tmp_path: Path):
        # _MultiVarPrompt declares text + sentiment; template only uses text.
        register_prompt_variables("userdrift", _MultiVarPrompt)
        cls = _make_step("UserdriftStep", base=_MultiVarStepBase)
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "userdrift", user="Just text: {text}")
        client = _FakePromptClient(present={"userdrift"})

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, PromptUserVariableDriftError) for e in errors)


# ---------------------------------------------------------------------------
# Phoenix-side errors (11)
# ---------------------------------------------------------------------------


class TestPhoenixSideErrors:
    def test_phoenix_prompt_missing(self, tmp_path: Path):
        register_prompt_variables("absent", _FixturePrompt)
        cls = _make_step("AbsentStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "absent")
        client = _FakePromptClient(present=set())  # nothing in Phoenix

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, PhoenixPromptMissingError) for e in errors)

    def test_phoenix_transport_failure(self, tmp_path: Path):
        register_prompt_variables("trans", _FixturePrompt)
        cls = _make_step("TransStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "trans")
        client = _FakePromptClient(present={"trans"})
        client.fail_with_phoenix_error()

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )
        errors = exc_info.value.errors
        assert any(isinstance(e, PhoenixPromptMissingError) for e in errors)


# ---------------------------------------------------------------------------
# Build vs dry-run mode behaviour
# ---------------------------------------------------------------------------


class TestModes:
    def test_build_mode_throws_on_error(self, tmp_path: Path):
        register_prompt_variables("any", _FixturePrompt)
        cls = _make_step("AnyStep")
        registry = {"p": _make_pipeline(cls)}
        # No YAML written.
        client = _FakePromptClient(present={"any"})

        with pytest.raises(PhoenixValidationFailed):
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )

    def test_dry_run_mode_warns_does_not_throw(
        self, tmp_path: Path, caplog,
    ):
        register_prompt_variables("dry", _FixturePrompt)
        cls = _make_step("DryStep")
        registry = {"p": _make_pipeline(cls)}
        # No YAML written.
        client = _FakePromptClient(present={"dry"})

        report = validate_phoenix_alignment(
            registry, tmp_path, prompt_client=client, mode="dry-run",
        )
        # Errors recorded, but no exception raised.
        assert not report.ok
        assert any(isinstance(e, PromptYamlMissingError) for e in report.errors)

    def test_build_mode_requires_phoenix_client(self, tmp_path: Path):
        registry: dict = {}
        with pytest.raises(RuntimeError):
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=None, mode="build",
            )

    def test_dry_run_mode_skips_phoenix_when_client_missing(
        self, tmp_path: Path,
    ):
        register_prompt_variables("offline", _FixturePrompt)
        cls = _make_step("OfflineStep")
        registry = {"p": _make_pipeline(cls)}
        _write_valid_yaml(tmp_path, "offline")

        # No client -> Phoenix-side check skipped; YAML/code checks
        # still run. With a valid YAML and registered class, no errors.
        report = validate_phoenix_alignment(
            registry, tmp_path, prompt_client=None, mode="dry-run",
        )
        assert report.ok

    def test_invalid_mode_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError):
            validate_phoenix_alignment(
                {}, tmp_path,
                prompt_client=_FakePromptClient(),
                mode="bogus",  # type: ignore[arg-type]
            )


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
        client = _FakePromptClient(present=set())

        with pytest.raises(PhoenixValidationFailed) as exc_info:
            validate_phoenix_alignment(
                registry, tmp_path, prompt_client=client, mode="build",
            )

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
        client = _FakePromptClient(present={"shared"})

        report = validate_phoenix_alignment(
            registry, tmp_path, prompt_client=client, mode="build",
        )
        # Only validated once despite two pipelines referencing it.
        assert len(report.steps) == 1
