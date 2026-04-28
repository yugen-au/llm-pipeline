"""Trace endpoint — queries Langfuse for a run's observability data.

The local DB owns operational state (run status, step status,
extractions). Langfuse owns observability (LLM call details, costs,
tokens, prompts/responses, hierarchical span structure).

This endpoint surfaces the Langfuse-side data for a given ``run_id``
without forcing the frontend to talk directly to Langfuse:

- Hides the Langfuse base URL + API keys behind the backend
- Filters/transforms Langfuse's response to a leaner shape suited
  for the run-detail page's timeline + drill-down panels
- Returns a stable structure regardless of whether the run is still
  in flight (Langfuse data may be empty/partial) or terminal

The frontend pairs this endpoint with the WebSocket span-broadcast
stream (``WebSocketBroadcastProcessor``): WS pushes "something
changed" signals; the frontend invalidates and re-fetches via this
route.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.state import PipelineRun
from llm_pipeline.ui.deps import DBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs/{run_id}/trace", tags=["trace"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TraceObservation(BaseModel):
    """One Langfuse observation flattened for the frontend.

    Hierarchy is conveyed via ``parent_observation_id``. The frontend
    builds the tree client-side. ``type`` is the Langfuse observation
    kind (``SPAN`` / ``GENERATION`` / ``EVENT`` / ``TOOL`` / etc.).
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

    # Only set for as_type='generation' (LLM calls)
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None

    input: Any = None
    output: Any = None
    metadata: Any = None


class TraceSummary(BaseModel):
    """One Langfuse trace for a run.

    A run usually maps to a single trace, but a paused-then-resumed
    run produces multiple traces sharing ``session_id == run_id``.
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
    langfuse_configured: bool
    traces: List[TraceSummary]
    # Convenience fan-out: every observation across every trace, ordered
    # by start time. Useful for flat timeline rendering when the
    # frontend doesn't want to walk the per-trace tree.
    observations: List[TraceObservation]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _langfuse_configured() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY")
        and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def _ms_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if start is None or end is None:
        return None
    return (end - start).total_seconds() * 1000.0


def _flatten_observation(raw: Any, trace_id: str) -> TraceObservation:
    """Map a Langfuse SDK observation (Pydantic-ish) to our flat shape.

    The SDK returns ``ObservationsView`` items with snake_case fields.
    Generation-typed observations carry token/cost details; spans don't.
    """
    usage = getattr(raw, "usage_details", None) or {}
    cost = getattr(raw, "cost_details", None) or {}
    return TraceObservation(
        id=raw.id,
        parent_observation_id=getattr(raw, "parent_observation_id", None),
        trace_id=trace_id,
        name=raw.name or "",
        type=str(raw.type),
        level=getattr(raw, "level", None),
        status_message=getattr(raw, "status_message", None),
        start_time=raw.start_time,
        end_time=raw.end_time,
        duration_ms=_ms_between(raw.start_time, raw.end_time),
        model=getattr(raw, "model", None),
        input_tokens=usage.get("input") if isinstance(usage, dict) else None,
        output_tokens=usage.get("output") if isinstance(usage, dict) else None,
        total_tokens=usage.get("total") if isinstance(usage, dict) else None,
        total_cost=cost.get("total") if isinstance(cost, dict) else None,
        input=raw.input,
        output=raw.output,
        metadata=getattr(raw, "metadata", None),
    )


def _fetch_run_traces(run_id: str) -> List[TraceSummary]:
    """Query Langfuse for every trace tied to this run (session_id=run_id).

    Returns [] when Langfuse is unconfigured or has no traces yet (e.g.
    an active run whose spans are still being batched). Errors are
    logged + swallowed so a missing trace never breaks the run-detail
    page.
    """
    if not _langfuse_configured():
        return []

    try:
        from langfuse import Langfuse
    except ImportError:
        return []

    try:
        client = Langfuse()
        # 1. Find trace IDs for this session. The list endpoint returns
        #    minimal stubs (name, observations, input/output are all null)
        #    so we can't render from these directly.
        traces_page = client.api.trace.list(session_id=run_id, limit=50)
        trace_stubs = list(getattr(traces_page, "data", []))
        if not trace_stubs:
            return []

        result: List[TraceSummary] = []
        for stub in trace_stubs:
            # 2. Pull the full trace (with embedded observations carrying
            #    name/input/output/level/usage/cost). The list+get_many
            #    pair returns minimal-only data — `trace.get` is the only
            #    SDK call that gives the full detail shape we render.
            #
            # Race: Langfuse's `trace.list` indexes session_id ahead of
            # the single-trace ingestion pipeline, so a fresh trace can
            # show up in `list` before `get` resolves it (404). Skip
            # per-trace on any SDK error rather than blanking the whole
            # response — the WS-pushed observations already cover the
            # live UI; the next reconcile poll picks up the trace once
            # ingestion catches up.
            try:
                full = client.api.trace.get(trace_id=stub.id)
            except Exception:
                logger.debug(
                    "Langfuse trace.get not ready for trace_id=%s "
                    "(run_id=%s); skipping this poll",
                    stub.id, run_id, exc_info=True,
                )
                continue
            raw_observations = list(getattr(full, "observations", []) or [])
            observations = [_flatten_observation(o, full.id) for o in raw_observations]
            observations.sort(
                key=lambda o: o.start_time or datetime.min,
            )
            total_cost = sum(
                (o.total_cost or 0.0) for o in observations
                if o.total_cost is not None
            ) or None
            result.append(TraceSummary(
                id=full.id,
                name=getattr(full, "name", None),
                user_id=getattr(full, "user_id", None),
                session_id=getattr(full, "session_id", None),
                tags=list(getattr(full, "tags", []) or []),
                start_time=getattr(full, "timestamp", None),
                end_time=None,  # Langfuse trace doesn't have a direct end_time field
                duration_ms=getattr(full, "latency", None) and float(full.latency) * 1000.0,
                total_cost=total_cost,
                observations=observations,
            ))
        # Sort traces by start time
        result.sort(key=lambda tr: tr.start_time or datetime.min)
        return result
    except Exception:
        logger.warning(
            "Failed to fetch Langfuse traces for run_id=%s", run_id,
            exc_info=True,
        )
        return []


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("", response_model=RunTraceResponse)
def get_run_trace(run_id: str, db: DBSession) -> RunTraceResponse:
    """Return Langfuse trace + observation data for a run.

    Operational metadata (status, pipeline name) comes from the local
    DB; the trace data comes from Langfuse. Returns an empty traces
    list (with ``langfuse_configured: false``) if Langfuse credentials
    are absent — keeps the endpoint usable in unconfigured environments.
    """
    run = db.exec(select(PipelineRun).where(PipelineRun.run_id == run_id)).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    traces = _fetch_run_traces(run_id)
    flat_observations: List[TraceObservation] = []
    for tr in traces:
        flat_observations.extend(tr.observations)
    flat_observations.sort(key=lambda o: o.start_time or datetime.min)

    return RunTraceResponse(
        run_id=run_id,
        pipeline_name=run.pipeline_name,
        status=run.status,
        langfuse_configured=_langfuse_configured(),
        traces=traces,
        observations=flat_observations,
    )
