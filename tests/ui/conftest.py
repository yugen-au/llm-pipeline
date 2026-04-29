"""Shared fixtures for UI endpoint tests."""
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session
from starlette.testclient import TestClient

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.db.pipeline_visibility import PipelineVisibility
from llm_pipeline.ui.app import create_app
from llm_pipeline.state import PipelineNodeSnapshot, PipelineRun


def _utc(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _publish_all(engine):
    """Set all pipeline_configs rows to published. For tests that need to trigger runs."""
    with Session(engine) as session:
        from sqlmodel import select
        for row in session.exec(select(PipelineVisibility)).all():
            row.status = "published"
        session.commit()


def _make_app():
    """Create app with true in-memory SQLite (shared-cache so all connections see same DB)."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from llm_pipeline.ui.routes.runs import router as runs_router
    from llm_pipeline.ui.routes.steps import router as steps_router
    from llm_pipeline.ui.routes.trace import router as trace_router
    from llm_pipeline.ui.routes.prompts import router as prompts_router
    from llm_pipeline.ui.routes.pipelines import router as pipelines_router
    from llm_pipeline.ui.routes.websocket import router as ws_router
    from llm_pipeline.ui.routes.creator import router as creator_router
    from llm_pipeline.ui.routes.auto_generate import router as auto_generate_router
    from llm_pipeline.ui.routes.reviews import router as reviews_router

    # Use connect_args check_same_thread=False + StaticPool so all connections
    # (including threadpool workers) share the same in-memory database.
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(engine)

    app = FastAPI(title="llm-pipeline UI")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.engine = engine
    app.state.pipeline_registry = {}
    app.state.default_model = "test-model"

    app.include_router(runs_router, prefix="/api")
    app.include_router(steps_router, prefix="/api")
    app.include_router(trace_router, prefix="/api")
    app.include_router(prompts_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")
    app.include_router(creator_router, prefix="/api")
    app.include_router(auto_generate_router, prefix="/api")
    app.include_router(reviews_router, prefix="/api")
    app.include_router(ws_router)
    return app


@pytest.fixture
def app_client():
    app = _make_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def seeded_app_client():
    app = _make_app()
    engine = app.state.engine

    with Session(engine) as session:
        run1 = PipelineRun(
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            pipeline_name="alpha_pipeline",
            status="completed",
            started_at=_utc(-300),
            completed_at=_utc(-290),
            step_count=2,
            total_time_ms=9800,
        )
        run2 = PipelineRun(
            run_id="aaaaaaaa-0000-0000-0000-000000000002",
            pipeline_name="beta_pipeline",
            status="failed",
            started_at=_utc(-200),
            completed_at=_utc(-195),
            step_count=1,
            total_time_ms=4500,
        )
        run3 = PipelineRun(
            run_id="aaaaaaaa-0000-0000-0000-000000000003",
            pipeline_name="alpha_pipeline",
            status="running",
            started_at=_utc(-100),
            completed_at=None,
            step_count=None,
            total_time_ms=None,
        )
        session.add(run1)
        session.add(run2)
        session.add(run3)

        # PipelineNodeSnapshot rows — one per node execution. Field
        # mapping from the legacy ``PipelineStepState`` shape:
        #   step_name        -> derived from ``node_class_name`` via
        #                       ``to_snake_case(name, strip='Step')``
        #   step_number      -> ``sequence + 1``
        #   result_data      -> ``state_snapshot.outputs[node_class_name]``
        #   context_snapshot -> ``state_snapshot.metadata``
        #   execution_time_ms -> ``duration * 1000`` (rounded)
        snap_a1 = PipelineNodeSnapshot(
            snapshot_id="StepA:run1",
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            pipeline_name="alpha_pipeline",
            sequence=0,
            kind="node",
            node_class_name="StepAStep",
            node_payload={},
            state_snapshot={
                "input_data": None,
                "outputs": {"StepAStep": [{"value": 1}]},
                "extractions": {},
                "metadata": {"k": "v"},
            },
            status="success",
            duration=3.0,
            created_at=_utc(-299),
        )
        snap_b1 = PipelineNodeSnapshot(
            snapshot_id="StepB:run1",
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            pipeline_name="alpha_pipeline",
            sequence=1,
            kind="node",
            node_class_name="StepBStep",
            node_payload={},
            state_snapshot={
                "input_data": None,
                "outputs": {
                    "StepAStep": [{"value": 1}],
                    "StepBStep": [{"value": 2}],
                },
                "extractions": {},
                "metadata": {"k": "v"},
            },
            status="success",
            duration=6.8,
            created_at=_utc(-295),
        )
        snap_a2 = PipelineNodeSnapshot(
            snapshot_id="StepA:run2",
            run_id="aaaaaaaa-0000-0000-0000-000000000002",
            pipeline_name="beta_pipeline",
            sequence=0,
            kind="node",
            node_class_name="StepAStep",
            node_payload={},
            state_snapshot={
                "input_data": None,
                "outputs": {"StepAStep": [{"value": 3}]},
                "extractions": {},
                "metadata": {},
            },
            status="success",
            duration=4.5,
            created_at=_utc(-199),
        )
        session.add(snap_a1)
        session.add(snap_b1)
        session.add(snap_a2)
        session.commit()

    # Events used to be seeded here for RUN_1 timeline tests, but the
    # events module is gone now — past traces live in Langfuse.

    with TestClient(app) as client:
        yield client
