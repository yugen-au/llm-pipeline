"""Shared fixtures and configuration for benchmark tests.

Provides:
- benchmark_engine: module-scoped in-memory SQLite with PRAGMA optimizations
- minimal_pipeline: MinimalPipeline concrete subclass for event emission benchmarks
- pytest.mark.benchmark_group marker for NFR categorization
"""
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.result import LLMCallResult
from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies


# -- Pytest markers ------------------------------------------------------------


def pytest_configure(config):
    """Register custom benchmark markers."""
    config.addinivalue_line(
        "markers",
        "benchmark_group(name): categorize benchmark by NFR group (e.g. NFR-001, NFR-004, NFR-005)",
    )


# -- Mock LLM provider --------------------------------------------------------


class _BenchmarkMockProvider(LLMProvider):
    """Minimal LLMProvider for benchmark fixtures. Never called."""

    def call_structured(
        self,
        prompt: str,
        system_instruction: str,
        result_class: Type[BaseModel],
        **kwargs,
    ) -> LLMCallResult:
        raise NotImplementedError("Benchmark mock provider should not be called")


# -- MinimalPipeline concrete subclass -----------------------------------------


class MinimalRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class _MinimalStrategy(PipelineStrategy):
    """No-op strategy; benchmarks don't execute steps."""

    def can_handle(self, context: Dict[str, Any]) -> bool:
        return True

    def get_steps(self) -> list:
        return []


class MinimalStrategies(PipelineStrategies, strategies=[_MinimalStrategy]):
    pass


class MinimalPipeline(
    PipelineConfig,
    registry=MinimalRegistry,
    strategies=MinimalStrategies,
):
    """Concrete PipelineConfig with empty registry/strategies for benchmarking _emit()."""

    pass


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture(scope="module")
def benchmark_engine():
    """In-memory SQLite engine with StaticPool and PRAGMA optimizations.

    Module-scoped to share expensive setup across all benchmarks in a module.
    PRAGMA settings are for benchmark consistency only, not production.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA cache_size = 10000")
        cursor.execute("PRAGMA mmap_size = 30000000")
        cursor.close()

    init_pipeline_db(engine)
    return engine


@pytest.fixture
def minimal_pipeline(benchmark_engine):
    """MinimalPipeline instance wired to benchmark_engine with mock provider.

    Function-scoped so each test gets a fresh pipeline state.
    """
    with Session(benchmark_engine) as session:
        pipeline = MinimalPipeline(
            engine=benchmark_engine,
            session=session,
            provider=_BenchmarkMockProvider(),
        )
        yield pipeline
