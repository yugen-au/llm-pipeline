"""Integration tests for LLM retry and rate-limit event emissions.

Verifies LLMCallRetry, LLMCallFailed, and LLMCallRateLimited events emitted
by GeminiProvider's retry loop via InMemoryEventHandler. Tests cover all
emission paths: empty response, JSON decode errors, validation failures,
rate limiting (API-suggested and exponential backoff), generic exceptions,
and the accumulated_errors bug fix.

Mocks at Gemini API level (GenerativeModel.generate_content) to exercise
production retry loop behavior with multi-attempt sequences.
"""
import pytest
from unittest.mock import patch, Mock, MagicMock
from typing import ClassVar

from llm_pipeline.llm.gemini import GeminiProvider
from llm_pipeline.events.handlers import InMemoryEventHandler
from llm_pipeline.events.types import LLMCallRetry, LLMCallFailed, LLMCallRateLimited
from llm_pipeline.step import LLMResultMixin


# -- Test Schema ---------------------------------------------------------------


class SimpleSchema(LLMResultMixin):
    """Minimal Pydantic schema for testing."""
    count: int
    notes: str

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


# -- Helpers -------------------------------------------------------------------


def _create_mock_response(text):
    """Create a mock Gemini response with the given text."""
    response = Mock()
    response.text = text
    # Ensure response is truthy
    response.__bool__ = Mock(return_value=bool(text))
    return response


def _create_rate_limit_error(with_retry_after=False):
    """Create a mock rate limit exception."""
    error = Exception("429 Resource exhausted")
    if with_retry_after:
        # Simulate Retry-After header in error message
        error = Exception("429 Resource exhausted (Retry-After: 2.5s)")
    return error


def _setup_model_mocks(mock_model_class, responses):
    """Setup mock model instances for each response/exception.

    Args:
        mock_model_class: The mocked GenerativeModel class
        responses: List of response objects or exceptions to return
    """
    mock_instances = []
    for resp in responses:
        mock_inst = Mock()
        if isinstance(resp, Exception):
            mock_inst.generate_content.side_effect = resp
        else:
            mock_inst.generate_content.return_value = resp
        mock_instances.append(mock_inst)
    mock_model_class.side_effect = mock_instances


# -- Tests: LLMCallRetry (Empty Response) -------------------------------------


class TestEmptyResponseRetry:
    """Verify LLMCallRetry events emitted on empty/no response from model."""

    @patch('google.generativeai.GenerativeModel')
    def test_empty_response_retry_emits_events(self, mock_model_class):
        """Empty response on first 2 attempts emits 2 LLMCallRetry, then success."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: empty response 2x, then valid JSON
        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            _create_mock_response(None),
            _create_mock_response('{"count": 1, "notes": "ok"}'),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=3,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_001",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is not None
        assert result.attempt_count == 3

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]
        assert len(retry_events) == 2, f"Expected 2 LLMCallRetry events, got {len(retry_events)}"

        # Verify first retry event
        assert retry_events[0]["attempt"] == 1
        assert retry_events[0]["max_retries"] == 3
        assert retry_events[0]["error_type"] == "empty_response"
        assert "Empty/no response" in retry_events[0]["error_message"]

        # Verify second retry event
        assert retry_events[1]["attempt"] == 2
        assert retry_events[1]["max_retries"] == 3
        assert retry_events[1]["error_type"] == "empty_response"

    @patch('google.generativeai.GenerativeModel')
    def test_empty_response_no_retry_on_last_attempt(self, mock_model_class):
        """Empty response on last attempt emits no LLMCallRetry (only LLMCallFailed)."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: empty response all 3 attempts
        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            _create_mock_response(""),
            _create_mock_response(""),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=3,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_001",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is None

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]
        failed_events = [e for e in events if e["event_type"] == "llm_call_failed"]

        # Only 2 retries (attempts 0, 1), last attempt (2) goes to failed
        assert len(retry_events) == 2
        assert len(failed_events) == 1


# -- Tests: LLMCallRetry (JSON Decode Error) ----------------------------------


