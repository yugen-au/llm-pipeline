"""Pydantic-ai toolset wrappers for pipeline event interception.

EventEmittingToolset wraps any toolset and emits ToolCallStarting /
ToolCallCompleted events through the pipeline event system. Used by
build_step_agent() when tools are registered on an agent.
"""
from __future__ import annotations

import itertools
import time
from typing import Any, TYPE_CHECKING

from pydantic_ai.toolsets import WrapperToolset

if TYPE_CHECKING:
    from pydantic_ai import RunContext
    from pydantic_ai.toolsets import AbstractToolset, ToolsetTool


class EventEmittingToolset(WrapperToolset):
    """Toolset wrapper that emits pipeline events around each tool call.

    Wraps an inner toolset (typically FunctionToolset) and intercepts
    call_tool to emit ToolCallStarting before execution and
    ToolCallCompleted after, using the event_emitter from StepDeps.

    If ctx.deps has no event_emitter (e.g. consensus path with different
    deps), event emission is silently skipped.
    """

    def __init__(self, wrapped: AbstractToolset) -> None:
        super().__init__(wrapped)
        self._call_counter = itertools.count()

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext,
        tool: ToolsetTool,
    ) -> Any:
        """Execute tool with event emission around the call."""
        from llm_pipeline.events.types import ToolCallCompleted, ToolCallStarting

        idx = next(self._call_counter)

        # Guard: deps may not have event_emitter (consensus path, tests, etc.)
        emitter = None
        deps = ctx.deps
        if hasattr(deps, "event_emitter"):
            emitter = deps.event_emitter

        # Common event kwargs when emitter is available
        event_kwargs: dict[str, Any] = {}
        if emitter is not None:
            event_kwargs = dict(
                run_id=deps.run_id,
                pipeline_name=deps.pipeline_name,
                step_name=deps.step_name,
            )

        if emitter is not None:
            emitter.emit(
                ToolCallStarting(
                    **event_kwargs,
                    tool_name=name,
                    tool_args=tool_args,
                    call_index=idx,
                )
            )

        start = time.perf_counter()
        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if emitter is not None:
                emitter.emit(
                    ToolCallCompleted(
                        **event_kwargs,
                        tool_name=name,
                        result_preview=None,
                        execution_time_ms=elapsed_ms,
                        call_index=idx,
                        error=str(exc),
                    )
                )
            raise
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            preview = str(result)[:200] if result is not None else None
            if emitter is not None:
                emitter.emit(
                    ToolCallCompleted(
                        **event_kwargs,
                        tool_name=name,
                        result_preview=preview,
                        execution_time_ms=elapsed_ms,
                        call_index=idx,
                        error=None,
                    )
                )
            return result


__all__ = ["EventEmittingToolset"]
