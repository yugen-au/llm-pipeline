"""Tests for llm_pipeline.observability.PipelineObserver."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Import at module top so any transitive load_dotenv() calls (e.g. from
# llm_pipeline.db package init) run once during test collection. Tests then
# strip the env vars via monkeypatch fixtures — without the early import the
# fixture would run before .env loaded and the delenv would be a no-op.
from llm_pipeline import observability as obs_mod
from llm_pipeline.observability import PipelineObserver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip Langfuse credentials so the observer falls into no-op mode."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)


@pytest.fixture
def with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set fake Langfuse credentials and patch the SDK client constructor."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.invalid")


@pytest.fixture(autouse=True)
def reset_configure_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level _CONFIGURED flag between tests.

    configure() is intentionally idempotent via a module-level flag so
    that production code can call it freely. Tests need a clean slate
    each run or only the first configure-related test would exercise
    the configuration path.
    """
    monkeypatch.setattr(obs_mod, "_CONFIGURED", False)


# ---------------------------------------------------------------------------
# No-op disabled mode
# ---------------------------------------------------------------------------


class TestDisabledNoOp:
    """When Langfuse credentials are absent, every observer method is silent."""

    def test_init_disables_when_creds_absent(self, no_credentials):
        obs = PipelineObserver(run_id="r1", pipeline_name="p")
        assert obs._enabled is False
        assert obs._client is None

    def test_pipeline_run_yields_none_when_disabled(self, no_credentials):
        obs = PipelineObserver(run_id="r1", pipeline_name="p")
        with obs.pipeline_run(input_data={"x": 1}) as root:
            assert root is None

    def test_step_yields_none_when_disabled(self, no_credentials):
        obs = PipelineObserver(run_id="r1", pipeline_name="p")
        with obs.pipeline_run() as _:
            with obs.step(step_name="s", step_number=1) as span:
                assert span is None

    def test_extraction_yields_none_when_disabled(self, no_credentials):
        obs = PipelineObserver(run_id="r1", pipeline_name="p")
        with obs.extraction(extraction_class="E", model_class="M") as span:
            assert span is None

    def test_transformation_yields_none_when_disabled(self, no_credentials):
        obs = PipelineObserver(run_id="r1", pipeline_name="p")
        with obs.transformation(transformation_class="T") as span:
            assert span is None

    def test_span_events_are_silent_when_disabled(self, no_credentials):
        obs = PipelineObserver(run_id="r1", pipeline_name="p")
        # None of these should raise or contact OTEL
        obs.cache_lookup(input_hash="abc")
        obs.cache_hit(input_hash="abc")
        obs.cache_miss(input_hash="abc")
        obs.cache_reconstructed(input_hash="abc")
        obs.step_skipped(reason="cached")
        obs.consensus_attempt(attempt=1, max_attempts=3, strategy="majority")
        obs.consensus_reached(attempts_used=2, agreement=0.66)
        obs.consensus_failed(attempts_used=3, reason="no agreement")

    def test_shutdown_safe_when_disabled(self, no_credentials):
        obs = PipelineObserver(run_id="r1", pipeline_name="p")
        obs.shutdown()  # no-op
        obs.shutdown()  # idempotent


# ---------------------------------------------------------------------------
# Enabled mode (Langfuse client mocked)
# ---------------------------------------------------------------------------


