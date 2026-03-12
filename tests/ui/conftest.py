"""Shared fixtures for UI endpoint tests."""
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session
from starlette.testclient import TestClient

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.ui.app import create_app
from llm_pipeline.state import PipelineRun, PipelineStepState
from llm_pipeline.events.models import PipelineEventRecord


def _utc(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _make_app():
    """Create app with true in-memory SQLite (shared-cache so all connections see same DB)."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from llm_pipeline.ui.routes.runs import router as runs_router
    from llm_pipeline.ui.routes.steps import router as steps_router
    from llm_pipeline.ui.routes.events import router as events_router
    from llm_pipeline.ui.routes.prompts import router as prompts_router
    from llm_pipeline.ui.routes.pipelines import router as pipelines_router
    from llm_pipeline.ui.routes.websocket import router as ws_router

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
    app.include_router(events_router, prefix="/api")
    app.include_router(prompts_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")
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

        step1 = PipelineStepState(
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            pipeline_name="alpha_pipeline",
            step_name="step_a",
            step_number=1,
            input_hash="hash_a1",
            result_data={"value": 1},
            context_snapshot={"k": "v"},
            execution_time_ms=3000,
            created_at=_utc(-299),
        )
        step2 = PipelineStepState(
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            pipeline_name="alpha_pipeline",
            step_name="step_b",
            step_number=2,
            input_hash="hash_b1",
            result_data={"value": 2},
            context_snapshot={"k": "v"},
            execution_time_ms=6800,
            created_at=_utc(-295),
        )
        step3 = PipelineStepState(
            run_id="aaaaaaaa-0000-0000-0000-000000000002",
            pipeline_name="beta_pipeline",
            step_name="step_a",
            step_number=1,
            input_hash="hash_a2",
            result_data={"value": 3},
            context_snapshot={},
            execution_time_ms=4500,
            created_at=_utc(-199),
        )
        session.add(step1)
        session.add(step2)
        session.add(step3)
        session.commit()

    # Seed events for RUN_1 only (RUN_2 and RUN_3 have no events)
    with Session(engine) as session:
        evt1 = PipelineEventRecord(
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            event_type="pipeline_started",
            pipeline_name="alpha_pipeline",
            timestamp=_utc(-298),
            event_data={"event_type": "pipeline_started", "run_id": "aaaaaaaa-0000-0000-0000-000000000001"},
        )
        evt2 = PipelineEventRecord(
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            event_type="step_started",
            pipeline_name="alpha_pipeline",
            timestamp=_utc(-297),
            event_data={"event_type": "step_started", "run_id": "aaaaaaaa-0000-0000-0000-000000000001", "step_name": "step_a"},
        )
        evt3 = PipelineEventRecord(
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            event_type="step_completed",
            pipeline_name="alpha_pipeline",
            timestamp=_utc(-294),
            event_data={"event_type": "step_completed", "run_id": "aaaaaaaa-0000-0000-0000-000000000001", "step_name": "step_a"},
        )
        evt4 = PipelineEventRecord(
            run_id="aaaaaaaa-0000-0000-0000-000000000001",
            event_type="pipeline_completed",
            pipeline_name="alpha_pipeline",
            timestamp=_utc(-291),
            event_data={"event_type": "pipeline_completed", "run_id": "aaaaaaaa-0000-0000-0000-000000000001"},
        )
        session.add(evt1)
        session.add(evt2)
        session.add(evt3)
        session.add(evt4)
        session.commit()

    with TestClient(app) as client:
        yield client