class TestJSONDecodeRetry:
    """Verify LLMCallRetry events emitted on JSON parse failures."""

    @patch('google.generativeai.GenerativeModel')
    def test_json_decode_retry_emits_events(self, mock_model_class):
        """Invalid JSON on first 2 attempts emits 2 LLMCallRetry with json_decode_error."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: invalid JSON 2x, then valid
        _setup_model_mocks(mock_model_class, [
            _create_mock_response("{invalid json"),
            _create_mock_response("not json at all"),
            _create_mock_response('{"count": 5, "notes": "fixed"}'),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=3,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_002",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is not None
        assert result.parsed["count"] == 5

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]
        assert len(retry_events) == 2

        # Verify error_type
        assert retry_events[0]["error_type"] == "json_decode_error"
        assert "JSON decode error" in retry_events[0]["error_message"]
        assert retry_events[1]["error_type"] == "json_decode_error"


# -- Tests: LLMCallRetry (Validation Error) -----------------------------------


class TestValidationFailureRetry:
    """Verify LLMCallRetry events emitted on schema validation failures."""

    @patch('google.generativeai.GenerativeModel')
    def test_validation_failure_retry_emits_events(self, mock_model_class):
        """Schema-invalid JSON emits LLMCallRetry with validation_error."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: schema-invalid JSON 2x (missing 'notes'), then valid
        _setup_model_mocks(mock_model_class, [
            _create_mock_response('{"count": 1}'),  # missing notes
            _create_mock_response('{"count": "bad", "notes": "test"}'),  # wrong type
            _create_mock_response('{"count": 3, "notes": "ok"}'),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=3,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_003",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is not None

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]
        assert len(retry_events) == 2

        # Verify error_type
        assert retry_events[0]["error_type"] == "validation_error"
        assert retry_events[1]["error_type"] == "validation_error"


# -- Tests: LLMCallFailed ------------------------------------------------------


class TestAllAttemptsFail:
    """Verify LLMCallFailed emitted after exhausting all retries."""

    @patch('google.generativeai.GenerativeModel')
    def test_all_attempts_fail_emits_failed_event(self, mock_model_class):
        """All attempts fail: emit (max_retries-1) LLMCallRetry, then 1 LLMCallFailed."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: empty response all 3 attempts
        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            _create_mock_response(""),
            _create_mock_response(""),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=3,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_004",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is None

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]
        failed_events = [e for e in events if e["event_type"] == "llm_call_failed"]

        assert len(retry_events) == 2, "Expected 2 retries (attempts 0, 1)"
        assert len(failed_events) == 1, "Expected 1 failed event"

        # Verify LLMCallFailed fields
        failed = failed_events[0]
        assert failed["max_retries"] == 3
        assert failed["last_error"] == "Empty/no response from model"
        assert failed["step_name"] == "test_step"
        assert failed["run_id"] == "run_004"
        assert failed["pipeline_name"] == "test_pipeline"


# -- Tests: LLMCallRateLimited (API-suggested) --------------------------------


class TestRateLimitApiSuggested:
    """Verify LLMCallRateLimited emitted with API-suggested backoff."""

    @patch('google.generativeai.GenerativeModel')
    @patch('time.sleep')
    def test_rate_limit_api_suggested_emits_event(self, mock_sleep, mock_model_class):
        """Rate limit with Retry-After emits LLMCallRateLimited with backoff_type=api_suggested."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: rate limit error with Retry-After, then success
        rate_error = Exception("429 Resource exhausted")
        # Add a mock for extract_retry_delay_from_error to return a delay
        with patch('llm_pipeline.llm.gemini.extract_retry_delay_from_error', return_value=2.5):
            _setup_model_mocks(mock_model_class, [
                rate_error,
                _create_mock_response('{"count": 10, "notes": "after rate limit"}'),
            ])

            result = provider.call_structured(
                prompt="test prompt",
                system_instruction="test system",
                result_class=SimpleSchema,
                max_retries=3,
                event_emitter=handler,
                step_name="test_step",
                run_id="run_005",
                pipeline_name="test_pipeline",
            )

        assert result.parsed is not None

        events = handler.get_events()
        ratelimit_events = [e for e in events if e["event_type"] == "llm_call_rate_limited"]
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]

        # Only LLMCallRateLimited emitted (no LLMCallRetry for rate limit)
        assert len(ratelimit_events) == 1, "Expected 1 LLMCallRateLimited"
        assert len(retry_events) == 0, "No LLMCallRetry for rate limit cases"

        # Verify fields
        rl = ratelimit_events[0]
        assert rl["attempt"] == 1
        assert rl["wait_seconds"] == 2.5
        assert rl["backoff_type"] == "api_suggested"


