"""Tests for LLMCallResult dataclass and its helper methods."""
import dataclasses
import json

import pytest

from llm_pipeline.llm import LLMCallResult


# ---------- Instantiation ----------


class TestInstantiation:
    def test_instantiation_defaults(self):
        """Default values: parsed=None, raw_response=None, model_name=None, attempt_count=1, validation_errors=[]."""
        result = LLMCallResult()
        assert result.parsed is None
        assert result.raw_response is None
        assert result.model_name is None
        assert result.attempt_count == 1
        assert result.validation_errors == []

    def test_instantiation_all_fields(self):
        """All fields set explicitly, all retrievable."""
        result = LLMCallResult(
            parsed={"key": "value"},
            raw_response='{"key": "value"}',
            model_name="gemini-2.0-flash",
            attempt_count=3,
            validation_errors=["retry1", "retry2"],
        )
        assert result.parsed == {"key": "value"}
        assert result.raw_response == '{"key": "value"}'
        assert result.model_name == "gemini-2.0-flash"
        assert result.attempt_count == 3
        assert result.validation_errors == ["retry1", "retry2"]


# ---------- Factory classmethods ----------


class TestFactories:
    def test_success_factory(self):
        """success() creates valid instance with is_success=True."""
        result = LLMCallResult.success(
            parsed={"count": 5},
            raw_response='{"count": 5}',
            model_name="gemini-2.0-flash",
        )
        assert result.parsed == {"count": 5}
        assert result.raw_response == '{"count": 5}'
        assert result.model_name == "gemini-2.0-flash"
        assert result.attempt_count == 1
        assert result.validation_errors == []
        assert result.is_success is True
        assert result.is_failure is False

    def test_failure_factory(self):
        """failure() creates valid instance with is_failure=True."""
        result = LLMCallResult.failure(
            raw_response="error text",
            model_name="gemini-2.0-flash",
            attempt_count=3,
            validation_errors=["schema mismatch"],
        )
        assert result.parsed is None
        assert result.raw_response == "error text"
        assert result.model_name == "gemini-2.0-flash"
        assert result.attempt_count == 3
        assert result.validation_errors == ["schema mismatch"]
        assert result.is_success is False
        assert result.is_failure is True

    def test_failure_factory_empty_errors(self):
        """failure() accepts empty validation_errors (timeout/network case)."""
        result = LLMCallResult.failure(
            raw_response="",
            model_name="gemini-2.0-flash",
            attempt_count=1,
            validation_errors=[],
        )
        assert result.parsed is None
        assert result.validation_errors == []
        assert result.is_failure is True

    def test_success_factory_none_parsed_raises(self):
        """success(parsed=None) raises ValueError."""
        with pytest.raises(ValueError, match="parsed must not be None"):
            LLMCallResult.success(
                parsed=None,
                raw_response="text",
                model_name="gemini-2.0-flash",
            )

    def test_failure_factory_non_none_parsed_raises(self):
        """failure(parsed=non-None) raises ValueError."""
        with pytest.raises(ValueError, match="parsed must be None"):
            LLMCallResult.failure(
                parsed={"data": "value"},
                raw_response="text",
                model_name="gemini-2.0-flash",
                attempt_count=1,
                validation_errors=[],
            )


# ---------- Serialization ----------


class TestSerialization:
    def test_to_dict_all_none(self):
        """to_dict() on default instance has all keys with None/default values."""
        result = LLMCallResult()
        d = result.to_dict()
        assert d == {
            "parsed": None,
            "raw_response": None,
            "model_name": None,
            "attempt_count": 1,
            "validation_errors": [],
        }

    def test_to_dict_all_set(self):
        """to_dict() with all fields set produces matching dict."""
        result = LLMCallResult(
            parsed={"a": 1},
            raw_response="raw",
            model_name="model-x",
            attempt_count=2,
            validation_errors=["e1"],
        )
        d = result.to_dict()
        assert d == {
            "parsed": {"a": 1},
            "raw_response": "raw",
            "model_name": "model-x",
            "attempt_count": 2,
            "validation_errors": ["e1"],
        }

    def test_to_json_structure(self):
        """to_json() produces valid JSON matching to_dict()."""
        result = LLMCallResult(
            parsed={"x": 42},
            raw_response="resp",
            model_name="model-y",
            attempt_count=1,
            validation_errors=[],
        )
        json_str = result.to_json()
        loaded = json.loads(json_str)
        assert loaded == result.to_dict()


# ---------- Status properties ----------


class TestStatusProperties:
    def test_is_success_true(self):
        """parsed={} -> is_success=True."""
        result = LLMCallResult(parsed={})
        assert result.is_success is True

    def test_is_success_false(self):
        """parsed=None -> is_success=False."""
        result = LLMCallResult(parsed=None)
        assert result.is_success is False

    def test_partial_success(self):
        """parsed={} + validation_errors -> is_success=True (CEO decision: errors are diagnostic only)."""
        result = LLMCallResult(
            parsed={"data": "ok"},
            validation_errors=["prior attempt error"],
        )
        assert result.is_success is True
        assert result.is_failure is False

    def test_is_failure_true(self):
        """parsed=None -> is_failure=True."""
        result = LLMCallResult(parsed=None)
        assert result.is_failure is True

    def test_is_failure_false(self):
        """parsed={} -> is_failure=False."""
        result = LLMCallResult(parsed={})
        assert result.is_failure is False


# ---------- Dataclass behavior ----------


class TestDataclassBehavior:
    def test_frozen_immutability(self):
        """Field reassignment raises FrozenInstanceError."""
        result = LLMCallResult(parsed={"a": 1})
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.parsed = {"b": 2}

    def test_equality(self):
        """Two instances with same values are equal."""
        a = LLMCallResult(parsed={"x": 1}, raw_response="r", model_name="m")
        b = LLMCallResult(parsed={"x": 1}, raw_response="r", model_name="m")
        assert a == b

    def test_inequality(self):
        """Two instances with different values are not equal."""
        a = LLMCallResult(parsed={"x": 1})
        b = LLMCallResult(parsed={"x": 2})
        assert a != b

    def test_repr(self):
        """repr contains class name and key field values (partial, not exact match)."""
        result = LLMCallResult(
            parsed={"k": "v"},
            raw_response="raw_resp_sentinel",
            model_name="model_sentinel",
            attempt_count=2,
            validation_errors=["err_sentinel"],
        )
        r = repr(result)
        assert "LLMCallResult" in r
        assert "raw_resp_sentinel" in r
        assert "model_sentinel" in r
        assert "err_sentinel" in r
        assert "attempt_count" in r
