"""Vendor-neutral OTEL-based pipeline observability.

The framework emits OpenTelemetry spans annotated with OpenInference
semantic conventions (``input.value``, ``output.value``,
``openinference.span.kind``, ``session.id``). Any OTLP-compatible
backend (Arize Phoenix, Langfuse OSS, Honeycomb, Datadog LLM
Observability, custom OTEL collector) can ingest the resulting trace
stream by pointing the standard OTEL env vars at it. The framework
itself imports no vendor SDKs.

Design contract:

* **Single sink, no fanout in code.** Spans are routed by the OTEL
  ``BatchSpanProcessor`` to whatever endpoint
  ``OTEL_EXPORTER_OTLP_ENDPOINT`` names. There is no event handler
  abstraction, no event emitter protocol, no in-process event types.
  Operational state (run status, review queue) lives separately in
  the framework's DB tables and is not an observability concern.
* **In-process live UI is always on.** A second
  ``WebSocketBroadcastProcessor`` taps the same span stream and
  pushes full ``TraceObservation``-shaped payloads to the UI's
  WebSocket bus. This works regardless of whether a remote OTLP
  backend is configured — the live UI never depends on a backend
  round-trip.
* **No-op when no endpoint set.** If ``OTEL_EXPORTER_OTLP_ENDPOINT``
  is absent, no remote exporter is attached. Spans are still created
  and run through the WS processor (so the in-app live view works
  in headless/dev contexts), but nothing ships off-host.
* **LLM calls and tool calls are instrumented by pydantic-ai** via
  ``Agent.instrument_all()``. Those spans carry standard ``gen_ai.*``
  semantic-convention attributes which Phoenix / Langfuse / Datadog
  all classify as generations server-side. We don't double-instrument.
* **One observer per pipeline run.** ``pipeline.execute()`` constructs
  a ``PipelineObserver``, opens the root span via ``pipeline_run()``,
  and threads the observer through the run. All nested observations
  attach to the active OTEL context implicitly.
"""
from __future__ import annotations

import contextlib
import json as _json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Iterator

from llm_pipeline.utils.json import maybe_parse_json

logger = logging.getLogger(__name__)

__all__ = ["PipelineObserver", "WebSocketBroadcastProcessor", "configure"]


# Module-level flag — idempotency for ``configure()``. The OTEL
# ``TracerProvider`` is a process-wide singleton, and
# ``Agent.instrument_all()`` should only be invoked once per process.
_CONFIGURED = False


# OpenInference span kinds we emit. Phoenix / Langfuse-OSS classify
# observations from this attribute. Pydantic-ai's spans set their own
# ``gen_ai.*`` attributes which the receiving backend classifies
# (LLM / TOOL) without our involvement.
_KIND_CHAIN = "CHAIN"
_KIND_AGENT = "AGENT"
_KIND_TOOL = "TOOL"
_KIND_RETRIEVER = "RETRIEVER"
_KIND_EVALUATOR = "EVALUATOR"


# ---------------------------------------------------------------------------
# Tracer accessor (single source of truth for the framework's spans)
# ---------------------------------------------------------------------------


def _get_tracer():
    """Return the OTEL tracer the framework's spans go through.

    Lives behind a function so tests can replace the provider mid-run
    without us caching a stale reference.
    """
    from opentelemetry import trace as _otel_trace
    return _otel_trace.get_tracer("llm_pipeline")


