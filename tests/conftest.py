"""Root-level test helpers shared across all test directories.

Provides mock builders used by both tests/events/ and root-level test modules.
"""
import os
from unittest.mock import MagicMock

import pytest


def _mock_usage(input_tokens=10, output_tokens=5):
    """Build MagicMock mimicking pydantic-ai Usage with configurable token values."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.requests = 1
    return usage


@pytest.fixture(scope="session", autouse=True)
def _strip_observability_endpoints_from_test_env():
    """Keep observability exporters asleep during the test session.

    The framework loads .env transitively (via llm_pipeline.db on import),
    so pytest would otherwise see real OTLP / Langfuse credentials and
    emit observations to the user's backend on every test that runs
    pipeline.execute() — burning quota and polluting traces with no
    diagnostic value. Tests that need to exercise the enabled path
    re-set the vars locally via ``monkeypatch.setenv``.
    """
    saved = {}
    keys = (
        # OpenTelemetry standard endpoint vars
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
        # Langfuse legacy vars (kept for transition)
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
        # Phoenix-specific vars
        "PHOENIX_BASE_URL",
        "PHOENIX_API_KEY",
    )
    for k in keys:
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    yield
    os.environ.update(saved)