class TestEnabledMode:
    """When credentials are present, observer talks to the SDK."""

    def _make_observer(self, with_credentials, mock_client_cls):
        """Construct an observer with the SDK constructor patched."""
        with patch.object(obs_mod, "_credentials_present", return_value=True):
            # Patch the deferred import inside __init__
            with patch("langfuse.Langfuse", mock_client_cls):
                return PipelineObserver(run_id="r1", pipeline_name="p")

    def test_init_constructs_client_when_creds_present(self, with_credentials):
        mock_client_cls = MagicMock()
        obs = self._make_observer(with_credentials, mock_client_cls)
        assert obs._enabled is True
        mock_client_cls.assert_called_once_with()

    def test_pipeline_run_opens_root_span_and_propagates_attrs(self, with_credentials):
        mock_client_cls = MagicMock()
        mock_client = mock_client_cls.return_value
        mock_root_span = MagicMock()
        mock_client.start_as_current_observation.return_value.__enter__.return_value = mock_root_span

        obs = self._make_observer(with_credentials, mock_client_cls)
        with patch("langfuse.propagate_attributes") as mock_propagate:
            with obs.pipeline_run(input_data={"q": 1}, user_id="u1", tags=["foo"]) as root:
                assert root is mock_root_span

        mock_client.start_as_current_observation.assert_called_once()
        start_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert start_kwargs["name"] == "pipeline.p"
        assert start_kwargs["as_type"] == "span"
        assert start_kwargs["input"] == {"q": 1}

        # Trace-level attributes go through the top-level propagate_attributes()
        # context manager (v4 API exposes it as a free function, not a client method)
        mock_propagate.assert_called_once_with(
            session_id="r1", user_id="u1", tags=["foo"],
        )
        mock_client.flush.assert_called_once()

    def test_pipeline_run_default_tags_use_pipeline_name(self, with_credentials):
        mock_client_cls = MagicMock()
        mock_client = mock_client_cls.return_value
        mock_root_span = MagicMock()
        mock_client.start_as_current_observation.return_value.__enter__.return_value = mock_root_span

        obs = self._make_observer(with_credentials, mock_client_cls)
        with patch("langfuse.propagate_attributes") as mock_propagate:
            with obs.pipeline_run():
                pass

        # user_id absent → key is omitted from propagate_attributes (not passed as None)
        mock_propagate.assert_called_once_with(
            session_id="r1", tags=["p"],
        )

    def test_step_opens_span_with_metadata(self, with_credentials):
        mock_client_cls = MagicMock()
        mock_client = mock_client_cls.return_value
        mock_step_span = MagicMock()
        mock_client.start_as_current_observation.return_value.__enter__.return_value = mock_step_span

        obs = self._make_observer(with_credentials, mock_client_cls)
        with obs.step(step_name="s", step_number=2, instructions_class="I") as span:
            assert span is mock_step_span

        kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert kwargs["name"] == "step.s"
        assert kwargs["as_type"] == "span"
        assert kwargs["input"] == {
            "step_name": "s",
            "step_number": 2,
            "instructions_class": "I",
        }

    def test_extraction_opens_span_with_metadata(self, with_credentials):
        mock_client_cls = MagicMock()
        mock_client = mock_client_cls.return_value
        mock_span = MagicMock()
        mock_client.start_as_current_observation.return_value.__enter__.return_value = mock_span

        obs = self._make_observer(with_credentials, mock_client_cls)
        with obs.extraction(extraction_class="WidgetExtraction", model_class="Widget"):
            pass

        kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert kwargs["name"] == "extraction.WidgetExtraction"
        assert kwargs["input"] == {
            "extraction_class": "WidgetExtraction",
            "model_class": "Widget",
        }

    def test_shutdown_flushes_and_clears_client(self, with_credentials):
        mock_client_cls = MagicMock()
        mock_client = mock_client_cls.return_value

        obs = self._make_observer(with_credentials, mock_client_cls)
        assert obs._client is mock_client

        obs.shutdown()
        mock_client.flush.assert_called_once()
        mock_client.shutdown.assert_called_once()
        assert obs._client is None

    def test_shutdown_is_idempotent(self, with_credentials):
        mock_client_cls = MagicMock()
        obs = self._make_observer(with_credentials, mock_client_cls)
        obs.shutdown()
        obs.shutdown()  # second call must not error


# ---------------------------------------------------------------------------
# Span events attach to the active OTEL span
# ---------------------------------------------------------------------------


