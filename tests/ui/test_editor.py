"""Endpoint tests for /api/editor routes.

Covers compile, available-steps, and DraftPipeline CRUD endpoints.
No mocking needed -- editor endpoints have no LLM calls or external deps.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select
from starlette.testclient import TestClient

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.state import DraftPipeline, DraftStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_seeded_editor_app():
    """In-memory SQLite app with seeded DraftStep + DraftPipeline rows."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from llm_pipeline.ui.routes.editor import router as editor_router

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(engine)

    app = FastAPI(title="editor-test")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.engine = engine
    app.state.introspection_registry = {}

    app.include_router(editor_router, prefix="/api")

    with Session(engine) as s:
        # alpha_step: non-errored draft
        s.add(DraftStep(
            name="alpha_step",
            description="Alpha step for testing",
            generated_code={
                "alpha_step_step.py": "class AlphaStepStep: pass",
            },
            status="draft",
            run_id="aaaa-0001",
        ))
        # beta_step: errored -- should be excluded from available steps / compile
        s.add(DraftStep(
            name="beta_step",
            description="Beta step with error",
            generated_code={
                "beta_step_step.py": "class BetaStepStep: pass",
            },
            status="error",
            run_id="aaaa-0002",
        ))
        # gamma_step: non-errored draft used for isolated position tests
        s.add(DraftStep(
            name="gamma_step",
            description="Gamma step for position isolation tests",
            generated_code={
                "gamma_step_step.py": "class GammaStepStep: pass",
            },
            status="draft",
            run_id="aaaa-0003",
        ))
        # Two seeded DraftPipeline rows
        s.add(DraftPipeline(
            name="pipeline_one",
            structure={"strategies": [{"name": "main", "steps": ["alpha_step"]}]},
        ))
        s.add(DraftPipeline(
            name="pipeline_two",
            structure={"strategies": []},
        ))
        s.commit()

    return app


@pytest.fixture
def editor_client():
    app = _make_seeded_editor_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def editor_app_and_client():
    """Yields (app, client) for tests that need direct DB access."""
    app = _make_seeded_editor_app()
    with TestClient(app) as client:
        yield app, client


# ---------------------------------------------------------------------------
# TestCompileEndpoint
# ---------------------------------------------------------------------------


