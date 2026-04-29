"""Tests for llm_pipeline.observability.

Vendor-neutral OTEL implementation: spans are emitted via raw OTEL,
annotated with OpenInference semantic conventions, and shipped to
whatever backend ``OTEL_EXPORTER_OTLP_ENDPOINT`` names. Tests use
OTEL's ``InMemorySpanExporter`` to capture spans without a remote
backend.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

# Import at module top so any transitive load_dotenv() calls (e.g. from
# llm_pipeline.db package init) run once during test collection. Tests
# then strip the env vars via the autouse session fixture in conftest.
from llm_pipeline import observability as obs_mod
from llm_pipeline.observability import (
    PipelineObserver,
    WebSocketBroadcastProcessor,
    _span_to_observation,
    configure,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_configure_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level _CONFIGURED flag between tests."""
    monkeypatch.setattr(obs_mod, "_CONFIGURED", False)


@pytest.fixture
def in_memory_exporter():
    """Install an in-memory span exporter on a fresh TracerProvider.

    Returns the exporter so tests can read out captured spans.
    Replaces the global tracer provider for the test's duration.
    """
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Force the new provider into the global slot. OTEL guards against
    # re-setting a provider once one is installed; bypass that by
    # poking the underlying module global.
    import opentelemetry.trace as _t
    saved_provider = _t._TRACER_PROVIDER
    saved_set_once = _t._TRACER_PROVIDER_SET_ONCE
    try:
        _t._TRACER_PROVIDER = provider
        # Reset the once-flag so ``set_tracer_provider`` doesn't no-op.
        try:
            _t._TRACER_PROVIDER_SET_ONCE = type(saved_set_once)()
        except Exception:
            pass
        yield exporter
    finally:
        _t._TRACER_PROVIDER = saved_provider
        _t._TRACER_PROVIDER_SET_ONCE = saved_set_once


def _attrs(span) -> dict:
    """Snapshot a ReadableSpan's attributes to a plain dict."""
    return dict(span.attributes or {})


def _by_name(spans, name: str):
    return next(s for s in spans if s.name == name)


# ---------------------------------------------------------------------------
# configure()
# ---------------------------------------------------------------------------


class TestConfigure:
    def test_idempotent_second_call_returns_true_without_re_setup(self) -> None:
        with patch("llm_pipeline.observability.WebSocketBroadcastProcessor") as ws_cls:
            assert configure(instrument_pydantic_ai=False) is True
            assert configure(instrument_pydantic_ai=False) is True
            # Constructor called once even though configure() ran twice.
            assert ws_cls.call_count == 1

    def test_no_otlp_exporter_when_endpoint_unset(self) -> None:
        # Endpoint env var stripped by the autouse session fixture in
        # tests/conftest.py. configure() should still succeed.
        with patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        ) as exporter_cls:
            configure(instrument_pydantic_ai=False)
            exporter_cls.assert_not_called()

    def test_otlp_exporter_attached_when_endpoint_set(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:6006",
        )
        with patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        ) as exporter_cls:
            configure(instrument_pydantic_ai=False)
            exporter_cls.assert_called_once()
            kwargs = exporter_cls.call_args.kwargs
            # Endpoint normalised to include /v1/traces.
            assert kwargs["endpoint"] == "http://localhost:6006/v1/traces"

    def test_otlp_exporter_keeps_explicit_v1_traces_path(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "https://example.com/v1/traces",
        )
        with patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        ) as exporter_cls:
            configure(instrument_pydantic_ai=False)
            kwargs = exporter_cls.call_args.kwargs
            assert kwargs["endpoint"] == "https://example.com/v1/traces"

    def test_websocket_processor_always_attached(self) -> None:
        with patch("llm_pipeline.observability.WebSocketBroadcastProcessor") as ws_cls:
            configure(instrument_pydantic_ai=False)
            ws_cls.assert_called_once()

    def test_pydantic_ai_instrumented_by_default(self) -> None:
        # Need a tracer provider attached by configure() before
        # instrument_all is called; patch instrument_all itself to
        # observe.
        with patch("pydantic_ai.Agent.instrument_all") as instrument:
            configure()
            instrument.assert_called_once()

    def test_pydantic_ai_skipped_when_flag_false(self) -> None:
        with patch("pydantic_ai.Agent.instrument_all") as instrument:
            configure(instrument_pydantic_ai=False)
            instrument.assert_not_called()


# ---------------------------------------------------------------------------
# PipelineObserver: span attributes
# ---------------------------------------------------------------------------


