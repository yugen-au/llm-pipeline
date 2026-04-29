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


@pytest.fixture
def phoenix_prompt_stub(monkeypatch):
    """Replace ``PromptService`` at the pipeline.execute call site with a
    fake backed by an in-memory dict, so tests that drive
    ``pipeline.execute()`` don't need a live Phoenix instance.

    Usage::

        def test_x(phoenix_prompt_stub):
            phoenix_prompt_stub.register(
                "gadget", system="...", user="Analyze: {data}",
            )
            pipeline.execute(...)

    Tests that don't register anything still get a working
    ``PromptService`` — calls to ``get_prompt`` for unknown keys raise
    ``ValueError("Prompt not found: ...")`` exactly like the live
    Phoenix backend would on a 404.
    """
    from llm_pipeline.prompts.phoenix_client import PromptNotFoundError
    from llm_pipeline.prompts.service import PromptService

    store: dict[str, dict] = {}

    class _Stub:
        def register(self, name: str, *, system: str | None = None, user: str | None = None) -> None:
            messages = []
            if system is not None:
                messages.append({"role": "system", "content": system})
            if user is not None:
                messages.append({"role": "user", "content": user})
            store[name] = {
                "id": f"v_{name}",
                "template": {"type": "chat", "messages": messages},
                "template_type": "CHAT",
                "template_format": "F_STRING",
            }

    class _FakeClient:
        def get_by_tag(self, name, tag):
            if name not in store:
                raise PromptNotFoundError(name)
            return store[name]

        def get_latest(self, name):
            return self.get_by_tag(name, "latest")

    def _factory(*args, **kwargs):
        return PromptService(client=_FakeClient())

    monkeypatch.setattr(
        "llm_pipeline.prompts.service.PromptService", _factory,
    )
    return _Stub()


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