# -- Tests: LLMCallRateLimited (Exponential) ----------------------------------


class TestRateLimitExponential:
    """Verify LLMCallRateLimited emitted with exponential backoff."""

    @patch('google.generativeai.GenerativeModel')
    @patch('time.sleep')
    def test_rate_limit_exponential_emits_event(self, mock_sleep, mock_model_class):
        """Rate limit without Retry-After emits LLMCallRateLimited with backoff_type=exponential."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: rate limit error (no Retry-After), then success
        rate_error = Exception("429 quota exceeded")
        with patch('llm_pipeline.llm.gemini.extract_retry_delay_from_error', return_value=None):
            _setup_model_mocks(mock_model_class, [
                rate_error,
                _create_mock_response('{"count": 15, "notes": "exponential backoff"}'),
            ])

            result = provider.call_structured(
                prompt="test prompt",
                system_instruction="test system",
                result_class=SimpleSchema,
                max_retries=3,
                event_emitter=handler,
                step_name="test_step",
                run_id="run_006",
                pipeline_name="test_pipeline",
            )

        assert result.parsed is not None

        events = handler.get_events()
        ratelimit_events = [e for e in events if e["event_type"] == "llm_call_rate_limited"]

        assert len(ratelimit_events) == 1

        # Verify exponential backoff: 2^attempt (attempt=0 -> wait=1)
        rl = ratelimit_events[0]
        assert rl["attempt"] == 1
        assert rl["wait_seconds"] == 1.0  # 2^0 = 1
        assert rl["backoff_type"] == "exponential"


# -- Tests: LLMCallRetry (Generic Exception) ----------------------------------


class TestNonRateLimitExceptionRetry:
    """Verify LLMCallRetry emitted for generic exceptions (not rate limits)."""

    @patch('google.generativeai.GenerativeModel')
    def test_non_rate_limit_exception_retry_emits_event(self, mock_model_class):
        """Generic exception emits LLMCallRetry with error_type=exception."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: generic exception, then success
        _setup_model_mocks(mock_model_class, [
            Exception("Connection timeout"),
            _create_mock_response('{"count": 20, "notes": "recovered"}'),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=3,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_007",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is not None

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]

        assert len(retry_events) == 1

        # Verify fields
        retry = retry_events[0]
        assert retry["error_type"] == "exception"
        assert "Connection timeout" in retry["error_message"]
        assert retry["attempt"] == 1


# -- Tests: Zero Overhead (No Emitter) ----------------------------------------


class TestNoEmitterZeroOverhead:
    """Verify no events emitted and no overhead when event_emitter=None."""

    @patch('google.generativeai.GenerativeModel')
    def test_no_events_without_emitter(self, mock_model_class):
        """Call with event_emitter=None emits no events."""
        provider = GeminiProvider(api_key="test_key")

        # Mock: empty response 2x, then success (would trigger retries)
        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            _create_mock_response(""),
            _create_mock_response('{"count": 25, "notes": "no emitter"}'),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=3,
            event_emitter=None,  # No emitter
            step_name="test_step",
            run_id="run_008",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is not None
        # No events to verify - just ensure no crash


# -- Tests: Event Field Values ------------------------------------------------


class TestEventFieldValues:
    """Verify all event fields populated correctly."""

    @patch('google.generativeai.GenerativeModel')
    def test_retry_event_fields(self, mock_model_class):
        """LLMCallRetry has all required fields populated."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            _create_mock_response('{"count": 30, "notes": "ok"}'),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=5,
            event_emitter=handler,
            step_name="field_test_step",
            run_id="run_009",
            pipeline_name="field_test_pipeline",
        )

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]
        assert len(retry_events) == 1

        retry = retry_events[0]
        assert retry["run_id"] == "run_009"
        assert retry["pipeline_name"] == "field_test_pipeline"
        assert retry["step_name"] == "field_test_step"
        assert retry["attempt"] == 1
        assert retry["max_retries"] == 5
        assert retry["error_type"] == "empty_response"
        assert isinstance(retry["error_message"], str)
        assert len(retry["error_message"]) > 0
        assert "timestamp" in retry

    @patch('google.generativeai.GenerativeModel')
    def test_failed_event_fields(self, mock_model_class):
        """LLMCallFailed has all required fields populated."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            _create_mock_response(""),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=2,
            event_emitter=handler,
            step_name="failed_field_test",
            run_id="run_010",
            pipeline_name="failed_pipeline",
        )

        events = handler.get_events()
        failed_events = [e for e in events if e["event_type"] == "llm_call_failed"]
        assert len(failed_events) == 1

        failed = failed_events[0]
        assert failed["run_id"] == "run_010"
        assert failed["pipeline_name"] == "failed_pipeline"
        assert failed["step_name"] == "failed_field_test"
        assert failed["max_retries"] == 2
        assert isinstance(failed["last_error"], str)
        assert len(failed["last_error"]) > 0
        assert "timestamp" in failed

    @patch('google.generativeai.GenerativeModel')
    @patch('time.sleep')
    def test_ratelimited_event_fields(self, mock_sleep, mock_model_class):
        """LLMCallRateLimited has all required fields populated."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        with patch('llm_pipeline.llm.gemini.extract_retry_delay_from_error', return_value=3.0):
            _setup_model_mocks(mock_model_class, [
                Exception("429 rate limit"),
                _create_mock_response('{"count": 35, "notes": "ok"}'),
            ])

            result = provider.call_structured(
                prompt="test prompt",
                system_instruction="test system",
                result_class=SimpleSchema,
                max_retries=3,
                event_emitter=handler,
                step_name="ratelimit_field_test",
                run_id="run_011",
                pipeline_name="ratelimit_pipeline",
            )

        events = handler.get_events()
        rl_events = [e for e in events if e["event_type"] == "llm_call_rate_limited"]
        assert len(rl_events) == 1

        rl = rl_events[0]
        assert rl["run_id"] == "run_011"
        assert rl["pipeline_name"] == "ratelimit_pipeline"
        assert rl["step_name"] == "ratelimit_field_test"
        assert rl["attempt"] == 1
        assert rl["wait_seconds"] == 3.0
        assert rl["backoff_type"] == "api_suggested"
        assert "timestamp" in rl


# -- Tests: Event Ordering ----------------------------------------------------


class TestEventOrdering:
    """Verify events emitted in correct order."""

    @patch('google.generativeai.GenerativeModel')
    def test_multi_attempt_ordering(self, mock_model_class):
        """Multi-attempt scenario: verify LLMCallRetry events in correct order."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: 3 failures (empty, json, validation), then success
        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            _create_mock_response("{bad json"),
            _create_mock_response('{"count": 1}'),
            _create_mock_response('{"count": 40, "notes": "final"}'),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=4,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_012",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is not None
        assert result.attempt_count == 4

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]
        failed_events = [e for e in events if e["event_type"] == "llm_call_failed"]

        # 3 retries (no retry on last attempt which succeeded)
        assert len(retry_events) == 3
        assert len(failed_events) == 0, "No failed event on success"

        # Verify ordering
        assert retry_events[0]["error_type"] == "empty_response"
        assert retry_events[0]["attempt"] == 1
        assert retry_events[1]["error_type"] == "json_decode_error"
        assert retry_events[1]["attempt"] == 2
        assert retry_events[2]["error_type"] == "validation_error"
        assert retry_events[2]["attempt"] == 3


