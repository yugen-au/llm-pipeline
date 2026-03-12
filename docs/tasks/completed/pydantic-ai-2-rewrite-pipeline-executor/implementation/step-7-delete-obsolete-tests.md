# IMPLEMENTATION - STEP 7: DELETE OBSOLETE TESTS
**Status:** completed

## Summary
Deleted two entire test files and removed specific test classes/methods from two other test files. All removed code references symbols deleted in Steps 1-6: GeminiProvider, LLMCallResult, format_schema_for_llm, flatten_schema, validate_structured_output, strip_number_prefix, RateLimiter, execute_llm_step.

## Files
**Created:** none
**Modified:** tests/test_pipeline.py, tests/events/test_llm_call_events.py
**Deleted:** tests/test_llm_call_result.py, tests/events/test_retry_ratelimit_events.py

## Changes

### File: `tests/test_llm_call_result.py`
Deleted entirely. All 226 lines tested LLMCallResult (deleted in Step 1).

### File: `tests/events/test_retry_ratelimit_events.py`
Deleted entirely. All 753 lines tested GeminiProvider retry loop (gemini.py deleted in Step 1).

### File: `tests/test_pipeline.py`
```
# Removed imports:
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.result import LLMCallResult
import json
from typing import Any, Dict  (unused after removal)
from pydantic import BaseModel  (unused after removal)
Type  (unused after removal)

# Removed class:
class MockProvider(LLMProvider): ...  (25 lines, references LLMProvider + LLMCallResult)

# Removed method from TestImports:
def test_llm_imports(self): ...  (imports LLMProvider, RateLimiter, format_schema_for_llm)

# Removed class:
class TestSchemaUtils: ...  (tests format_schema_for_llm, flatten_schema)

# Removed class:
class TestValidation: ...  (tests validate_structured_output, strip_number_prefix)

# Removed class:
class TestRateLimiter: ...  (tests RateLimiter)
```

### File: `tests/events/test_llm_call_events.py`
```
# Removed method from TestNoEmitterZeroOverhead:
def test_no_event_params_in_call_kwargs(self, seeded_session, monkeypatch): ...
# Monkeypatched llm_pipeline.llm.executor.execute_llm_step (deleted in Step 1)
# test_no_events_without_emitter retained (references only MockProvider, handled in Step 8)
```

## Decisions

### Scope boundary: remaining MockProvider references in test_pipeline.py
**Choice:** Left all MockProvider usages in TestPipelineNaming, TestPipelineInit, TestPipelineExecution, TestEventEmitter intact.
**Rationale:** Contract explicitly scopes Step 7 to deleting tests for deleted symbols only. MockProvider replacement is Step 8's scope. Touching those now would exceed the step boundary.

### Unused imports cleanup in test_pipeline.py
**Choice:** Removed `json`, `Any`, `Dict`, `BaseModel`, `Type` imports that became unused after MockProvider deletion.
**Rationale:** Leaving dead imports would cause linter warnings and obscure the file's actual dependencies. No risk since grep confirmed zero remaining usages.

### test_no_events_without_emitter retention
**Choice:** Kept `test_no_events_without_emitter` in TestNoEmitterZeroOverhead.
**Rationale:** Contract says "keep test_no_events_without_emitter if it doesn't reference deleted symbols." The method only uses MockProvider (Step 8 scope), not execute_llm_step or other deleted symbols.

## Verification
- [x] tests/test_llm_call_result.py deleted
- [x] tests/events/test_retry_ratelimit_events.py deleted
- [x] test_llm_imports removed from TestImports
- [x] TestSchemaUtils removed from test_pipeline.py
- [x] TestValidation removed from test_pipeline.py (included strip_number_prefix test)
- [x] TestRateLimiter removed from test_pipeline.py
- [x] test_no_event_params_in_call_kwargs removed from test_llm_call_events.py
- [x] test_no_events_without_emitter retained in test_llm_call_events.py
- [x] No remaining references to deleted symbols in modified files
- [x] MockProvider references outside Step 7 scope left intact for Step 8