class TestPipelineRunSpan:
    def test_emits_root_span_with_session_id_and_input(
        self, in_memory_exporter,
    ) -> None:
        obs = PipelineObserver(run_id="run-abc", pipeline_name="my_pipeline")
        with obs.pipeline_run(input_data={"data": "raw"}, tags=["my_pipeline"]):
            pass

        spans = in_memory_exporter.get_finished_spans()
        root = _by_name(spans, "pipeline.my_pipeline")
        attrs = _attrs(root)
        assert attrs["session.id"] == "run-abc"
        assert attrs["openinference.span.kind"] == "CHAIN"
        # Input is JSON-encoded with mime type set.
        assert attrs["input.mime_type"] == "application/json"
        assert "raw" in attrs["input.value"]

    def test_user_id_propagates_via_attribute(self, in_memory_exporter) -> None:
        obs = PipelineObserver(run_id="run-xyz", pipeline_name="p")
        with obs.pipeline_run(user_id="user-42"):
            pass
        attrs = _attrs(_by_name(in_memory_exporter.get_finished_spans(), "pipeline.p"))
        assert attrs.get("user.id") == "user-42"

    def test_tags_default_to_pipeline_name(self, in_memory_exporter) -> None:
        obs = PipelineObserver(run_id="r", pipeline_name="alpha")
        with obs.pipeline_run():
            pass
        attrs = _attrs(_by_name(in_memory_exporter.get_finished_spans(), "pipeline.alpha"))
        # Tags stored as JSON array under tag.tags.
        assert "alpha" in attrs.get("tag.tags", "")


class TestStepSpan:
    def test_step_carries_metadata_and_session(self, in_memory_exporter) -> None:
        obs = PipelineObserver(run_id="run-1", pipeline_name="p")
        with obs.pipeline_run():
            with obs.step(
                step_name="detect", step_number=1,
                instructions_class="DetectInstructions",
            ):
                pass

        step_span = _by_name(in_memory_exporter.get_finished_spans(), "step.detect")
        attrs = _attrs(step_span)
        assert attrs["session.id"] == "run-1"
        assert attrs["openinference.span.kind"] == "CHAIN"
        # Metadata about the step is in input.value.
        assert "detect" in attrs["input.value"]
        assert "DetectInstructions" in attrs["input.value"]


class TestExtractionSpan:
    def test_extraction_span_carries_classes(self, in_memory_exporter) -> None:
        obs = PipelineObserver(run_id="r", pipeline_name="p")
        with obs.pipeline_run():
            with obs.extraction(
                extraction_class="WidgetExtraction", model_class="Widget",
            ):
                pass
        span = _by_name(
            in_memory_exporter.get_finished_spans(), "extraction.WidgetExtraction",
        )
        attrs = _attrs(span)
        assert attrs["openinference.span.kind"] == "CHAIN"
        assert "Widget" in attrs["input.value"]


class TestTransformationSpan:
    def test_transformation_span_carries_class(self, in_memory_exporter) -> None:
        obs = PipelineObserver(run_id="r", pipeline_name="p")
        with obs.pipeline_run():
            with obs.transformation(transformation_class="Aggregate"):
                pass
        span = _by_name(
            in_memory_exporter.get_finished_spans(), "transformation.Aggregate",
        )
        attrs = _attrs(span)
        assert "Aggregate" in attrs["input.value"]


class TestReviewSpan:
    def test_emits_backdated_span_with_decision_metadata(
        self, in_memory_exporter,
    ) -> None:
        obs = PipelineObserver(run_id="r", pipeline_name="p")
        start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        with obs.pipeline_run():
            obs.review(
                step_name="detect",
                start_time=start,
                end_time=end,
                decision="approved",
                notes="lgtm",
                user_id="alice",
                review_data={"output": "thing"},
                token="tok-1",
            )
        review = _by_name(in_memory_exporter.get_finished_spans(), "review.detect")
        attrs = _attrs(review)
        assert attrs["openinference.span.kind"] == "EVALUATOR"
        assert attrs["session.id"] == "r"
        assert attrs["review.decision"] == "approved"
        assert attrs["review.token"] == "tok-1"
        assert attrs["review.user_id"] == "alice"
        # Backdating: span timestamps land on the supplied start/end.
        assert review.start_time == int(start.timestamp() * 1_000_000_000)
        assert review.end_time == int(end.timestamp() * 1_000_000_000)
        # Wait window persisted in metadata.
        assert "wait_duration_ms" in attrs["metadata"]
        # Output JSON contains decision + notes.
        assert "approved" in attrs["output.value"]

    def test_rejected_decision_marks_span_error(self, in_memory_exporter) -> None:
        obs = PipelineObserver(run_id="r", pipeline_name="p")
        with obs.pipeline_run():
            obs.review(
                step_name="x",
                start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
                decision="rejected",
            )
        review = _by_name(in_memory_exporter.get_finished_spans(), "review.x")
        from opentelemetry.trace import StatusCode
        assert review.status.status_code == StatusCode.ERROR


