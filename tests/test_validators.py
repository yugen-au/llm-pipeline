"""
Tests for llm_pipeline/validators.py: not_found_validator and array_length_validator.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.usage import RunUsage

from llm_pipeline.agent_builders import StepDeps
from llm_pipeline.types import ArrayValidationConfig
from llm_pipeline.validators import (
    DEFAULT_NOT_FOUND_INDICATORS,
    array_length_validator,
    not_found_validator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(deps: Any) -> RunContext[Any]:
    """Build a minimal RunContext with the given deps."""
    return RunContext(
        deps=deps,
        model=MagicMock(),
        usage=RunUsage(),
    )


def _make_deps(array_validation: Any = None, validation_context: Any = None) -> StepDeps:
    return StepDeps(
        session=MagicMock(),
        pipeline_context={},
        prompt_service=MagicMock(),
        run_id="run-test",
        pipeline_name="test_pipeline",
        step_name="test_step",
        array_validation=array_validation,
        validation_context=validation_context,
    )


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# not_found_validator
# ---------------------------------------------------------------------------

class TestNotFoundValidator:
    """Tests for not_found_validator() factory."""

    def test_default_indicators_match_not_found(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry):
            _run(validator(ctx, "not found"))

    def test_default_indicators_match_no_data(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry):
            _run(validator(ctx, "no data available"))

    def test_default_indicators_match_na(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry):
            _run(validator(ctx, "N/A"))

    def test_default_indicators_match_none_string(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry):
            _run(validator(ctx, "none"))

    def test_default_indicators_match_unknown(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry):
            _run(validator(ctx, "The value is unknown"))

    def test_default_indicators_match_case_insensitive(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry):
            _run(validator(ctx, "NOT FOUND"))

    def test_custom_indicators_match(self):
        validator = not_found_validator(indicators=["no result", "unavailable"])
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry):
            _run(validator(ctx, "no result for this query"))

    def test_custom_indicators_match_second(self):
        validator = not_found_validator(indicators=["no result", "unavailable"])
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry):
            _run(validator(ctx, "value is UNAVAILABLE"))

    def test_custom_indicators_do_not_match_defaults(self):
        # custom list replaces defaults; "not found" no longer triggers
        validator = not_found_validator(indicators=["no result"])
        ctx = _make_ctx(_make_deps())
        result = _run(validator(ctx, "not found"))
        assert result == "not found"

    def test_non_matching_passes_through(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        result = _run(validator(ctx, "Paris, France"))
        assert result == "Paris, France"

    def test_empty_string_passes_through(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        result = _run(validator(ctx, ""))
        assert result == ""

    def test_non_string_output_returns_unchanged_int(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        result = _run(validator(ctx, 42))
        assert result == 42

    def test_non_string_output_returns_unchanged_none(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        result = _run(validator(ctx, None))
        assert result is None

    def test_non_string_output_returns_unchanged_model(self):
        class FakeModel(BaseModel):
            value: str = "hello"

        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        obj = FakeModel()
        result = _run(validator(ctx, obj))
        assert result is obj

    def test_modelretry_raised_on_match(self):
        """ModelRetry is raised (not some other exception)."""
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry) as exc_info:
            _run(validator(ctx, "not available"))
        assert "not available" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()

    def test_default_indicators_constant_unchanged(self):
        # calling factory must not mutate DEFAULT_NOT_FOUND_INDICATORS
        original = list(DEFAULT_NOT_FOUND_INDICATORS)
        not_found_validator(indicators=None)
        assert DEFAULT_NOT_FOUND_INDICATORS == original

    def test_model_retry_message_contains_output(self):
        validator = not_found_validator()
        ctx = _make_ctx(_make_deps())
        with pytest.raises(ModelRetry) as exc_info:
            _run(validator(ctx, "not found"))
        assert "not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# array_length_validator
# ---------------------------------------------------------------------------

class _Item(BaseModel):
    original: str
    value: str


class _Container(BaseModel):
    items: list[_Item]


def _make_config(
    input_array: list[Any],
    array_field_name: str = "items",
    match_field: str = "original",
    allow_reordering: bool = False,
    filter_empty_inputs: bool = False,
    strip_number_prefix: bool = False,
) -> ArrayValidationConfig:
    return ArrayValidationConfig(
        input_array=input_array,
        array_field_name=array_field_name,
        match_field=match_field,
        allow_reordering=allow_reordering,
        filter_empty_inputs=filter_empty_inputs,
        strip_number_prefix=strip_number_prefix,
    )


class TestArrayLengthValidator:
    """Tests for array_length_validator() factory."""

    def test_noop_when_array_validation_is_none(self):
        validator = array_length_validator()
        deps = _make_deps(array_validation=None)
        ctx = _make_ctx(deps)
        obj = _Container(items=[_Item(original="a", value="A")])
        result = _run(validator(ctx, obj))
        assert result is obj

    def test_correct_length_passes(self):
        input_array = ["alpha", "beta"]
        config = _make_config(input_array=input_array)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        output = _Container(items=[
            _Item(original="alpha", value="Alpha"),
            _Item(original="beta", value="Beta"),
        ])
        result = _run(validator(ctx, output))
        assert result is output

    def test_length_mismatch_raises_model_retry(self):
        input_array = ["alpha", "beta", "gamma"]
        config = _make_config(input_array=input_array)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        output = _Container(items=[
            _Item(original="alpha", value="Alpha"),
        ])
        with pytest.raises(ModelRetry):
            _run(validator(ctx, output))

    def test_length_mismatch_message_contains_counts(self):
        input_array = ["alpha", "beta"]
        config = _make_config(input_array=input_array)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        output = _Container(items=[_Item(original="alpha", value="Alpha")])
        with pytest.raises(ModelRetry) as exc_info:
            _run(validator(ctx, output))
        msg = str(exc_info.value)
        assert "2" in msg  # expected
        assert "1" in msg  # got

    def test_no_reorder_when_flag_false(self):
        input_array = ["beta", "alpha"]
        config = _make_config(input_array=input_array, allow_reordering=False)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        items = [_Item(original="alpha", value="Alpha"), _Item(original="beta", value="Beta")]
        output = _Container(items=items)
        result = _run(validator(ctx, output))
        # no reorder: order preserved as-is
        assert result.items[0].original == "alpha"
        assert result.items[1].original == "beta"

    def test_reordering_with_allow_reordering_true(self):
        input_array = ["beta", "alpha"]
        config = _make_config(input_array=input_array, allow_reordering=True)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        # LLM returned in different order than input
        output = _Container(items=[
            _Item(original="alpha", value="Alpha"),
            _Item(original="beta", value="Beta"),
        ])
        result = _run(validator(ctx, output))
        assert result.items[0].original == "beta"
        assert result.items[1].original == "alpha"

    def test_reordering_returns_model_copy(self):
        input_array = ["beta", "alpha"]
        config = _make_config(input_array=input_array, allow_reordering=True)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        output = _Container(items=[
            _Item(original="alpha", value="Alpha"),
            _Item(original="beta", value="Beta"),
        ])
        result = _run(validator(ctx, output))
        # result is a new object (model_copy), not the same instance
        assert result is not output

    def test_strip_number_prefix_matching(self):
        input_array = ["alpha", "beta"]
        config = _make_config(
            input_array=input_array,
            allow_reordering=True,
            strip_number_prefix=True,
        )
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        # LLM returned items with number prefixes in original field
        output = _Container(items=[
            _Item(original="2. beta", value="Beta"),
            _Item(original="1. alpha", value="Alpha"),
        ])
        result = _run(validator(ctx, output))
        # reordering matches "1. alpha" -> "alpha", "2. beta" -> "beta"
        assert result.items[0].original == "1. alpha"
        assert result.items[1].original == "2. beta"

    def test_filter_empty_inputs_reduces_expected_count(self):
        input_array = ["alpha", "", "beta"]
        config = _make_config(input_array=input_array, filter_empty_inputs=True)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        # After filtering, effective input is 2 items
        output = _Container(items=[
            _Item(original="alpha", value="Alpha"),
            _Item(original="beta", value="Beta"),
        ])
        result = _run(validator(ctx, output))
        assert result is output

    def test_filter_empty_inputs_mismatch_still_raises(self):
        input_array = ["alpha", "", "beta"]
        config = _make_config(input_array=input_array, filter_empty_inputs=True)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        # Only 1 item but effective input has 2
        output = _Container(items=[_Item(original="alpha", value="Alpha")])
        with pytest.raises(ModelRetry):
            _run(validator(ctx, output))

    def test_empty_array_field_name_raises_value_error(self):
        config = ArrayValidationConfig(
            input_array=["a"],
            array_field_name="",  # invalid
        )
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)

        class DummyOutput(BaseModel):
            pass

        with pytest.raises(ValueError, match="array_field_name"):
            _run(validator(ctx, DummyOutput()))

    def test_already_correct_order_preserved(self):
        input_array = ["alpha", "beta"]
        config = _make_config(input_array=input_array, allow_reordering=True)
        validator = array_length_validator()
        deps = _make_deps(array_validation=config)
        ctx = _make_ctx(deps)
        output = _Container(items=[
            _Item(original="alpha", value="Alpha"),
            _Item(original="beta", value="Beta"),
        ])
        result = _run(validator(ctx, output))
        # Items should remain in same order
        assert result.items[0].original == "alpha"
        assert result.items[1].original == "beta"
