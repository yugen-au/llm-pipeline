"""Tests for pipeline event handler implementations.

Covers LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler,
and PipelineEventRecord model. Verifies Protocol conformance, thread safety,
DB persistence, and category-based log levels.
"""
import logging
import threading
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel, select

from llm_pipeline.events.emitter import PipelineEventEmitter
from llm_pipeline.events.handlers import (
    DEFAULT_LEVEL_MAP,
    InMemoryEventHandler,
    LoggingEventHandler,
    SQLiteEventHandler,
)
from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.events.types import (
    CATEGORY_CACHE,
    CATEGORY_CONSENSUS,
    CATEGORY_PIPELINE_LIFECYCLE,
    CacheHit,
    ConsensusReached,
    PipelineStarted,
)


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def sample_event() -> PipelineStarted:
    """Create a minimal PipelineStarted event for testing."""
    return PipelineStarted(run_id="test-run-1", pipeline_name="test_pipeline")


@pytest.fixture
def in_memory_handler() -> InMemoryEventHandler:
    """Fresh InMemoryEventHandler for each test."""
    return InMemoryEventHandler()


@pytest.fixture
def sqlite_handler():
    """SQLiteEventHandler with in-memory database."""
    engine = create_engine("sqlite:///:memory:")
    return SQLiteEventHandler(engine)


# -- LoggingEventHandler -------------------------------------------------------


class TestLoggingEventHandler:
    """LoggingEventHandler tests: category-based log levels, custom logger, extras."""

    def test_logging_handler_default_levels(self, sample_event, caplog):
        """Lifecycle/consensus events at INFO, details at DEBUG."""
        logger = logging.getLogger("test.default_levels")
        logger.setLevel(logging.DEBUG)
        handler = LoggingEventHandler(logger=logger)

        # INFO for CATEGORY_PIPELINE_LIFECYCLE
        with caplog.at_level(logging.DEBUG):
            handler.emit(sample_event)
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.INFO
        assert "pipeline_started" in caplog.records[0].message

        caplog.clear()

        # INFO for CATEGORY_CONSENSUS
        consensus_event = ConsensusReached(
            run_id="run-2",
            pipeline_name="test",
            step_name="step1",
            attempt=1,
            threshold=3,
        )
        with caplog.at_level(logging.DEBUG):
            handler.emit(consensus_event)
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.INFO

        caplog.clear()

        # DEBUG for CATEGORY_CACHE
        cache_event = CacheHit(
            run_id="run-3",
            pipeline_name="test",
            step_name="step1",
            input_hash="abc123",
            cached_at=datetime.now(),
        )
        with caplog.at_level(logging.DEBUG):
            handler.emit(cache_event)
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.DEBUG

    def test_logging_handler_custom_logger(self, sample_event, caplog):
        """Custom logger name appears in log records."""
        logger = logging.getLogger("custom.pipeline.logger")
        logger.setLevel(logging.INFO)
        handler = LoggingEventHandler(logger=logger)

        with caplog.at_level(logging.INFO):
            handler.emit(sample_event)
        assert caplog.records[0].name == "custom.pipeline.logger"

    def test_logging_handler_custom_level_map(self, sample_event, caplog):
        """Override default level map to force DEBUG for lifecycle events."""
        logger = logging.getLogger("test.custom_map")
        logger.setLevel(logging.DEBUG)
        custom_map = {CATEGORY_PIPELINE_LIFECYCLE: logging.DEBUG}
        handler = LoggingEventHandler(logger=logger, level_map=custom_map)

        with caplog.at_level(logging.DEBUG):
            handler.emit(sample_event)
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.DEBUG

    def test_logging_handler_extra_data(self, sample_event, caplog):
        """Verify extra dict contains event_data in log record."""
        logger = logging.getLogger("test.extra_data")
        logger.setLevel(logging.INFO)
        handler = LoggingEventHandler(logger=logger)

        with caplog.at_level(logging.INFO):
            handler.emit(sample_event)
        record = caplog.records[0]
        assert hasattr(record, "event_data")
        assert isinstance(record.event_data, dict)
        assert record.event_data["run_id"] == "test-run-1"
        assert record.event_data["pipeline_name"] == "test_pipeline"

    def test_logging_handler_unknown_category(self, caplog):
        """Unknown category falls back to INFO level."""
        logger = logging.getLogger("test.unknown_category")
        logger.setLevel(logging.INFO)
        handler = LoggingEventHandler(logger=logger)

        # Create custom event with EVENT_CATEGORY not in DEFAULT_LEVEL_MAP
        class _UnknownCategoryEvent(PipelineStarted):
            EVENT_CATEGORY = "unknown_test_category"

        event = _UnknownCategoryEvent(run_id="run-1", pipeline_name="test")

        with caplog.at_level(logging.DEBUG):
            handler.emit(event)
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.INFO

    def test_logging_handler_repr(self):
        """__repr__ returns logger name."""
        logger = logging.getLogger("test.repr_check")
        handler = LoggingEventHandler(logger=logger)
        assert repr(handler) == "LoggingEventHandler(logger=test.repr_check)"


