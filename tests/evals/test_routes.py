"""Tests for the Phoenix-passthrough eval routes.

Covers two surgical Phase-3 additions:

- ``POST /datasets/{id}/runs`` pre-creates the Phoenix experiment in
  the foreground and returns ``experiment_id``.
- ``GET /datasets/{id}/prod-prompts`` resolves the dataset's step
  target to a Phoenix prompt name + returns the production version's
  system + user content.
"""
from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic_graph import End, GraphRunContext
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from starlette.testclient import TestClient

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llm_pipeline.db import init_pipeline_db
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
from llm_pipeline.ui.routes.evals import router as evals_router


# ---------------------------------------------------------------------------
# A tiny pipeline used by every test
# ---------------------------------------------------------------------------


class _RouteInput(PipelineInputData):
    text: str


class _RouteInputs(StepInputs):
    text: str


class _RouteInstructions(LLMResultMixin):
    label: str = ""

    example: ClassVar[dict] = {"label": "neutral", "confidence_score": 0.9}


class _RoutePrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class _RouteStep(LLMStepNode):
    INPUTS = _RouteInputs
    INSTRUCTIONS = _RouteInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _RouteInputs) -> list[_RoutePrompt]:
        return [_RoutePrompt(
            system=_RoutePrompt.system(),
            user=_RoutePrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


class _RoutePipeline(Pipeline):
    INPUT_DATA = _RouteInput
    nodes = [
        Step(
            _RouteStep,
            inputs_spec=_RouteInputs.sources(text=FromInput("text")),
        ),
    ]


# ---------------------------------------------------------------------------
# Phoenix stubs
# ---------------------------------------------------------------------------


class _DatasetStub:
    """In-memory dataset/experiments client mirroring the surface used by routes."""

    def __init__(self, dataset: dict[str, Any]):
        self._dataset = dataset
        self.experiments: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []
        self.evaluations: list[dict[str, Any]] = []

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        return self._dataset

    def list_examples(self, dataset_id: str, **kwargs: Any) -> dict[str, Any]:
        return {"data": {"examples": []}}

    def list_experiments(self, dataset_id: str) -> dict[str, Any]:
        return {"data": list(self.experiments)}

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        for exp in self.experiments:
            if exp["id"] == experiment_id:
                return exp
        from llm_pipeline.evals.phoenix_client import ExperimentNotFoundError
        raise ExperimentNotFoundError(experiment_id)

    def list_runs(self, experiment_id: str) -> dict[str, Any]:
        return {"data": [r for r in self.runs if r["experiment_id"] == experiment_id]}

    def create_experiment(self, dataset_id: str, **kwargs: Any) -> dict[str, Any]:
        record = {
            "id": f"exp-{len(self.experiments) + 1}",
            "dataset_id": dataset_id,
            **kwargs,
        }
        self.experiments.append(record)
        return record

    def record_run(self, experiment_id: str, **kwargs: Any) -> dict[str, Any]:
        run = {
            "id": f"run-{len(self.runs) + 1}",
            "experiment_id": experiment_id,
            **kwargs,
        }
        self.runs.append(run)
        return run

    def attach_evaluation(self, experiment_id: str, run_id: str, **kwargs: Any) -> dict[str, Any]:
        ev = {"id": f"ev-{len(self.evaluations) + 1}", **kwargs}
        self.evaluations.append(ev)
        return ev


class _PromptClientStub:
    """In-memory prompt client mirroring the surface used by /prod-prompts."""

    def __init__(self, *, by_tag: dict[str, dict] | None = None,
                 latest: dict[str, dict] | None = None,
                 records: list[dict] | None = None):
        self._by_tag = by_tag or {}
        self._latest = latest or {}
        self._records = records or []

    def get_by_tag(self, name: str, tag: str) -> dict:
        key = (name, tag)
        if key in self._by_tag:
            return self._by_tag[key]
        from llm_pipeline.prompts.phoenix_client import PromptNotFoundError
        raise PromptNotFoundError(name)

    def get_latest(self, name: str) -> dict:
        if name in self._latest:
            return self._latest[name]
        from llm_pipeline.prompts.phoenix_client import PromptNotFoundError
        raise PromptNotFoundError(name)

    def list_prompts(self, *, limit: int = 100) -> dict:
        return {"data": list(self._records)}


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


def _build_app(
    *,
    dataset_stub: _DatasetStub,
    prompt_stub: _PromptClientStub | None = None,
    default_model: str | None = "test",
) -> tuple[FastAPI, _DatasetStub]:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(eng)
    SQLModel.metadata.create_all(eng)

    app = FastAPI(title="evals-routes-test")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.state.engine = eng
    app.state.pipeline_registry = {_RoutePipeline.pipeline_name(): _RoutePipeline}
    app.state.introspection_registry = {
        _RoutePipeline.pipeline_name(): _RoutePipeline,
    }
    app.state.default_model = default_model
    app.state._phoenix_dataset_client = dataset_stub
    if prompt_stub is not None:
        app.state._phoenix_prompt_client = prompt_stub

    app.include_router(evals_router, prefix="/api")
    return app, dataset_stub


# ---------------------------------------------------------------------------
# trigger_run
# ---------------------------------------------------------------------------


class TestTriggerRun:
    def test_returns_experiment_id_and_pre_creates_record(self):
        stub = _DatasetStub(dataset={
            "id": "ds-1",
            "metadata": {"target_type": "step", "target_name": "_route"},
        })
        app, ds_stub = _build_app(dataset_stub=stub)
        with TestClient(app) as client:
            resp = client.post(
                "/api/evals/datasets/ds-1/runs",
                json={"variant": {"model": "test"}, "run_name": "smoke"},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["dataset_id"] == "ds-1"
        assert body["experiment_id"]

        # Experiment was created in the foreground; metadata captured the variant.
        assert len(ds_stub.experiments) == 1
        exp = ds_stub.experiments[0]
        assert exp["name"] == "smoke"
        assert exp["metadata"]["variant"]["model"] == "test"
        assert exp["metadata"]["target_type"] == "step"
        assert exp["metadata"]["target_name"] == "_route"

    def test_dataset_missing_target_returns_422(self):
        stub = _DatasetStub(dataset={"id": "ds-x", "metadata": {}})
        app, _ = _build_app(dataset_stub=stub)
        with TestClient(app) as client:
            resp = client.post(
                "/api/evals/datasets/ds-x/runs",
                json={"variant": {"model": "test"}},
            )
        assert resp.status_code == 422
        assert "target_type" in resp.json()["detail"]

    def test_no_default_model_and_no_variant_model_returns_422(self):
        stub = _DatasetStub(dataset={
            "id": "ds-1",
            "metadata": {"target_type": "step", "target_name": "_route"},
        })
        app, _ = _build_app(dataset_stub=stub, default_model=None)
        with TestClient(app) as client:
            resp = client.post(
                "/api/evals/datasets/ds-1/runs", json={},
            )
        assert resp.status_code == 422

    def test_variant_model_alone_satisfies_model_requirement(self):
        stub = _DatasetStub(dataset={
            "id": "ds-1",
            "metadata": {"target_type": "step", "target_name": "_route"},
        })
        app, _ = _build_app(dataset_stub=stub, default_model=None)
        with TestClient(app) as client:
            resp = client.post(
                "/api/evals/datasets/ds-1/runs",
                json={"variant": {"model": "test"}},
            )
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# /prod-prompts
# ---------------------------------------------------------------------------


def _chat_version(*, version_id: str, system: str, user: str) -> dict:
    return {
        "id": version_id,
        "template": {
            "type": "chat",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    }


class TestProdPrompts:
    def test_step_target_happy_path_returns_system_user(self):
        prompt_name = _RouteStep.step_name()
        prompt_stub = _PromptClientStub(
            by_tag={(prompt_name, "production"): _chat_version(
                version_id="v-prod", system="System.", user="Text: {text}",
            )},
            records=[
                {
                    "name": prompt_name,
                    "metadata": {"variable_definitions": [{"name": "text"}]},
                },
            ],
        )
        stub = _DatasetStub(dataset={
            "id": "ds-1",
            "metadata": {"target_type": "step", "target_name": "_route"},
        })
        app, _ = _build_app(dataset_stub=stub, prompt_stub=prompt_stub)
        with TestClient(app) as client:
            resp = client.get("/api/evals/datasets/ds-1/prod-prompts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["prompt_name"] == prompt_name
        assert body["step_name"] == _RouteStep.step_name()
        assert body["system"] == "System."
        assert body["user"] == "Text: {text}"
        assert body["variable_definitions"] == [{"name": "text"}]

    def test_falls_back_to_latest_when_no_production_tag(self):
        prompt_name = _RouteStep.step_name()
        prompt_stub = _PromptClientStub(
            latest={prompt_name: _chat_version(
                version_id="v-latest", system="L.", user="L: {text}",
            )},
        )
        stub = _DatasetStub(dataset={
            "id": "ds-1",
            "metadata": {"target_type": "step", "target_name": "_route"},
        })
        app, _ = _build_app(dataset_stub=stub, prompt_stub=prompt_stub)
        with TestClient(app) as client:
            resp = client.get("/api/evals/datasets/ds-1/prod-prompts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["system"] == "L."
        assert body["user"] == "L: {text}"

    def test_returns_nulls_when_prompt_not_in_phoenix(self):
        prompt_stub = _PromptClientStub()  # nothing registered
        stub = _DatasetStub(dataset={
            "id": "ds-1",
            "metadata": {"target_type": "step", "target_name": "_route"},
        })
        app, _ = _build_app(dataset_stub=stub, prompt_stub=prompt_stub)
        with TestClient(app) as client:
            resp = client.get("/api/evals/datasets/ds-1/prod-prompts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["system"] is None
        assert body["user"] is None

    def test_pipeline_target_returns_422(self):
        prompt_stub = _PromptClientStub()
        stub = _DatasetStub(dataset={
            "id": "ds-pipe",
            "metadata": {
                "target_type": "pipeline",
                "target_name": _RoutePipeline.pipeline_name(),
            },
        })
        app, _ = _build_app(dataset_stub=stub, prompt_stub=prompt_stub)
        with TestClient(app) as client:
            resp = client.get("/api/evals/datasets/ds-pipe/prod-prompts")
        assert resp.status_code == 422
        assert "step-targets only" in resp.json()["detail"]

    def test_unknown_step_returns_404(self):
        prompt_stub = _PromptClientStub()
        stub = _DatasetStub(dataset={
            "id": "ds-1",
            "metadata": {"target_type": "step", "target_name": "MissingStep"},
        })
        app, _ = _build_app(dataset_stub=stub, prompt_stub=prompt_stub)
        with TestClient(app) as client:
            resp = client.get("/api/evals/datasets/ds-1/prod-prompts")
        assert resp.status_code == 404
