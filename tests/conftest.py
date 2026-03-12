"""Root-level test helpers shared across all test directories.

Provides mock builders used by both tests/events/ and root-level test modules.
"""
from unittest.mock import MagicMock


def _mock_usage(input_tokens=10, output_tokens=5):
    """Build MagicMock mimicking pydantic-ai Usage with configurable token values."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.requests = 1
    return usage
