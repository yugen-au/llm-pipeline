# IMPLEMENTATION - STEP 3: UPDATE MOCKPROVIDER
**Status:** completed

## Summary
Updated MockProvider in tests/test_pipeline.py to return LLMCallResult instead of Optional[Dict]. Dict responses wrapped via LLMCallResult.success(), None fallback uses plain constructor with parsed=None.

## Files
**Created:** none
**Modified:** tests/test_pipeline.py
**Deleted:** none

## Changes
### File: `tests/test_pipeline.py`
Added `import json` and `from llm_pipeline.llm.result import LLMCallResult`. Replaced raw dict/None returns in call_structured() with LLMCallResult construction.

```python
# Before
def call_structured(self, prompt, system_instruction, result_class, **kwargs):
    if self._call_count < len(self._responses):
        response = self._responses[self._call_count]
        self._call_count += 1
        return response
    return None

# After
def call_structured(self, prompt, system_instruction, result_class, **kwargs):
    if self._call_count < len(self._responses):
        response = self._responses[self._call_count]
        self._call_count += 1
        return LLMCallResult.success(
            parsed=response,
            raw_response=json.dumps(response),
            model_name="mock-model",
            attempt_count=1,
        )
    return LLMCallResult(
        parsed=None,
        raw_response="",
        model_name="mock-model",
        attempt_count=1,
        validation_errors=[],
    )
```

## Decisions
### None required
All decisions pre-made in PLAN.md (success() for dict, plain constructor for None, "mock-model" name, attempt_count=1).

## Verification
- [x] MockProvider returns LLMCallResult.success() for dict responses
- [x] MockProvider returns LLMCallResult(parsed=None) for fallback
- [x] 29 tests pass, 3 integration tests fail as expected (executor.py incompatibility, Task 5 fixes)
- [x] Failed tests: test_full_execution, test_save_persists_to_db, test_step_state_saved -- all in TestPipelineExecution, all due to executor.py unpacking LLMCallResult as dict