def _serialize_for_attr(value: Any) -> str | None:
    """JSON-encode an arbitrary value for storage in an OTEL string attribute.

    OTEL attributes can't carry arbitrary Python objects, so structured
    data goes through JSON. ``default=str`` is permissive — datetimes,
    pydantic models, etc. get a string fallback rather than raising.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return _json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def _set_oi_attributes(
    span: Any,
    *,
    span_kind: str,
    input_value: Any = None,
    output_value: Any = None,
    metadata: dict[str, Any] | None = None,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Stamp OpenInference-convention attributes on a span.

    All attribute names follow the OpenInference spec so Phoenix /
    Langfuse-OSS / Arize AX classify the span correctly without
    custom mapping code.
    """
    span.set_attribute("openinference.span.kind", span_kind)
    if session_id is not None:
        span.set_attribute("session.id", session_id)
    if input_value is not None:
        encoded = _serialize_for_attr(input_value)
        if encoded is not None:
            span.set_attribute("input.value", encoded)
            span.set_attribute("input.mime_type", "application/json")
    if output_value is not None:
        encoded = _serialize_for_attr(output_value)
        if encoded is not None:
            span.set_attribute("output.value", encoded)
            span.set_attribute("output.mime_type", "application/json")
    if metadata:
        encoded = _serialize_for_attr(metadata)
        if encoded is not None:
            span.set_attribute("metadata", encoded)
    if extra:
        for k, v in extra.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                span.set_attribute(k, v)
            else:
                encoded = _serialize_for_attr(v)
                if encoded is not None:
                    span.set_attribute(k, encoded)


# ---------------------------------------------------------------------------
# OTEL span processor for live UI updates over WebSocket
# ---------------------------------------------------------------------------


def _extract_run_id_from_span(span: Any) -> str | None:
    """Read the run_id off a span via the OpenInference session_id attribute.

    ``PipelineObserver.pipeline_run`` sets ``session.id = self.run_id``
    on every span it opens. Keeping a fallback to the legacy
    ``langfuse.session.id`` keeps the broadcaster compatible with
    spans produced before the vendor-neutral migration.
    """
    attrs = getattr(span, "attributes", None) or {}
    return (
        attrs.get("session.id")
        or attrs.get("openinference.session.id")
        or attrs.get("langfuse.session.id")
    )


def _span_id_hex(span: Any) -> str:
    """Format an OTEL span_id as a 16-char hex string."""
    sid = span.context.span_id if span.context else 0
    return format(sid, "016x")


def _trace_id_hex(span: Any) -> str:
    """Format an OTEL trace_id as a 32-char hex string."""
    tid = span.context.trace_id if span.context else 0
    return format(tid, "032x")


def _parent_span_id_hex(span: Any) -> str | None:
    """Parent span ID as 16-char hex, or None for root spans."""
    parent = getattr(span, "parent", None)
    if parent is None:
        return None
    sid = getattr(parent, "span_id", 0) or 0
    if sid == 0:
        return None
    return format(sid, "016x")


def _ns_to_iso(ns: int | None) -> str | None:
    """OTEL stamps span times in nanoseconds since epoch (UTC)."""
    if not ns:
        return None
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc).isoformat()


def _classify_observation_type(name: str, attrs: dict) -> str:
    """Mimic Phoenix's / Langfuse's server-side type classification.

    Reads ``openinference.span.kind`` first (set by our own observer),
    falls back to gen_ai-attribute heuristics for spans pydantic-ai
    instruments. Returns one of the labels the frontend's
    ``TraceTimeline`` rendering branches on (SPAN/GENERATION/TOOL).
    """
    oi_kind = attrs.get("openinference.span.kind")
    if oi_kind:
        if oi_kind == "LLM":
            return "GENERATION"
        if oi_kind == "TOOL":
            return "TOOL"
        return "SPAN"

    name_l = (name or "").lower()
    has_gen_ai = any(k.startswith("gen_ai.") for k in attrs)
    if has_gen_ai and (
        "gen_ai.usage.input_tokens" in attrs
        or "gen_ai.usage.output_tokens" in attrs
        or "gen_ai.usage.prompt_tokens" in attrs
        or "gen_ai.usage.completion_tokens" in attrs
        or "gen_ai.request.model" in attrs
        or "gen_ai.response.model" in attrs
        or name_l.startswith("chat ")
    ):
        return "GENERATION"
    if "running tool" in name_l or name_l.startswith("tool "):
        return "TOOL"
    return "SPAN"


