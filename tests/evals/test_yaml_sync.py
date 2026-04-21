"""Tests for eval dataset YAML sync with versioning."""
import logging
from pathlib import Path

import pytest
import yaml
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals.models import EvaluationCase, EvaluationDataset
from llm_pipeline.evals.yaml_sync import sync_evals_yaml_to_db, write_dataset_to_yaml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return init_pipeline_db(e)


def _write_yaml(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


DATASET_YAML_V1 = """\
name: ds_test
target_type: step
target_name: my_step
cases:
  - name: case_a
    version: "1.0"
    inputs:
      x: 1
    expected_output:
      y: 2
  - name: case_b
    version: "1.0"
    inputs:
      x: 10
"""

DATASET_YAML_V1_5 = """\
name: ds_test
target_type: step
target_name: my_step
cases:
  - name: case_a
    version: "1.5"
    inputs:
      x: 99
    expected_output:
      y: 100
  - name: case_b
    version: "1.0"
    inputs:
      x: 10
"""


# ---------------------------------------------------------------------------
# Test #15: YAML newer inserts case version
# ---------------------------------------------------------------------------


class TestDatasetYamlNewerInsertsCaseVersion:
    def test_yaml_newer_inserts_and_flips(self, tmp_path, engine):
        """YAML version > DB latest -> new case row, old flipped is_latest=False."""
        # Seed DB with v1.0
        _write_yaml(tmp_path, "ds_test.yaml", DATASET_YAML_V1)
        sync_evals_yaml_to_db(engine, [tmp_path])

        with Session(engine) as s:
            cases = s.exec(
                select(EvaluationCase).where(EvaluationCase.name == "case_a")
            ).all()
            assert len(cases) == 1
            assert cases[0].version == "1.0"
            assert cases[0].is_latest is True

        # Now sync with newer YAML (v1.5 for case_a)
        _write_yaml(tmp_path, "ds_test.yaml", DATASET_YAML_V1_5)
        sync_evals_yaml_to_db(engine, [tmp_path])

        with Session(engine) as s:
            cases = s.exec(
                select(EvaluationCase)
                .where(EvaluationCase.name == "case_a")
                .order_by(EvaluationCase.id)
            ).all()
            assert len(cases) == 2
            # Old row flipped
            assert cases[0].version == "1.0"
            assert cases[0].is_latest is False
            # New row is latest
            assert cases[1].version == "1.5"
            assert cases[1].is_latest is True
            assert cases[1].is_active is True
            assert cases[1].inputs == {"x": 99}


# ---------------------------------------------------------------------------
# Test #16: YAML older/equal logs WARNING and no-op
# ---------------------------------------------------------------------------


class TestDatasetYamlOlderOrEqualLogsWarning:
    def test_yaml_older_logs_warning_noop(self, tmp_path, engine, caplog):
        """YAML version <= DB latest -> DB unchanged, WARNING logged."""
        # Seed DB with v1.5
        _write_yaml(tmp_path, "ds_test.yaml", DATASET_YAML_V1_5)
        sync_evals_yaml_to_db(engine, [tmp_path])

        # Now sync with older YAML (v1.0)
        _write_yaml(tmp_path, "ds_test.yaml", DATASET_YAML_V1)
        with caplog.at_level(logging.WARNING, logger="llm_pipeline.evals.yaml_sync"):
            sync_evals_yaml_to_db(engine, [tmp_path])

        # DB should still have only the v1.5 row as latest
        with Session(engine) as s:
            latest = s.exec(
                select(EvaluationCase).where(
                    EvaluationCase.name == "case_a",
                    EvaluationCase.is_latest == True,  # noqa: E712
                )
            ).first()
            assert latest.version == "1.5"

        # WARNING was logged
        assert any("skipping" in r.message.lower() for r in caplog.records)

    def test_yaml_equal_version_logs_warning_noop(self, tmp_path, engine, caplog):
        """Same version -> no-op, WARNING logged."""
        _write_yaml(tmp_path, "ds_test.yaml", DATASET_YAML_V1)
        sync_evals_yaml_to_db(engine, [tmp_path])

        # Sync again with same version
        with caplog.at_level(logging.WARNING, logger="llm_pipeline.evals.yaml_sync"):
            sync_evals_yaml_to_db(engine, [tmp_path])

        with Session(engine) as s:
            cases = s.exec(
                select(EvaluationCase).where(EvaluationCase.name == "case_a")
            ).all()
            # Should still be just 1 row
            assert len(cases) == 1
            assert cases[0].version == "1.0"

        assert any("skipping" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Test #17: writeback fires on PUT case (via route)
# ---------------------------------------------------------------------------


class TestDatasetWritebackOnPutCase:
    def test_put_case_triggers_yaml_writeback(self, tmp_path, engine):
        """PUT /evals/.../cases/{id} -> YAML file reflects new case version."""
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from llm_pipeline.ui.routes.evals import router as evals_router

        app = FastAPI()
        app.state.engine = engine
        app.state.evals_dir = str(tmp_path)
        app.state.pipeline_registry = {}
        app.state.introspection_registry = {}
        app.include_router(evals_router, prefix="/api")

        # Seed dataset + case
        with Session(engine) as s:
            ds = EvaluationDataset(
                name="ds_wb", target_type="step", target_name="s1"
            )
            s.add(ds)
            s.commit()
            s.refresh(ds)
            ds_id = ds.id

        # Seed a case via the versioning path
        from llm_pipeline.db.versioning import save_new_version

        with Session(engine) as s:
            case = save_new_version(
                s, EvaluationCase,
                key_filters={"dataset_id": ds_id, "name": "c1"},
                new_fields={"inputs": {"a": 1}, "expected_output": None, "metadata_": None},
            )
            s.commit()
            s.refresh(case)
            case_id = case.id

        client = TestClient(app)
        resp = client.put(
            f"/api/evals/{ds_id}/cases/{case_id}",
            json={"inputs": {"a": 2}},
        )
        assert resp.status_code == 200, resp.text

        # YAML file should exist and reflect updated case
        yaml_path = tmp_path / "ds_wb.yaml"
        assert yaml_path.exists()
        with open(yaml_path) as f:
            doc = yaml.safe_load(f)
        assert doc["name"] == "ds_wb"
        case_entry = next(c for c in doc["cases"] if c["name"] == "c1")
        assert case_entry["inputs"] == {"a": 2}


# ---------------------------------------------------------------------------
# Test #18: writeback fires on DELETE case
# ---------------------------------------------------------------------------


class TestDatasetWritebackOnDeleteCase:
    def test_delete_case_triggers_yaml_writeback(self, tmp_path, engine):
        """DELETE -> YAML file excludes the soft-deleted case."""
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from llm_pipeline.ui.routes.evals import router as evals_router

        app = FastAPI()
        app.state.engine = engine
        app.state.evals_dir = str(tmp_path)
        app.state.pipeline_registry = {}
        app.state.introspection_registry = {}
        app.include_router(evals_router, prefix="/api")

        # Seed dataset + 2 cases
        with Session(engine) as s:
            ds = EvaluationDataset(
                name="ds_del", target_type="step", target_name="s1"
            )
            s.add(ds)
            s.commit()
            s.refresh(ds)
            ds_id = ds.id

        from llm_pipeline.db.versioning import save_new_version

        with Session(engine) as s:
            save_new_version(
                s, EvaluationCase,
                key_filters={"dataset_id": ds_id, "name": "keep"},
                new_fields={"inputs": {"k": 1}, "expected_output": None, "metadata_": None},
            )
            del_case = save_new_version(
                s, EvaluationCase,
                key_filters={"dataset_id": ds_id, "name": "remove"},
                new_fields={"inputs": {"r": 1}, "expected_output": None, "metadata_": None},
            )
            s.commit()
            s.refresh(del_case)
            del_case_id = del_case.id

        client = TestClient(app)
        resp = client.delete(f"/api/evals/{ds_id}/cases/{del_case_id}")
        assert resp.status_code == 204

        # YAML should only have "keep"
        yaml_path = tmp_path / "ds_del.yaml"
        assert yaml_path.exists()
        with open(yaml_path) as f:
            doc = yaml.safe_load(f)
        case_names = [c["name"] for c in doc["cases"]]
        assert "keep" in case_names
        assert "remove" not in case_names
