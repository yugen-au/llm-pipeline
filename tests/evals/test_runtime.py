"""Tests for ``build_step_task`` + ``build_pipeline_task``.

Both task wrappers are async callables ``(case_input) -> dict`` that
``Dataset.evaluate`` invokes per case. These tests pin:

- the step task returns the validated instructions dump for a single
  step (with variant overrides applied);
- the pipeline task drives the whole graph and returns ``state.outputs``;
- variant overrides (model, prompt, instructions delta) are honoured
  through both task shapes.
"""
from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
from pydantic_graph import End, GraphRunContext
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals.runtime import build_pipeline_task, build_step_task
from llm_pipeline.evals.variants import Variant
from pydantic import BaseModel, Field

from llm_pipeline.graph import (
    FromInput,
    FromOutput,
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
# A two-step pipeline so build_pipeline_task has multiple node outputs to dump
# ---------------------------------------------------------------------------


class _RuntimeInput(PipelineInputData):
    text: str


class _ClassifyInputs(StepInputs):
    text: str


class _ClassifyInstructions(LLMResultMixin):
    label: str = ""

    example: ClassVar[dict] = {"label": "neutral", "confidence_score": 0.9}


class _ClassifyPrompt(PromptVariables):
    text: str = Field(description="text")


class _ClassifyStep(LLMStepNode):
    INPUTS = _ClassifyInputs
    INSTRUCTIONS = _ClassifyInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _ClassifyInputs) -> list[_ClassifyPrompt]:
        return [_ClassifyPrompt(
            text=inputs.text)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> _SummaryStep:
        await self._run_llm(ctx)
        return _SummaryStep()


class _SummaryInputs(StepInputs):
    label: str


class _SummaryInstructions(LLMResultMixin):
    summary: str = ""

    example: ClassVar[dict] = {"summary": "ok", "confidence_score": 0.9}


class _SummaryPrompt(PromptVariables):
    label: str = Field(description="label")


class _SummaryStep(LLMStepNode):
    INPUTS = _SummaryInputs
    INSTRUCTIONS = _SummaryInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _SummaryInputs) -> list[_SummaryPrompt]:
        return [_SummaryPrompt(
            label=inputs.label)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_llm(ctx)
        return End(None)


class _RuntimePipeline(Pipeline):
    INPUT_DATA = _RuntimeInput
    nodes = [
        Step(_ClassifyStep, inputs_spec=_ClassifyInputs.sources(
            text=FromInput("text"),
        )),
        Step(_SummaryStep, inputs_spec=_SummaryInputs.sources(
            label=FromOutput(_ClassifyStep, field="label"),
        )),
    ]


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


# ---------------------------------------------------------------------------
# build_step_task
# ---------------------------------------------------------------------------


class TestBuildStepTask:
    def test_returns_validated_instructions_dump(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register(
            "classify",
            system="Classify.",
            user="Text: {text}",
        )
        task = build_step_task(
            _RuntimePipeline,
            _ClassifyStep,
            Variant(),
            model="test",
            engine=_engine,
        )
        result = asyncio.run(task({"text": "hello"}))
        # Test model populates string fields with deterministic values.
        assert "label" in result
        assert "confidence_score" in result

    def test_prompt_override_runs_without_user_prompt_registered(
        self, phoenix_prompt_stub, _engine,
    ):
        """Override-only run: the user-prompt fetch is skipped entirely.

        The system prompt fetch still happens via ``@agent.instructions``,
        so we register only that piece. If the user-prompt fetch fired,
        no ``user`` would be registered and the run would fail.
        """
        phoenix_prompt_stub.register("classify", system="Classify.")
        task = build_step_task(
            _RuntimePipeline,
            _ClassifyStep,
            Variant(
                prompt_overrides={
                    _ClassifyStep.step_name(): "Override: {text}",
                },
            ),
            model="test",
            engine=_engine,
        )
        result = asyncio.run(task({"text": "x"}))
        assert "label" in result

    def test_instructions_delta_swaps_output_schema(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register(
            "classify",
            system="Classify.",
            user="Text: {text}",
        )
        task = build_step_task(
            _RuntimePipeline,
            _ClassifyStep,
            Variant(
                instructions_delta=[
                    {"op": "add", "field": "intensity", "type_str": "float", "default": 0.5},
                ],
            ),
            model="test",
            engine=_engine,
        )
        result = asyncio.run(task({"text": "x"}))
        assert "intensity" in result


# ---------------------------------------------------------------------------
# build_pipeline_task
# ---------------------------------------------------------------------------


class TestBuildPipelineTask:
    def test_runs_full_graph_returns_state_outputs(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register("classify", system="A.", user="A: {text}")
        phoenix_prompt_stub.register("summary", system="B.", user="B: {label}")

        task = build_pipeline_task(
            _RuntimePipeline,
            Variant(),
            model="test",
            engine=_engine,
        )
        result = asyncio.run(task({"text": "hi"}))
        # Both step outputs must be present, keyed by class name.
        assert "_ClassifyStep" in result
        assert "_SummaryStep" in result

    def test_input_validation_errors_surface(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register("classify", system="A.", user="A: {text}")
        task = build_pipeline_task(
            _RuntimePipeline, Variant(), model="test", engine=_engine,
        )
        # Missing required `text` field -> validation error.
        with pytest.raises(Exception):
            asyncio.run(task({}))

    def test_instructions_delta_applies_to_all_step_schemas(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register("classify", system="A.", user="A: {text}")
        phoenix_prompt_stub.register("summary", system="B.", user="B: {label}")

        task = build_pipeline_task(
            _RuntimePipeline,
            Variant(
                instructions_delta=[
                    {"op": "add", "field": "intensity", "type_str": "float", "default": 0.5},
                ],
            ),
            model="test",
            engine=_engine,
        )
        result = asyncio.run(task({"text": "hi"}))
        # Both steps' outputs gained the new field.
        assert "intensity" in result["_ClassifyStep"][0]
        assert "intensity" in result["_SummaryStep"][0]
