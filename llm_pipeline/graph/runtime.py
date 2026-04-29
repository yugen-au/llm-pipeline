"""Phase-1 in-memory runtime for pydantic-graph-native pipelines.

``run_pipeline_in_memory`` builds the graph state, wires deps,
instantiates a ``SimpleStatePersistence`` (no DB), and runs the graph
to completion. Phase 2 introduces a SQLModel-backed persistence + the
UI ``run_pipeline`` / ``resume_pipeline`` entry points.

This entry point is **not** what the UI calls — it's the bare-metal
verifier the smoke test and unit tests use to confirm the new
declarative shape works end-to-end before the UI runtime swap lands.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from llm_pipeline.graph.state import PipelineDeps, PipelineState

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlmodel import Session

    from llm_pipeline.graph.pipeline import Pipeline


__all__ = ["run_pipeline_in_memory"]


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

    Args:
        pipeline_cls: The compiled ``Pipeline`` subclass.
        input_data: Dict matching ``pipeline_cls.INPUT_DATA``. Required
            unless ``INPUT_DATA`` is ``None``.
        model: pydantic-ai model string (e.g. ``"test"``,
            ``"google-gla:gemini-2.0-flash-lite"``).
        session: Optional SQLModel session. Defaults to a fresh session
            on ``engine`` (or an auto-init'd SQLite engine if neither
            is provided).
        engine: Optional SQLAlchemy engine. Used to make a session if
            ``session`` is omitted.
        run_id: Optional explicit run ID. UUID4 if omitted.
        instrumentation_settings: pydantic-ai
            ``InstrumentationSettings`` for OTEL tracing.

    Returns:
        ``(final_state, end_payload)`` — ``final_state`` is the
        ``PipelineState`` after the run completes; ``end_payload`` is
        whatever the terminal node passed to ``End(...)``.
    """
    from sqlmodel import Session

    from llm_pipeline.db import init_pipeline_db
    from llm_pipeline.prompts.service import PromptService

    # ---- Validate input ---------------------------------------------------
    input_cls = pipeline_cls.INPUT_DATA
    validated_input_dump: dict[str, Any] | None = None
    if input_cls is not None:
        if not input_data:
            raise ValueError(
                f"Pipeline '{pipeline_cls.__name__}' requires input_data "
                f"matching {input_cls.__name__}, got {input_data!r}."
            )
        try:
            validated = input_cls.model_validate(input_data)
        except ValidationError as exc:
            raise ValueError(
                f"Pipeline '{pipeline_cls.__name__}' input_data validation "
                f"failed: {exc}"
            ) from exc
        validated_input_dump = validated.model_dump(mode="json")
    elif input_data:
        # Input-less pipeline got input_data anyway — keep as raw dict.
        validated_input_dump = dict(input_data)

    # ---- Build deps -------------------------------------------------------
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

    # ---- Run the graph ----------------------------------------------------
    graph = pipeline_cls.graph()
    start_node_cls = pipeline_cls.start_node
    if start_node_cls is None:
        raise RuntimeError(
            f"{pipeline_cls.__name__}.start_node is None — declare nodes "
            f"or set start_node explicitly."
        )

    try:
        result = await graph.run(
            start_node_cls(),
            state=state,
            deps=deps,
        )
    finally:
        if owns_session:
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise
            session.close()

    return result.state, result.output