# -- InMemoryEventHandler ------------------------------------------------------


class TestInMemoryEventHandler:
    """InMemoryEventHandler tests: emit, query methods, thread safety."""

    def test_inmemory_handler_emit_and_get(self, in_memory_handler, sample_event):
        """Basic emit + retrieve all events."""
        in_memory_handler.emit(sample_event)
        events = in_memory_handler.get_events()
        assert len(events) == 1
        assert events[0]["run_id"] == "test-run-1"
        assert events[0]["event_type"] == "pipeline_started"

    def test_inmemory_handler_get_by_run_id_none(self, in_memory_handler):
        """get_events(run_id=None) returns all events."""
        event1 = PipelineStarted(run_id="run-1", pipeline_name="p1")
        event2 = PipelineStarted(run_id="run-2", pipeline_name="p2")
        in_memory_handler.emit(event1)
        in_memory_handler.emit(event2)

        all_events = in_memory_handler.get_events(run_id=None)
        assert len(all_events) == 2

    def test_inmemory_handler_get_by_run_id_specific(self, in_memory_handler):
        """get_events(run_id='x') filters by run_id."""
        event1 = PipelineStarted(run_id="run-1", pipeline_name="p1")
        event2 = PipelineStarted(run_id="run-2", pipeline_name="p2")
        event3 = PipelineStarted(run_id="run-1", pipeline_name="p3")
        in_memory_handler.emit(event1)
        in_memory_handler.emit(event2)
        in_memory_handler.emit(event3)

        filtered = in_memory_handler.get_events(run_id="run-1")
        assert len(filtered) == 2
        assert all(e["run_id"] == "run-1" for e in filtered)

    def test_inmemory_handler_get_by_type(self, in_memory_handler):
        """get_events_by_type filters by event_type."""
        event1 = PipelineStarted(run_id="run-1", pipeline_name="p1")
        event2 = ConsensusReached(
            run_id="run-1",
            pipeline_name="p1",
            step_name="s1",
            attempt=1,
            threshold=3,
        )
        in_memory_handler.emit(event1)
        in_memory_handler.emit(event2)

        started_events = in_memory_handler.get_events_by_type("pipeline_started")
        assert len(started_events) == 1
        assert started_events[0]["event_type"] == "pipeline_started"

    def test_inmemory_handler_get_by_type_and_run_id(self, in_memory_handler):
        """get_events_by_type with run_id filter."""
        event1 = PipelineStarted(run_id="run-1", pipeline_name="p1")
        event2 = PipelineStarted(run_id="run-2", pipeline_name="p2")
        event3 = ConsensusReached(
            run_id="run-1",
            pipeline_name="p1",
            step_name="s1",
            attempt=1,
            threshold=3,
        )
        in_memory_handler.emit(event1)
        in_memory_handler.emit(event2)
        in_memory_handler.emit(event3)

        filtered = in_memory_handler.get_events_by_type(
            "pipeline_started", run_id="run-1"
        )
        assert len(filtered) == 1
        assert filtered[0]["run_id"] == "run-1"

    def test_inmemory_handler_clear(self, in_memory_handler, sample_event):
        """clear() empties the event list."""
        in_memory_handler.emit(sample_event)
        assert len(in_memory_handler.get_events()) == 1
        in_memory_handler.clear()
        assert len(in_memory_handler.get_events()) == 0

    def test_inmemory_handler_thread_safety(self, in_memory_handler):
        """Concurrent emit from 10 threads, verify final count."""
        num_threads = 10
        events_per_thread = 20

        def _worker():
            for i in range(events_per_thread):
                event = PipelineStarted(
                    run_id=f"run-{threading.current_thread().ident}-{i}",
                    pipeline_name="test",
                )
                in_memory_handler.emit(event)

        threads = [threading.Thread(target=_worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        all_events = in_memory_handler.get_events()
        assert len(all_events) == num_threads * events_per_thread

    def test_inmemory_handler_get_returns_copy(self, in_memory_handler, sample_event):
        """get_events returns a shallow copy; mutation doesn't affect store."""
        in_memory_handler.emit(sample_event)
        events1 = in_memory_handler.get_events()
        events2 = in_memory_handler.get_events()

        # Mutate one list
        events1.clear()
        assert len(events2) == 1
        assert len(in_memory_handler.get_events()) == 1

    def test_inmemory_handler_repr(self, in_memory_handler, sample_event):
        """__repr__ shows event count."""
        assert repr(in_memory_handler) == "InMemoryEventHandler(events=0)"
        in_memory_handler.emit(sample_event)
        assert repr(in_memory_handler) == "InMemoryEventHandler(events=1)"


# -- SQLiteEventHandler --------------------------------------------------------


class TestSQLiteEventHandler:
    """SQLiteEventHandler tests: table creation, persistence, indexes, session isolation."""

    def test_sqlite_handler_table_creation(self, sqlite_handler):
        """Verify pipeline_events table exists after init."""
        engine = sqlite_handler._engine
        with Session(engine) as session:
            result = session.exec(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_events'"
                )
            )
            tables = result.fetchall()
        assert len(tables) == 1

    def test_sqlite_handler_emit(self, sqlite_handler, sample_event):
        """Emit persists record in DB."""
        sqlite_handler.emit(sample_event)

        engine = sqlite_handler._engine
        with Session(engine) as session:
            statement = select(PipelineEventRecord)
            records = session.exec(statement).all()

        assert len(records) == 1
        record = records[0]
        assert record.run_id == "test-run-1"
        assert record.event_type == "pipeline_started"
        assert record.pipeline_name == "test_pipeline"
        assert isinstance(record.event_data, dict)
        assert record.event_data["run_id"] == "test-run-1"

    def test_sqlite_handler_multiple_emits(self, sqlite_handler):
        """Multiple events stored correctly."""
        event1 = PipelineStarted(run_id="run-1", pipeline_name="p1")
        event2 = PipelineStarted(run_id="run-2", pipeline_name="p2")
        event3 = ConsensusReached(
            run_id="run-1",
            pipeline_name="p1",
            step_name="s1",
            attempt=1,
            threshold=3,
        )

        sqlite_handler.emit(event1)
        sqlite_handler.emit(event2)
        sqlite_handler.emit(event3)

        engine = sqlite_handler._engine
        with Session(engine) as session:
            statement = select(PipelineEventRecord)
            records = session.exec(statement).all()

        assert len(records) == 3

    def test_sqlite_handler_indexes(self, sqlite_handler, sample_event):
        """Verify indexes created: composite (run_id, event_type) + standalone event_type."""
        sqlite_handler.emit(sample_event)

        engine = sqlite_handler._engine
        with Session(engine) as session:
            # Query sqlite_master for indexes
            result = session.exec(
                text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pipeline_events'"
                )
            )
            index_names = [row[0] for row in result.fetchall()]

        # Verify both indexes exist
        assert "ix_pipeline_events_run_event" in index_names
        assert "ix_pipeline_events_type" in index_names

    def test_sqlite_handler_session_isolation(self, sqlite_handler):
        """No lingering session state after emit."""
        event1 = PipelineStarted(run_id="run-1", pipeline_name="p1")
        sqlite_handler.emit(event1)

        # Emit second event; should not conflict with closed session from first emit
        event2 = PipelineStarted(run_id="run-2", pipeline_name="p2")
        sqlite_handler.emit(event2)  # should not raise

        engine = sqlite_handler._engine
        with Session(engine) as session:
            statement = select(PipelineEventRecord)
            records = session.exec(statement).all()
        assert len(records) == 2

    def test_sqlite_handler_json_field_storage(self, sqlite_handler, sample_event):
        """event_data field stores full JSON dict."""
        sqlite_handler.emit(sample_event)

        engine = sqlite_handler._engine
        with Session(engine) as session:
            statement = select(PipelineEventRecord)
            record = session.exec(statement).one()

        # Verify JSON field contains full event dict
        assert isinstance(record.event_data, dict)
        assert "run_id" in record.event_data
        assert "pipeline_name" in record.event_data
        assert "timestamp" in record.event_data
        assert "event_type" in record.event_data

    def test_sqlite_handler_repr(self, sqlite_handler):
        """__repr__ shows engine URL."""
        assert "SQLiteEventHandler(engine=" in repr(sqlite_handler)
        assert "sqlite:///:memory:" in repr(sqlite_handler)


