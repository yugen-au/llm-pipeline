"""Tests for evals YAML sync: insert-if-missing, no duplicates, writeback."""
import yaml
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals.models import EvaluationDataset, EvaluationCase
from llm_pipeline.evals.yaml_sync import sync_evals_yaml_to_db, write_dataset_to_yaml


@pytest.fixture()
def engine():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(e)
    return e


@pytest.fixture()
def sample_yaml(tmp_path):
    data = {
        "name": "test_dataset",
        "target_type": "step",
        "target_name": "sentiment_analysis",
        "description": "Test dataset",
        "cases": [
            {
                "name": "case_one",
                "inputs": {"text": "I love it"},
                "expected_output": {"sentiment": "positive"},
                "metadata": {"difficulty": "easy"},
            },
            {
                "name": "case_two",
                "inputs": {"text": "I hate it"},
                "expected_output": {"sentiment": "negative"},
            },
        ],
    }
    yaml_file = tmp_path / "test_dataset.yaml"
    yaml_file.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    return tmp_path


class TestSyncEvalsYamlToDb:
    def test_insert_new_dataset_and_cases(self, engine, sample_yaml):
        sync_evals_yaml_to_db(engine, [sample_yaml])

        with Session(engine) as session:
            ds = session.exec(select(EvaluationDataset)).all()
            assert len(ds) == 1
            assert ds[0].name == "test_dataset"
            assert ds[0].target_type == "step"
            assert ds[0].target_name == "sentiment_analysis"

            cases = session.exec(select(EvaluationCase)).all()
            assert len(cases) == 2
            names = {c.name for c in cases}
            assert names == {"case_one", "case_two"}

    def test_no_duplicate_on_resync(self, engine, sample_yaml):
        sync_evals_yaml_to_db(engine, [sample_yaml])
        sync_evals_yaml_to_db(engine, [sample_yaml])

        with Session(engine) as session:
            ds = session.exec(select(EvaluationDataset)).all()
            assert len(ds) == 1

            cases = session.exec(select(EvaluationCase)).all()
            assert len(cases) == 2

    def test_empty_dir_no_error(self, engine, tmp_path):
        sync_evals_yaml_to_db(engine, [tmp_path])

        with Session(engine) as session:
            assert session.exec(select(EvaluationDataset)).all() == []

    def test_nonexistent_dir_no_error(self, engine, tmp_path):
        sync_evals_yaml_to_db(engine, [tmp_path / "nonexistent"])

        with Session(engine) as session:
            assert session.exec(select(EvaluationDataset)).all() == []

    def test_case_metadata_stored(self, engine, sample_yaml):
        sync_evals_yaml_to_db(engine, [sample_yaml])

        with Session(engine) as session:
            case = session.exec(
                select(EvaluationCase).where(EvaluationCase.name == "case_one")
            ).first()
            assert case.metadata_ == {"difficulty": "easy"}

            case2 = session.exec(
                select(EvaluationCase).where(EvaluationCase.name == "case_two")
            ).first()
            assert case2.metadata_ is None


class TestWriteDatasetToYaml:
    def test_writeback_produces_parseable_yaml(self, engine, sample_yaml):
        sync_evals_yaml_to_db(engine, [sample_yaml])

        with Session(engine) as session:
            ds = session.exec(select(EvaluationDataset)).first()
            ds_id = ds.id

        out_dir = sample_yaml / "output"
        write_dataset_to_yaml(engine, ds_id, out_dir)

        written = out_dir / "test_dataset.yaml"
        assert written.exists()

        data = yaml.safe_load(written.read_text(encoding="utf-8"))
        assert data["name"] == "test_dataset"
        assert data["target_type"] == "step"
        assert len(data["cases"]) == 2

    def test_writeback_roundtrip(self, engine, sample_yaml):
        """Writeback YAML can be re-synced without errors."""
        sync_evals_yaml_to_db(engine, [sample_yaml])

        with Session(engine) as session:
            ds = session.exec(select(EvaluationDataset)).first()
            ds_id = ds.id

        out_dir = sample_yaml / "roundtrip"
        write_dataset_to_yaml(engine, ds_id, out_dir)

        # Create fresh DB, sync from written YAML
        e2 = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_pipeline_db(e2)
        sync_evals_yaml_to_db(e2, [out_dir])

        with Session(e2) as session:
            ds2 = session.exec(select(EvaluationDataset)).first()
            assert ds2.name == "test_dataset"
            cases = session.exec(select(EvaluationCase)).all()
            assert len(cases) == 2

    def test_nonexistent_dataset_raises(self, engine):
        with pytest.raises(ValueError, match="not found"):
            write_dataset_to_yaml(engine, 9999, __import__("pathlib").Path("/tmp/x"))
