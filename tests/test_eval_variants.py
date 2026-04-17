"""Tests for evals v2 variants.

Suites:
- Step 1 (TestFreshDbCreation / TestMigrationOnExistingDb): schema + migrations.
- Step 2 (TestApplyInstructionDelta): delta application + ACE hardening.
"""
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine, inspect, text
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals import apply_instruction_delta
from llm_pipeline.evals.delta import (
    _MAX_DELTA_ITEMS,
    _MAX_STRING_LEN,
    _resolve_type,
    _validate_default,
)
from llm_pipeline.evals.models import (
    EvaluationDataset,
    EvaluationVariant,
    EvaluationRun,
)
from llm_pipeline.step import LLMResultMixin


class TestFreshDbCreation:
    """init_pipeline_db() creates eval_variants and updated eval_runs schema."""

    def test_eval_variants_table_created(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            assert "eval_variants" in inspector.get_table_names()
        finally:
            engine.dispose()

    def test_eval_variants_columns(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            cols = {c["name"] for c in inspector.get_columns("eval_variants")}
            expected = {
                "id",
                "dataset_id",
                "name",
                "description",
                "delta",
                "created_at",
                "updated_at",
            }
            assert expected.issubset(cols), f"missing: {expected - cols}"
        finally:
            engine.dispose()

    def test_eval_variants_fk_to_dataset(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            fks = inspector.get_foreign_keys("eval_variants")
            # expect one FK: dataset_id -> eval_datasets.id
            assert any(
                fk["referred_table"] == "eval_datasets"
                and "dataset_id" in fk["constrained_columns"]
                and "id" in fk["referred_columns"]
                for fk in fks
            ), f"dataset_id FK not found in {fks}"
        finally:
            engine.dispose()

    def test_eval_variants_dataset_index(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            indexes = inspector.get_indexes("eval_variants")
            names = {idx["name"] for idx in indexes}
            assert "ix_eval_variants_dataset" in names
        finally:
            engine.dispose()

    def test_eval_runs_has_variant_columns(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            cols = {c["name"] for c in inspector.get_columns("eval_runs")}
            assert "variant_id" in cols
            assert "delta_snapshot" in cols
        finally:
            engine.dispose()

    def test_variant_round_trip_insert(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            with Session(engine) as session:
                ds = EvaluationDataset(
                    name="test_ds",
                    target_type="step",
                    target_name="my_step",
                )
                session.add(ds)
                session.commit()
                session.refresh(ds)
                ds_id = ds.id

                variant = EvaluationVariant(
                    dataset_id=ds_id,
                    name="variant-a",
                    description="first variant",
                    delta={
                        "model": "claude-3.5-sonnet",
                        "system_prompt": "override sys",
                        "user_prompt": "override user",
                        "instructions_delta": [
                            {"op": "add", "field": "foo", "type_str": "str"}
                        ],
                    },
                )
                session.add(variant)
                session.commit()
                session.refresh(variant)

            with Session(engine) as session:
                retrieved = session.exec(
                    select(EvaluationVariant).where(
                        EvaluationVariant.name == "variant-a"
                    )
                ).one()
                assert retrieved.dataset_id == ds_id
                assert retrieved.delta["model"] == "claude-3.5-sonnet"
                assert retrieved.delta["instructions_delta"][0]["field"] == "foo"
        finally:
            engine.dispose()

    def test_run_delta_snapshot_round_trip(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            with Session(engine) as session:
                ds = EvaluationDataset(
                    name="ds_for_run",
                    target_type="step",
                    target_name="my_step",
                )
                session.add(ds)
                session.commit()
                session.refresh(ds)
                ds_id = ds.id

                variant = EvaluationVariant(
                    dataset_id=ds_id,
                    name="v1",
                    delta={"model": "m", "system_prompt": None,
                           "user_prompt": None, "instructions_delta": []},
                )
                session.add(variant)
                session.commit()
                session.refresh(variant)
                variant_id = variant.id

                run = EvaluationRun(
                    dataset_id=ds_id,
                    variant_id=variant_id,
                    delta_snapshot={"model": "m", "system_prompt": None,
                                    "user_prompt": None,
                                    "instructions_delta": []},
                )
                session.add(run)
                session.commit()
                session.refresh(run)
                run_id = run.id

            with Session(engine) as session:
                retrieved = session.exec(
                    select(EvaluationRun).where(EvaluationRun.id == run_id)
                ).one()
                assert retrieved.variant_id == variant_id
                assert retrieved.delta_snapshot["model"] == "m"
        finally:
            engine.dispose()


class TestMigrationOnExistingDb:
    """_migrate_add_columns adds variant_id + delta_snapshot to legacy eval_runs."""

    def test_migration_adds_columns_to_existing_eval_runs(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            # Create a pre-migration eval_runs table without the new columns.
            with engine.connect() as conn:
                conn.execute(text(
                    "CREATE TABLE eval_datasets ("
                    "id INTEGER PRIMARY KEY, name VARCHAR(200), "
                    "target_type VARCHAR(20), target_name VARCHAR(200), "
                    "description TEXT, created_at DATETIME, updated_at DATETIME)"
                ))
                conn.execute(text(
                    "CREATE TABLE eval_runs ("
                    "id INTEGER PRIMARY KEY, dataset_id INTEGER, "
                    "status VARCHAR(20), total_cases INTEGER, passed INTEGER, "
                    "failed INTEGER, errored INTEGER, report_data TEXT, "
                    "error_message TEXT, started_at DATETIME, "
                    "completed_at DATETIME)"
                ))
                conn.commit()

            # Sanity: new columns not present yet.
            inspector = inspect(engine)
            pre_cols = {c["name"] for c in inspector.get_columns("eval_runs")}
            assert "variant_id" not in pre_cols
            assert "delta_snapshot" not in pre_cols
        finally:
            engine.dispose()

        # Now run init_pipeline_db against the same file — should migrate.
        engine2 = create_engine(f"sqlite:///{db_path}")
        try:
            init_pipeline_db(engine=engine2)
            inspector = inspect(engine2)
            post_cols = {c["name"] for c in inspector.get_columns("eval_runs")}
            assert "variant_id" in post_cols
            assert "delta_snapshot" in post_cols
            # eval_variants table now created by create_all.
            assert "eval_variants" in inspector.get_table_names()
        finally:
            engine2.dispose()

    def test_migration_idempotent(self, tmp_path):
        db_path = tmp_path / "idem.db"
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            init_pipeline_db(engine=engine)
        finally:
            engine.dispose()

        engine2 = create_engine(f"sqlite:///{db_path}")
        try:
            # Second run must not raise.
            init_pipeline_db(engine=engine2)
            inspector = inspect(engine2)
            cols = {c["name"] for c in inspector.get_columns("eval_runs")}
            assert "variant_id" in cols
            assert "delta_snapshot" in cols
        finally:
            engine2.dispose()