class TestSpanEventsAttachToActiveSpan:
    """When enabled, span event helpers add events to the current OTEL span."""

    @pytest.fixture
    def patch_active_span(self):
        with patch("opentelemetry.trace.get_current_span") as get_span:
            mock_span = MagicMock()
            get_span.return_value = mock_span
            yield mock_span

    def _enabled_observer(self):
        with patch.object(obs_mod, "_credentials_present", return_value=True):
            with patch("langfuse.Langfuse"):
                return PipelineObserver(run_id="r1", pipeline_name="p")

    def test_cache_hit_emits_span_event(self, patch_active_span):
        obs = self._enabled_observer()
        obs.cache_hit(input_hash="abc")
        patch_active_span.add_event.assert_called_once_with(
            "cache.hit", attributes={"input_hash": "abc"},
        )

    def test_consensus_attempt_emits_span_event(self, patch_active_span):
        obs = self._enabled_observer()
        obs.consensus_attempt(attempt=2, max_attempts=3, strategy="majority")
        patch_active_span.add_event.assert_called_once_with(
            "consensus.attempt",
            attributes={"attempt": 2, "max_attempts": 3, "strategy": "majority"},
        )

    def test_consensus_reached_drops_none_attributes(self, patch_active_span):
        """OTEL rejects None values; the observer must filter them out."""
        obs = self._enabled_observer()
        obs.consensus_reached(attempts_used=2, agreement=None)
        patch_active_span.add_event.assert_called_once_with(
            "consensus.reached", attributes={"attempts_used": 2},
        )


# ---------------------------------------------------------------------------
# configure() bootstrap
# ---------------------------------------------------------------------------


class TestConfigure:
    """``configure()`` initializes Langfuse + pydantic-ai instrumentation once."""

    def test_returns_false_and_noop_when_creds_absent(self, no_credentials):
        with (
            patch("langfuse.Langfuse") as mock_langfuse,
            patch("pydantic_ai.Agent") as mock_agent,
        ):
            assert obs_mod.configure() is False
        mock_langfuse.assert_not_called()
        mock_agent.instrument_all.assert_not_called()
        assert obs_mod._CONFIGURED is False

    def test_returns_true_and_initializes_when_creds_present(self, with_credentials):
        with (
            patch("langfuse.Langfuse") as mock_langfuse,
            patch("pydantic_ai.Agent") as mock_agent,
        ):
            assert obs_mod.configure() is True
        mock_langfuse.assert_called_once_with()
        mock_agent.instrument_all.assert_called_once()
        assert obs_mod._CONFIGURED is True

    def test_idempotent_second_call_skips_initialization(self, with_credentials):
        with (
            patch("langfuse.Langfuse") as mock_langfuse,
            patch("pydantic_ai.Agent") as mock_agent,
        ):
            assert obs_mod.configure() is True
            assert obs_mod.configure() is True
        # Initialization happens exactly once across both calls
        mock_langfuse.assert_called_once()
        mock_agent.instrument_all.assert_called_once()

    def test_instrument_pydantic_ai_false_skips_agent_instrumentation(
        self, with_credentials,
    ):
        with (
            patch("langfuse.Langfuse") as mock_langfuse,
            patch("pydantic_ai.Agent") as mock_agent,
        ):
            assert obs_mod.configure(instrument_pydantic_ai=False) is True
        mock_langfuse.assert_called_once()
        mock_agent.instrument_all.assert_not_called()

    def test_forwards_environment_release_and_sample_rate(self, with_credentials):
        with (
            patch("langfuse.Langfuse") as mock_langfuse,
            patch("pydantic_ai.Agent"),
        ):
            obs_mod.configure(
                environment="staging",
                release="v1.2.3",
                sample_rate=0.5,
            )
        mock_langfuse.assert_called_once_with(
            environment="staging",
            release="v1.2.3",
            sample_rate=0.5,
        )

    def test_omits_optional_kwargs_when_not_provided(self, with_credentials):
        """When None, the kwargs aren't passed — Langfuse SDK uses its own defaults."""
        with (
            patch("langfuse.Langfuse") as mock_langfuse,
            patch("pydantic_ai.Agent"),
        ):
            obs_mod.configure()
        mock_langfuse.assert_called_once_with()