# -- Protocol Conformance ------------------------------------------------------


class TestProtocolConformance:
    """All 3 handlers satisfy PipelineEventEmitter protocol."""

    def test_logging_handler_satisfies_protocol(self):
        handler = LoggingEventHandler()
        assert isinstance(handler, PipelineEventEmitter)

    def test_inmemory_handler_satisfies_protocol(self):
        handler = InMemoryEventHandler()
        assert isinstance(handler, PipelineEventEmitter)

    def test_sqlite_handler_satisfies_protocol(self):
        engine = create_engine("sqlite:///:memory:")
        handler = SQLiteEventHandler(engine)
        assert isinstance(handler, PipelineEventEmitter)


# -- PipelineEventRecord -------------------------------------------------------


class TestPipelineEventRecord:
    """PipelineEventRecord model tests: JSON field, repr."""

    def test_event_record_json_field(self):
        """event_data stores dict via JSON column."""
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine, tables=[PipelineEventRecord.__table__])

        event_data = {"run_id": "r1", "event_type": "test", "extra": [1, 2, 3]}
        record = PipelineEventRecord(
            run_id="r1",
            event_type="test_event",
            pipeline_name="test_pipeline",
            event_data=event_data,
        )

        with Session(engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            record_id = record.id

        # Retrieve and verify JSON deserialization
        with Session(engine) as session:
            statement = select(PipelineEventRecord).where(
                PipelineEventRecord.id == record_id
            )
            retrieved = session.exec(statement).one()

        assert isinstance(retrieved.event_data, dict)
        assert retrieved.event_data["extra"] == [1, 2, 3]

    def test_event_record_repr(self):
        """__repr__ format includes id, run_id, event_type."""
        record = PipelineEventRecord(
            id=42,
            run_id="run-abc",
            event_type="pipeline_started",
            pipeline_name="test_pipeline",
            event_data={},
        )
        repr_str = repr(record)
        assert repr_str == "<PipelineEventRecord(id=42, run=run-abc, type=pipeline_started)>"

    def test_event_record_timestamp_default(self):
        """timestamp defaults to utc_now."""
        record = PipelineEventRecord(
            run_id="r1",
            event_type="test",
            pipeline_name="p1",
            event_data={},
        )
        assert isinstance(record.timestamp, datetime)


# -- DEFAULT_LEVEL_MAP ---------------------------------------------------------


class TestDefaultLevelMap:
    """Verify DEFAULT_LEVEL_MAP contains all 9 category constants."""

    def test_all_categories_present(self):
        """All 9 categories mapped in DEFAULT_LEVEL_MAP."""
        from llm_pipeline.events.types import (
            CATEGORY_EXTRACTION,
            CATEGORY_INSTRUCTIONS_CONTEXT,
            CATEGORY_LLM_CALL,
            CATEGORY_STATE,
            CATEGORY_STEP_LIFECYCLE,
            CATEGORY_TRANSFORMATION,
        )

        expected_categories = {
            CATEGORY_PIPELINE_LIFECYCLE,
            CATEGORY_STEP_LIFECYCLE,
            CATEGORY_LLM_CALL,
            CATEGORY_CONSENSUS,
            CATEGORY_CACHE,
            CATEGORY_INSTRUCTIONS_CONTEXT,
            CATEGORY_TRANSFORMATION,
            CATEGORY_EXTRACTION,
            CATEGORY_STATE,
        }

        assert set(DEFAULT_LEVEL_MAP.keys()) == expected_categories

    def test_lifecycle_categories_at_info(self):
        """Lifecycle-significant categories at INFO."""
        from llm_pipeline.events.types import CATEGORY_LLM_CALL, CATEGORY_STEP_LIFECYCLE

        assert DEFAULT_LEVEL_MAP[CATEGORY_PIPELINE_LIFECYCLE] == logging.INFO
        assert DEFAULT_LEVEL_MAP[CATEGORY_STEP_LIFECYCLE] == logging.INFO
        assert DEFAULT_LEVEL_MAP[CATEGORY_LLM_CALL] == logging.INFO
        assert DEFAULT_LEVEL_MAP[CATEGORY_CONSENSUS] == logging.INFO

    def test_detail_categories_at_debug(self):
        """Implementation detail categories at DEBUG."""
        from llm_pipeline.events.types import (
            CATEGORY_EXTRACTION,
            CATEGORY_INSTRUCTIONS_CONTEXT,
            CATEGORY_STATE,
            CATEGORY_TRANSFORMATION,
        )

        assert DEFAULT_LEVEL_MAP[CATEGORY_CACHE] == logging.DEBUG
        assert DEFAULT_LEVEL_MAP[CATEGORY_INSTRUCTIONS_CONTEXT] == logging.DEBUG
        assert DEFAULT_LEVEL_MAP[CATEGORY_TRANSFORMATION] == logging.DEBUG
        assert DEFAULT_LEVEL_MAP[CATEGORY_EXTRACTION] == logging.DEBUG
        assert DEFAULT_LEVEL_MAP[CATEGORY_STATE] == logging.DEBUG
