"""Tests for LLM_PIPELINE_DB_SCHEMA env var support."""
import pytest
from unittest.mock import patch
from sqlalchemy import create_engine, inspect, text
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db, _get_schema
from llm_pipeline.db import _schema_registered_engines, _wal_registered_engines
from llm_pipeline.state import PipelineRun


class TestGetSchema:
    def test_returns_none_when_unset(self):
        with patch.dict("os.environ", {}, clear=False):
            # Remove if present
            import os
            os.environ.pop("LLM_PIPELINE_DB_SCHEMA", None)
            assert _get_schema() is None

    def test_returns_none_for_empty_string(self):
        with patch.dict("os.environ", {"LLM_PIPELINE_DB_SCHEMA": ""}):
            assert _get_schema() is None

    def test_returns_none_for_whitespace(self):
        with patch.dict("os.environ", {"LLM_PIPELINE_DB_SCHEMA": "  "}):
            assert _get_schema() is None

    def test_returns_schema_when_set(self):
        with patch.dict("os.environ", {"LLM_PIPELINE_DB_SCHEMA": "llm_pipeline"}):
            assert _get_schema() == "llm_pipeline"

    def test_strips_whitespace(self):
        with patch.dict("os.environ", {"LLM_PIPELINE_DB_SCHEMA": " myschema "}):
            assert _get_schema() == "myschema"


class TestSqliteUnaffectedBySchema:
    """SQLite should work unchanged regardless of LLM_PIPELINE_DB_SCHEMA."""

    def test_sqlite_creates_tables_with_schema_env_set(self):
        with patch.dict("os.environ", {"LLM_PIPELINE_DB_SCHEMA": "llm_pipeline"}):
            engine = create_engine("sqlite://")
            try:
                init_pipeline_db(engine=engine)
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                assert "pipeline_step_states" in tables
                assert "pipeline_runs" in tables
            finally:
                _schema_registered_engines.discard(id(engine))
                _wal_registered_engines.discard(id(engine))
                engine.dispose()

    def test_sqlite_round_trip_with_schema_env_set(self):
        with patch.dict("os.environ", {"LLM_PIPELINE_DB_SCHEMA": "llm_pipeline"}):
            engine = create_engine("sqlite://")
            try:
                init_pipeline_db(engine=engine)
                record = PipelineRun(
                    run_id="schema-test",
                    pipeline_name="test",
                    status="running",
                )
                with Session(engine) as session:
                    session.add(record)
                    session.commit()

                with Session(engine) as session:
                    stmt = select(PipelineRun).where(
                        PipelineRun.run_id == "schema-test"
                    )
                    retrieved = session.exec(stmt).one()
                assert retrieved.pipeline_name == "test"
            finally:
                _schema_registered_engines.discard(id(engine))
                _wal_registered_engines.discard(id(engine))
                engine.dispose()


class TestSchemaSearchPathRegistration:
    """Verify search_path listener is registered for non-SQLite engines."""

    def test_no_schema_listener_on_sqlite(self):
        engine = create_engine("sqlite://")
        engine_id = id(engine)
        try:
            with patch.dict("os.environ", {"LLM_PIPELINE_DB_SCHEMA": "custom"}):
                init_pipeline_db(engine=engine)
            # SQLite should not be in _schema_registered_engines
            assert engine_id not in _schema_registered_engines
        finally:
            _wal_registered_engines.discard(engine_id)
            engine.dispose()
