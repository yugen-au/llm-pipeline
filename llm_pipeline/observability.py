"""Langfuse-backed pipeline observability.

Replaces the legacy ``llm_pipeline.events`` module. ``PipelineObserver``
is a thin domain wrapper around the Langfuse v4 SDK that exposes
context managers for spans (pipeline run, step, extraction,
transformation) and methods for point-in-time span events (cache
hits, consensus attempts, etc.).

Design contract:

* **Single sink, no fanout.** Langfuse is the only observability
  backend. There is no event handler abstraction, no event emitter
  protocol, no in-process event types. Operational state (run status,
  review queue) lives separately in the framework's DB tables and is
  not an observability concern.
* **No-op when credentials are absent.** If ``LANGFUSE_PUBLIC_KEY`` or
  ``LANGFUSE_SECRET_KEY`` are not set in the environment, every
  observer method becomes a silent no-op and context managers yield
  ``None``. This keeps tests and local development running without a
  Langfuse account.
* **LLM calls and tool calls are instrumented by pydantic-ai**, not
  by this observer. ``Agent.instrument_all()`` (wired at framework
  bootstrap) makes every ``Agent.run()`` emit an OTEL generation that
  auto-attaches to whichever step span is currently active via OTEL
  context propagation. We do not double-instrument those.
* **One observer per pipeline run.** ``pipeline.execute()``
  constructs a ``PipelineObserver``, opens the root span via
  ``pipeline_run()``, and threads the observer through the run. All
  nested observations (step spans, extraction spans, span events)
  attach to the active OTEL context implicitly — no manual
  parent-passing required.
"""
from __future__ import annotations

import contextlib
import logging
import os
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterator

from llm_pipeline.utils.json import maybe_parse_json

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = logging.getLogger(__name__)

__all__ = ["PipelineObserver", "WebSocketBroadcastProcessor", "configure"]


# Module-level flag — idempotency for ``configure()``. The Langfuse SDK
# is a singleton internally, but ``Agent.instrument_all()`` should only
# be invoked once per process to avoid double-instrumentation.
_CONFIGURED = False


# ---------------------------------------------------------------------------
# OTEL span processor for live UI updates over WebSocket
# ---------------------------------------------------------------------------


def _extract_run_id_from_span(span: Any) -> str | None:
    """Read the run_id off a span via the Langfuse session_id attribute.

    ``PipelineObserver.pipeline_run`` calls ``langfuse.propagate_attributes
    (session_id=run_id, ...)`` which sets ``langfuse.session.id`` on every
    descendant span. Reading that attribute lets the processor route the
    broadcast to subscribers of the right run — without the framework
    having to thread run_id through the span machinery itself.
    """
    attrs = getattr(span, "attributes", None) or {}
    return attrs.get("langfuse.session.id") or attrs.get("session.id")


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
    """Mimic Langfuse's server-side type classification locally.

    Langfuse buckets observations into SPAN/GENERATION/TOOL/EVENT/etc. based
    on ``gen_ai.*`` attributes + name conventions. The frontend's existing
    rendering paths key off this field, so the WS-pushed payload must match
    what Langfuse would have produced server-side.
    """
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

    Mirrors what the ``/runs/{run_id}/trace`` route returns after
    Langfuse fetch (minus ``total_cost``, which Langfuse computes
    server-side from its pricing table — fills in on the next reconcile
    poll). Field names are snake_case to match the frontend's
    ``TraceObservation`` interface.
    """
    raw_attrs = getattr(span, "attributes", None) or {}
    # Snapshot attrs to a plain dict — OTEL's BoundedAttributes proxy
    # isn't a dict and doesn't survive `dict(...)` semantics on every
    # platform.
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
        attrs.get("langfuse.observation.input")
        or attrs.get("input.value")
        or attrs.get("gen_ai.prompt")
    )
    obs_output = maybe_parse_json(
        attrs.get("langfuse.observation.output")
        or attrs.get("output.value")
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
        "metadata": None,
    }


class WebSocketBroadcastProcessor:
    """OTEL ``SpanProcessor`` that pushes full span data to the UI WS bus.

    Acts as the live data feed (not a doorbell): each ``on_start`` /
    ``on_end`` callback ships a complete TraceObservation-shaped payload
    so the frontend can render the trace tree without round-tripping
    Langfuse. Langfuse's API ingest still happens in parallel (via its
    own SpanProcessor) and remains the system of record for cost,
    history, search, evals — but the live UX never waits for the
    Langfuse batch flush.

    Run-id resolution:
        ``langfuse.propagate_attributes(session_id=run_id, ...)``
        attaches ``langfuse.session.id`` to spans created within its
        context. In practice not every nested span carries the
        attribute directly (depends on baggage propagation timing), so
        we cache ``trace_id -> run_id`` the first time a span in a
        trace exposes the attribute and fall back to the cache for
        nested spans. The cache is cleaned up when the root span ends.

    Thread safety: ``broadcast_to_run`` uses ``queue.Queue.put_nowait``
    which is safe to call from any thread. The trace_id cache is
    guarded by a ``threading.Lock`` since OTEL may invoke ``on_start``
    / ``on_end`` from worker threads (pydantic-ai async dispatch, span
    closer threads, etc.).

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
        """Return run_id for this span, populating + reading the cache.

        Direct attribute wins; trace_id cache is the fallback for nested
        spans where ``propagate_attributes`` hasn't materialised the
        ``langfuse.session.id`` attribute on the span itself.
        """
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
        """Drop the trace_id cache entry when the root span ends.

        Prevents the map from growing unbounded across many runs.
        Detects the root by absence of a parent SpanContext.
        """
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
        """Send the message via the UI's WebSocket manager.

        Lazy import + try/except keeps this processor safe to run in
        environments without the UI subsystem (smoke scripts, headless
        contract jobs).
        """
        try:
            from llm_pipeline.ui.routes.websocket import manager
        except ImportError:
            return
        try:
            manager.broadcast_to_run(run_id, message)
        except Exception:
            # Never propagate WS errors out of the OTEL pipeline — they
            # would taint the parent operation. Best-effort delivery.
            logger.debug(
                "WebSocketBroadcastProcessor: broadcast failed",
                exc_info=True,
            )


