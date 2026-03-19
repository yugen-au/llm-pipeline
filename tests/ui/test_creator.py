"""Endpoint tests for /api/creator routes.

Mocks StepCreatorPipeline, StepSandbox, and StepIntegrator at their source
modules so lazy imports inside route handlers pick up the mocks.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select
from starlette.testclient import TestClient

from llm_pipeline.creator.models import GeneratedStep, IntegrationResult
from llm_pipeline.creator.sandbox import SandboxResult
from llm_pipeline.db import init_pipeline_db
from llm_pipeline.state import DraftStep, PipelineRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_seeded_creator_app():
    """In-memory SQLite app with 2 pre-seeded DraftStep rows."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from llm_pipeline.ui.routes.creator import router as creator_router

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(engine)

    app = FastAPI(title="creator-test")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.engine = engine
    app.state.default_model = "test-model"

    app.include_router(creator_router, prefix="/api")

    # Seed two DraftStep rows
    with Session(engine) as s:
        s.add(DraftStep(
            name="alpha_step",
            description="Alpha step for testing",
            generated_code={
                "alpha_step_step.py": "class AlphaStepStep: pass",
                "alpha_step_instructions.py": "class AlphaStepInstructions: pass",
                "alpha_step_prompts.py": "ALL_PROMPTS = []",
            },
            status="draft",
            run_id="aaaa-0001",
        ))
        s.add(DraftStep(
            name="beta_step",
            description="Beta step -- tested",
            generated_code={
                "beta_step_step.py": "class BetaStepStep: pass",
                "beta_step_instructions.py": "class BetaStepInstructions: pass",
                "beta_step_prompts.py": "ALL_PROMPTS = []",
            },
            test_results={"import_ok": True, "sandbox_skipped": True},
            status="tested",
            run_id="aaaa-0002",
        ))
        s.commit()

    return app


@pytest.fixture
def creator_client():
    app = _make_seeded_creator_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def creator_app_and_client():
    """Yields (app, client) for tests that need direct DB access."""
    app = _make_seeded_creator_app()
    with TestClient(app) as client:
        yield app, client


# ---------------------------------------------------------------------------
# TestGenerateEndpoint
# ---------------------------------------------------------------------------

