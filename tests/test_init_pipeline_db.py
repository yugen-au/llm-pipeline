"""Integration tests for init_pipeline_db() - pipeline_events table creation."""
import pytest
from sqlalchemy import create_engine, inspect
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.events.models import PipelineEventRecord


class TestInitPipelineDbPipelineEvents:
    """Verify init_pipeline_db() creates the pipeline_events table correctly."""

    def test_table_creation(self):
        """init_pipeline_db() with in-memory engine creates pipeline_events table."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            assert "pipeline_events" in tables
        finally:
            engine.dispose()

    def test_index_creation(self):
        """pipeline_events table has composite index ix_pipeline_events_run_event."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            indexes = inspector.get_indexes("pipeline_events")
            index_names = {idx["name"] for idx in indexes}
            assert "ix_pipeline_events_run_event" in index_names
        finally:
            engine.dispose()

    def test_round_trip_insert(self):
        """PipelineEventRecord row inserted via Session is queryable with correct fields."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            event_data = {
                "run_id": "abc-123",
                "event_type": "pipeline_started",
                "pipeline_name": "test_pipeline",
                "extra": "value",
            }
            record = PipelineEventRecord(
                run_id="abc-123",
                event_type="pipeline_started",
                pipeline_name="test_pipeline",
                event_data=event_data,
            )

            with Session(engine) as session:
                session.add(record)
                session.commit()

            with Session(engine) as session:
                statement = select(PipelineEventRecord).where(
                    PipelineEventRecord.run_id == "abc-123"
                )
                retrieved = session.exec(statement).one()

            assert retrieved.run_id == "abc-123"
            assert retrieved.event_type == "pipeline_started"
            assert retrieved.pipeline_name == "test_pipeline"
            assert retrieved.event_data["extra"] == "value"
        finally:
            engine.dispose()