def configure(
    *,
    instrument_pydantic_ai: bool = True,
    environment: str | None = None,
    release: str | None = None,
    sample_rate: float | None = None,
) -> bool:
    """Bootstrap Langfuse + pydantic-ai instrumentation for the process.

    Call once at application startup (``llm-pipeline ui`` CLI, smoke
    tests, contract entry points). Subsequent calls are idempotent
    no-ops.

    No-op when ``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY`` are
    absent. This preserves the framework-wide contract that observability
    is opt-in via environment variables — local dev and tests run
    without it, no instrumentation overhead, no warning spam.

    Order matters: Langfuse must be instantiated *before* ``Agent.
    instrument_all()`` so the Langfuse SDK sets up the OTEL tracer
    provider that pydantic-ai then attaches to.

    Args:
        instrument_pydantic_ai: When True (default), call
            ``Agent.instrument_all()`` so every pydantic-ai LLM call
            and tool invocation produces an OTEL generation span that
            auto-nests under the active step span. Disable only for
            tests that want to verify the bootstrap path without
            globally instrumenting pydantic-ai.
        environment: Tags traces with the deployment environment
            (``production`` / ``staging`` / ``smoke-test``).
        release: Tracks the application release/version on traces.
        sample_rate: Trace sampling rate (0.0–1.0). Use for high-volume
            production where shipping every trace is wasteful. Do NOT
            use during eval / variant comparison runs — sampling
            defeats statistical significance.

    Returns:
        True if Langfuse was configured (creds present and SDK
        initialized). False if the call was a no-op (creds absent).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return True
    if not _credentials_present():
        logger.debug(
            "llm_pipeline.observability.configure(): credentials absent, "
            "skipping Langfuse + pydantic-ai instrumentation."
        )
        return False

    from langfuse import Langfuse

    init_kwargs: dict[str, Any] = {}
    if environment is not None:
        init_kwargs["environment"] = environment
    if release is not None:
        init_kwargs["release"] = release
    if sample_rate is not None:
        init_kwargs["sample_rate"] = sample_rate
    Langfuse(**init_kwargs)

    if instrument_pydantic_ai:
        from pydantic_ai import Agent
        Agent.instrument_all()

    # Tap the same OTEL tracer provider Langfuse just configured: same
    # spans, two consumers. Langfuse stores them; our processor pushes
    # lightweight live signals to the UI WebSocket. No parallel emit
    # machinery — OTEL is the single source of truth.
    try:
        from opentelemetry import trace as _trace
        provider = _trace.get_tracer_provider()
        # Some no-op providers (and the pre-Langfuse default) don't
        # implement add_span_processor. Skip silently in those cases.
        add_processor = getattr(provider, "add_span_processor", None)
        if callable(add_processor):
            add_processor(WebSocketBroadcastProcessor())
    except Exception:
        logger.debug(
            "Failed to attach WebSocketBroadcastProcessor; live UI "
            "updates over WebSocket will be unavailable.",
            exc_info=True,
        )

    _CONFIGURED = True
    logger.info("Langfuse + pydantic-ai instrumentation configured.")
    return True


def _credentials_present() -> bool:
    """True iff both Langfuse keys are set in the environment.

    The base URL has a built-in default (EU cloud) so we don't require
    it to be set explicitly.
    """
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY")
        and os.environ.get("LANGFUSE_SECRET_KEY")
    )


class PipelineObserver:
    """Domain wrapper around the Langfuse v4 SDK for one pipeline run.

    Construct one per ``execute()`` call. Use ``pipeline_run()`` as the
    outermost context manager; nested ``step()`` / ``extraction()`` /
    ``transformation()`` calls attach automatically via OTEL context.

    When Langfuse credentials are absent, every method is a no-op and
    every context manager yields ``None``.
    """

    def __init__(self, run_id: str, pipeline_name: str) -> None:
        self.run_id = run_id
        self.pipeline_name = pipeline_name
        self._enabled = _credentials_present()
        self._client: "Langfuse | None" = None
        if self._enabled:
            from langfuse import Langfuse
            self._client = Langfuse()

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

        Sets ``session_id = self.run_id`` and ``user_id`` / ``tags`` on
        the underlying Langfuse trace via ``propagate_attributes`` so
        the UI can surface the run in listings. Flushes pending traces
        on exit so they ship before the process can terminate.

        Resume semantics: when ``parent_trace_id`` and ``parent_span_id``
        are provided (re-execution after a review pause), this method
        does NOT open a new ``pipeline.X`` root span. Instead it
        attaches the OTEL context to the original run's root span (via
        ``SpanContext`` reconstruction + ``context.attach``). New step
        / extraction spans opened inside the with-block then nest under
        the original root in the same trace, instead of producing a
        second standalone trace per resume.
        """
        if not self._enabled:
            yield None
            return
        assert self._client is not None
        from langfuse import propagate_attributes

        # Build kwargs dropping None so the SDK uses its own defaults
        # rather than recording an explicit-None attribute.
        propagate_kwargs: dict[str, Any] = {"session_id": self.run_id}
        if user_id is not None:
            propagate_kwargs["user_id"] = user_id
        propagate_kwargs["tags"] = tags or [self.pipeline_name]

        # Resume path: attach to the original trace's root span as
        # OTEL parent. Skip opening a new pipeline observation so the
        # resumed steps appear directly under the original root.
        if parent_trace_id and parent_span_id:
            from opentelemetry import context as _otel_context
            from opentelemetry import trace as _otel_trace
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
                    with propagate_attributes(**propagate_kwargs):
                        yield None
                    self._client.flush()
                    return
                finally:
                    _otel_context.detach(token)

        # First-execution path: open a fresh root span for this run.
        with self._client.start_as_current_observation(
            name=f"pipeline.{self.pipeline_name}",
            as_type="span",
            input=input_data,
        ) as root:
            with propagate_attributes(**propagate_kwargs):
                yield root
        self._client.flush()

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
        """Emit a span representing a completed human review.

        Opens + closes a Langfuse span via the SDK wrapper (raw OTEL
        spans aren't ingested by Langfuse's processor — only spans
        created through ``start_observation`` are picked up). Must be
        called inside the parent-context-attached ``pipeline_run`` on
        a resume so the span nests under the original root via the
        active OTEL context.

        The Langfuse SDK doesn't accept an explicit ``start_time``, so
        the span's wall-clock position is "now" (at review submission)
        rather than the actual wait window. The wait period is
        preserved on the observation as metadata: ``requested_at``,
        ``completed_at`` and ``wait_duration_ms``. The review thus
        renders as a single visible step in the trace at submission
        time, with the wait duration available on click-through.

        No-op when Langfuse is unconfigured.
        """
        if not self._enabled:
            return
        assert self._client is not None

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

        span = self._client.start_observation(
            name=f"review.{step_name}",
            as_type="span",
            input=review_data,
            output=output or None,
            metadata=metadata,
            level="ERROR" if (decision or "").lower() in {"rejected", "fail"} else None,
        )
        try:
            span.end()
        except Exception:
            logger.debug(
                "Failed to end review span for step=%s token=%s",
                step_name, token, exc_info=True,
            )

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
        created via ``extraction()`` likewise attach as children.
        """
        if not self._enabled:
            yield None
            return
        assert self._client is not None
        with self._client.start_as_current_observation(
            name=f"step.{step_name}",
            as_type="span",
            input={
                "step_name": step_name,
                "step_number": step_number,
                "instructions_class": instructions_class,
            },
        ) as span:
            yield span

    @contextlib.contextmanager
    def extraction(
        self,
        *,
        extraction_class: str,
        model_class: str,
    ) -> Iterator[Any]:
        """Open a span for an extraction inside a step."""
        if not self._enabled:
            yield None
            return
        assert self._client is not None
        with self._client.start_as_current_observation(
            name=f"extraction.{extraction_class}",
            as_type="span",
            input={
                "extraction_class": extraction_class,
                "model_class": model_class,
            },
        ) as span:
            yield span

    @contextlib.contextmanager
    def transformation(
        self,
        *,
        transformation_class: str,
    ) -> Iterator[Any]:
        """Open a span for a transformation inside a step."""
        if not self._enabled:
            yield None
            return
        assert self._client is not None
        with self._client.start_as_current_observation(
            name=f"transformation.{transformation_class}",
            as_type="span",
            input={"transformation_class": transformation_class},
        ) as span:
            yield span

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
        """Flush and shut down the Langfuse client.

        Safe to call multiple times. Should be called at process exit
        (or explicitly at the end of long-running scripts) to ensure
        all buffered traces are shipped.
        """
        if self._client is not None:
            self._client.flush()
            self._client.shutdown()
            self._client = None

    # ---------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------

    def _add_event(self, name: str, **attributes: Any) -> None:
        if not self._enabled:
            return
        from opentelemetry import trace
        span = trace.get_current_span()
        # OTEL rejects None values; skip keys whose value is None.
        clean = {k: v for k, v in attributes.items() if v is not None}
        span.add_event(name, attributes=clean)
