"""SQLModel-backed persistence for pydantic-graph runs.

Implements ``BaseStatePersistence`` against the
``pipeline_node_snapshots`` table. One row per node-execution attempt;
the full ``PipelineState`` lives in ``state_snapshot`` and the node
instance is dumped to ``node_payload`` so resume can rehydrate both.

The backend is **the** record of the run — there's no parallel
"audit trail" table. The UI's run-detail panel reads from these rows
directly.
"""
from __future__ import annotations

import dataclasses
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel
from pydantic_graph import End
from pydantic_graph.nodes import BaseNode
from pydantic_graph.persistence import (
    BaseStatePersistence,
    EndSnapshot,
    NodeSnapshot,
    RunEndT,
    Snapshot,
    StateT,
)
from pydantic_graph import exceptions as pg_exceptions
from sqlmodel import Session, select

from llm_pipeline.graph.state import PipelineState
from llm_pipeline.state import PipelineNodeSnapshot

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)


__all__ = ["SqlmodelStatePersistence"]


class SqlmodelStatePersistence(BaseStatePersistence[PipelineState, Any]):
    """Persistence backend that writes pydantic-graph snapshots to SQLModel.

    One instance per run. The backend opens a fresh ``Session`` per
    operation so concurrent reads (UI status polls) don't collide with
    writes (the running graph). The provided ``engine`` is the
    framework's existing pipeline engine.

    ``nodes`` is the list of node classes for the running pipeline —
    used to rehydrate ``BaseNode`` instances on ``load_next`` /
    ``load_all`` by class name.
    """

    def __init__(
        self,
        *,
        engine: "Engine",
        run_id: str,
        pipeline_name: str,
        nodes: list[type[BaseNode]],
    ) -> None:
        self._engine = engine
        self._run_id = run_id
        self._pipeline_name = pipeline_name
        self._nodes_by_name: dict[str, type[BaseNode]] = {
            n.__name__: n for n in nodes
        }
        self._sequence_lock_seq = 0  # in-process sequence assignment

    # ------------------------------------------------------------------
    # Required abstract methods
    # ------------------------------------------------------------------

    async def snapshot_node(
        self,
        state: PipelineState,
        next_node: BaseNode[PipelineState, Any, Any],
    ) -> None:
        """Record a NodeSnapshot row in 'created' status."""
        snapshot_id = next_node.get_snapshot_id()
        self._write_node_snapshot(
            snapshot_id=snapshot_id, state=state, next_node=next_node,
        )

    async def snapshot_node_if_new(
        self,
        snapshot_id: str,
        state: PipelineState,
        next_node: BaseNode[PipelineState, Any, Any],
    ) -> None:
        """Idempotent variant — skip if a row with this id already exists."""
        with Session(self._engine) as session:
            existing = session.exec(
                select(PipelineNodeSnapshot).where(
                    PipelineNodeSnapshot.snapshot_id == snapshot_id,
                )
            ).first()
            if existing is not None:
                return
        self._write_node_snapshot(
            snapshot_id=snapshot_id, state=state, next_node=next_node,
        )

    async def snapshot_end(
        self, state: PipelineState, end: End[Any],
    ) -> None:
        """Write the End snapshot — graph completed."""
        snapshot_id = end.get_snapshot_id()
        with Session(self._engine) as session:
            row = PipelineNodeSnapshot(
                snapshot_id=snapshot_id,
                run_id=self._run_id,
                pipeline_name=self._pipeline_name,
                sequence=self._next_sequence(session),
                kind="end",
                node_class_name="End",
                node_payload=_dump_end_data(end),
                state_snapshot=_dump_state(state),
                status="success",
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            session.commit()

    @asynccontextmanager
    async def record_run(self, snapshot_id: str) -> AsyncIterator[None]:
        """Mark a snapshot as running, then update on success/error."""
        # Pull-and-validate the snapshot we're about to run.
        with Session(self._engine) as session:
            row = session.exec(
                select(PipelineNodeSnapshot).where(
                    PipelineNodeSnapshot.snapshot_id == snapshot_id,
                )
            ).first()
            if row is None:
                raise LookupError(f"No snapshot found with id={snapshot_id!r}")
            pg_exceptions.GraphNodeStatusError.check(row.status)
            row.status = "running"
            row.started_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()

        start = perf_counter()
        try:
            yield
        except Exception as exc:  # capture and re-raise
            duration = perf_counter() - start
            with Session(self._engine) as session:
                row = session.exec(
                    select(PipelineNodeSnapshot).where(
                        PipelineNodeSnapshot.snapshot_id == snapshot_id,
                    )
                ).first()
                if row is not None:
                    row.status = "error"
                    row.duration = duration
                    row.error = {
                        "type": type(exc).__name__,
                        "message": str(exc)[:2000],
                    }
                    session.add(row)
                    session.commit()
            raise
        else:
            duration = perf_counter() - start
            with Session(self._engine) as session:
                row = session.exec(
                    select(PipelineNodeSnapshot).where(
                        PipelineNodeSnapshot.snapshot_id == snapshot_id,
                    )
                ).first()
                if row is not None:
                    row.status = "success"
                    row.duration = duration
                    session.add(row)
                    session.commit()

    async def load_next(self) -> NodeSnapshot[PipelineState, Any] | None:
        """Pull the next 'created' snapshot, mark it 'pending', return it."""
        with Session(self._engine) as session:
            row = session.exec(
                select(PipelineNodeSnapshot)
                .where(
                    PipelineNodeSnapshot.run_id == self._run_id,
                    PipelineNodeSnapshot.kind == "node",
                    PipelineNodeSnapshot.status == "created",
                )
                .order_by(PipelineNodeSnapshot.sequence)
            ).first()
            if row is None:
                return None
            row.status = "pending"
            session.add(row)
            session.commit()
            return self._row_to_node_snapshot(row)

    async def load_all(self) -> list[Snapshot[PipelineState, Any]]:
        """Return every snapshot for this run, ordered by sequence."""
        with Session(self._engine) as session:
            rows = session.exec(
                select(PipelineNodeSnapshot)
                .where(PipelineNodeSnapshot.run_id == self._run_id)
                .order_by(PipelineNodeSnapshot.sequence)
            ).all()
        return [self._row_to_snapshot(row) for row in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write_node_snapshot(
        self,
        *,
        snapshot_id: str,
        state: PipelineState,
        next_node: BaseNode[PipelineState, Any, Any],
    ) -> None:
        with Session(self._engine) as session:
            row = PipelineNodeSnapshot(
                snapshot_id=snapshot_id,
                run_id=self._run_id,
                pipeline_name=self._pipeline_name,
                sequence=self._next_sequence(session),
                kind="node",
                node_class_name=type(next_node).__name__,
                node_payload=_dump_node(next_node),
                state_snapshot=_dump_state(state),
                status="created",
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            session.commit()

    def _next_sequence(self, session: Session) -> int:
        """0-based sequence within ``run_id``. Cheap query each call."""
        from sqlalchemy import func

        max_seq = session.exec(
            select(func.max(PipelineNodeSnapshot.sequence)).where(
                PipelineNodeSnapshot.run_id == self._run_id,
            )
        ).first()
        return 0 if max_seq is None else int(max_seq) + 1

    def _row_to_node_snapshot(
        self, row: PipelineNodeSnapshot,
    ) -> NodeSnapshot[PipelineState, Any]:
        node_cls = self._nodes_by_name.get(row.node_class_name)
        if node_cls is None:
            raise RuntimeError(
                f"Snapshot {row.snapshot_id!r} references unknown node "
                f"class {row.node_class_name!r}; the pipeline may have "
                f"changed since this run started."
            )
        node = _rehydrate_node(node_cls, row.node_payload or {})
        node.set_snapshot_id(row.snapshot_id)
        state = PipelineState.model_validate(row.state_snapshot or {})
        snapshot: NodeSnapshot[PipelineState, Any] = NodeSnapshot(
            state=state,
            node=node,
            status=row.status,  # type: ignore[arg-type]
            start_ts=row.started_at,
            duration=row.duration,
            id=row.snapshot_id,
        )
        return snapshot

    def _row_to_snapshot(
        self, row: PipelineNodeSnapshot,
    ) -> Snapshot[PipelineState, Any]:
        state = PipelineState.model_validate(row.state_snapshot or {})
        if row.kind == "end":
            end = End(row.node_payload.get("data") if row.node_payload else None)
            end.set_snapshot_id(row.snapshot_id)
            return EndSnapshot(state=state, result=end, id=row.snapshot_id)
        return self._row_to_node_snapshot(row)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _dump_state(state: PipelineState) -> dict[str, Any]:
    """Serialise ``PipelineState`` to a JSON-friendly dict."""
    return state.model_dump(mode="json")


def _dump_node(node: BaseNode[Any, Any, Any]) -> dict[str, Any]:
    """Serialise a node instance's per-instance fields.

    For dataclass-style nodes (``@dataclass class FooNode(BaseNode):
    field: int``) returns ``dataclasses.asdict(node)``. For pydantic
    BaseModel-derived nodes returns ``model_dump``. For plain classes
    with no per-instance state (the Phase-1 default) returns ``{}``.
    """
    if isinstance(node, BaseModel):
        return node.model_dump(mode="json")
    if dataclasses.is_dataclass(node):
        return dataclasses.asdict(node)
    return {}


def _dump_end_data(end: End[Any]) -> dict[str, Any]:
    """Serialise ``End[T].data``. For ``End(None)`` returns ``{}``."""
    data = end.data
    if data is None:
        return {}
    if isinstance(data, BaseModel):
        return {"data": data.model_dump(mode="json")}
    if dataclasses.is_dataclass(data):
        return {"data": dataclasses.asdict(data)}
    if isinstance(data, dict):
        return {"data": dict(data)}
    return {"data": data}


def _rehydrate_node(
    cls: type[BaseNode[Any, Any, Any]], payload: dict[str, Any],
) -> BaseNode[Any, Any, Any]:
    """Rebuild a node instance from ``payload``.

    Handles three shapes (matching ``_dump_node``):
    - pydantic ``BaseModel`` subclass: ``cls.model_validate(payload)``
    - dataclass: ``cls(**payload)`` (asdict round-trip)
    - plain class with no fields: ``cls()``
    """
    if isinstance(cls, type) and issubclass(cls, BaseModel):
        return cls.model_validate(payload)  # type: ignore[return-value]
    if dataclasses.is_dataclass(cls):
        return cls(**payload)  # type: ignore[arg-type]
    return cls()
