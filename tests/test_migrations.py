"""Tests for migration functions in llm_pipeline.db — partial unique indexes and dedupe.

Phase 3 of the evals migration retires the entire ``eval_*`` SQLModel
schema (Phoenix is the source of truth now). The legacy
``eval_cases`` dedupe tests below are skipped — the migration helper
``_migrate_partial_unique_indexes`` survives as an idempotent no-op
on fresh DBs but no longer has rows to dedupe.
"""
import pytest
from datetime import datetime, timezone

from sqlalchemy import text, inspect
from sqlmodel import SQLModel, create_engine

from llm_pipeline.db import (
    init_pipeline_db,
    _migrate_partial_unique_indexes,
    _migrate_add_columns,
)

pytestmark = pytest.mark.skip(
    reason=(
        "Phase-3 evals migration: eval_* tables retired; legacy "
        "dedupe tests no longer applicable."
    ),
)


def _fresh_engine():
    """Create an in-memory SQLite engine with full schema."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    return engine


def _get_index_names(engine, table_name: str) -> set[str]:
    """Return all index names for a table."""
    insp = inspect(engine)
    try:
        indexes = insp.get_indexes(table_name)
    except Exception:
        return set()
    return {idx["name"] for idx in indexes}


class TestMigrationDedupesEvalCases:
    """#19: seed pre-migration DB with duplicate (dataset_id, name) rows;
    run migration; assert exactly one row with is_latest=True per group."""

    def test_dedupe_keeps_newest_by_created_at(self):
        engine = _fresh_engine()
        # Init full schema (creates tables + columns + indexes)
        init_pipeline_db(engine)

        # Insert a dataset first
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO eval_datasets (id, name, target_type, target_name, created_at, updated_at) "
                "VALUES (1, 'ds1', 'step', 'step1', '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            ))
            conn.commit()

        # Insert duplicate eval_cases with same (dataset_id, name)
        # but different created_at — older row should get is_latest=0
        with engine.connect() as conn:
            # First: clear any existing partial unique index to allow duplicates
            conn.execute(text("DROP INDEX IF EXISTS uq_eval_cases_active_latest"))
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO eval_cases (id, dataset_id, name, inputs, version, is_active, is_latest, created_at, updated_at) "
                "VALUES (10, 1, 'case_a', '{}', '1.0', 1, 1, '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            ))
            conn.execute(text(
                "INSERT INTO eval_cases (id, dataset_id, name, inputs, version, is_active, is_latest, created_at, updated_at) "
                "VALUES (20, 1, 'case_a', '{}', '1.1', 1, 1, '2024-01-02 00:00:00', '2024-01-02 00:00:00')"
            ))
            conn.commit()

        # Run the migration function
        _migrate_partial_unique_indexes(engine)

        # Assert: newest (id=20) keeps is_latest=1, older (id=10) gets is_latest=0
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, is_latest FROM eval_cases WHERE dataset_id = 1 AND name = 'case_a' ORDER BY id"
            )).fetchall()

        assert len(rows) == 2
        assert rows[0] == (10, 0)  # older -> is_latest=0
        assert rows[1] == (20, 1)  # newer -> is_latest=1

    def test_dedupe_tiebreak_by_id_desc(self):
        """When created_at is identical, highest id wins."""
        engine = _fresh_engine()
        init_pipeline_db(engine)

        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO eval_datasets (id, name, target_type, target_name, created_at, updated_at) "
                "VALUES (1, 'ds1', 'step', 'step1', '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            ))
            conn.execute(text("DROP INDEX IF EXISTS uq_eval_cases_active_latest"))
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO eval_cases (id, dataset_id, name, inputs, version, is_active, is_latest, created_at, updated_at) "
                "VALUES (5, 1, 'tied', '{}', '1.0', 1, 1, '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            ))
            conn.execute(text(
                "INSERT INTO eval_cases (id, dataset_id, name, inputs, version, is_active, is_latest, created_at, updated_at) "
                "VALUES (9, 1, 'tied', '{}', '1.0', 1, 1, '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            ))
            conn.commit()

        _migrate_partial_unique_indexes(engine)

        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, is_latest FROM eval_cases WHERE dataset_id = 1 AND name = 'tied' ORDER BY id"
            )).fetchall()

        assert rows[0] == (5, 0)  # lower id -> is_latest=0
        assert rows[1] == (9, 1)  # higher id -> is_latest=1


class TestPromptsTableDropped:
    """Phase E: the local ``prompts`` table is removed on init.

    Simulates an older DB with a ``prompts`` table (and a couple of
    legacy indexes), then asserts that ``init_pipeline_db`` drops them.
    """

    def test_prompts_table_dropped_on_init(self):
        engine = _fresh_engine()

        # Manually create the legacy prompts table + indexes before init.
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE prompts ("
                "id INTEGER PRIMARY KEY, "
                "prompt_key VARCHAR(100), "
                "prompt_type VARCHAR(50), "
                "is_active INTEGER, "
                "is_latest INTEGER)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_prompts_active ON prompts (is_active)"
            ))
            conn.commit()

        init_pipeline_db(engine)

        # Verify the table itself was dropped.
        with engine.connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ))
            }
        assert "prompts" not in tables


class TestMigrationIsIdempotent:
    """#21: run twice on the same DB, no errors, schema identical."""

    def test_double_run_no_errors(self):
        engine = _fresh_engine()
        init_pipeline_db(engine)

        # Insert test data
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO eval_datasets (id, name, target_type, target_name, created_at, updated_at) "
                "VALUES (1, 'ds1', 'step', 'step1', '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            ))
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("DROP INDEX IF EXISTS uq_eval_cases_active_latest"))
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO eval_cases (id, dataset_id, name, inputs, version, is_active, is_latest, created_at, updated_at) "
                "VALUES (1, 1, 'x', '{}', '1.0', 1, 1, '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            ))
            conn.commit()

        # First run
        _migrate_partial_unique_indexes(engine)
        indexes_after_first = _get_index_names(engine, "prompts")
        eval_indexes_first = _get_index_names(engine, "eval_cases")

        # Second run — should not raise
        _migrate_partial_unique_indexes(engine)
        indexes_after_second = _get_index_names(engine, "prompts")
        eval_indexes_second = _get_index_names(engine, "eval_cases")

        # Schema identical
        assert indexes_after_first == indexes_after_second
        assert eval_indexes_first == eval_indexes_second

        # Data unchanged
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, is_latest FROM eval_cases ORDER BY id"
            )).fetchall()
        assert rows == [(1, 1)]

    def test_full_init_pipeline_db_idempotent(self):
        """Calling init_pipeline_db twice produces no errors."""
        engine = _fresh_engine()
        init_pipeline_db(engine)
        # Second call — must not raise
        init_pipeline_db(engine)