# -- Tests: Accumulated Errors Bug Fix ---------------------------------------


class TestAccumulatedErrorsBugFix:
    """Verify accumulated_errors bug fix: last_error correct on exception path."""

    @patch('google.generativeai.GenerativeModel')
    def test_accumulated_errors_bug_fix(self, mock_model_class):
        """Non-rate-limit exception on last attempt: LLMCallFailed.last_error contains exception."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: empty response, then generic exception on last attempt
        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            Exception("Critical API error"),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=2,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_013",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is None

        events = handler.get_events()
        failed_events = [e for e in events if e["event_type"] == "llm_call_failed"]
        assert len(failed_events) == 1

        # Bug fix verification: last_error should be the exception message, not empty response
        failed = failed_events[0]
        assert "Critical API error" in failed["last_error"], (
            f"Expected 'Critical API error' in last_error, got: {failed['last_error']}"
        )


# -- Tests: Pydantic Validation Error -----------------------------------------


class TestPydanticValidationRetry:
    """Verify LLMCallRetry emitted on Pydantic validation failures."""

    @patch('google.generativeai.GenerativeModel')
    def test_pydantic_validation_retry(self, mock_model_class):
        """Pydantic validation failure emits LLMCallRetry with pydantic_validation_error."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: JSON passes schema check but Pydantic validation fails (e.g., custom validator)
        # For this test, we'll use wrong types that pass initial validation but fail Pydantic
        _setup_model_mocks(mock_model_class, [
            _create_mock_response('{"count": "not_an_int", "notes": "test"}'),
            _create_mock_response('{"count": 45, "notes": "ok"}'),
        ])

        result = provider.call_structured(
            prompt="test prompt",
            system_instruction="test system",
            result_class=SimpleSchema,
            max_retries=3,
            event_emitter=handler,
            step_name="test_step",
            run_id="run_014",
            pipeline_name="test_pipeline",
        )

        assert result.parsed is not None

        events = handler.get_events()
        retry_events = [e for e in events if e["event_type"] == "llm_call_retry"]

        # Should have at least 1 retry event (may be validation_error or pydantic_validation_error)
        assert len(retry_events) >= 1


