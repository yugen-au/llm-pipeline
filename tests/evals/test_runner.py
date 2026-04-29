"""End-to-end runner tests against an in-memory Phoenix dataset stub.

The stub mirrors ``phoenix_prompt_stub`` from the root conftest:
in-memory dict + same method surface as :class:`PhoenixDatasetClient`,
no network. The runner is invoked with the stub as its ``client``;
assertions cover:

- Phoenix experiment + per-case run + evaluation scores all land
- Variant overrides flow through to the task
- Step-target and pipeline-target both resolve correctly
"""
from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest
from pydantic_graph import End, GraphRunContext
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals.runner import (
    EvalTargetError,
    create_experiment_record,
    run_dataset,
)
from llm_pipeline.evals.variants import Variant
from llm_pipeline.graph import (
    FromInput,
    LLMResultMixin,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    StepInputs,
)


# ---------------------------------------------------------------------------
# Tiny pipeline used by every runner test
# ---------------------------------------------------------------------------


class _RunnerInput(PipelineInputData):
    text: str


class _RunnerInputs(StepInputs):
    text: str


class _RunnerInstructions(LLMResultMixin):
    label: str = ""

    example: ClassVar[dict] = {"label": "neutral", "confidence_score": 0.9}


class _RunnerStep(LLMStepNode):
    INPUTS = _RunnerInputs
    INSTRUCTIONS = _RunnerInstructions
    inputs_spec = _RunnerInputs.sources(text=FromInput("text"))

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_llm(ctx)
        return End(None)


class _RunnerPipeline(Pipeline):
    INPUT_DATA = _RunnerInput
    nodes = [_RunnerStep]


# ---------------------------------------------------------------------------
# Phoenix dataset stub
# ---------------------------------------------------------------------------


