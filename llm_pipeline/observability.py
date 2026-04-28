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
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = logging.getLogger(__name__)

__all__ = ["PipelineObserver", "configure"]


# Module-level flag — idempotency for ``configure()``. The Langfuse SDK
# is a singleton internally, but ``Agent.instrument_all()`` should only
# be invoked once per process to avoid double-instrumentation.
_CONFIGURED = False


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
    ) -> Iterator[Any]:
        """Open the root trace span for this pipeline run.

        Sets ``session_id = self.run_id`` and ``user_id`` / ``tags`` on
        the underlying Langfuse trace via ``propagate_attributes`` so
        the UI can surface the run in listings. Flushes pending traces
        on exit so they ship before the process can terminate.
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
        with self._client.start_as_current_observation(
            name=f"pipeline.{self.pipeline_name}",
            as_type="span",
            input=input_data,
        ) as root:
            with propagate_attributes(**propagate_kwargs):
                yield root
        self._client.flush()

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