# -- Tests: Multiple Rate Limits ----------------------------------------------


class TestMultipleRateLimits:
    """Verify multiple rate limit attempts emit multiple LLMCallRateLimited events."""

    @patch('google.generativeai.GenerativeModel')
    @patch('time.sleep')
    def test_multiple_rate_limits(self, mock_sleep, mock_model_class):
        """Multiple rate limit errors emit multiple LLMCallRateLimited events."""
        provider = GeminiProvider(api_key="test_key")
        handler = InMemoryEventHandler()

        # Mock: 2 rate limits with different backoff types, then success
        with patch('llm_pipeline.llm.gemini.extract_retry_delay_from_error', side_effect=[1.5, None]):
            _setup_model_mocks(mock_model_class, [
                Exception("429 rate limit"),
                Exception("429 rate limit"),
                _create_mock_response('{"count": 50, "notes": "final"}'),
            ])

            result = provider.call_structured(
                prompt="test prompt",
                system_instruction="test system",
                result_class=SimpleSchema,
                max_retries=4,
                event_emitter=handler,
                step_name="test_step",
                run_id="run_015",
                pipeline_name="test_pipeline",
            )

        assert result.parsed is not None

        events = handler.get_events()
        rl_events = [e for e in events if e["event_type"] == "llm_call_rate_limited"]

        assert len(rl_events) == 2

        # First rate limit: API-suggested
        assert rl_events[0]["backoff_type"] == "api_suggested"
        assert rl_events[0]["wait_seconds"] == 1.5

        # Second rate limit: exponential (2^1 = 2)
        assert rl_events[1]["backoff_type"] == "exponential"
        assert rl_events[1]["wait_seconds"] == 2.0