class _PhoenixDatasetStub:
    """In-memory mock of the methods ``run_dataset`` invokes."""

    def __init__(self, dataset: dict[str, Any], examples: list[dict[str, Any]]):
        self._dataset = dataset
        self._examples = examples
        self.experiments: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []
        self.evaluations: list[dict[str, Any]] = []

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        if dataset_id != self._dataset["id"]:
            from llm_pipeline.evals.phoenix_client import DatasetNotFoundError
            raise DatasetNotFoundError(dataset_id)
        return self._dataset

    def list_examples(self, dataset_id: str, **kwargs: Any) -> dict[str, Any]:
        return {"data": {"examples": list(self._examples)}}

    def create_experiment(self, dataset_id: str, **kwargs: Any) -> dict[str, Any]:
        record = {
            "id": f"exp-{len(self.experiments) + 1}",
            "dataset_id": dataset_id,
            **kwargs,
        }
        self.experiments.append(record)
        return record

    def record_run(
        self,
        experiment_id: str,
        *,
        dataset_example_id: str,
        output: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        run = {
            "id": f"run-{len(self.runs) + 1}",
            "experiment_id": experiment_id,
            "dataset_example_id": dataset_example_id,
            "output": output,
            **kwargs,
        }
        self.runs.append(run)
        return run

    def attach_evaluation(
        self, experiment_id: str, run_id: str, **kwargs: Any,
    ) -> dict[str, Any]:
        ev = {
            "id": f"ev-{len(self.evaluations) + 1}",
            "experiment_id": experiment_id,
            "run_id": run_id,
            **kwargs,
        }
        self.evaluations.append(ev)
        return ev


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


@pytest.fixture
def _step_dataset_stub():
    return _PhoenixDatasetStub(
        dataset={
            "id": "ds-step-1",
            "name": "step-eval",
            "metadata": {
                "target_type": "step",
                "target_name": "_RunnerStep",
            },
        },
        examples=[
            {
                "id": "ex-1",
                "input": {"text": "first"},
                "output": {"label": "neutral"},
                "metadata": {},
            },
            {
                "id": "ex-2",
                "input": {"text": "second"},
                "output": {"label": "neutral"},
                "metadata": {},
            },
        ],
    )


@pytest.fixture
def _pipeline_dataset_stub():
    return _PhoenixDatasetStub(
        dataset={
            "id": "ds-pipe-1",
            "name": "pipe-eval",
            "metadata": {
                "target_type": "pipeline",
                "target_name": "_RunnerPipeline",
            },
        },
        examples=[
            {
                "id": "ex-1",
                "input": {"text": "hello"},
                "output": {"_RunnerStep": [{"label": "neutral"}]},
                "metadata": {},
            },
        ],
    )


# ---------------------------------------------------------------------------
# Step-target eval
# ---------------------------------------------------------------------------


class TestRunDatasetStep:
    def test_step_target_resolves_and_runs(
        self, phoenix_prompt_stub, _engine, _step_dataset_stub,
    ):
        phoenix_prompt_stub.register(
            "runner",
            system="Classify.",
            user="Text: {text}",
        )

        report = asyncio.run(run_dataset(
            "ds-step-1",
            Variant(),
            pipeline_registry={"runner": _RunnerPipeline},
            model="test",
            engine=_engine,
            client=_step_dataset_stub,
        ))

        assert len(report.cases) == 2
        # An experiment was opened on Phoenix.
        assert len(_step_dataset_stub.experiments) == 1
        assert _step_dataset_stub.experiments[0]["dataset_id"] == "ds-step-1"

    def test_per_case_runs_recorded(
        self, phoenix_prompt_stub, _engine, _step_dataset_stub,
    ):
        phoenix_prompt_stub.register(
            "runner",
            system="Classify.",
            user="Text: {text}",
        )
        asyncio.run(run_dataset(
            "ds-step-1",
            Variant(),
            pipeline_registry={"runner": _RunnerPipeline},
            model="test",
            engine=_engine,
            client=_step_dataset_stub,
        ))
        assert len(_step_dataset_stub.runs) == 2
        example_ids = {r["dataset_example_id"] for r in _step_dataset_stub.runs}
        assert example_ids == {"ex-1", "ex-2"}

    def test_evaluations_attached(
        self, phoenix_prompt_stub, _engine, _step_dataset_stub,
    ):
        phoenix_prompt_stub.register(
            "runner",
            system="Classify.",
            user="Text: {text}",
        )
        asyncio.run(run_dataset(
            "ds-step-1",
            Variant(),
            pipeline_registry={"runner": _RunnerPipeline},
            model="test",
            engine=_engine,
            client=_step_dataset_stub,
        ))
        # Auto evaluator on `label` -> one assertion per case = 2 evaluations.
        assert len(_step_dataset_stub.evaluations) >= 2

    def test_variant_metadata_round_tripped(
        self, phoenix_prompt_stub, _engine, _step_dataset_stub,
    ):
        phoenix_prompt_stub.register(
            "runner",
            system="Classify.",
            user="Text: {text}",
        )
        variant = Variant(model="test", prompt_overrides={"_runner": "X: {text}"})
        asyncio.run(run_dataset(
            "ds-step-1",
            variant,
            pipeline_registry={"runner": _RunnerPipeline},
            model="test",
            engine=_engine,
            client=_step_dataset_stub,
        ))
        exp = _step_dataset_stub.experiments[0]
        meta = exp["metadata"]
        assert meta["variant"]["model"] == "test"
        assert meta["target_type"] == "step"
        assert meta["target_name"] == "_RunnerStep"


# ---------------------------------------------------------------------------
# Pipeline-target eval
# ---------------------------------------------------------------------------


class TestRunDatasetPipeline:
    def test_pipeline_target_resolves_and_runs(
        self, phoenix_prompt_stub, _engine, _pipeline_dataset_stub,
    ):
        phoenix_prompt_stub.register(
            "runner",
            system="Classify.",
            user="Text: {text}",
        )
        report = asyncio.run(run_dataset(
            "ds-pipe-1",
            Variant(),
            pipeline_registry={"_RunnerPipeline": _RunnerPipeline},
            model="test",
            engine=_engine,
            client=_pipeline_dataset_stub,
        ))
        assert len(report.cases) == 1


# ---------------------------------------------------------------------------
# Target resolution errors
# ---------------------------------------------------------------------------


class TestTargetResolution:
    def test_unknown_target_type_raises(self, _engine):
        stub = _PhoenixDatasetStub(
            dataset={
                "id": "ds-x",
                "metadata": {"target_type": "unknown", "target_name": "y"},
            },
            examples=[],
        )
        with pytest.raises(EvalTargetError, match="target_type"):
            asyncio.run(run_dataset(
                "ds-x",
                Variant(),
                pipeline_registry={},
                model="test",
                engine=_engine,
                client=stub,
            ))

    def test_unknown_step_target_raises(self, _engine):
        stub = _PhoenixDatasetStub(
            dataset={
                "id": "ds-x",
                "metadata": {"target_type": "step", "target_name": "MissingStep"},
            },
            examples=[],
        )
        with pytest.raises(EvalTargetError, match="not found"):
            asyncio.run(run_dataset(
                "ds-x",
                Variant(),
                pipeline_registry={"runner": _RunnerPipeline},
                model="test",
                engine=_engine,
                client=stub,
            ))

    def test_unknown_pipeline_target_raises(self, _engine):
        stub = _PhoenixDatasetStub(
            dataset={
                "id": "ds-x",
                "metadata": {"target_type": "pipeline", "target_name": "MissingPipeline"},
            },
            examples=[],
        )
        with pytest.raises(EvalTargetError, match="not in registry"):
            asyncio.run(run_dataset(
                "ds-x",
                Variant(),
                pipeline_registry={"runner": _RunnerPipeline},
                model="test",
                engine=_engine,
                client=stub,
            ))


# ---------------------------------------------------------------------------
# Pre-created experiment passthrough
# ---------------------------------------------------------------------------


class TestPreCreatedExperiment:
    """Verify the UI's foreground create_experiment + background run_dataset flow."""

    def test_create_experiment_record_returns_id_with_metadata(
        self, _step_dataset_stub,
    ):
        record = create_experiment_record(
            client=_step_dataset_stub,
            dataset_id="ds-step-1",
            variant=Variant(model="m"),
            target_type="step",
            target_name="_RunnerStep",
            run_name="explicit-name",
        )
        assert record["id"]
        # Metadata round-trip: variant + target captured.
        meta = record["metadata"]
        assert meta["variant"] == {
            "model": "m",
            "prompt_overrides": {},
            "instructions_delta": [],
        }
        assert meta["target_type"] == "step"
        assert meta["target_name"] == "_RunnerStep"
        # The single experiment we created is the only one on the stub.
        assert len(_step_dataset_stub.experiments) == 1

    def test_run_dataset_with_experiment_id_skips_create(
        self, phoenix_prompt_stub, _engine, _step_dataset_stub,
    ):
        """When ``experiment_id`` is supplied, runner does NOT create a new one."""
        phoenix_prompt_stub.register(
            "runner", system="Classify.", user="Text: {text}",
        )

        # Pre-create the experiment (foreground), then run with that id.
        pre = create_experiment_record(
            client=_step_dataset_stub,
            dataset_id="ds-step-1",
            variant=Variant(),
            target_type="step",
            target_name="_RunnerStep",
        )
        pre_id = pre["id"]
        assert len(_step_dataset_stub.experiments) == 1

        asyncio.run(run_dataset(
            "ds-step-1",
            Variant(),
            pipeline_registry={"runner": _RunnerPipeline},
            model="test",
            engine=_engine,
            client=_step_dataset_stub,
            experiment_id=pre_id,
        ))

        # Crucially: no second create_experiment call; per-case runs land
        # under the pre-created id.
        assert len(_step_dataset_stub.experiments) == 1
        assert all(r["experiment_id"] == pre_id for r in _step_dataset_stub.runs)
        assert len(_step_dataset_stub.runs) == 2  # 2 cases in the stub

    def test_run_dataset_without_experiment_id_creates_one(
        self, phoenix_prompt_stub, _engine, _step_dataset_stub,
    ):
        """Default behaviour preserved: no id supplied -> runner creates one."""
        phoenix_prompt_stub.register(
            "runner", system="Classify.", user="Text: {text}",
        )
        asyncio.run(run_dataset(
            "ds-step-1",
            Variant(),
            pipeline_registry={"runner": _RunnerPipeline},
            model="test",
            engine=_engine,
            client=_step_dataset_stub,
        ))
        assert len(_step_dataset_stub.experiments) == 1
