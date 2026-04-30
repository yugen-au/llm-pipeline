"""Runtime behaviour of ``LLMStepNode``, ``ExtractionNode``, ``ReviewNode``.

End-to-end through ``run_pipeline_in_memory`` with the pydantic-ai
``test`` model and a stubbed Phoenix client (no network, no LLM key).
"""
from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
from pydantic import BaseModel, Field
from pydantic_graph import End, GraphRunContext
from sqlmodel import Field as SQLField, SQLModel, create_engine

from llm_pipeline.graph import (
    Extraction,
    ExtractionNode,
    FromInput,
    FromOutput,
    FromPipeline,
    LLMResultMixin,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    Step,
    StepInputs,
    run_pipeline_in_memory,
)
from llm_pipeline.prompts import PromptVariables


# ---------------------------------------------------------------------------
# Test pipeline definition (module-level so __init_subclass__ runs once)
# ---------------------------------------------------------------------------


class _NodeTestInput(PipelineInputData):
    text: str


class _NodeTestRow(SQLModel, table=True):
    __tablename__ = "test_node_rows"
    __table_args__ = {"extend_existing": True}
    id: int | None = SQLField(default=None, primary_key=True)
    label: str
    run_id: str


class _ClassifyInputs(StepInputs):
    text: str


class _ClassifyInstructions(LLMResultMixin):
    label: str = ""

    example: ClassVar[dict] = {"label": "neutral", "confidence_score": 0.9}


class _ClassifyPrompt(PromptVariables):
    text: str = Field(description="Input text")


class _ClassifyStep(LLMStepNode):
    INPUTS = _ClassifyInputs
    INSTRUCTIONS = _ClassifyInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _ClassifyInputs) -> list[_ClassifyPrompt]:
        return [
            _ClassifyPrompt(
                text=inputs.text),
        ]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> _ClassifyExtraction:
        await self._run_llm(ctx)
        return _ClassifyExtraction()


class _FromClassifyInputs(StepInputs):
    label: str
    run_id: str


class _ClassifyExtraction(ExtractionNode):
    MODEL = _NodeTestRow
    INPUTS = _FromClassifyInputs

    def extract(self, inputs: _FromClassifyInputs) -> list[_NodeTestRow]:
        return [_NodeTestRow(label=inputs.label, run_id=inputs.run_id)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_extraction(ctx)
        return End(None)


class _NodeTestPipeline(Pipeline):
    INPUT_DATA = _NodeTestInput
    nodes = [
        Step(
            _ClassifyStep,
            inputs_spec=_ClassifyInputs.sources(text=FromInput("text")),
        ),
        Extraction(
            _ClassifyExtraction,
            inputs_spec=_FromClassifyInputs.sources(
                label=FromOutput(_ClassifyStep, field="label"),
                run_id=FromPipeline("run_id"),
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def _engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)
    return eng


class TestEndToEnd:
    """Full ``LLMStepNode -> ExtractionNode`` run with stubbed Phoenix."""

    def test_run_pipeline_records_step_output(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register(
            "classify",
            system="Classify the text.",
            user="Text: {text}",
        )

        state, _end = asyncio.run(run_pipeline_in_memory(
            _NodeTestPipeline,
            input_data={"text": "the sky is blue"},
            model="test",
            engine=_engine,
        ))

        assert "_ClassifyStep" in state.outputs
        recorded = state.outputs["_ClassifyStep"]
        assert isinstance(recorded, list)
        assert len(recorded) == 1
        assert "label" in recorded[0]

    def test_run_pipeline_persists_extraction_rows(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register(
            "classify",
            system="Classify the text.",
            user="Text: {text}",
        )

        state, _end = asyncio.run(run_pipeline_in_memory(
            _NodeTestPipeline,
            input_data={"text": "another input"},
            model="test",
            engine=_engine,
        ))

        assert "_NodeTestRow" in state.extractions
        rows = state.extractions["_NodeTestRow"]
        assert len(rows) == 1
        # extraction wired run_id from FromPipeline; must be set on the row
        assert rows[0].get("run_id")


# ---------------------------------------------------------------------------
# State helpers — exercised against bare classes (don't go through
# LLMStepNode.__init_subclass__ validation; we just need a class with
# an ``INSTRUCTIONS`` attribute and a ``__name__`` to key state by).
# ---------------------------------------------------------------------------


class TestPipelineState:
    """Round-trip outputs/extractions through ``PipelineState``."""

    def test_record_output_dumps_pydantic_model(self):
        class _Foo(BaseModel):
            x: int

        class _FooNodeStub:
            __name__ = "_FooNodeStub"
            INSTRUCTIONS = _Foo

        state = PipelineState()
        state.record_output(_FooNodeStub, [_Foo(x=42)])
        assert state.outputs["_FooNodeStub"] == [{"x": 42}]

    def test_to_adapter_ctx_rehydrates_outputs(self):
        class _Bar(BaseModel):
            n: int = 0

        class _BarNodeStub:
            __name__ = "_BarNodeStub"
            INSTRUCTIONS = _Bar

        state = PipelineState(outputs={"_BarNodeStub": [{"n": 7}]})
        adapter_ctx = state.to_adapter_ctx(
            input_cls=None,
            node_classes={"_BarNodeStub": _BarNodeStub},
            pipeline=None,
        )
        rehydrated = adapter_ctx.outputs[_BarNodeStub]
        assert isinstance(rehydrated[0], _Bar)
        assert rehydrated[0].n == 7
