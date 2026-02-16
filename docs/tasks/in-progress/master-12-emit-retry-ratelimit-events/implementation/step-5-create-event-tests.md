# IMPLEMENTATION - STEP 5: CREATE EVENT TESTS
**Status:** completed

## Summary
Created comprehensive test suite for LLMCallRetry, LLMCallFailed, and LLMCallRateLimited event emissions in GeminiProvider's retry loop. Tests cover all 8 emission paths with 16 test cases verifying event fields, ordering, and CEO decisions (rate limit event semantics, retry timing, accumulated_errors bug fix).

## Files
**Created:** tests/events/test_retry_ratelimit_events.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/events/test_retry_ratelimit_events.py`
Created comprehensive integration test suite with 16 test cases covering:
- Empty response retry (2 tests)
- JSON decode error retry (1 test)
- Validation failure retry (1 test)
- All attempts fail (1 test)
- Rate limit API-suggested backoff (1 test)
- Rate limit exponential backoff (1 test)
- Generic exception retry (1 test)
- Zero overhead when no emitter (1 test)
- Event field values verification (3 tests)
- Event ordering (1 test)
- Accumulated errors bug fix (1 test)
- Pydantic validation retry (1 test)
- Multiple rate limits (1 test)

```python
# Test structure
class TestEmptyResponseRetry:
    """Verify LLMCallRetry events emitted on empty/no response from model."""

    def test_empty_response_retry_emits_events(self, mock_model_class):
        """Empty response on first 2 attempts emits 2 LLMCallRetry, then success."""
        # Mock: empty response 2x, then valid JSON
        _setup_model_mocks(mock_model_class, [
            _create_mock_response(""),
            _create_mock_response(None),
            _create_mock_response('{"count": 1, "notes": "ok"}'),
        ])
        # Verify 2 LLMCallRetry events with error_type="empty_response"
```

Key implementation details:
1. Test schema inherits from LLMResultMixin with example ClassVar (required by format_schema_for_llm)
2. Mocking at Gemini API level using `@patch('google.generativeai.GenerativeModel')`
3. Helper function `_setup_model_mocks()` creates mock instances per retry attempt
4. Each test verifies specific emission path, event fields, and CEO decisions

## Decisions
### Mock Strategy
**Choice:** Mock at Gemini API level (GenerativeModel class) with per-attempt instances
**Rationale:** GeminiProvider instantiates GenerativeModel inside the retry loop (line 101-104). Each retry creates a new model instance, so side_effect must return a list of mock instances rather than a single instance with side_effect on generate_content. This exercises production retry loop behavior.

### Test Schema Design
**Choice:** SimpleSchema inherits from LLMResultMixin with example ClassVar
**Rationale:** format_schema_for_llm (line 106) expects result_class.get_example() (defined in LLMResultMixin). Using plain BaseModel caused "get_example" errors. Matches existing test patterns in conftest.py.

### Helper Function Pattern
**Choice:** Created `_setup_model_mocks(mock_model_class, responses)` helper
**Rationale:** Centralizes mocking logic for 16 tests. Handles both response objects and exceptions uniformly. Reduces duplication and makes test intent clearer.

### Test Coverage Scope
**Choice:** 16 test cases covering all 8 emission paths plus field/ordering verification
**Rationale:** Follows PLAN.md Step 5 requirements (14+ test cases). Covers:
- 5 validation retry paths (empty, JSON, validation, array, Pydantic)
- 2 rate-limit paths (API-suggested, exponential)
- 1 generic exception path
- 1 post-loop failure path
- Field values, ordering, bug fix verification

### CEO Decision Verification
**Choice:** Tests explicitly verify CEO decisions from PLAN.md Architecture Decisions
**Rationale:**
- Rate limit: Only LLMCallRateLimited emitted (test verifies no LLMCallRetry on rate limit)
- Retry timing: Only non-last attempts emit LLMCallRetry (test verifies last attempt goes to LLMCallFailed only)
- Bug fix: last_error contains exception from last attempt (test verifies exception not overwritten by previous error)

## Verification
- [x] All 16 tests pass
- [x] Tests cover all 8 emission paths from PLAN.md Step 3
- [x] Tests verify event field values (run_id, pipeline_name, step_name, attempt, max_retries, error_type, error_message, wait_seconds, backoff_type, last_error)
- [x] Tests verify event ordering (LLMCallRetry x N, then success/fail)
- [x] Tests verify zero overhead when event_emitter=None
- [x] Tests verify CEO decisions (rate limit semantics, retry timing, bug fix)
- [x] Tests mock at Gemini API level (GenerativeModel.generate_content)
- [x] Tests follow existing patterns from tests/events/ (InMemoryEventHandler, conftest.py fixtures)
- [x] Test schema inherits from LLMResultMixin with example ClassVar
- [x] google-generativeai available in dev dependencies (verified in pyproject.toml)
