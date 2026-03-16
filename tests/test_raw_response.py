"""Unit tests for _extract_raw_response helper in pipeline.py.

Testing _extract_raw_response directly despite underscore prefix because it is
a standalone utility with complex edge cases (ToolCallPart serialization,
multi-part joining, exception handling) that warrant isolated unit coverage.
"""
import json
from unittest.mock import MagicMock

import pytest

from llm_pipeline.pipeline import _extract_raw_response


def _make_run_result(messages):
    """Build a mock run_result whose new_messages() returns *messages*."""
    rr = MagicMock()
    rr.new_messages.return_value = messages
    return rr


def _model_response(parts):
    """Build a mock ModelResponse with given *parts*."""
    from pydantic_ai.messages import ModelResponse

    mr = MagicMock(spec=ModelResponse)
    mr.parts = parts
    # Override __class__ so isinstance() checks in _extract_raw_response match
    # ModelResponse. MagicMock(spec=...) alone does not satisfy isinstance();
    # __class__ assignment is the lightest way to fake it without constructing
    # real pydantic-ai message objects (which require valid constructor args).
    mr.__class__ = ModelResponse
    return mr


def _tool_call_part(args):
    from pydantic_ai.messages import ToolCallPart

    p = MagicMock(spec=ToolCallPart)
    p.args = args
    # See _model_response docstring for why __class__ override is needed.
    p.__class__ = ToolCallPart
    return p


def _text_part(content):
    from pydantic_ai.messages import TextPart

    p = MagicMock(spec=TextPart)
    p.content = content
    # See _model_response docstring for why __class__ override is needed.
    p.__class__ = TextPart
    return p


class TestExtractRawResponse:
    """Tests for _extract_raw_response()."""

    def test_tool_call_part_returns_json_args(self):
        """ToolCallPart: result is JSON string of args dict."""
        args = {"name": "Widget", "count": 3}
        part = _tool_call_part(args)
        mr = _model_response([part])
        rr = _make_run_result([mr])

        result = _extract_raw_response(rr)

        assert result == json.dumps(args)
        # Verify it round-trips
        assert json.loads(result) == args

    def test_text_part_returns_content(self):
        """TextPart: result equals part.content."""
        part = _text_part("Hello, world!")
        mr = _model_response([part])
        rr = _make_run_result([mr])

        result = _extract_raw_response(rr)

        assert result == "Hello, world!"

    def test_no_model_response_returns_none(self):
        """No ModelResponse in messages: result is None."""
        # Empty messages list
        rr = _make_run_result([])
        assert _extract_raw_response(rr) is None

        # Messages with non-ModelResponse items
        non_mr = MagicMock()
        non_mr.__class__ = type("UserPrompt", (), {})
        rr2 = _make_run_result([non_mr])
        assert _extract_raw_response(rr2) is None

    def test_multiple_parts_joined_with_newline(self):
        """Multiple parts: result joins them with newline."""
        text = _text_part("first line")
        args = {"key": "value"}
        tool = _tool_call_part(args)
        mr = _model_response([text, tool])
        rr = _make_run_result([mr])

        result = _extract_raw_response(rr)

        expected = "first line\n" + json.dumps(args)
        assert result == expected

    def test_uses_last_model_response(self):
        """When multiple ModelResponses exist, uses the last one."""
        first_mr = _model_response([_text_part("ignored")])
        last_mr = _model_response([_text_part("used")])
        rr = _make_run_result([first_mr, last_mr])

        result = _extract_raw_response(rr)

        assert result == "used"

    def test_new_messages_exception_returns_none(self):
        """If new_messages() raises, returns None gracefully."""
        rr = MagicMock()
        rr.new_messages.side_effect = RuntimeError("broken")

        assert _extract_raw_response(rr) is None

    def test_non_serializable_args_falls_back_to_str(self):
        """ToolCallPart with non-JSON-serializable args falls back to str()."""
        # object() is not JSON-serializable
        bad_args = object()
        part = _tool_call_part(bad_args)
        mr = _model_response([part])
        rr = _make_run_result([mr])

        result = _extract_raw_response(rr)

        assert result == str(bad_args)
