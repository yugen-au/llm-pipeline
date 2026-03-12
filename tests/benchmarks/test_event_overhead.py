"""NFR-001: Event emission overhead benchmarks.

Measures _emit() overhead for three scenarios:
1. No handler (emitter=None) -- primary NFR target: <1ms
2. LoggingEventHandler attached
3. InMemoryEventHandler attached

Uses benchmark.pedantic() for sub-millisecond precision.
"""

import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.events import (
    InMemoryEventHandler,
    LoggingEventHandler,
    PipelineStarted,
)
from llm_pipeline.events.emitter import CompositeEmitter
from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.strategy import PipelineStrategies


# -- Minimal concrete subclasses to satisfy PipelineConfig ABC requirements --


class BenchmarkRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class BenchmarkStrategies(PipelineStrategies, strategies=[]):
    pass


class BenchmarkPipeline(
    PipelineConfig,
    registry=BenchmarkRegistry,
    strategies=BenchmarkStrategies,
):
    pass


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture(scope="module")
def benchmark_engine():
    """In-memory SQLite engine with StaticPool for benchmark isolation."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(engine)
    return engine


@pytest.fixture()
def minimal_pipeline(benchmark_engine):
    """BenchmarkPipeline with no event emitter (emitter=None)."""
    session = Session(benchmark_engine)
    try:
        pipeline = BenchmarkPipeline(
            strategies=[],
            session=session,
            model="test-model",
        )
        yield pipeline
    finally:
        session.close()


@pytest.fixture()
def pipeline_with_logging(benchmark_engine):
    """BenchmarkPipeline with LoggingEventHandler attached."""
    session = Session(benchmark_engine)
    handler = LoggingEventHandler(
        logger=logging.getLogger("benchmark.events"),
        level_map={},  # empty map -> all events fall back to INFO
    )
    emitter = CompositeEmitter(handlers=[handler])
    try:
        pipeline = BenchmarkPipeline(
            strategies=[],
            session=session,
            model="test-model",
            event_emitter=emitter,
        )
        yield pipeline
    finally:
        session.close()


@pytest.fixture()
def pipeline_with_inmemory(benchmark_engine):
    """BenchmarkPipeline with InMemoryEventHandler attached."""
    session = Session(benchmark_engine)
    handler = InMemoryEventHandler()
    emitter = CompositeEmitter(handlers=[handler])
    try:
        pipeline = BenchmarkPipeline(
            strategies=[],
            session=session,
            model="test-model",
            event_emitter=emitter,
        )
        yield pipeline
    finally:
        session.close()


def _make_event(pipeline: PipelineConfig) -> PipelineStarted:
    """Create a PipelineStarted event for the given pipeline."""
    return PipelineStarted(
        run_id=pipeline.run_id,
        pipeline_name=pipeline.pipeline_name,
    )


# -- Benchmarks (NFR-001) ---------------------------------------------------


@pytest.mark.benchmark_group("NFR-001")
def test_emit_no_handler(benchmark, minimal_pipeline):
    """Benchmark _emit() with emitter=None.

    Primary NFR-001 target: <1ms per event point when no handler attached.
    The fast-path is a single ``if self._event_emitter is not None`` check.
    """
    event = _make_event(minimal_pipeline)

    result = benchmark.pedantic(
        minimal_pipeline._emit,
        args=(event,),
        warmup_rounds=10,
        rounds=100,
        iterations=1000,
    )

    # Verify the call completed (returns None)
    assert result is None
    # NFR-001: mean < 1ms (1e-3 seconds)
    assert benchmark.stats.stats.mean < 1e-3, (
        f"NFR-001 FAILED: mean emit time {benchmark.stats.stats.mean * 1e6:.2f}us > 1000us"
    )


@pytest.mark.benchmark_group("NFR-001")
def test_emit_with_logging_handler(benchmark, pipeline_with_logging):
    """Benchmark _emit() with LoggingEventHandler attached.

    Supplementary benchmark measuring event construction + to_dict() +
    logging overhead. Not a hard NFR target but tracks regression.
    """
    event = _make_event(pipeline_with_logging)

    benchmark.pedantic(
        pipeline_with_logging._emit,
        args=(event,),
        warmup_rounds=10,
        rounds=100,
        iterations=1000,
    )


@pytest.mark.benchmark_group("NFR-001")
def test_emit_with_inmemory_handler(benchmark, pipeline_with_inmemory):
    """Benchmark _emit() with InMemoryEventHandler attached.

    Supplementary benchmark measuring event construction + to_dict() +
    list append + Lock overhead. Not a hard NFR target but tracks regression.
    """
    event = _make_event(pipeline_with_inmemory)

    benchmark.pedantic(
        pipeline_with_inmemory._emit,
        args=(event,),
        warmup_rounds=10,
        rounds=100,
        iterations=1000,
    )
