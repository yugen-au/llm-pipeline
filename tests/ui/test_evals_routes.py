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