def _span_to_observation(span: Any) -> dict[str, Any]:
    """Build a TraceObservation-shaped dict from an OTEL span.

    Field names + shape match what the ``/runs/{run_id}/trace`` route
    returns, so the WS-pushed payload and the HTTP-fetched payload
    merge cleanly in the frontend cache. Reads OpenInference attribute
    conventions first (``input.value``, ``output.value``,
    ``openinference.span.kind``); falls back to legacy
    ``langfuse.observation.*`` and ``gen_ai.*`` aliases for spans
    produced by other instrumentation.
    """
    raw_attrs = getattr(span, "attributes", None) or {}
    attrs: dict[str, Any] = {}
    try:
        for k, v in raw_attrs.items():
            attrs[k] = v
    except Exception:
        attrs = {}

    obs_type = _classify_observation_type(span.name or "", attrs)

    input_tokens = (
        attrs.get("gen_ai.usage.input_tokens")
        or attrs.get("gen_ai.usage.prompt_tokens")
    )
    output_tokens = (
        attrs.get("gen_ai.usage.output_tokens")
        or attrs.get("gen_ai.usage.completion_tokens")
    )
    total_tokens: int | None = None
    if input_tokens is not None or output_tokens is not None:
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    obs_input = maybe_parse_json(
        attrs.get("input.value")
        or attrs.get("langfuse.observation.input")
        or attrs.get("gen_ai.prompt")
    )
    obs_output = maybe_parse_json(
        attrs.get("output.value")
        or attrs.get("langfuse.observation.output")
        or attrs.get("gen_ai.completion")
    )

    model = (
        attrs.get("gen_ai.request.model")
        or attrs.get("gen_ai.response.model")
        or attrs.get("model")
    )

    status_code_name = "UNSET"
    status_message = None
    status = getattr(span, "status", None)
    if status is not None:
        status_code_name = getattr(getattr(status, "status_code", None), "name", "UNSET")
        status_message = getattr(status, "description", None)
    level = "ERROR" if status_code_name == "ERROR" else "DEFAULT"

    start_ns = getattr(span, "start_time", None)
    end_ns = getattr(span, "end_time", None)
    duration_ms: float | None = None
    if start_ns and end_ns:
        duration_ms = (end_ns - start_ns) / 1_000_000.0

    return {
        "id": _span_id_hex(span),
        "parent_observation_id": _parent_span_id_hex(span),
        "trace_id": _trace_id_hex(span),
        "name": span.name or "",
        "type": obs_type,
        "level": level,
        "status_message": status_message,
        "start_time": _ns_to_iso(start_ns),
        "end_time": _ns_to_iso(end_ns),
        "duration_ms": duration_ms,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "total_cost": None,
        "input": obs_input,
        "output": obs_output,
        "metadata": maybe_parse_json(attrs.get("metadata")),
    }