# ---------------------------------------------------------------------------
# Resume parent context propagation
# ---------------------------------------------------------------------------


class TestResumeParentContext:
    def test_resume_attaches_parent_trace_id(self, in_memory_exporter) -> None:
        # First run: capture trace_id + span_id.
        obs = PipelineObserver(run_id="r", pipeline_name="p")
        with obs.pipeline_run() as root:
            captured_trace = format(root.get_span_context().trace_id, "032x")
            captured_span = format(root.get_span_context().span_id, "016x")
            with obs.step(step_name="s1", step_number=1):
                pass

        # Resume: pass parent context, open a step inside.
        in_memory_exporter.clear()
        with obs.pipeline_run(
            parent_trace_id=captured_trace,
            parent_span_id=captured_span,
        ):
            with obs.step(step_name="s2", step_number=2):
                pass

        spans = in_memory_exporter.get_finished_spans()
        # No new pipeline.p root span on resume.
        assert all(s.name != "pipeline.p" for s in spans)
        # The resumed step's trace_id matches the original.
        s2 = _by_name(spans, "step.s2")
        assert format(s2.context.trace_id, "032x") == captured_trace
        # And its parent is the original root span.
        assert s2.parent is not None
        assert format(s2.parent.span_id, "016x") == captured_span

    def test_invalid_parent_ids_fall_through_to_fresh_root(
        self, in_memory_exporter,
    ) -> None:
        obs = PipelineObserver(run_id="r", pipeline_name="p")
        with obs.pipeline_run(
            parent_trace_id="not-hex-at-all",
            parent_span_id="zzz",
        ):
            pass
        # Falls through to a new root span.
        spans = in_memory_exporter.get_finished_spans()
        assert any(s.name == "pipeline.p" for s in spans)


# ---------------------------------------------------------------------------
# Span events
# ---------------------------------------------------------------------------


class TestSpanEvents:
    def test_cache_hit_attaches_event_to_active_span(
        self, in_memory_exporter,
    ) -> None:
        obs = PipelineObserver(run_id="r", pipeline_name="p")
        with obs.pipeline_run():
            with obs.step(step_name="s", step_number=1):
                obs.cache_hit(input_hash="abc123")
        step_span = _by_name(in_memory_exporter.get_finished_spans(), "step.s")
        events = [e for e in step_span.events if e.name == "cache.hit"]
        assert len(events) == 1
        assert events[0].attributes["input_hash"] == "abc123"

    def test_consensus_reached_drops_none_attributes(
        self, in_memory_exporter,
    ) -> None:
        obs = PipelineObserver(run_id="r", pipeline_name="p")
        with obs.pipeline_run():
            with obs.step(step_name="s", step_number=1):
                obs.consensus_reached(attempts_used=3, agreement=None)
        step_span = _by_name(in_memory_exporter.get_finished_spans(), "step.s")
        events = [e for e in step_span.events if e.name == "consensus.reached"]
        assert len(events) == 1
        # None attributes silently dropped (OTEL rejects None values).
        assert "agreement" not in events[0].attributes
        assert events[0].attributes["attempts_used"] == 3


# ---------------------------------------------------------------------------
# WebSocketBroadcastProcessor span -> observation mapping
# ---------------------------------------------------------------------------


class TestSpanToObservation:
    def test_real_span_maps_to_observation(self, in_memory_exporter) -> None:
        obs = PipelineObserver(run_id="run-99", pipeline_name="alpha")
        with obs.pipeline_run(input_data={"data": "x"}):
            pass
        spans = in_memory_exporter.get_finished_spans()
        observation = _span_to_observation(spans[0])
        assert observation["name"] == "pipeline.alpha"
        assert observation["type"] == "SPAN"
        assert observation["level"] == "DEFAULT"
        assert observation["start_time"] is not None
        assert observation["end_time"] is not None
        assert observation["duration_ms"] is not None
        assert observation["input"] == {"data": "x"}
