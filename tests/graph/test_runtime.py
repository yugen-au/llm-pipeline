"""DB-backed runtime tests: ``run_pipeline`` + ``SqlmodelStatePersistence``.

Drives a graph pipeline through the production runtime entry point
(``llm_pipeline.graph.runtime.run_pipeline``) and verifies the
expected ``PipelineRun`` + ``PipelineNodeSnapshot`` rows land in the
DB.
"""
from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
from pydantic_graph import End, GraphRunContext
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.graph import (
    FromInput,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    StepInputs,
    run_pipeline,
)
from llm_pipeline.state import PipelineNodeSnapshot, PipelineRun
from llm_pipeline.graph import LLMResultMixin


# ---------------------------------------------------------------------------
# Tiny one-step pipeline
# ---------------------------------------------------------------------------


class _DBRuntimeInput(PipelineInputData):
    text: str


class _DBClassifyInputs(StepInputs):
    text: str


class _DBClassifyInstructions(LLMResultMixin):
    label: str = ""

    example: ClassVar[dict] = {"label": "neutral", "confidence_score": 0.9}


class _DBClassifyStep(LLMStepNode):
    INPUTS = _DBClassifyInputs
    INSTRUCTIONS = _DBClassifyInstructions
    inputs_spec = _DBClassifyInputs.sources(text=FromInput("text"))

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_llm(ctx)
        return End(None)


class _DBRuntimePipeline(Pipeline):
    INPUT_DATA = _DBRuntimeInput
    nodes = [_DBClassifyStep]


# ---------------------------------------------------------------------------
# Tests
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


class TestRunPipeline:
    """End-to-end: ``run_pipeline`` writes ``PipelineRun`` + node snapshots."""

    def test_run_completes_and_writes_pipeline_run(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register(
            "db_classify",
            system="Classify.",
            user="Text: {text}",
        )

        result = asyncio.run(run_pipeline(
            _DBRuntimePipeline,
            input_data={"text": "hello"},
            model="test",
            engine=_engine,
            run_id="run-completion-test",
        ))
        assert result.run_id == "run-completion-test"
        assert result.status == "completed"
        assert result.completed_at is not None

    def test_run_writes_node_snapshots(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register(
            "db_classify",
            system="Classify.",
            user="Text: {text}",
        )

        asyncio.run(run_pipeline(
            _DBRuntimePipeline,
            input_data={"text": "hello"},
            model="test",
            engine=_engine,
            run_id="run-snapshots-test",
        ))

        with Session(_engine) as session:
            snaps = session.exec(
                select(PipelineNodeSnapshot)
                .where(PipelineNodeSnapshot.run_id == "run-snapshots-test")
                .order_by(PipelineNodeSnapshot.sequence)
            ).all()

        # One node snapshot for the step + one End snapshot when it returns End[None].
        kinds = [s.kind for s in snaps]
        assert "node" in kinds
        assert "end" in kinds
        node_snap = next(s for s in snaps if s.kind == "node")
        assert node_snap.node_class_name == "_DBClassifyStep"
        assert node_snap.status == "success"
        assert node_snap.duration is not None and node_snap.duration >= 0
        assert (node_snap.state_snapshot or {}).get("input_data") == {"text": "hello"}

    def test_run_id_preserved_when_supplied(
        self, phoenix_prompt_stub, _engine,
    ):
        phoenix_prompt_stub.register(
            "db_classify",
            system="Classify.",
            user="Text: {text}",
        )

        result = asyncio.run(run_pipeline(
            _DBRuntimePipeline,
            input_data={"text": "x"},
            model="test",
            engine=_engine,
            run_id="my-explicit-run-id",
        ))
        assert result.run_id == "my-explicit-run-id"

        with Session(_engine) as session:
            run = session.exec(
                select(PipelineRun).where(
                    PipelineRun.run_id == "my-explicit-run-id",
                )
            ).first()
        assert run is not None
        assert run.status == "completed"