class WebSocketBroadcastProcessor:
    """OTEL ``SpanProcessor`` that pushes full span data to the UI WS bus.

    Acts as the live data feed (not a doorbell): each ``on_start`` /
    ``on_end`` callback ships a complete TraceObservation-shaped
    payload so the frontend can render the trace tree without
    round-tripping the remote OTLP backend. The remote backend (Phoenix,
    Langfuse OSS, etc.) ingests in parallel via the standard OTLP
    exporter and remains the system of record for cost, history,
    search, evals — but the live UX never waits for that backend's
    batch flush.

    Run-id resolution: every span we open carries ``session.id`` set
    explicitly to the run_id. For nested spans created by
    instrumentation we don't control (pydantic-ai's ``chat`` /
    ``running tool`` spans), the attribute may not be present
    directly; we cache ``trace_id -> run_id`` the first time a span
    in a trace exposes the attribute and fall back to the cache for
    nested spans. The cache is cleaned up when the root span ends.

    Thread safety: ``broadcast_to_run`` uses ``queue.Queue.put_nowait``
    which is safe to call from any thread. The trace_id cache is
    guarded by ``threading.Lock`` since OTEL may invoke ``on_start`` /
    ``on_end`` from worker threads.

    No-op when the UI WS module isn't importable (smoke scripts,
    headless deployments).
    """

    def __init__(self) -> None:
        self._trace_to_run: dict[int, str] = {}
        self._lock = threading.Lock()

    # OTEL ``SpanProcessor`` protocol --------------------------------------

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        run_id = self._resolve_run_id(span)
        if not run_id:
            return
        observation = _span_to_observation(span)
        self._broadcast(run_id, {
            "type": "span_started",
            "run_id": run_id,
            "observation": observation,
        })

    def on_end(self, span: Any) -> None:
        run_id = self._resolve_run_id(span)
        if not run_id:
            self._maybe_evict_trace(span)
            return
        observation = _span_to_observation(span)
        self._broadcast(run_id, {
            "type": "span_ended",
            "run_id": run_id,
            "observation": observation,
        })
        self._maybe_evict_trace(span)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True

    # Internals ------------------------------------------------------------

    def _resolve_run_id(self, span: Any) -> str | None:
        """Return run_id for this span, populating + reading the cache."""
        direct = _extract_run_id_from_span(span)
        ctx = getattr(span, "context", None)
        trace_id = getattr(ctx, "trace_id", None) if ctx else None
        if direct:
            if trace_id is not None:
                with self._lock:
                    self._trace_to_run[trace_id] = direct
            return direct
        if trace_id is None:
            return None
        with self._lock:
            return self._trace_to_run.get(trace_id)

    def _maybe_evict_trace(self, span: Any) -> None:
        """Drop the trace_id cache entry when the root span ends."""
        if getattr(span, "parent", None) is not None:
            return
        ctx = getattr(span, "context", None)
        trace_id = getattr(ctx, "trace_id", None) if ctx else None
        if trace_id is None:
            return
        with self._lock:
            self._trace_to_run.pop(trace_id, None)

    @staticmethod
    def _broadcast(run_id: str, message: dict) -> None:
        """Send the message via the UI's WebSocket manager."""
        try:
            from llm_pipeline.ui.routes.websocket import manager
        except ImportError:
            return
        try:
            manager.broadcast_to_run(run_id, message)
        except Exception:
            logger.debug(
                "WebSocketBroadcastProcessor: broadcast failed",
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def _otel_endpoint() -> str | None:
    """The OTLP collector base URL, if configured.

    Reads ``OTEL_EXPORTER_OTLP_ENDPOINT`` (the OpenTelemetry standard
    env var). Returns None when unset — observability runs in-process
    only (live UI works; nothing ships off-host).
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    return endpoint or None


def _normalised_traces_endpoint(endpoint: str) -> str:
    """OTLP HTTP exporter expects the full path including ``/v1/traces``.

    Users typically set the env var to the collector base URL
    (``http://localhost:6006``); accept both forms.
    """
    if endpoint.rstrip("/").endswith("/v1/traces"):
        return endpoint
    return endpoint.rstrip("/") + "/v1/traces"


def configure(
    *,
    instrument_pydantic_ai: bool = True,
    service_name: str = "llm-pipeline",
) -> bool:
    """Bootstrap the OTEL pipeline + pydantic-ai instrumentation.

    Call once at application startup (``llm-pipeline ui`` CLI, smoke
    tests, contract entry points). Subsequent calls are idempotent
    no-ops.

    Always sets up:
        * A process-global ``TracerProvider`` with
          ``service.name=<service_name>`` (used by Phoenix / Langfuse
          to group traces into a project).
        * ``WebSocketBroadcastProcessor`` so the in-app live UI works
          regardless of whether a remote backend is configured.
        * Pydantic-ai instrumentation so LLM calls and tool calls
          produce ``gen_ai.*`` spans that auto-nest under the active
          step span.

    If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, also attaches a
    ``BatchSpanProcessor`` with an HTTP/protobuf OTLP exporter so spans
    ship to the configured backend. Auth / headers come from the
    standard ``OTEL_EXPORTER_OTLP_HEADERS`` env var (key=value,key=value),
    handled by the SDK.

    Args:
        instrument_pydantic_ai: When True (default), call
            ``Agent.instrument_all()`` so every pydantic-ai LLM call
            and tool invocation produces an OTEL generation span.
            Disable only for tests that want to verify the bootstrap
            path without globally instrumenting pydantic-ai.
        service_name: Resource attribute attached to every span the
            framework emits. Most OTEL backends use this to scope
            traces to a project/service.

    Returns:
        Always True (configuration is idempotent — there's nothing to
        fail when the endpoint is absent).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return True

    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # Idempotent against tests that may have already installed a
    # provider; if a real ``TracerProvider`` is already in place, we
    # add our processors to it instead of replacing it.
    current = otel_trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        provider = current
    else:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        otel_trace.set_tracer_provider(provider)

    endpoint = _otel_endpoint()
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        traces_endpoint = _normalised_traces_endpoint(endpoint)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_endpoint))
        )
        logger.info("OTEL exporter configured: %s", traces_endpoint)
    else:
        logger.debug(
            "OTEL_EXPORTER_OTLP_ENDPOINT not set; spans stay in-process "
            "(live UI works, nothing ships off-host)."
        )

    provider.add_span_processor(WebSocketBroadcastProcessor())

    if instrument_pydantic_ai:
        try:
            from pydantic_ai import Agent
            Agent.instrument_all()
        except ImportError:
            logger.debug(
                "pydantic_ai not importable; skipping Agent.instrument_all()"
            )

    _CONFIGURED = True
    return True


