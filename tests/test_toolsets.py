"""Tests for EventEmittingToolset -- tool call event interception.

Covers three branches of EventEmittingToolset.call_tool():
1. Success path with emitter present
2. Error path with emitter present (exception re-raised)
3. Absent emitter path (no event_emitter on deps)
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, sentinel

import pytest

from pydantic_ai._run_context import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from llm_pipeline.events.types import ToolCallCompleted, ToolCallStarting
from llm_pipeline.toolsets import EventEmittingToolset, _RESULT_PREVIEW_MAX_LEN


# -- Helpers -------------------------------------------------------------------


class _DepsWithEmitter:
    """Fake deps that has event_emitter + pipeline context fields."""

    def __init__(self, emitter: Any = None) -> None:
        self.run_id = "run-test-1"
        self.pipeline_name = "test-pipeline"
        self.step_name = "test-step"
        self.event_emitter = emitter


class _DepsWithoutEmitter:
    """Fake deps missing event_emitter attribute entirely."""

    pass


class _DepsWithNoneEmitter:
    """Fake deps where event_emitter is explicitly None."""

    def __init__(self) -> None:
        self.run_id = "run-test-1"
        self.pipeline_name = "test-pipeline"
        self.step_name = "test-step"
        self.event_emitter = None


def _make_ctx(deps: Any) -> RunContext:
    """Construct a minimal RunContext with the given deps."""
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
    )


def _make_toolset(*, call_result: Any = "tool-ok", call_side_effect: Exception | None = None) -> EventEmittingToolset:
    """Create EventEmittingToolset wrapping a mock inner toolset.

    The inner toolset's call_tool is an AsyncMock that either returns
    call_result or raises call_side_effect.
    """
    inner = MagicMock()
    inner.call_tool = AsyncMock(
        return_value=call_result,
        side_effect=call_side_effect,
    )
    return EventEmittingToolset(inner)


# -- Success path (emitter present) -------------------------------------------


class TestSuccessWithEmitter:
    """Tool call succeeds, emitter receives ToolCallStarting + ToolCallCompleted."""

    def test_emits_starting_then_completed(self) -> None:
        emitter = MagicMock()
        toolset = _make_toolset(call_result="hello world")
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        result = asyncio.run(
            toolset.call_tool("greet", {"name": "Alice"}, ctx, sentinel.tool)
        )

        assert result == "hello world"
        assert emitter.emit.call_count == 2

        starting = emitter.emit.call_args_list[0][0][0]
        completed = emitter.emit.call_args_list[1][0][0]

        assert isinstance(starting, ToolCallStarting)
        assert isinstance(completed, ToolCallCompleted)

    def test_starting_event_fields(self) -> None:
        emitter = MagicMock()
        toolset = _make_toolset()
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        asyncio.run(toolset.call_tool("my_tool", {"x": 1}, ctx, sentinel.tool))

        starting: ToolCallStarting = emitter.emit.call_args_list[0][0][0]
        assert starting.tool_name == "my_tool"
        assert starting.tool_args == {"x": 1}
        assert starting.call_index == 0
        assert starting.run_id == "run-test-1"
        assert starting.pipeline_name == "test-pipeline"
        assert starting.step_name == "test-step"

    def test_completed_event_fields(self) -> None:
        emitter = MagicMock()
        toolset = _make_toolset(call_result=42)
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        asyncio.run(toolset.call_tool("calc", {}, ctx, sentinel.tool))

        completed: ToolCallCompleted = emitter.emit.call_args_list[1][0][0]
        assert completed.tool_name == "calc"
        assert completed.result_preview == "42"
        assert completed.execution_time_ms > 0
        assert completed.call_index == 0
        assert completed.error is None

    def test_none_result_preview(self) -> None:
        emitter = MagicMock()
        toolset = _make_toolset(call_result=None)
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        result = asyncio.run(toolset.call_tool("void_fn", {}, ctx, sentinel.tool))

        assert result is None
        completed: ToolCallCompleted = emitter.emit.call_args_list[1][0][0]
        assert completed.result_preview is None

    def test_result_preview_truncated(self) -> None:
        emitter = MagicMock()
        long_result = "x" * 500
        toolset = _make_toolset(call_result=long_result)
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        asyncio.run(toolset.call_tool("big", {}, ctx, sentinel.tool))

        completed: ToolCallCompleted = emitter.emit.call_args_list[1][0][0]
        assert len(completed.result_preview) == _RESULT_PREVIEW_MAX_LEN
        assert completed.result_preview == "x" * _RESULT_PREVIEW_MAX_LEN

    def test_call_index_increments(self) -> None:
        emitter = MagicMock()
        toolset = _make_toolset()
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        asyncio.run(toolset.call_tool("a", {}, ctx, sentinel.tool))
        asyncio.run(toolset.call_tool("b", {}, ctx, sentinel.tool))

        first_starting: ToolCallStarting = emitter.emit.call_args_list[0][0][0]
        second_starting: ToolCallStarting = emitter.emit.call_args_list[2][0][0]
        assert first_starting.call_index == 0
        assert second_starting.call_index == 1

    def test_delegates_to_wrapped_toolset(self) -> None:
        toolset = _make_toolset(call_result="delegated")
        ctx = _make_ctx(_DepsWithEmitter(MagicMock()))

        result = asyncio.run(
            toolset.call_tool("fn", {"a": 1}, ctx, sentinel.tool)
        )

        assert result == "delegated"
        toolset.wrapped.call_tool.assert_awaited_once_with(
            "fn", {"a": 1}, ctx, sentinel.tool
        )


# -- Error path (emitter present) ---------------------------------------------


class TestErrorWithEmitter:
    """Tool call raises exception; ToolCallCompleted has error field; exception re-raised."""

    def test_exception_reraised(self) -> None:
        emitter = MagicMock()
        toolset = _make_toolset(call_side_effect=ValueError("bad input"))
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        with pytest.raises(ValueError, match="bad input"):
            asyncio.run(toolset.call_tool("fail", {}, ctx, sentinel.tool))

    def test_completed_event_has_error(self) -> None:
        emitter = MagicMock()
        toolset = _make_toolset(call_side_effect=RuntimeError("boom"))
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        with pytest.raises(RuntimeError):
            asyncio.run(toolset.call_tool("fail", {}, ctx, sentinel.tool))

        # Should still emit both starting and completed
        assert emitter.emit.call_count == 2
        completed: ToolCallCompleted = emitter.emit.call_args_list[1][0][0]
        assert completed.error == "boom"
        assert completed.result_preview is None
        assert completed.execution_time_ms > 0
        assert completed.call_index == 0
        assert completed.tool_name == "fail"

    def test_starting_emitted_before_error(self) -> None:
        emitter = MagicMock()
        toolset = _make_toolset(call_side_effect=TypeError("type err"))
        ctx = _make_ctx(_DepsWithEmitter(emitter))

        with pytest.raises(TypeError):
            asyncio.run(toolset.call_tool("bad", {"v": "x"}, ctx, sentinel.tool))

        starting: ToolCallStarting = emitter.emit.call_args_list[0][0][0]
        assert isinstance(starting, ToolCallStarting)
        assert starting.tool_name == "bad"
        assert starting.tool_args == {"v": "x"}


# -- Absent emitter path ------------------------------------------------------


class TestAbsentEmitter:
    """No event_emitter on deps (or it's None). Tool executes; no events emitted."""

    def test_no_emitter_attr_still_returns_result(self) -> None:
        toolset = _make_toolset(call_result="ok")
        ctx = _make_ctx(_DepsWithoutEmitter())

        result = asyncio.run(toolset.call_tool("fn", {}, ctx, sentinel.tool))
        assert result == "ok"

    def test_no_emitter_attr_no_events(self) -> None:
        """Deps without event_emitter attribute -- hasattr guard skips emission."""
        toolset = _make_toolset(call_result="ok")
        deps = _DepsWithoutEmitter()
        ctx = _make_ctx(deps)

        asyncio.run(toolset.call_tool("fn", {}, ctx, sentinel.tool))
        # No emitter to check calls on; just verify no AttributeError raised

    def test_none_emitter_no_events(self) -> None:
        """event_emitter is present but None -- emission skipped."""
        toolset = _make_toolset(call_result="ok")
        ctx = _make_ctx(_DepsWithNoneEmitter())

        result = asyncio.run(toolset.call_tool("fn", {}, ctx, sentinel.tool))
        assert result == "ok"

    def test_no_emitter_error_still_reraised(self) -> None:
        """Exception re-raised even when no emitter present."""
        toolset = _make_toolset(call_side_effect=ValueError("no emitter boom"))
        ctx = _make_ctx(_DepsWithoutEmitter())

        with pytest.raises(ValueError, match="no emitter boom"):
            asyncio.run(toolset.call_tool("fn", {}, ctx, sentinel.tool))

    def test_none_emitter_error_still_reraised(self) -> None:
        """Exception re-raised when emitter is explicitly None."""
        toolset = _make_toolset(call_side_effect=KeyError("missing"))
        ctx = _make_ctx(_DepsWithNoneEmitter())

        with pytest.raises(KeyError):
            asyncio.run(toolset.call_tool("fn", {}, ctx, sentinel.tool))


# -- Constant -----------------------------------------------------------------


class TestResultPreviewMaxLen:
    """_RESULT_PREVIEW_MAX_LEN constant is accessible and sane."""

    def test_constant_value(self) -> None:
        assert _RESULT_PREVIEW_MAX_LEN == 200

    def test_constant_is_int(self) -> None:
        assert isinstance(_RESULT_PREVIEW_MAX_LEN, int)
