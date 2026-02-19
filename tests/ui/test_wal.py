"""WAL mode verification tests for init_pipeline_db()."""
import pytest
from sqlmodel import create_engine, Session

from llm_pipeline.db import init_pipeline_db


class TestWALMode:
    def test_file_based_sqlite_sets_wal(self, tmp_path):
        db_file = str(tmp_path / "wal_test.db")
        engine = create_engine(f"sqlite:///{db_file}")
        init_pipeline_db(engine)

        with Session(engine) as session:
            result = session.exec(  # type: ignore[call-overload]
                __import__("sqlmodel").text("PRAGMA journal_mode")
            ).scalar()
        assert result == "wal"

    def test_memory_engine_does_not_raise(self):
        engine = create_engine("sqlite://")
        # WAL pragma on :memory: is silently ignored; must not raise
        try:
            init_pipeline_db(engine)
        except Exception as exc:
            pytest.fail(f"init_pipeline_db raised on :memory: engine: {exc}")

    def test_memory_engine_returns_engine(self):
        engine = create_engine("sqlite://")
        result = init_pipeline_db(engine)
        assert result is engine

    def test_file_engine_returns_engine(self, tmp_path):
        db_file = str(tmp_path / "ret_test.db")
        engine = create_engine(f"sqlite:///{db_file}")
        result = init_pipeline_db(engine)
        assert result is engine