class TestCompileEndpoint:
    """POST /api/editor/compile"""

    def test_compile_valid_returns_valid_true(self, editor_client):
        resp = editor_client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "main",
                        "steps": [
                            {"step_ref": "alpha_step", "source": "draft", "position": 0},
                        ],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["errors"] == []

    def test_compile_unknown_step_returns_error(self, editor_client):
        resp = editor_client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "main",
                        "steps": [
                            {"step_ref": "nonexistent_step", "source": "draft", "position": 0},
                        ],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert len(body["errors"]) >= 1
        refs = [e["step_ref"] for e in body["errors"]]
        assert "nonexistent_step" in refs

    def test_compile_duplicate_steps_in_strategy(self, editor_client):
        resp = editor_client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "main",
                        "steps": [
                            {"step_ref": "alpha_step", "source": "draft", "position": 0},
                            {"step_ref": "alpha_step", "source": "draft", "position": 1},
                        ],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        dup_errors = [e for e in body["errors"] if e.get("field") == "step_ref"]
        assert len(dup_errors) >= 1
        assert dup_errors[0]["step_ref"] == "alpha_step"

    def test_compile_empty_strategy(self, editor_client):
        resp = editor_client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "empty_strategy",
                        "steps": [],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        empty_errors = [e for e in body["errors"] if e.get("field") == "steps"]
        assert len(empty_errors) >= 1
        assert empty_errors[0]["strategy_name"] == "empty_strategy"

    def test_compile_position_gap(self, editor_client):
        """Positions [0, 2] have a gap -- isolated with distinct step_refs to avoid Pass 2."""
        resp = editor_client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "main",
                        "steps": [
                            {"step_ref": "alpha_step", "source": "draft", "position": 0},
                            {"step_ref": "gamma_step", "source": "draft", "position": 2},
                        ],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        pos_errors = [e for e in body["errors"] if e.get("field") == "position"]
        assert len(pos_errors) >= 1

    def test_compile_position_duplicate(self, editor_client):
        """Positions [0, 0] are duplicated -- isolated with distinct step_refs to avoid Pass 2."""
        resp = editor_client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "main",
                        "steps": [
                            {"step_ref": "alpha_step", "source": "draft", "position": 0},
                            {"step_ref": "gamma_step", "source": "draft", "position": 0},
                        ],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        pos_errors = [e for e in body["errors"] if e.get("field") == "position"]
        assert len(pos_errors) >= 1

    def test_compile_empty_strategies_list(self, editor_client):
        """strategies=[] (no strategies at all) is valid -- nothing to validate."""
        resp = editor_client.post(
            "/api/editor/compile",
            json={"strategies": []},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["errors"] == []

    def test_compile_stateful_writes_errors(self, editor_app_and_client):
        """Compile with invalid draft_id payload writes errors to DB row."""
        app, client = editor_app_and_client
        # Get id of pipeline_one (first seeded pipeline)
        with Session(app.state.engine) as s:
            draft = s.exec(
                select(DraftPipeline).where(DraftPipeline.name == "pipeline_one")
            ).first()
            assert draft is not None
            draft_id = draft.id

        resp = client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "main",
                        "steps": [
                            {"step_ref": "no_such_step", "source": "draft", "position": 0},
                        ],
                    }
                ],
                "draft_id": draft_id,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False

        with Session(app.state.engine) as s:
            draft = s.get(DraftPipeline, draft_id)
            assert draft.compilation_errors is not None
            assert "errors" in draft.compilation_errors
            assert len(draft.compilation_errors["errors"]) >= 1

    def test_compile_stateful_valid_clears_errors(self, editor_app_and_client):
        """Valid compile with draft_id sets compilation_errors={"errors":[]} and status=draft."""
        app, client = editor_app_and_client
        with Session(app.state.engine) as s:
            draft = s.exec(
                select(DraftPipeline).where(DraftPipeline.name == "pipeline_one")
            ).first()
            draft_id = draft.id
            # Pre-set errors so we can verify they get cleared
            draft.compilation_errors = {"errors": [{"msg": "stale"}]}
            draft.status = "error"
            s.add(draft)
            s.commit()

        resp = client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "main",
                        "steps": [
                            {"step_ref": "alpha_step", "source": "draft", "position": 0},
                        ],
                    }
                ],
                "draft_id": draft_id,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

        with Session(app.state.engine) as s:
            draft = s.get(DraftPipeline, draft_id)
            assert draft.compilation_errors == {"errors": []}
            assert draft.status == "draft"

    def test_compile_stateful_draft_not_found(self, editor_client):
        resp = editor_client.post(
            "/api/editor/compile",
            json={
                "strategies": [],
                "draft_id": 9999,
            },
        )
        assert resp.status_code == 404

    def test_compile_excludes_errored_draft_steps(self, editor_client):
        """beta_step has status=error and should NOT be a valid step_ref."""
        resp = editor_client.post(
            "/api/editor/compile",
            json={
                "strategies": [
                    {
                        "strategy_name": "main",
                        "steps": [
                            {"step_ref": "beta_step", "source": "draft", "position": 0},
                        ],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        refs = [e["step_ref"] for e in body["errors"]]
        assert "beta_step" in refs


# ---------------------------------------------------------------------------
# TestAvailableStepsEndpoint
# ---------------------------------------------------------------------------


class TestAvailableStepsEndpoint:
    """GET /api/editor/available-steps"""

    def test_available_steps_returns_non_errored_drafts(self, editor_client):
        """alpha_step (draft) present; beta_step (error) absent."""
        resp = editor_client.get("/api/editor/available-steps")
        assert resp.status_code == 200
        steps = resp.json()["steps"]
        step_refs = [s["step_ref"] for s in steps]
        assert "alpha_step" in step_refs
        assert "beta_step" not in step_refs

    def test_available_steps_deduplicates_registered_wins(self, editor_app_and_client):
        """When registry has same name as draft, registered entry wins (source=registered)."""
        from unittest.mock import MagicMock

        app, client = editor_app_and_client

        # Build a fake introspection registry that exposes "alpha_step"
        mock_cls = MagicMock()
        mock_introspector = MagicMock()
        mock_introspector.get_metadata.return_value = {
            "strategies": [
                {
                    "steps": [
                        {"step_name": "alpha_step"},
                    ]
                }
            ]
        }

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "llm_pipeline.ui.routes.editor.PipelineIntrospector",
                lambda cls: mock_introspector,
            )
            app.state.introspection_registry = {"fake_pipeline": mock_cls}
            resp = client.get("/api/editor/available-steps")

        assert resp.status_code == 200
        steps = resp.json()["steps"]
        alpha_entries = [s for s in steps if s["step_ref"] == "alpha_step"]
        assert len(alpha_entries) == 1
        assert alpha_entries[0]["source"] == "registered"

    def test_available_steps_empty_registry_returns_drafts_only(self, editor_app_and_client):
        """With empty introspection_registry, only non-errored draft steps returned."""
        app, client = editor_app_and_client
        app.state.introspection_registry = {}
        resp = client.get("/api/editor/available-steps")
        assert resp.status_code == 200
        steps = resp.json()["steps"]
        for s in steps:
            assert s["source"] == "draft"
        step_refs = [s["step_ref"] for s in steps]
        assert "alpha_step" in step_refs
        assert "beta_step" not in step_refs


# ---------------------------------------------------------------------------
# TestDraftPipelineCRUD
# ---------------------------------------------------------------------------


class TestDraftPipelineCRUD:
    """POST/GET/PATCH/DELETE /api/editor/drafts"""

    def test_create_draft_pipeline_returns_201(self, editor_client):
        resp = editor_client.post(
            "/api/editor/drafts",
            json={
                "name": "new_pipeline",
                "structure": {"strategies": [{"name": "main", "steps": []}]},
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["name"] == "new_pipeline"
        assert body["status"] == "draft"
        assert body["structure"] == {"strategies": [{"name": "main", "steps": []}]}

    def test_create_draft_pipeline_name_conflict_returns_409(self, editor_client):
        # pipeline_one is seeded
        resp = editor_client.post(
            "/api/editor/drafts",
            json={"name": "pipeline_one", "structure": {}},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["detail"] == "name_conflict"

    def test_list_draft_pipelines_returns_seeded(self, editor_client):
        resp = editor_client.get("/api/editor/drafts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_get_draft_pipeline_returns_detail(self, editor_app_and_client):
        app, client = editor_app_and_client
        with Session(app.state.engine) as s:
            draft = s.exec(
                select(DraftPipeline).where(DraftPipeline.name == "pipeline_one")
            ).first()
            draft_id = draft.id

        resp = client.get(f"/api/editor/drafts/{draft_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "pipeline_one"
        assert "structure" in body
        assert "compilation_errors" in body

    def test_get_draft_pipeline_not_found_returns_404(self, editor_client):
        resp = editor_client.get("/api/editor/drafts/9999")
        assert resp.status_code == 404

    def test_update_draft_pipeline_name(self, editor_app_and_client):
        app, client = editor_app_and_client
        with Session(app.state.engine) as s:
            draft = s.exec(
                select(DraftPipeline).where(DraftPipeline.name == "pipeline_one")
            ).first()
            draft_id = draft.id
            original_updated_at = draft.updated_at

        resp = client.patch(
            f"/api/editor/drafts/{draft_id}",
            json={"name": "pipeline_one_renamed"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "pipeline_one_renamed"
        # updated_at should be present and reflect change
        assert body["updated_at"] is not None

    def test_update_draft_pipeline_name_conflict_returns_409_with_suggested(
        self, editor_client
    ):
        """PATCH to a name that already exists returns 409 with suggested_name."""
        # Get pipeline_one id, attempt rename to pipeline_two (taken)
        resp = editor_client.get("/api/editor/drafts")
        items = resp.json()["items"]
        pipeline_one_id = next(i["id"] for i in items if i["name"] == "pipeline_one")

        resp = editor_client.patch(
            f"/api/editor/drafts/{pipeline_one_id}",
            json={"name": "pipeline_two"},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["detail"] == "name_conflict"
        assert "suggested_name" in body
        assert body["suggested_name"] != "pipeline_two"

    def test_update_draft_pipeline_not_found_returns_404(self, editor_client):
        resp = editor_client.patch(
            "/api/editor/drafts/9999",
            json={"name": "ghost"},
        )
        assert resp.status_code == 404

    def test_delete_draft_pipeline_returns_204(self, editor_app_and_client):
        app, client = editor_app_and_client
        with Session(app.state.engine) as s:
            draft = s.exec(
                select(DraftPipeline).where(DraftPipeline.name == "pipeline_one")
            ).first()
            draft_id = draft.id

        delete_resp = client.delete(f"/api/editor/drafts/{draft_id}")
        assert delete_resp.status_code == 204

        get_resp = client.get(f"/api/editor/drafts/{draft_id}")
        assert get_resp.status_code == 404

    def test_delete_draft_pipeline_not_found_returns_404(self, editor_client):
        resp = editor_client.delete("/api/editor/drafts/9999")
        assert resp.status_code == 404