class TestGenerateEndpoint:
    """POST /api/creator/generate"""

    @patch("llm_pipeline.creator.pipeline.StepCreatorPipeline")
    @patch("llm_pipeline.ui.routes.creator._ensure_seeded")
    @patch("llm_pipeline.ui.routes.creator.ws_manager")
    def test_generate_returns_202_accepted(
        self, mock_ws, mock_seed, MockPipeline, creator_app_and_client
    ):
        # Mock pipeline so background task completes without LLM calls
        mock_pipe = MockPipeline.return_value
        mock_pipe.execute.return_value = None
        mock_pipe.save.return_value = None
        mock_pipe._context = None

        app, client = creator_app_and_client
        resp = client.post(
            "/api/creator/generate",
            json={"description": "Sentiment analysis step"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"
        assert "run_id" in body
        assert body["draft_name"].startswith("draft_")

        # PipelineRun row pre-created
        engine = app.state.engine
        with Session(engine) as s:
            run = s.exec(
                select(PipelineRun).where(PipelineRun.run_id == body["run_id"])
            ).first()
            assert run is not None
            assert run.pipeline_name == "step_creator"

    @patch("llm_pipeline.creator.pipeline.StepCreatorPipeline")
    @patch("llm_pipeline.ui.routes.creator._ensure_seeded")
    @patch("llm_pipeline.ui.routes.creator.ws_manager")
    def test_generate_creates_draft_step_row(
        self, mock_ws, mock_seed, MockPipeline, creator_app_and_client
    ):
        mock_pipe = MockPipeline.return_value
        mock_pipe.execute.return_value = None
        mock_pipe.save.return_value = None
        mock_pipe._context = None

        app, client = creator_app_and_client
        resp = client.post("/api/creator/generate", json={"description": "New step"})
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

        engine = app.state.engine
        with Session(engine) as s:
            draft = s.exec(
                select(DraftStep).where(DraftStep.run_id == run_id)
            ).first()
            assert draft is not None
            assert draft.description == "New step"

    def test_generate_missing_model_returns_422(self, creator_app_and_client):
        app, client = creator_app_and_client
        app.state.default_model = None
        resp = client.post(
            "/api/creator/generate", json={"description": "Whatever"}
        )
        assert resp.status_code == 422
        assert "No model configured" in resp.json()["detail"]

    @patch("llm_pipeline.creator.pipeline.StepCreatorPipeline")
    @patch("llm_pipeline.ui.routes.creator._ensure_seeded")
    @patch("llm_pipeline.ui.routes.creator.ws_manager")
    def test_generate_broadcasts_ws_event(
        self, mock_ws, mock_seed, MockPipeline, creator_app_and_client
    ):
        mock_pipe = MockPipeline.return_value
        mock_pipe.execute.return_value = None
        mock_pipe.save.return_value = None
        mock_pipe._context = None

        _, client = creator_app_and_client
        resp = client.post("/api/creator/generate", json={"description": "WS test"})
        assert resp.status_code == 202
        mock_ws.broadcast_global.assert_called_once()
        event = mock_ws.broadcast_global.call_args[0][0]
        assert event["type"] == "run_created"
        assert event["pipeline_name"] == "step_creator"


# ---------------------------------------------------------------------------
# TestTestEndpoint
# ---------------------------------------------------------------------------

class TestTestEndpoint:
    """POST /api/creator/test/{draft_id}"""

    @patch("llm_pipeline.creator.sandbox.StepSandbox")
    def test_test_no_overrides_runs_sandbox(self, MockSandbox, creator_client):
        mock_instance = MockSandbox.return_value
        mock_instance.run.return_value = SandboxResult(
            import_ok=True,
            security_issues=[],
            sandbox_skipped=True,
            output="ok",
            errors=[],
            modules_found=["alpha_step_step"],
        )
        resp = creator_client.post("/api/creator/test/1", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["import_ok"] is True
        assert body["sandbox_skipped"] is True
        assert body["draft_status"] == "tested"

    @patch("llm_pipeline.creator.sandbox.StepSandbox")
    def test_test_with_code_overrides_persists(
        self, MockSandbox, creator_app_and_client
    ):
        app, client = creator_app_and_client
        mock_instance = MockSandbox.return_value
        mock_instance.run.return_value = SandboxResult(
            import_ok=True,
            security_issues=[],
            sandbox_skipped=True,
            output="ok",
            errors=[],
            modules_found=[],
        )
        overrides = {"alpha_step_step.py": "class AlphaStepStep:\n    updated = True"}
        resp = client.post(
            "/api/creator/test/1", json={"code_overrides": overrides}
        )
        assert resp.status_code == 200

        # Verify generated_code was updated in DB
        with Session(app.state.engine) as s:
            draft = s.get(DraftStep, 1)
            assert (
                draft.generated_code["alpha_step_step.py"]
                == overrides["alpha_step_step.py"]
            )
            # Other keys preserved
            assert "alpha_step_instructions.py" in draft.generated_code

    @patch("llm_pipeline.creator.sandbox.StepSandbox")
    def test_test_sandbox_failure_sets_error_status(
        self, MockSandbox, creator_app_and_client
    ):
        app, client = creator_app_and_client
        mock_instance = MockSandbox.return_value
        mock_instance.run.return_value = SandboxResult(
            import_ok=False,
            security_issues=["dangerous import"],
            sandbox_skipped=False,
            output="",
            errors=["ImportError"],
            modules_found=[],
        )
        resp = client.post("/api/creator/test/1", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["import_ok"] is False
        assert body["draft_status"] == "error"

        with Session(app.state.engine) as s:
            draft = s.get(DraftStep, 1)
            assert draft.status == "error"

    def test_test_404_for_missing_draft(self, creator_client):
        resp = creator_client.post("/api/creator/test/9999", json={})
        assert resp.status_code == 404
        assert "Draft not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# TestAcceptEndpoint
# ---------------------------------------------------------------------------

class TestAcceptEndpoint:
    """POST /api/creator/accept/{draft_id}"""

    @patch("llm_pipeline.creator.integrator.StepIntegrator")
    @patch("llm_pipeline.creator.models.GeneratedStep.from_draft")
    @patch("llm_pipeline.ui.routes.creator._derive_target_dir")
    def test_accept_calls_integrator_and_returns_result(
        self, mock_derive, mock_from_draft, mock_integrator_cls, creator_client
    ):
        mock_derive.return_value = Path("/tmp/steps/alpha_step")
        mock_from_draft.return_value = MagicMock(spec=GeneratedStep)
        mock_integrator = mock_integrator_cls.return_value
        mock_integrator.integrate.return_value = IntegrationResult(
            files_written=["/tmp/steps/alpha_step/alpha_step_step.py"],
            prompts_registered=2,
            pipeline_file_updated=False,
            target_dir="/tmp/steps/alpha_step",
        )
        resp = creator_client.post("/api/creator/accept/1", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["files_written"] == [
            "/tmp/steps/alpha_step/alpha_step_step.py"
        ]
        assert body["prompts_registered"] == 2
        assert body["pipeline_file_updated"] is False
        assert body["target_dir"] == "/tmp/steps/alpha_step"

        # Verify integrator was constructed without pipeline_file
        mock_integrator_cls.assert_called_once()
        call_kwargs = mock_integrator_cls.call_args
        pf = call_kwargs.kwargs.get("pipeline_file")
        assert pf is None

    @patch("llm_pipeline.creator.integrator.StepIntegrator")
    @patch("llm_pipeline.creator.models.GeneratedStep.from_draft")
    @patch("llm_pipeline.ui.routes.creator._derive_target_dir")
    def test_accept_with_pipeline_file(
        self, mock_derive, mock_from_draft, mock_integrator_cls, creator_client
    ):
        mock_derive.return_value = Path("/tmp/steps/alpha_step")
        mock_from_draft.return_value = MagicMock(spec=GeneratedStep)
        mock_integrator = mock_integrator_cls.return_value
        mock_integrator.integrate.return_value = IntegrationResult(
            files_written=[],
            prompts_registered=0,
            pipeline_file_updated=True,
            target_dir="/tmp/steps/alpha_step",
        )
        resp = creator_client.post(
            "/api/creator/accept/1",
            json={"pipeline_file": "my_pipeline.py"},
        )
        assert resp.status_code == 200
        assert resp.json()["pipeline_file_updated"] is True

        # Verify StepIntegrator got the pipeline_file as Path
        call_kwargs = mock_integrator_cls.call_args
        pf = call_kwargs.kwargs.get("pipeline_file")
        assert pf == Path("my_pipeline.py")

    def test_accept_404_for_missing_draft(self, creator_client):
        resp = creator_client.post("/api/creator/accept/9999", json={})
        assert resp.status_code == 404
        assert "Draft not found" in resp.json()["detail"]

    @patch("llm_pipeline.creator.integrator.StepIntegrator")
    @patch("llm_pipeline.creator.models.GeneratedStep.from_draft")
    @patch("llm_pipeline.ui.routes.creator._derive_target_dir")
    def test_accept_integrator_failure_returns_500(
        self, mock_derive, mock_from_draft, mock_integrator_cls, creator_client
    ):
        mock_derive.return_value = Path("/tmp/steps/alpha_step")
        mock_from_draft.return_value = MagicMock(spec=GeneratedStep)
        mock_integrator = mock_integrator_cls.return_value
        mock_integrator.integrate.side_effect = RuntimeError("disk full")
        resp = creator_client.post("/api/creator/accept/1", json={})
        assert resp.status_code == 500
        assert "Integration failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# TestDraftsEndpoint
# ---------------------------------------------------------------------------

class TestDraftsEndpoint:
    """GET /api/creator/drafts and GET /api/creator/drafts/{id}"""

    def test_list_drafts_returns_all(self, creator_client):
        resp = creator_client.get("/api/creator/drafts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_list_drafts_ordered_by_created_at_desc(self, creator_client):
        resp = creator_client.get("/api/creator/drafts")
        items = resp.json()["items"]
        created_ats = [item["created_at"] for item in items]
        assert created_ats == sorted(created_ats, reverse=True)

    def test_list_drafts_item_schema(self, creator_client):
        resp = creator_client.get("/api/creator/drafts")
        item = resp.json()["items"][0]
        for field in (
            "id", "name", "description", "status",
            "run_id", "created_at", "updated_at",
        ):
            assert field in item

    def test_get_draft_by_id(self, creator_client):
        resp = creator_client.get("/api/creator/drafts/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "alpha_step"
        assert body["status"] == "draft"

    def test_get_draft_by_id_second(self, creator_client):
        resp = creator_client.get("/api/creator/drafts/2")
        assert resp.status_code == 200
        assert resp.json()["name"] == "beta_step"
        assert resp.json()["status"] == "tested"

    def test_get_draft_404(self, creator_client):
        resp = creator_client.get("/api/creator/drafts/9999")
        assert resp.status_code == 404
        assert "Draft not found" in resp.json()["detail"]
