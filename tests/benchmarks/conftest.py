"""Benchmark conftest stubbed pending Phase 3b rewrite.

The legacy fixtures (``benchmark_engine``, ``minimal_pipeline``)
declared a ``PipelineConfig`` subclass to exercise event emission
hot-paths. The pydantic-graph migration retired ``PipelineConfig``;
the equivalent benchmark fixture against ``run_pipeline`` lands as
a Phase 3b follow-up.

The ``benchmark_group`` marker registration is preserved so other
tests using it don't trigger pytest warnings.
"""
import pytest


def pytest_configure(config):
    """Register the ``benchmark_group`` marker used by benchmark tests."""
    config.addinivalue_line(
        "markers",
        "benchmark_group(name): label benchmarks with an NFR group",
    )
