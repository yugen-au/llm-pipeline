"""Endpoint tests for /api/evals variant CRUD, run trigger + list extensions."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session
from starlette.testclient import TestClient

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals.models import (
    EvaluationDataset,
    EvaluationRun,
    EvaluationVariant,
)
from llm_pipeline.ui.routes.evals import router as evals_router


def _make_evals_app():
    """Minimal app mounting only evals routes, with shared in-memory SQLite."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(engine)

    app = FastAPI(title="evals-test")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.engine = engine
    app.state.pipeline_registry = {}
    app.state.introspection_registry = {}
    app.state.default_model = "test-model"

    app.include_router(evals_router, prefix="/api")
    return app, engine


@pytest.fixture
def evals_app():
    app, engine = _make_evals_app()
    with TestClient(app) as client:
        yield client, engine


@pytest.fixture
def seeded_dataset(evals_app):
    """Provides (client, engine, dataset_id) with a single dataset row."""
    client, engine = evals_app
    with Session(engine) as session:
        ds = EvaluationDataset(
            name="ds1",
            target_type="step",
            target_name="step_a",
            description=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(ds)
        session.commit()
        session.refresh(ds)
        dataset_id = ds.id
    return client, engine, dataset_id


# ---------------------------------------------------------------------------
# POST /evals/{dataset_id}/variants
# ---------------------------------------------------------------------------


class TestCreateVariant:
    def test_create_variant_success(self, seeded_dataset):
        client, _, dataset_id = seeded_dataset
        body = {
            "name": "v1",
            "description": "first",
            "delta": {
                "model": "claude-3-opus",
                "system_prompt": "sys",
                "user_prompt": "user",
                "instructions_delta": [
                    {
                        "op": "add",
                        "field": "new_field",
                        "type_str": "str",
                        "default": "hello",
                    }
                ],
            },
        }
        resp = client.post(f"/api/evals/{dataset_id}/variants", json=body)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "v1"
        assert data["description"] == "first"
        assert data["dataset_id"] == dataset_id
        assert data["delta"]["model"] == "claude-3-opus"
        assert data["delta"]["instructions_delta"][0]["field"] == "new_field"
        assert "created_at" in data
        assert "updated_at" in data
        assert "id" in data

    def test_create_variant_empty_delta_allowed(self, seeded_dataset):
        client, _, dataset_id = seeded_dataset
        body = {"name": "v2", "delta": {}}
        resp = client.post(f"/api/evals/{dataset_id}/variants", json=body)
        assert resp.status_code == 201
        assert resp.json()["delta"] == {}

    def test_create_variant_dataset_not_found(self, evals_app):
        client, _ = evals_app
        resp = client.post(
            "/api/evals/9999/variants", json={"name": "v", "delta": {}}
        )
        assert resp.status_code == 404

    @pytest.mark.parametrize(
        "bad_delta_item,match_fragment",
        [
            # malicious field name: dunder
            (
                {
                    "op": "add",
                    "field": "__class__",
                    "type_str": "str",
                    "default": "",
                },
                "identifier",
            ),
            # malicious op
            (
                {
                    "op": "remove",
                    "field": "category",
                    "type_str": "str",
                    "default": "",
                },
                "op must be",
            ),
            # malicious type_str: non-whitelisted module path
            (
                {
                    "op": "add",
                    "field": "x",
                    "type_str": "os.system",
                    "default": "",
                },
                "whitelist",
            ),
            # malicious type_str: attempted code injection
            (
                {
                    "op": "add",
                    "field": "x",
                    "type_str": "__import__('os').system('ls')",
                    "default": "",
                },
                None,
            ),
            # field traversal
            (
                {
                    "op": "add",
                    "field": "items.append",
                    "type_str": "str",
                    "default": "",
                },
                "identifier",
            ),
        ],
    )
    def test_create_variant_malicious_delta_returns_422(
        self, seeded_dataset, bad_delta_item, match_fragment
    ):
        client, _, dataset_id = seeded_dataset
        body = {
            "name": "bad",
            "delta": {"instructions_delta": [bad_delta_item]},
        }
        resp = client.post(f"/api/evals/{dataset_id}/variants", json=body)
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        # ValueError message surfaces in detail string
        assert isinstance(detail, str)
        if match_fragment is not None:
            assert match_fragment in detail


# ---------------------------------------------------------------------------
# GET /evals/{dataset_id}/variants (list)
# ---------------------------------------------------------------------------


class TestListVariants:
    def test_list_empty(self, seeded_dataset):
        client, _, dataset_id = seeded_dataset
        resp = client.get(f"/api/evals/{dataset_id}/variants")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_ordered_by_created_at_desc(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        # seed 3 variants with staggered created_at
        with Session(engine) as session:
            t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            for i, name in enumerate(["oldest", "middle", "newest"]):
                session.add(
                    EvaluationVariant(
                        dataset_id=dataset_id,
                        name=name,
                        delta={},
                        created_at=t0.replace(hour=12 + i),
                        updated_at=t0.replace(hour=12 + i),
                    )
                )
            session.commit()

        resp = client.get(f"/api/evals/{dataset_id}/variants")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [i["name"] for i in items] == ["newest", "middle", "oldest"]
        assert resp.json()["total"] == 3

    def test_list_dataset_not_found(self, evals_app):
        client, _ = evals_app
        resp = client.get("/api/evals/9999/variants")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /evals/{dataset_id}/variants/{variant_id}
# ---------------------------------------------------------------------------


class TestGetVariant:
    def test_get_variant_success(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        with Session(engine) as session:
            v = EvaluationVariant(
                dataset_id=dataset_id, name="v", delta={"model": "m"}
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vid = v.id

        resp = client.get(f"/api/evals/{dataset_id}/variants/{vid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == vid
        assert resp.json()["delta"]["model"] == "m"

    def test_get_variant_not_found(self, seeded_dataset):
        client, _, dataset_id = seeded_dataset
        resp = client.get(f"/api/evals/{dataset_id}/variants/9999")
        assert resp.status_code == 404

    def test_get_variant_wrong_dataset_returns_404(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        # create a second dataset and a variant on it
        with Session(engine) as session:
            ds2 = EvaluationDataset(
                name="ds2", target_type="step", target_name="sx"
            )
            session.add(ds2)
            session.commit()
            session.refresh(ds2)
            v = EvaluationVariant(dataset_id=ds2.id, name="v_other", delta={})
            session.add(v)
            session.commit()
            session.refresh(v)
            other_variant_id = v.id

        # request variant via the WRONG dataset_id -> 404
        resp = client.get(
            f"/api/evals/{dataset_id}/variants/{other_variant_id}"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /evals/{dataset_id}/variants/{variant_id}
# ---------------------------------------------------------------------------


class TestUpdateVariant:
    def test_update_variant_fields(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        with Session(engine) as session:
            v = EvaluationVariant(
                dataset_id=dataset_id,
                name="orig",
                description="d0",
                delta={"model": "m0"},
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vid = v.id

        body = {
            "name": "updated",
            "description": "d1",
            "delta": {"model": "m1"},
        }
        resp = client.put(f"/api/evals/{dataset_id}/variants/{vid}", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated"
        assert data["description"] == "d1"
        assert data["delta"]["model"] == "m1"

    def test_update_partial_only_name(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        with Session(engine) as session:
            v = EvaluationVariant(
                dataset_id=dataset_id,
                name="orig",
                description="keep_me",
                delta={"model": "m0"},
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vid = v.id

        resp = client.put(
            f"/api/evals/{dataset_id}/variants/{vid}",
            json={"name": "renamed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "renamed"
        assert data["description"] == "keep_me"
        assert data["delta"]["model"] == "m0"

    def test_update_malicious_delta_returns_422(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        with Session(engine) as session:
            v = EvaluationVariant(
                dataset_id=dataset_id, name="v", delta={}
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vid = v.id

        body = {
            "delta": {
                "instructions_delta": [
                    {
                        "op": "add",
                        "field": "__class__",
                        "type_str": "str",
                        "default": "",
                    }
                ]
            }
        }
        resp = client.put(f"/api/evals/{dataset_id}/variants/{vid}", json=body)
        assert resp.status_code == 422

    def test_update_variant_not_found(self, seeded_dataset):
        client, _, dataset_id = seeded_dataset
        resp = client.put(
            f"/api/evals/{dataset_id}/variants/9999", json={"name": "x"}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /evals/{dataset_id}/variants/{variant_id}
# ---------------------------------------------------------------------------


class TestDeleteVariant:
    def test_delete_variant_returns_204(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        with Session(engine) as session:
            v = EvaluationVariant(dataset_id=dataset_id, name="v", delta={})
            session.add(v)
            session.commit()
            session.refresh(v)
            vid = v.id

        resp = client.delete(f"/api/evals/{dataset_id}/variants/{vid}")
        assert resp.status_code == 204

        # GET should now return 404
        resp2 = client.get(f"/api/evals/{dataset_id}/variants/{vid}")
        assert resp2.status_code == 404

    def test_delete_variant_not_found(self, seeded_dataset):
        client, _, dataset_id = seeded_dataset
        resp = client.delete(f"/api/evals/{dataset_id}/variants/9999")
        assert resp.status_code == 404

    def test_delete_variant_nulls_run_fk_preserves_snapshot(
        self, seeded_dataset
    ):
        """Deleting a variant nulls ``EvaluationRun.variant_id`` references
        but preserves ``delta_snapshot`` for run reproducibility."""
        client, engine, dataset_id = seeded_dataset

        # Create variant + run referencing it with a delta_snapshot.
        snapshot = {
            "model": "claude-3-opus",
            "instructions_delta": [
                {
                    "op": "add",
                    "field": "new_field",
                    "type_str": "str",
                    "default": "hello",
                }
            ],
        }
        with Session(engine) as session:
            v = EvaluationVariant(
                dataset_id=dataset_id, name="v", delta=snapshot
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vid = v.id

            run = EvaluationRun(
                dataset_id=dataset_id,
                status="completed",
                total_cases=1,
                passed=1,
                failed=0,
                errored=0,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                variant_id=vid,
                delta_snapshot=snapshot,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

        resp = client.delete(f"/api/evals/{dataset_id}/variants/{vid}")
        assert resp.status_code == 204

        # Run still exists with variant_id nulled; delta_snapshot intact.
        with Session(engine) as session:
            from sqlmodel import select

            persisted = session.exec(
                select(EvaluationRun).where(EvaluationRun.id == run_id)
            ).first()
            assert persisted is not None
            assert persisted.variant_id is None
            assert persisted.delta_snapshot == snapshot


# ---------------------------------------------------------------------------
# Cascade delete: variants removed when dataset deleted
# ---------------------------------------------------------------------------


class TestDeleteDatasetCascade:
    def test_deleting_dataset_removes_its_variants(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        with Session(engine) as session:
            v1 = EvaluationVariant(dataset_id=dataset_id, name="v1", delta={})
            v2 = EvaluationVariant(dataset_id=dataset_id, name="v2", delta={})
            session.add(v1)
            session.add(v2)
            session.commit()

        resp = client.delete(f"/api/evals/{dataset_id}")
        assert resp.status_code == 204

        with Session(engine) as session:
            from sqlmodel import select

            remaining = session.exec(
                select(EvaluationVariant).where(
                    EvaluationVariant.dataset_id == dataset_id
                )
            ).all()
            assert remaining == []

    def test_delete_dataset_does_not_remove_other_dataset_variants(
        self, seeded_dataset
    ):
        client, engine, dataset_id = seeded_dataset
        with Session(engine) as session:
            ds2 = EvaluationDataset(
                name="ds_other", target_type="step", target_name="x"
            )
            session.add(ds2)
            session.commit()
            session.refresh(ds2)
            other_id = ds2.id
            session.add(
                EvaluationVariant(dataset_id=other_id, name="keep", delta={})
            )
            session.add(
                EvaluationVariant(
                    dataset_id=dataset_id, name="remove", delta={}
                )
            )
            session.commit()

        resp = client.delete(f"/api/evals/{dataset_id}")
        assert resp.status_code == 204

        with Session(engine) as session:
            from sqlmodel import select

            surviving = session.exec(
                select(EvaluationVariant).where(
                    EvaluationVariant.dataset_id == other_id
                )
            ).all()
            assert len(surviving) == 1
            assert surviving[0].name == "keep"


# ---------------------------------------------------------------------------
# Run trigger with variant_id
# ---------------------------------------------------------------------------


class TestTriggerRunWithVariant:
    def test_trigger_with_valid_variant_id(self, seeded_dataset, monkeypatch):
        client, engine, dataset_id = seeded_dataset
        # create variant on dataset
        with Session(engine) as session:
            v = EvaluationVariant(
                dataset_id=dataset_id, name="v", delta={"model": "override"}
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            variant_id = v.id

        # stub EvalRunner.run_dataset so we assert kwargs flow through
        captured: dict = {}

        def _fake_run_dataset(self, dataset_id, model=None, variant_id=None):
            captured["dataset_id"] = dataset_id
            captured["model"] = model
            captured["variant_id"] = variant_id
            return 1

        from llm_pipeline.evals.runner import EvalRunner

        monkeypatch.setattr(EvalRunner, "run_dataset", _fake_run_dataset)

        resp = client.post(
            f"/api/evals/{dataset_id}/runs",
            json={"variant_id": variant_id},
        )
        assert resp.status_code == 202
        # background task executes synchronously for TestClient on context exit;
        # give it a chance to run by issuing a follow-up call.
        # TestClient processes background tasks after the response is sent.
        assert captured.get("variant_id") == variant_id
        assert captured.get("dataset_id") == dataset_id

    def test_trigger_without_variant_id_still_works(
        self, seeded_dataset, monkeypatch
    ):
        client, _, dataset_id = seeded_dataset
        captured: dict = {}

        def _fake_run_dataset(self, dataset_id, model=None, variant_id=None):
            captured["variant_id"] = variant_id
            return 1

        from llm_pipeline.evals.runner import EvalRunner

        monkeypatch.setattr(EvalRunner, "run_dataset", _fake_run_dataset)

        resp = client.post(f"/api/evals/{dataset_id}/runs", json={})
        assert resp.status_code == 202
        assert captured.get("variant_id") is None

    def test_trigger_with_mismatched_dataset_variant_returns_422(
        self, seeded_dataset
    ):
        client, engine, dataset_id = seeded_dataset
        # variant belongs to a DIFFERENT dataset
        with Session(engine) as session:
            ds2 = EvaluationDataset(
                name="other_ds", target_type="step", target_name="y"
            )
            session.add(ds2)
            session.commit()
            session.refresh(ds2)
            v = EvaluationVariant(dataset_id=ds2.id, name="v", delta={})
            session.add(v)
            session.commit()
            session.refresh(v)
            other_variant_id = v.id

        resp = client.post(
            f"/api/evals/{dataset_id}/runs",
            json={"variant_id": other_variant_id},
        )
        assert resp.status_code == 422
        assert "variant_id" in resp.json()["detail"]

    def test_trigger_with_nonexistent_variant_returns_422(
        self, seeded_dataset
    ):
        client, _, dataset_id = seeded_dataset
        resp = client.post(
            f"/api/evals/{dataset_id}/runs", json={"variant_id": 99999}
        )
        assert resp.status_code == 422

    def test_trigger_on_missing_dataset_returns_404(self, evals_app):
        client, _ = evals_app
        resp = client.post("/api/evals/9999/runs", json={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RunListItem / RunDetail expose variant_id + delta_snapshot
# ---------------------------------------------------------------------------


class TestRunExposesVariantFields:
    def test_list_runs_exposes_variant_fields(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        now = datetime.now(timezone.utc)
        snapshot = {"model": "m", "instructions_delta": []}
        with Session(engine) as session:
            variant = EvaluationVariant(
                dataset_id=dataset_id, name="v", delta=snapshot
            )
            session.add(variant)
            session.commit()
            session.refresh(variant)
            variant_id = variant.id

            run = EvaluationRun(
                dataset_id=dataset_id,
                status="completed",
                total_cases=1,
                passed=1,
                failed=0,
                errored=0,
                started_at=now,
                completed_at=now,
                variant_id=variant_id,
                delta_snapshot=snapshot,
            )
            session.add(run)
            session.commit()
            session.refresh(run)

        resp = client.get(f"/api/evals/{dataset_id}/runs")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["variant_id"] == variant_id
        assert item["delta_snapshot"] == snapshot

    def test_list_runs_baseline_has_null_variant_fields(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            run = EvaluationRun(
                dataset_id=dataset_id,
                status="completed",
                total_cases=0,
                started_at=now,
                completed_at=now,
            )
            session.add(run)
            session.commit()

        resp = client.get(f"/api/evals/{dataset_id}/runs")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["variant_id"] is None
        assert item["delta_snapshot"] is None

    def test_get_run_detail_exposes_variant_fields(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        now = datetime.now(timezone.utc)
        snapshot = {"model": "m2"}
        with Session(engine) as session:
            variant = EvaluationVariant(
                dataset_id=dataset_id, name="v", delta=snapshot
            )
            session.add(variant)
            session.commit()
            session.refresh(variant)
            variant_id = variant.id

            run = EvaluationRun(
                dataset_id=dataset_id,
                status="completed",
                total_cases=0,
                started_at=now,
                variant_id=variant_id,
                delta_snapshot=snapshot,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

        resp = client.get(f"/api/evals/{dataset_id}/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["variant_id"] == variant_id
        assert data["delta_snapshot"] == snapshot


# ---------------------------------------------------------------------------
# GET /evals/delta-type-whitelist
# ---------------------------------------------------------------------------


class TestDeltaTypeWhitelist:
    def test_returns_200_with_canonical_types(self, evals_app):
        """Endpoint returns the sorted type_str whitelist so the frontend
        editor can source its type dropdown from a single backend truth."""
        client, _ = evals_app
        resp = client.get("/api/evals/delta-type-whitelist")
        assert resp.status_code == 200
        data = resp.json()
        assert "types" in data
        types = data["types"]
        assert isinstance(types, list)
        # Must include the documented canonical values.
        for expected in ("str", "int", "Optional[str]"):
            assert expected in types, f"{expected!r} missing from whitelist"
        # Sorted for stable client-side rendering.
        assert types == sorted(types)


# ---------------------------------------------------------------------------
# GET /evals/{dataset_id}/prod-prompts
# ---------------------------------------------------------------------------


class TestProdPrompts:
    """Prod prompts endpoint: resolves (system, user) for a dataset's step.

    Each test builds a tiny pipeline (one strategy, one step) in-module,
    registers it on app.state.introspection_registry, seeds the Prompt table
    and exercises the resolver tiers end-to-end.
    """

    @pytest.fixture
    def prod_prompts_app(self):
        """Build app with a pipeline that declares tier-1/2 keys on a step."""
        from typing import ClassVar as _CV

        from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition

        class DeclaredInstructions(LLMResultMixin):
            x: int = 0

            example: _CV[dict] = {"x": 1, "notes": "ok"}

        @step_definition(
            instructions=DeclaredInstructions,
            default_system_key="declared.system",
            default_user_key="declared.user",
        )
        class DeclaredStep(LLMStep):
            def prepare_calls(self):
                return []

        app, engine = _make_evals_app()
        client = TestClient(app)

        # Register pipeline after app creation
        from llm_pipeline import (
            PipelineConfig,
            PipelineDatabaseRegistry,
            PipelineStrategies,
            PipelineStrategy,
        )

        class DeclaredTestStrategy(PipelineStrategy):
            def can_handle(self, context):
                return True

            def get_steps(self):
                return [DeclaredStep.create_definition()]

        class DeclaredTestRegistry(PipelineDatabaseRegistry, models=[]):
            pass

        class DeclaredTestStrategies(
            PipelineStrategies, strategies=[DeclaredTestStrategy]
        ):
            pass

        class DeclaredTestPipeline(
            PipelineConfig,
            registry=DeclaredTestRegistry,
            strategies=DeclaredTestStrategies,
        ):
            pass

        app.state.introspection_registry["p1"] = DeclaredTestPipeline

        # seed prompts for declared keys
        from llm_pipeline.db.prompt import Prompt as _P_model

        with Session(engine) as session:
            session.add(
                _P_model(
                    prompt_key="declared.system",
                    prompt_name="declared sys",
                    prompt_type="system",
                    content="SYS CONTENT",
                    version="1.2",
                )
            )
            session.add(
                _P_model(
                    prompt_key="declared.user",
                    prompt_name="declared usr",
                    prompt_type="user",
                    content="USR CONTENT",
                    version="1.2",
                )
            )
            session.commit()

        return client, engine, "declared"

    def test_happy_path_declared_keys(self, prod_prompts_app):
        client, engine, step_name = prod_prompts_app
        with Session(engine) as session:
            ds = EvaluationDataset(
                name="ds_declared",
                target_type="step",
                target_name=step_name,
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-prompts")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["system"]["prompt_key"] == "declared.system"
        assert data["system"]["content"] == "SYS CONTENT"
        assert data["system"]["version"] == "1.2"
        assert data["user"]["prompt_key"] == "declared.user"
        assert data["user"]["content"] == "USR CONTENT"

    def test_happy_path_auto_discovery(self, evals_app):
        """Step declares no keys, DB has step-level prompts → tier-3 hit."""
        from typing import ClassVar as _CV

        from llm_pipeline import (
            PipelineConfig,
            PipelineDatabaseRegistry,
            PipelineStrategies,
            PipelineStrategy,
        )
        from llm_pipeline.db.prompt import Prompt as _P_model
        from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition

        client, engine = evals_app

        class AutoDiscInstructions(LLMResultMixin):
            x: int = 0

            example: _CV[dict] = {"x": 1, "notes": "ok"}

        @step_definition(instructions=AutoDiscInstructions)
        class AutoDiscStep(LLMStep):
            def prepare_calls(self):
                return []

        class AutoDiscTestStrategy(PipelineStrategy):
            def can_handle(self, context):
                return True

            def get_steps(self):
                return [AutoDiscStep.create_definition()]

        class AutoTestRegistry(PipelineDatabaseRegistry, models=[]):
            pass

        class AutoTestStrategies(
            PipelineStrategies, strategies=[AutoDiscTestStrategy]
        ):
            pass

        class AutoTestPipeline(
            PipelineConfig,
            registry=AutoTestRegistry,
            strategies=AutoTestStrategies,
        ):
            pass

        client.app.state.introspection_registry["auto_pipeline"] = AutoTestPipeline

        with Session(engine) as session:
            session.add(
                _P_model(
                    prompt_key="auto_disc",
                    prompt_name="auto disc sys",
                    prompt_type="system",
                    content="AUTO SYS",
                    is_active=True,
                )
            )
            session.add(
                _P_model(
                    prompt_key="auto_disc",
                    prompt_name="auto disc usr",
                    prompt_type="user",
                    content="AUTO USR",
                    is_active=True,
                )
            )
            ds = EvaluationDataset(
                name="ds_auto",
                target_type="step",
                target_name="auto_disc",
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-prompts")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["system"]["prompt_key"] == "auto_disc"
        assert data["system"]["content"] == "AUTO SYS"
        assert data["user"]["prompt_key"] == "auto_disc"
        assert data["user"]["content"] == "AUTO USR"

    def test_only_system_declared_user_null_when_no_db_row(self, evals_app):
        """Step declares only system_key, DB has no user row → user=null."""
        from typing import ClassVar as _CV

        from llm_pipeline import (
            PipelineConfig,
            PipelineDatabaseRegistry,
            PipelineStrategies,
            PipelineStrategy,
        )
        from llm_pipeline.db.prompt import Prompt as _P_model
        from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition

        client, engine = evals_app

        class PartialInstructions(LLMResultMixin):
            x: int = 0

            example: _CV[dict] = {"x": 1, "notes": "ok"}

        @step_definition(
            instructions=PartialInstructions,
            default_system_key="partial.system",
        )
        class PartialStep(LLMStep):
            def prepare_calls(self):
                return []

        class PartialTestStrategy(PipelineStrategy):
            def can_handle(self, context):
                return True

            def get_steps(self):
                return [PartialStep.create_definition()]

        class PartialTestRegistry(PipelineDatabaseRegistry, models=[]):
            pass

        class PartialTestStrategies(
            PipelineStrategies, strategies=[PartialTestStrategy]
        ):
            pass

        class PartialTestPipeline(
            PipelineConfig,
            registry=PartialTestRegistry,
            strategies=PartialTestStrategies,
        ):
            pass

        client.app.state.introspection_registry["partial_pipeline"] = PartialTestPipeline

        with Session(engine) as session:
            session.add(
                _P_model(
                    prompt_key="partial.system",
                    prompt_name="sys",
                    prompt_type="system",
                    content="PARTIAL SYS",
                )
            )
            ds = EvaluationDataset(
                name="ds_partial",
                target_type="step",
                target_name="partial",
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-prompts")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["system"]["prompt_key"] == "partial.system"
        assert data["system"]["content"] == "PARTIAL SYS"
        assert data["user"] is None

    def test_dataset_not_found(self, evals_app):
        client, _ = evals_app
        resp = client.get("/api/evals/9999/prod-prompts")
        assert resp.status_code == 404

    def test_pipeline_target_returns_422(self, evals_app):
        client, engine = evals_app
        with Session(engine) as session:
            ds = EvaluationDataset(
                name="ds_pipe",
                target_type="pipeline",
                target_name="some_pipeline",
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-prompts")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "step-targets only" in detail

    def test_step_not_found_in_any_pipeline(self, evals_app):
        """Step target name that no registered pipeline defines → 404."""
        client, engine = evals_app
        with Session(engine) as session:
            ds = EvaluationDataset(
                name="ds_missing",
                target_type="step",
                target_name="nonexistent_step",
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-prompts")
        assert resp.status_code == 404
        assert "nonexistent_step" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /evals/{dataset_id}/prod-model
# ---------------------------------------------------------------------------


class TestProdModel:
    """Prod model endpoint: resolves step model across the three tiers.

    Same pipeline-registration pattern as TestProdPrompts.
    """

    def _register_pipeline(
        self,
        client,
        *,
        step_model: str | None,
        default_model: str | None,
        step_name: str = "prod_model_step",
        pipeline_key: str = "pm_pipeline",
    ):
        """Register a 1-strategy, 1-step pipeline with configurable tiers.

        Dynamically builds CamelCase step + instruction classes derived from
        ``step_name`` so ``step_definition``'s naming-convention assertion
        passes. Returns the snake_case step_name (matches sd.step_name).
        """
        from typing import ClassVar as _CV

        from llm_pipeline import (
            PipelineConfig,
            PipelineDatabaseRegistry,
            PipelineStrategies,
            PipelineStrategy,
        )
        from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition

        # CamelCase from snake_case: "foo_bar" -> "FooBar"
        prefix = "".join(p.capitalize() for p in step_name.split("_"))

        # Build instruction class via exec so the ClassVar annotation is
        # parsed by Python's annotation machinery (type() with a raw
        # __annotations__ dict doesn't trigger pydantic's ClassVar
        # special-casing correctly).
        ns: dict = {
            "LLMResultMixin": LLMResultMixin,
            "ClassVar": _CV,
        }
        exec(
            f"class {prefix}Instructions(LLMResultMixin):\n"
            f"    x: int = 0\n"
            f"    example: ClassVar[dict] = {{'x': 1, 'notes': 'ok'}}\n",
            ns,
        )
        InstrCls = ns[f"{prefix}Instructions"]

        # Build step class with expected name "{Prefix}Step"
        StepCls = type(
            f"{prefix}Step",
            (LLMStep,),
            {
                "prepare_calls": lambda self: [],
                "__module__": __name__,
            },
        )

        decorator_kwargs: dict = {"instructions": InstrCls}
        if step_model is not None:
            decorator_kwargs["model"] = step_model

        StepCls = step_definition(**decorator_kwargs)(StepCls)

        class _Strategy(PipelineStrategy):
            def can_handle(self, context):
                return True

            def get_steps(self):
                return [StepCls.create_definition()]

        class _Registry(PipelineDatabaseRegistry, models=[]):
            pass

        class _Strategies(PipelineStrategies, strategies=[_Strategy]):
            pass

        class _Pipeline(
            PipelineConfig,
            registry=_Registry,
            strategies=_Strategies,
        ):
            _default_model = default_model

        client.app.state.introspection_registry[pipeline_key] = _Pipeline
        return step_name

    def test_step_definition_tier(self, evals_app):
        """Step decorator declares model, no DB row, no pipeline default →
        source == 'step_definition'."""
        client, engine = evals_app
        step_name = self._register_pipeline(
            client, step_model="gpt-step-def", default_model=None,
            step_name="sd_step", pipeline_key="sd_pipeline",
        )

        with Session(engine) as session:
            ds = EvaluationDataset(
                name="ds_sd",
                target_type="step",
                target_name=step_name,
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-model")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] == "gpt-step-def"
        assert data["source"] == "step_definition"

    def test_db_override_tier(self, evals_app):
        """StepModelConfig row beats step_def.model."""
        from llm_pipeline.db.step_config import StepModelConfig

        client, engine = evals_app
        step_name = self._register_pipeline(
            client, step_model="gpt-step-def", default_model="pipe-default",
            step_name="db_step", pipeline_key="db_pipeline",
        )

        with Session(engine) as session:
            session.add(
                StepModelConfig(
                    pipeline_name="db_pipeline",
                    step_name=step_name,
                    model="gpt-db-override",
                )
            )
            ds = EvaluationDataset(
                name="ds_db",
                target_type="step",
                target_name=step_name,
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-model")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] == "gpt-db-override"
        assert data["source"] == "db"

    def test_pipeline_default_tier(self, evals_app):
        """Only pipeline _default_model is set → source 'pipeline_default'."""
        client, engine = evals_app
        step_name = self._register_pipeline(
            client, step_model=None, default_model="pipe-default",
            step_name="pd_step", pipeline_key="pd_pipeline",
        )

        with Session(engine) as session:
            ds = EvaluationDataset(
                name="ds_pd",
                target_type="step",
                target_name=step_name,
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-model")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] == "pipe-default"
        assert data["source"] == "pipeline_default"

    def test_all_tiers_empty(self, evals_app):
        """Nothing set anywhere → model null, source 'none'."""
        client, engine = evals_app
        step_name = self._register_pipeline(
            client, step_model=None, default_model=None,
            step_name="empty_step", pipeline_key="empty_pipeline",
        )

        with Session(engine) as session:
            ds = EvaluationDataset(
                name="ds_empty",
                target_type="step",
                target_name=step_name,
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-model")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] is None
        assert data["source"] == "none"

    def test_dataset_not_found(self, evals_app):
        client, _ = evals_app
        resp = client.get("/api/evals/9999/prod-model")
        assert resp.status_code == 404

    def test_pipeline_target_returns_422(self, evals_app):
        client, engine = evals_app
        with Session(engine) as session:
            ds = EvaluationDataset(
                name="ds_pipe_m",
                target_type="pipeline",
                target_name="some_pipeline",
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-model")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "step-targets only" in detail

    def test_step_not_found_in_any_pipeline(self, evals_app):
        """Step target name that no registered pipeline defines → 404."""
        client, engine = evals_app
        with Session(engine) as session:
            ds = EvaluationDataset(
                name="ds_missing_m",
                target_type="step",
                target_name="nonexistent_step_m",
            )
            session.add(ds)
            session.commit()
            session.refresh(ds)
            ds_id = ds.id

        resp = client.get(f"/api/evals/{ds_id}/prod-model")
        assert resp.status_code == 404
        assert "nonexistent_step_m" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test #12: Run detail endpoint tolerates null snapshot columns
# ---------------------------------------------------------------------------


class TestRunDetailToleratesNullSnapshots:
    """Legacy compat: runs created before snapshot columns exist have NULLs."""

    def test_run_detail_null_snapshots_returns_200(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            run = EvaluationRun(
                dataset_id=dataset_id,
                status="completed",
                total_cases=1,
                passed=1,
                failed=0,
                errored=0,
                started_at=now,
                completed_at=now,
                # All snapshot cols left as None (legacy row)
                case_versions=None,
                prompt_versions=None,
                model_snapshot=None,
                instructions_schema_snapshot=None,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

        resp = client.get(f"/api/evals/{dataset_id}/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_versions"] is None
        assert data["prompt_versions"] is None
        assert data["model_snapshot"] is None
        assert data["instructions_schema_snapshot"] is None

    def test_list_runs_null_snapshots_returns_200(self, seeded_dataset):
        client, engine, dataset_id = seeded_dataset
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            run = EvaluationRun(
                dataset_id=dataset_id,
                status="completed",
                total_cases=0,
                started_at=now,
            )
            session.add(run)
            session.commit()

        resp = client.get(f"/api/evals/{dataset_id}/runs")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
