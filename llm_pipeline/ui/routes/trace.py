"""Trace endpoint — fetches a run's observations from the OTEL backend.

The local DB owns operational state (run status, step status,
extractions). The OTEL backend (Arize Phoenix by default; any
OpenInference-compatible store works) owns observability — LLM call
details, tokens, prompts/responses, hierarchical span structure.

This endpoint hides the backend's URL + auth behind the FastAPI app and
flattens the response into a shape the frontend's ``TraceTimeline``
renders directly. Live updates land via the WebSocket span-broadcast
stream; this endpoint is the reconcile path that fills in anything WS
missed and the canonical post-run history.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.state import PipelineRun
from llm_pipeline.ui.deps import DBSession
from llm_pipeline.utils.json import maybe_parse_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs/{run_id}/trace", tags=["trace"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TraceObservation(BaseModel):
    """One observation flattened for the frontend.

    Hierarchy is conveyed via ``parent_observation_id``. The frontend
    builds the tree client-side. ``type`` is the rendered observation
    kind (``SPAN`` / ``GENERATION`` / ``TOOL``) classified from
    OpenInference / gen_ai attributes server-side here so the frontend
    doesn't need to know about either convention.
    """
    id: str
    parent_observation_id: Optional[str] = None
    trace_id: str
    name: str
    type: str
    level: Optional[str] = None
    status_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None

    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None

    input: Any = None
    output: Any = None
    metadata: Any = None


class TraceSummary(BaseModel):
    """One trace for a run.

    A run usually maps to a single trace, but a paused-then-resumed run
    that didn't re-attach the parent context produces multiple traces
    sharing ``session.id == run_id``.
    """
    id: str
    name: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: List[str] = []
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    total_cost: Optional[float] = None
    observations: List[TraceObservation] = []


class RunTraceResponse(BaseModel):
    """Trace data for a run, plus operational metadata pulled from local DB."""
    run_id: str
    pipeline_name: str
    status: str
    # True when a backend URL is configured (e.g. Phoenix is running).
    # The frontend uses this to decide between "waiting for first span"
    # and "no backend, observability disabled" empty states.
    trace_backend_configured: bool
    traces: List[TraceSummary]
    # Convenience fan-out: every observation across every trace, ordered
    # by start time. Useful for flat timeline rendering when the
    # frontend doesn't want to walk the per-trace tree.
    observations: List[TraceObservation]


# ---------------------------------------------------------------------------
# Backend configuration
# ---------------------------------------------------------------------------


def _phoenix_base_url() -> Optional[str]:
    """Resolve the Phoenix HTTP base URL.

    Order:
      1. Explicit ``PHOENIX_BASE_URL`` (e.g. ``http://localhost:6006``).
      2. Derived from ``OTEL_EXPORTER_OTLP_ENDPOINT`` (strip
         ``/v1/traces`` if present) — convenient for setups where the
         same host runs OTLP ingest + the Phoenix REST API on the
         same port (the standard self-hosted topology).

    Returns None when no backend is configured.
    """
    explicit = os.environ.get("PHOENIX_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    otlp = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if otlp:
        base = otlp.rstrip("/")
        if base.endswith("/v1/traces"):
            base = base[: -len("/v1/traces")]
        return base
    return None


def _phoenix_project() -> str:
    """Project name to query traces under. Phoenix auto-creates ``default``."""
    return os.environ.get("PHOENIX_PROJECT", "default")


def _trace_backend_configured() -> bool:
    return _phoenix_base_url() is not None


def _phoenix_headers() -> Dict[str, str]:
    """Auth headers for Phoenix Cloud; empty for self-hosted with no auth."""
    headers: Dict[str, str] = {}
    api_key = os.environ.get("PHOENIX_API_KEY", "").strip()
    if api_key:
        # Phoenix Cloud expects the API key in this header. Self-hosted
        # without auth ignores it.
        headers["api_key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


# ---------------------------------------------------------------------------
# Span -> TraceObservation mapping (Phoenix REST shape)
# ---------------------------------------------------------------------------


def _ms_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if start is None or end is None:
        return None
    return (end - start).total_seconds() * 1000.0


def _parse_iso(value: Any) -> Optional[datetime]:
    """Phoenix returns ISO 8601 strings; coerce to timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        # ``fromisoformat`` accepts trailing 'Z' on Python 3.11+.
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _classify_observation_type(name: str, attrs: dict) -> str:
    """Mirror the WS processor's classification so live + reconciled
    observations share the same ``type`` string regardless of where
    they came from."""
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


def _phoenix_span_to_observation(
    span: dict, trace_id: str, id_to_span_id: Dict[str, str],
) -> TraceObservation:
    """Map a Phoenix REST span to our flat observation shape.

    Phoenix's ``parent_id`` is its internal span identifier, which may
    or may not equal the OTEL span_id depending on the shape Phoenix
    chooses to expose. The mapping is robust either way: we build
    ``id_to_span_id`` across all spans in the trace and look up
    ``parent_id`` against it. If the lookup misses we fall back to
    using ``parent_id`` directly (covers the case where Phoenix
    already exposes OTEL span_ids).
    """
    attrs = span.get("attributes") or {}
    if not isinstance(attrs, dict):
        attrs = {}

    name = span.get("name") or ""
    obs_type = _classify_observation_type(name, attrs)

    # Token counts come from gen_ai.usage.* attributes.
    input_tokens = (
        attrs.get("gen_ai.usage.input_tokens")
        or attrs.get("gen_ai.usage.prompt_tokens")
    )
    output_tokens = (
        attrs.get("gen_ai.usage.output_tokens")
        or attrs.get("gen_ai.usage.completion_tokens")
    )
    total_tokens: Optional[int] = None
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

    status = (span.get("status_code") or "UNSET").upper()
    level = "ERROR" if status == "ERROR" else "DEFAULT"

    start_time = _parse_iso(span.get("start_time"))
    end_time = _parse_iso(span.get("end_time"))

    context = span.get("context") or {}
    span_id = context.get("span_id") or span.get("id") or ""

    parent_phoenix_id = span.get("parent_id")
    parent_observation_id: Optional[str] = None
    if parent_phoenix_id:
        parent_observation_id = (
            id_to_span_id.get(parent_phoenix_id) or parent_phoenix_id
        )

    return TraceObservation(
        id=span_id,
        parent_observation_id=parent_observation_id,
        trace_id=trace_id,
        name=name,
        type=obs_type,
        level=level,
        status_message=span.get("status_message") or None,
        start_time=start_time,
        end_time=end_time,
        duration_ms=_ms_between(start_time, end_time),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        total_cost=None,  # Phoenix doesn't compute cost server-side.
        input=obs_input,
        output=obs_output,
        metadata=maybe_parse_json(attrs.get("metadata")),
    )


# ---------------------------------------------------------------------------
# Phoenix REST fetch
# ---------------------------------------------------------------------------


def _fetch_run_traces(run_id: str) -> List[TraceSummary]:
    """Query Phoenix for every trace tied to this run (session.id=run_id).

    Returns [] when no backend is configured or the project has no
    traces yet (e.g. an active run whose spans are still being
    batched). Errors are logged + swallowed so a missing trace never
    breaks the run-detail page.
    """
    base_url = _phoenix_base_url()
    if base_url is None:
        return []
    project = _phoenix_project()
    url = f"{base_url}/v1/projects/{project}/traces"
    params = {"session_identifier": run_id, "include_spans": "true"}

    try:
        with httpx.Client(timeout=5.0, headers=_phoenix_headers()) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 404:
                # Project doesn't exist yet (no spans ever ingested).
                return []
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "Failed to fetch traces from Phoenix at %s for run_id=%s: %s",
            base_url, run_id, exc,
        )
        return []

    raw_traces = payload.get("data") or []
    result: List[TraceSummary] = []
    for raw in raw_traces:
        trace_id = raw.get("trace_id") or raw.get("id") or ""
        spans = raw.get("spans") or []

        # Build a phoenix-id -> otel span_id map for parent resolution.
        id_to_span_id: Dict[str, str] = {}
        for s in spans:
            phoenix_id = s.get("id")
            otel_span_id = (s.get("context") or {}).get("span_id")
            if phoenix_id and otel_span_id:
                id_to_span_id[phoenix_id] = otel_span_id

        observations = [
            _phoenix_span_to_observation(s, trace_id, id_to_span_id)
            for s in spans
        ]
        observations.sort(
            key=lambda o: o.start_time or datetime.min.replace(tzinfo=timezone.utc),
        )

        # Trace-level rollups derived from the spans themselves.
        start = _parse_iso(raw.get("start_time"))
        end = _parse_iso(raw.get("end_time"))
        duration_ms = _ms_between(start, end)

        # session.id and tags are typically on the root span's
        # attributes, not the trace envelope. Hoist them up.
        root_attrs: dict = {}
        for s in spans:
            if not s.get("parent_id"):
                root_attrs = s.get("attributes") or {}
                break
        tags_raw = root_attrs.get("tag.tags")
        if isinstance(tags_raw, str):
            tags = list(maybe_parse_json(tags_raw)) if tags_raw else []
        elif isinstance(tags_raw, list):
            tags = list(tags_raw)
        else:
            tags = []
        if not isinstance(tags, list):
            tags = []
        tags = [str(t) for t in tags if t is not None]

        result.append(TraceSummary(
            id=trace_id,
            name=root_attrs.get("name") or (spans[0].get("name") if spans else None),
            user_id=root_attrs.get("user.id"),
            session_id=root_attrs.get("session.id") or run_id,
            tags=tags,
            start_time=start,
            end_time=end,
            duration_ms=duration_ms,
            total_cost=None,
            observations=observations,
        ))

    result.sort(
        key=lambda tr: tr.start_time or datetime.min.replace(tzinfo=timezone.utc),
    )
    return result


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("", response_model=RunTraceResponse)
def get_run_trace(run_id: str, db: DBSession) -> RunTraceResponse:
    """Return trace + observation data for a run.

    Operational metadata (status, pipeline name) comes from the local
    DB; the trace data comes from the configured OTEL backend (Phoenix
    by default). Returns an empty traces list (with
    ``trace_backend_configured: false``) if no backend URL is set —
    keeps the endpoint usable in unconfigured environments.
    """
    run = db.exec(select(PipelineRun).where(PipelineRun.run_id == run_id)).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    traces = _fetch_run_traces(run_id)
    flat_observations: List[TraceObservation] = []
    for tr in traces:
        flat_observations.extend(tr.observations)
    flat_observations.sort(
        key=lambda o: o.start_time or datetime.min.replace(tzinfo=timezone.utc),
    )

    return RunTraceResponse(
        run_id=run_id,
        pipeline_name=run.pipeline_name,
        status=run.status,
        trace_backend_configured=_trace_backend_configured(),
        traces=traces,
        observations=flat_observations,
    )