# ---------------------------------------------------------------------------
# PipelineObserver
# ---------------------------------------------------------------------------


class PipelineObserver:
    """Vendor-neutral OTEL wrapper for one pipeline run.

    Construct one per ``execute()`` call. Use ``pipeline_run()`` as the
    outermost context manager; nested ``step()`` / ``extraction()`` /
    ``transformation()`` calls auto-attach as children via the active
    OTEL context.

    All spans are stamped with OpenInference semantic conventions so
    Phoenix / Langfuse-OSS / Datadog LLM Observability classify them
    consistently. ``session.id`` set on every span lets the receiving
    backend group all traces of one run (including paused-and-resumed
    runs that span multiple traces).
    """

    def __init__(self, run_id: str, pipeline_name: str) -> None:
        self.run_id = run_id
        self.pipeline_name = pipeline_name

    # ---------------------------------------------------------------
    # Span context managers (operations with duration)
    # ---------------------------------------------------------------

    @contextlib.contextmanager
    def pipeline_run(
        self,
        *,
        input_data: Any = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
        parent_trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> Iterator[Any]:
        """Open the root trace span for this pipeline run.

        Stamps ``session.id`` on the span (and via the trace_id cache
        in ``WebSocketBroadcastProcessor``, on every descendant span)
        so the receiving backend groups the run as one session.

        Resume semantics: when ``parent_trace_id`` and ``parent_span_id``
        are provided (re-execution after a review pause), this method
        does NOT open a new ``pipeline.X`` root span. Instead it
        attaches the OTEL context to the original run's root span (via
        ``SpanContext`` reconstruction + ``context.attach``). Nested
        spans then nest under the original root in the same trace,
        instead of producing a second standalone trace per resume.
        """
        from opentelemetry import context as _otel_context
        from opentelemetry import trace as _otel_trace

        # Resume path: attach to the original trace's root span as the
        # OTEL parent. Skip opening a new pipeline observation so the
        # resumed steps appear directly under the original root.
        if parent_trace_id and parent_span_id:
            from opentelemetry.trace import (
                NonRecordingSpan,
                SpanContext,
                TraceFlags,
            )
            try:
                parent_ctx_obj = SpanContext(
                    trace_id=int(parent_trace_id, 16),
                    span_id=int(parent_span_id, 16),
                    is_remote=True,
                    trace_flags=TraceFlags(0x01),
                )
            except (ValueError, TypeError):
                logger.debug(
                    "pipeline_run: invalid parent IDs trace=%s span=%s; "
                    "falling through to a fresh root span.",
                    parent_trace_id, parent_span_id,
                )
            else:
                ctx = _otel_trace.set_span_in_context(
                    NonRecordingSpan(parent_ctx_obj),
                )
                token = _otel_context.attach(ctx)
                try:
                    yield None
                    self._force_flush()
                    return
                finally:
                    _otel_context.detach(token)

        # First-execution path: open a fresh root span for this run.
        tracer = _get_tracer()
        with tracer.start_as_current_span(f"pipeline.{self.pipeline_name}") as root:
            extra: dict[str, Any] = {}
            if user_id is not None:
                extra["user.id"] = user_id
            tag_list = tags or [self.pipeline_name]
            if tag_list:
                extra["tag.tags"] = list(tag_list)
            _set_oi_attributes(
                root,
                span_kind=_KIND_CHAIN,
                input_value=input_data,
                session_id=self.run_id,
                extra=extra,
            )
            yield root
        self._force_flush()

    @contextlib.contextmanager
    def step(
        self,
        *,
        step_name: str,
        step_number: int,
        instructions_class: str | None = None,
    ) -> Iterator[Any]:
        """Open a span for one step's execution.

        Pydantic-ai LLM-call generations created inside this block
        auto-attach as children via OTEL context. Extraction spans
        opened via ``extraction()`` likewise attach as children.
        """
        tracer = _get_tracer()
        with tracer.start_as_current_span(f"step.{step_name}") as span:
            _set_oi_attributes(
                span,
                span_kind=_KIND_CHAIN,
                input_value={
                    "step_name": step_name,
                    "step_number": step_number,
                    "instructions_class": instructions_class,
                },
                session_id=self.run_id,
            )
            yield span

    @contextlib.contextmanager
    def extraction(
        self,
        *,
        extraction_class: str,
        model_class: str,
    ) -> Iterator[Any]:
        """Open a span for an extraction inside a step."""
        tracer = _get_tracer()
        with tracer.start_as_current_span(f"extraction.{extraction_class}") as span:
            _set_oi_attributes(
                span,
                span_kind=_KIND_CHAIN,
                input_value={
                    "extraction_class": extraction_class,
                    "model_class": model_class,
                },
                session_id=self.run_id,
            )
            yield span

    @contextlib.contextmanager
    def transformation(
        self,
        *,
        transformation_class: str,
    ) -> Iterator[Any]:
        """Open a span for a transformation inside a step."""
        tracer = _get_tracer()
        with tracer.start_as_current_span(
            f"transformation.{transformation_class}"
        ) as span:
            _set_oi_attributes(
                span,
                span_kind=_KIND_CHAIN,
                input_value={"transformation_class": transformation_class},
                session_id=self.run_id,
            )
            yield span

    def review(
        self,
        *,
        step_name: str,
        start_time: datetime,
        end_time: datetime,
        decision: str | None = None,
        notes: str | None = None,
        user_id: str | None = None,
        review_data: Any = None,
        token: str | None = None,
    ) -> None:
        """Emit a backdated span representing a completed human review.

        Open + close in one call with explicit ``start_time`` /
        ``end_time`` (in nanoseconds, OTEL native). Unlike the
        Langfuse SDK, raw OTEL accepts arbitrary timestamps — so the
        span lands at its true position in the trace timeline (the
        wait window between the paused step and the resumed one),
        with the bar width reflecting the actual wait duration.

        Must be called inside the parent-context-attached
        ``pipeline_run`` on a resume so the span nests under the
        original root via the active OTEL context.
        """
        tracer = _get_tracer()
        start_ns = int(start_time.timestamp() * 1_000_000_000)
        end_ns = int(end_time.timestamp() * 1_000_000_000)

        wait_ms = int((end_time - start_time).total_seconds() * 1000)
        metadata: dict[str, Any] = {
            "requested_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "wait_duration_ms": wait_ms,
        }
        if token:
            metadata["token"] = token
        if user_id:
            metadata["user_id"] = user_id

        output: dict[str, Any] = {}
        if decision is not None:
            output["decision"] = decision
        if notes is not None:
            output["notes"] = notes

        span = tracer.start_span(
            name=f"review.{step_name}",
            start_time=start_ns,
        )
        try:
            _set_oi_attributes(
                span,
                span_kind=_KIND_EVALUATOR,
                input_value=review_data,
                output_value=output or None,
                metadata=metadata,
                session_id=self.run_id,
                extra={
                    "review.step_name": step_name,
                    "review.token": token,
                    "review.user_id": user_id,
                    "review.decision": decision,
                },
            )
            if (decision or "").lower() in {"rejected", "fail"}:
                from opentelemetry.trace import Status, StatusCode
                span.set_status(Status(StatusCode.ERROR))
        finally:
            span.end(end_time=end_ns)

    # ---------------------------------------------------------------
    # Span events (point-in-time signals on the active span)
    # ---------------------------------------------------------------

    def cache_lookup(self, *, input_hash: str) -> None:
        self._add_event("cache.lookup", input_hash=input_hash)

    def cache_hit(self, *, input_hash: str) -> None:
        self._add_event("cache.hit", input_hash=input_hash)

    def cache_miss(self, *, input_hash: str) -> None:
        self._add_event("cache.miss", input_hash=input_hash)

    def cache_reconstructed(self, *, input_hash: str) -> None:
        self._add_event("cache.reconstructed", input_hash=input_hash)

    def step_skipped(self, *, reason: str) -> None:
        self._add_event("step.skipped", reason=reason)

    def consensus_attempt(
        self,
        *,
        attempt: int,
        max_attempts: int,
        strategy: str,
    ) -> None:
        self._add_event(
            "consensus.attempt",
            attempt=attempt,
            max_attempts=max_attempts,
            strategy=strategy,
        )

    def consensus_reached(
        self,
        *,
        attempts_used: int,
        agreement: float | None = None,
    ) -> None:
        self._add_event(
            "consensus.reached",
            attempts_used=attempts_used,
            agreement=agreement,
        )

    def consensus_failed(
        self,
        *,
        attempts_used: int,
        reason: str,
    ) -> None:
        self._add_event(
            "consensus.failed",
            attempts_used=attempts_used,
            reason=reason,
        )

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def shutdown(self) -> None:
        """Flush pending spans through every span processor.

        Safe to call multiple times. Should be called at process exit
        (or explicitly at the end of long-running scripts) to ensure
        all buffered spans are shipped to the configured backend.
        """
        self._force_flush()

    # ---------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------

    def _add_event(self, name: str, **attributes: Any) -> None:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span is None or not span.is_recording():
            return
        # OTEL rejects None values; skip keys whose value is None.
        clean = {k: v for k, v in attributes.items() if v is not None}
        span.add_event(name, attributes=clean)

    @staticmethod
    def _force_flush() -> None:
        """Best-effort flush of every span processor on the global provider.

        Replaces the Langfuse SDK's ``client.flush()`` call. The OTEL
        ``TracerProvider`` exposes ``force_flush`` which delegates to
        every attached processor (BatchSpanProcessor, our WS broadcaster,
        anything else). Errors are swallowed — flushing is best-effort.
        """
        try:
            from opentelemetry import trace as _otel_trace
            provider = _otel_trace.get_tracer_provider()
            flush = getattr(provider, "force_flush", None)
            if callable(flush):
                flush()
        except Exception:
            logger.debug("force_flush failed", exc_info=True)
