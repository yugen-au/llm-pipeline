"""``LLMStepNode._run_llm`` honours ``PipelineDeps`` overrides.

The eval runner threads variant-style overrides through the runtime
via ``PipelineDeps.prompt_overrides`` and
``PipelineDeps.instructions_overrides``. These tests pin the
contract: when an override is set, the step bypasses the Phoenix
prompt fetch / uses the override class for the agent's output type.
"""
from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
from pydantic_graph import End, GraphRunContext
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals.variants import apply_instruction_delta
from pydantic import BaseModel, Field

from llm_pipeline.graph import (
    FromInput,
    LLMResultMixin,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    Step,
    StepInputs,
)
from llm_pipeline.prompts import PromptVariables


# ---------------------------------------------------------------------------
# Tiny one-step pipeline
# ---------------------------------------------------------------------------


class _OverrideInput(PipelineInputData):
    text: str


class _OverrideInputs(StepInputs):
    text: str


class _OverrideInstructions(LLMResultMixin):
    label: str = ""

    example: ClassVar[dict] = {"label": "neutral", "confidence_score": 0.9}


class _OverridePrompt(PromptVariables):
    text: str = Field(description="Input text")


class _OverrideStep(LLMStepNode):
    INPUTS = _OverrideInputs
    INSTRUCTIONS = _OverrideInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _OverrideInputs) -> list[_OverridePrompt]:
        return [
            _OverridePrompt(
                text=inputs.text),
        ]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_llm(ctx)
        return End(None)


class _OverridePipeline(Pipeline):
    INPUT_DATA = _OverrideInput
    nodes = [
        Step(
            _OverrideStep,
            inputs_spec=_OverrideInputs.sources(text=FromInput("text")),
        ),
    ]


# ---------------------------------------------------------------------------
# Spy prompt service — captures which methods are called
# ---------------------------------------------------------------------------


class _SpyPromptService:
    """Minimal PromptService double for override tests.

    Records every call so tests can assert which paths fired. Returns
    canned strings so the agent gets a non-empty system / user prompt
    when the production path is exercised.
    """

    def __init__(self) -> None:
        self.user_calls: list[dict] = []
        self.system_calls: list[dict] = []

    def get_user_prompt(self, *, prompt_key: str, variables: dict) -> str:
        self.user_calls.append({"prompt_key": prompt_key, "variables": variables})
        return f"PROD-USER:{prompt_key}:{variables}"

    def get_prompt(self, *, prompt_key: str, prompt_type: str) -> str:
        self.system_calls.append(
            {"prompt_key": prompt_key, "prompt_type": prompt_type},
        )
        return f"PROD-{prompt_type}:{prompt_key}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(eng)
    SQLModel.metadata.create_all(eng)
    return eng


def _build_ctx(*, engine, prompt_overrides=None, instructions_overrides=None):
    """Build a ``GraphRunContext`` with the requested overrides set."""
    state = PipelineState(input_data={"text": "hello"})
    session = Session(engine)
    deps = PipelineDeps(
        session=session,
        prompt_service=_SpyPromptService(),
        run_id="override-test-run",
        pipeline_name=_OverridePipeline.pipeline_name(),
        model="test",
        input_cls=_OverrideInput,
        node_classes=dict(_OverridePipeline._node_classes),
        wiring=dict(_OverridePipeline._wiring),
        prompt_overrides=prompt_overrides or {},
        instructions_overrides=instructions_overrides or {},
    )
    ctx = GraphRunContext(state=state, deps=deps)
    return ctx, session


# ---------------------------------------------------------------------------
# Prompt override
# ---------------------------------------------------------------------------


class TestPromptOverride:
    def test_override_bypasses_phoenix_user_prompt_fetch(self, _engine):
        """When ``prompt_overrides[step_name]`` is set, ``get_user_prompt`` is not called."""
        ctx, session = _build_ctx(
            engine=_engine,
            prompt_overrides={_OverrideStep.step_name(): "OVERRIDE-USER:{text}"},
        )
        step = _OverrideStep()
        try:
            asyncio.run(step._run_llm(ctx))
        finally:
            session.close()

        assert ctx.deps.prompt_service.user_calls == []
        # System prompt fetch still happens (the agent's
        # ``@agent.instructions`` hook calls it independently).
        assert any(
            c["prompt_type"] == "system"
            for c in ctx.deps.prompt_service.system_calls
        )

    def test_override_renders_template_variables(self, _engine):
        """The override template is rendered with ``user_prompt_variables``."""
        ctx, session = _build_ctx(
            engine=_engine,
            prompt_overrides={_OverrideStep.step_name(): "OVERRIDE-USER:{text}"},
        )
        # No assertion on the rendered string per se — but the run must
        # complete without KeyError, proving the variables were threaded.
        step = _OverrideStep()
        try:
            asyncio.run(step._run_llm(ctx))
        finally:
            session.close()

    def test_override_unknown_variable_raises_value_error(self, _engine):
        """Bad template -> KeyError -> ValueError surface."""
        ctx, session = _build_ctx(
            engine=_engine,
            prompt_overrides={
                _OverrideStep.step_name(): "{nonexistent_field}",
            },
        )
        step = _OverrideStep()
        try:
            with pytest.raises(ValueError, match="prompt override"):
                asyncio.run(step._run_llm(ctx))
        finally:
            session.close()

    def test_no_override_falls_through_to_phoenix(self, _engine):
        """Without an override, the production prompt service is consulted."""
        ctx, session = _build_ctx(engine=_engine, prompt_overrides=None)
        step = _OverrideStep()
        try:
            asyncio.run(step._run_llm(ctx))
        finally:
            session.close()

        assert len(ctx.deps.prompt_service.user_calls) == 1
        assert (
            ctx.deps.prompt_service.user_calls[0]["prompt_key"]
            == _OverrideStep.step_name()
        )


# ---------------------------------------------------------------------------
# Instructions override
# ---------------------------------------------------------------------------


class TestInstructionsOverride:
    def test_override_class_used_as_agent_output_type(self, _engine):
        """When ``instructions_overrides`` maps the prod class -> a delta-derived
        subclass, the agent validates against the override schema."""
        # Build a delta-derived subclass with an extra field. The agent's
        # output should validate against this — i.e. a `_OverrideInstructions`
        # missing the new field would not satisfy the override.
        override_cls = apply_instruction_delta(
            _OverrideInstructions,
            [{"op": "add", "field": "extra", "type_str": "str", "default": "x"}],
        )
        assert "extra" in override_cls.model_fields

        ctx, session = _build_ctx(
            engine=_engine,
            instructions_overrides={_OverrideInstructions: override_cls},
        )
        step = _OverrideStep()
        try:
            asyncio.run(step._run_llm(ctx))
        finally:
            session.close()

        # The output dump is recorded under the production class name
        # (state outputs are keyed by node class, not output class), so
        # the dump shape carries the override fields.
        recorded = ctx.state.outputs.get("_OverrideStep", [])
        assert len(recorded) == 1
        # The extra field landed (default value) — proves the override
        # class was the schema pydantic-ai validated against.
        assert "extra" in recorded[0]

    def test_no_override_uses_declared_instructions(self, _engine):
        """Without an override, the step's declared INSTRUCTIONS class is used."""
        ctx, session = _build_ctx(engine=_engine, instructions_overrides=None)
        step = _OverrideStep()
        try:
            asyncio.run(step._run_llm(ctx))
        finally:
            session.close()

        recorded = ctx.state.outputs.get("_OverrideStep", [])
        assert len(recorded) == 1
        # Production schema fields only.
        assert "extra" not in recorded[0]
        assert "label" in recorded[0]
