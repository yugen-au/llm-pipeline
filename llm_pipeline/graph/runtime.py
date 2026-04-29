"""Runtime entry points for pydantic-graph-native pipelines.

Two surfaces:

- ``run_pipeline_in_memory`` — Phase-1 verification helper. Uses
  ``SimpleStatePersistence`` (no DB). Exists for unit tests and the
  smoke script.

- ``run_pipeline`` / ``resume_pipeline`` — the DB-backed runtime that
  the UI's ``POST /api/runs`` and ``POST /api/reviews/{token}`` call.
  Writes node snapshots to ``pipeline_node_snapshots`` via
  ``SqlmodelStatePersistence``; updates ``PipelineRun.status``;
  honours the pause-for-review flag set by ``ReviewNode``.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from pydantic_graph import End

from llm_pipeline.graph.state import PipelineDeps, PipelineState

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlmodel import Session

    from llm_pipeline.graph.pipeline import Pipeline
    from llm_pipeline.state import PipelineRun


logger = logging.getLogger(__name__)


__all__ = [
    "RunOutcome",
    "resume_pipeline",
    "run_pipeline",
    "run_pipeline_in_memory",
]


class RunOutcome:
    """Sentinel statuses for ``run_pipeline`` / ``resume_pipeline`` results."""

    COMPLETED = "completed"
    AWAITING_REVIEW = "awaiting_review"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Phase-1 in-memory runtime (kept for tests + smoke)
# ---------------------------------------------------------------------------


async def run_pipeline_in_memory(
    pipeline_cls: type["Pipeline"],
    input_data: dict[str, Any] | None = None,
    *,
    model: str,
    session: "Session | None" = None,
    engine: "Engine | None" = None,
    run_id: str | None = None,
    instrumentation_settings: Any | None = None,
) -> tuple[PipelineState, Any]:
    """Run ``pipeline_cls`` to completion using in-memory persistence.

    Returns ``(final_state, end_payload)``. Does not write to the
    pipeline DB tables; useful for unit tests and the smoke script.
    """
    from sqlmodel import Session

    from llm_pipeline.db import init_pipeline_db
    from llm_pipeline.prompts.service import PromptService

    input_cls = pipeline_cls.INPUT_DATA
    validated_input_dump = _validate_input(pipeline_cls, input_cls, input_data)

    if session is None:
        if engine is None:
            engine = init_pipeline_db()
        else:
            init_pipeline_db(engine)
        session = Session(engine)
        owns_session = True
    else:
        owns_session = False

    state = PipelineState(input_data=validated_input_dump)
    deps = PipelineDeps(
        session=session,
        prompt_service=PromptService(),
        run_id=run_id or str(uuid.uuid4()),
        pipeline_name=pipeline_cls.pipeline_name(),
        model=model,
        input_cls=input_cls,
        node_classes=dict(pipeline_cls._node_classes),
        instrumentation_settings=instrumentation_settings,
    )

    graph = pipeline_cls.graph()
    start_node_cls = pipeline_cls.start_node
    if start_node_cls is None:
        raise RuntimeError(
            f"{pipeline_cls.__name__}.start_node is None — declare nodes "
            f"or set start_node explicitly."
        )

    try:
        result = await graph.run(start_node_cls(), state=state, deps=deps)
    finally:
        if owns_session:
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise
            session.close()

    return result.state, result.output


# ---------------------------------------------------------------------------
# DB-backed runtime (Phase 2)
# ---------------------------------------------------------------------------


async def run_pipeline(
    pipeline_cls: type["Pipeline"],
    input_data: dict[str, Any] | None = None,
    *,
    model: str,
    engine: "Engine",
    run_id: str | None = None,
    instrumentation_settings: Any | None = None,
) -> "PipelineRun":
    """Run ``pipeline_cls`` to completion or pause-for-review.

    Writes node snapshots to ``pipeline_node_snapshots`` and updates
    the ``PipelineRun`` row's status. On a pause-for-review the next
    node's snapshot is left in ``'created'`` status so
    ``resume_pipeline`` can pick up via ``Graph.iter_from_persistence``.
    """
    from llm_pipeline.graph.persistence import SqlmodelStatePersistence
    from llm_pipeline.prompts.service import PromptService
    from sqlmodel import Session

    input_cls = pipeline_cls.INPUT_DATA
    validated_input_dump = _validate_input(pipeline_cls, input_cls, input_data)

    pipeline_run = _ensure_pipeline_run(
        engine=engine,
        pipeline_name=pipeline_cls.pipeline_name(),
        run_id=run_id,
    )

    state = PipelineState(input_data=validated_input_dump)
    session_for_deps = Session(engine)
    deps = PipelineDeps(
        session=session_for_deps,
        prompt_service=PromptService(),
        run_id=pipeline_run.run_id,
        pipeline_name=pipeline_cls.pipeline_name(),
        model=model,
        input_cls=input_cls,
        node_classes=dict(pipeline_cls._node_classes),
        instrumentation_settings=instrumentation_settings,
    )

    persistence = SqlmodelStatePersistence(
        engine=engine,
        run_id=pipeline_run.run_id,
        pipeline_name=pipeline_cls.pipeline_name(),
        nodes=list(pipeline_cls.nodes),
    )

    start_node_cls = pipeline_cls.start_node
    if start_node_cls is None:
        raise RuntimeError(f"{pipeline_cls.__name__}.start_node is None.")

    final_status = RunOutcome.COMPLETED
    error_message: str | None = None
    try:
        graph = pipeline_cls.graph()
        async with graph.iter(
            start_node_cls(), state=state, deps=deps, persistence=persistence,
        ) as graph_run:
            async for _node in graph_run:
                if state.metadata.get("awaiting_review"):
                    final_status = RunOutcome.AWAITING_REVIEW
                    break
                if isinstance(_node, End):
                    break
    except Exception as exc:
        logger.exception(
            "Pipeline run failed: pipeline=%s run_id=%s",
            pipeline_cls.__name__, pipeline_run.run_id,
        )
        final_status = RunOutcome.FAILED
        error_message = f"{type(exc).__name__}: {exc}"[:2000]
    finally:
        try:
            session_for_deps.commit()
        except Exception:
            session_for_deps.rollback()
        session_for_deps.close()

    return _finalise_pipeline_run(
        engine=engine,
        run_id=pipeline_run.run_id,
        status=final_status,
        error_message=error_message,
    )


async def resume_pipeline(
    pipeline_cls: type["Pipeline"],
    *,
    run_id: str,
    model: str,
    engine: "Engine",
    metadata_patch: dict[str, Any] | None = None,
    instrumentation_settings: Any | None = None,
) -> "PipelineRun":
    """Continue a paused-for-review run from its persisted snapshot.

    ``metadata_patch`` is merged into ``state.metadata`` before resume —
    use it to feed reviewer feedback through to the post-review step
    (e.g. ``{"review_decision": "approved", "review_notes": "..."}``).
    Clears the ``awaiting_review`` flag so the loop runs to completion.
    """
    from llm_pipeline.graph.persistence import SqlmodelStatePersistence
    from llm_pipeline.prompts.service import PromptService
    from sqlmodel import Session

    pipeline_run = _ensure_pipeline_run(
        engine=engine,
        pipeline_name=pipeline_cls.pipeline_name(),
        run_id=run_id,
    )

    persistence = SqlmodelStatePersistence(
        engine=engine,
        run_id=pipeline_run.run_id,
        pipeline_name=pipeline_cls.pipeline_name(),
        nodes=list(pipeline_cls.nodes),
    )

    session_for_deps = Session(engine)
    deps = PipelineDeps(
        session=session_for_deps,
        prompt_service=PromptService(),
        run_id=pipeline_run.run_id,
        pipeline_name=pipeline_cls.pipeline_name(),
        model=model,
        input_cls=pipeline_cls.INPUT_DATA,
        node_classes=dict(pipeline_cls._node_classes),
        instrumentation_settings=instrumentation_settings,
        review_context=metadata_patch.copy() if metadata_patch else None,
    )

    final_status = RunOutcome.COMPLETED
    error_message: str | None = None
    try:
        graph = pipeline_cls.graph()
        async with graph.iter_from_persistence(
            persistence, deps=deps,
        ) as graph_run:
            # Apply metadata patch to the rehydrated state before iter advances.
            if metadata_patch:
                graph_run.state.metadata.update(metadata_patch)
            graph_run.state.metadata.pop("awaiting_review", None)

            async for _node in graph_run:
                if graph_run.state.metadata.get("awaiting_review"):
                    final_status = RunOutcome.AWAITING_REVIEW
                    break
                if isinstance(_node, End):
                    break
    except Exception as exc:
        logger.exception(
            "Pipeline resume failed: pipeline=%s run_id=%s",
            pipeline_cls.__name__, pipeline_run.run_id,
        )
        final_status = RunOutcome.FAILED
        error_message = f"{type(exc).__name__}: {exc}"[:2000]
    finally:
        try:
            session_for_deps.commit()
        except Exception:
            session_for_deps.rollback()
        session_for_deps.close()

    return _finalise_pipeline_run(
        engine=engine,
        run_id=pipeline_run.run_id,
        status=final_status,
        error_message=error_message,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_input(
    pipeline_cls: type["Pipeline"],
    input_cls: type | None,
    input_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate input against ``INPUT_DATA``; return JSON-safe dump."""
    if input_cls is None:
        return dict(input_data) if input_data else None
    if not input_data:
        raise ValueError(
            f"Pipeline '{pipeline_cls.__name__}' requires input_data "
            f"matching {input_cls.__name__}."
        )
    try:
        validated = input_cls.model_validate(input_data)
    except ValidationError as exc:
        raise ValueError(
            f"Pipeline '{pipeline_cls.__name__}' input_data validation "
            f"failed: {exc}"
        ) from exc
    return validated.model_dump(mode="json")


def _ensure_pipeline_run(
    *,
    engine: "Engine",
    pipeline_name: str,
    run_id: str | None,
) -> "PipelineRun":
    """Fetch or create the ``PipelineRun`` row + mark it ``running``."""
    from sqlmodel import Session, select

    from llm_pipeline.state import PipelineRun

    rid = run_id or str(uuid.uuid4())
    with Session(engine) as session:
        run = session.exec(
            select(PipelineRun).where(PipelineRun.run_id == rid)
        ).first()
        if run is None:
            run = PipelineRun(
                run_id=rid,
                pipeline_name=pipeline_name,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            session.add(run)
        else:
            run.status = "running"
            run.error_message = None
            session.add(run)
        session.commit()
        session.refresh(run)
        return run


def _finalise_pipeline_run(
    *,
    engine: "Engine",
    run_id: str,
    status: str,
    error_message: str | None,
) -> "PipelineRun":
    """Update the ``PipelineRun`` row at the end of a run/resume."""
    from sqlmodel import Session, select

    from llm_pipeline.state import PipelineRun

    with Session(engine) as session:
        run = session.exec(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        ).first()
        if run is None:
            raise RuntimeError(
                f"PipelineRun row missing for run_id={run_id!r} "
                f"after run completion."
            )
        run.status = status
        if status in (RunOutcome.COMPLETED, RunOutcome.FAILED):
            run.completed_at = datetime.now(timezone.utc)
        if error_message is not None:
            run.error_message = error_message
        session.add(run)
        session.commit()
        session.refresh(run)
        return run
