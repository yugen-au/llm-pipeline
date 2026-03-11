# IMPLEMENTATION - STEP 2: FIX DOCS/API/LLM.MD
**Status:** completed

## Summary
Fixed `call_structured()` return type from `Optional[Dict[str, Any]]` to `LLMCallResult`, added 4 missing parameters, updated Returns description, fixed abstract method example return annotation, fixed GeminiProvider example to use `result.is_success` and `result.parsed`.

## Files
**Created:** none
**Modified:** docs/api/llm.md
**Deleted:** none

## Changes
### File: `docs/api/llm.md`
1. Signature return type annotation

```
# Before
) -> Optional[Dict[str, Any]]

# After
) -> LLMCallResult
```

2. Added 4 missing parameters to signature block

```
# Before
    validation_context: Optional[ValidationContext] = None,
    **kwargs

# After
    validation_context: Optional[ValidationContext] = None,
    event_emitter: Optional[PipelineEventEmitter] = None,
    step_name: Optional[str] = None,
    run_id: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    **kwargs
```

3. Added 4 missing parameters to Parameters list

```
# Before
- `validation_context` (Optional[ValidationContext]): Context data for Pydantic validators

# After
- `validation_context` (Optional[ValidationContext]): Context data for Pydantic validators
- `event_emitter` (Optional[PipelineEventEmitter]): Event emitter for LLM call events
- `step_name` (Optional[str]): Step name for event scoping
- `run_id` (Optional[str]): Run identifier for event correlation
- `pipeline_name` (Optional[str]): Pipeline name for event scoping
```

4. Updated Returns description

```
# Before
**Returns:** `Optional[Dict[str, Any]]` - Validated JSON response dict, or None if all retries failed

# After
**Returns:** `LLMCallResult` - Result object containing parsed output, raw_response, model_name, attempt_count, and validation_errors
```

5. Fixed abstract method example return annotation and import

```
# Before
from llm_pipeline.llm import LLMProvider
...
    ) -> Optional[Dict[str, Any]]:

# After
from llm_pipeline.llm import LLMProvider
from llm_pipeline.llm.result import LLMCallResult
...
    ) -> LLMCallResult:
```

6. Fixed GeminiProvider example dict-based result access

```
# Before
if result:
    data = ParsedData(**result)

# After
if result.is_success:
    data = ParsedData(**result.parsed)
```

## Decisions
### None
No ambiguous decisions - all changes directly match provider.py:34-71 and result.py.

## Verification
[x] Return type in signature matches provider.py:50 (`-> LLMCallResult`)
[x] All 4 params from provider.py:45-48 present in signature and Parameters list
[x] Returns description updated to describe LLMCallResult fields
[x] Abstract method example uses `LLMCallResult` return type
[x] GeminiProvider example uses `result.is_success` and `result.parsed`
[x] `result.parsed` is confirmed valid attribute on LLMCallResult (result.py:20)
[x] `result.is_success` is confirmed valid property on LLMCallResult (result.py:39)

---

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] CustomProvider example references non-existent `validate_and_return(response, result_class)` helper - replaced with realistic retry loop using `LLMCallResult.success()` and `LLMCallResult(parsed=None, ...)` matching the pattern in gemini.py:237-304

### Changes Made
#### File: `docs/api/llm.md`
Replaced the placeholder `validate_and_return()` call with a realistic implementation skeleton that mirrors the actual pattern used in `llm_pipeline/llm/gemini.py`.

```
# Before
        # Implement custom provider logic
        response = self.api.generate(prompt, system_instruction)
        return validate_and_return(response, result_class)

# After
        errors = []
        for attempt in range(max_retries):
            try:
                # Call your provider API
                response_text = self.api.generate(prompt)
                response_json = parse_json(response_text)

                # Validate with Pydantic
                result_class(**response_json)

                return LLMCallResult.success(
                    parsed=response_json,
                    raw_response=response_text,
                    model_name=self.model_name,
                    attempt_count=attempt + 1,
                    validation_errors=errors,
                )
            except Exception as e:
                errors.append(str(e))

        return LLMCallResult(
            parsed=None,
            raw_response=None,
            model_name=self.model_name,
            attempt_count=max_retries,
            validation_errors=errors,
        )
```

Also added `max_retries: int = 3` to the method signature to make the retry loop coherent.

### Verification
[x] `LLMCallResult.success()` factory confirmed in result.py:54-76
[x] `LLMCallResult(parsed=None, ...)` direct construction confirmed in gemini.py:298-304
[x] `LLMCallResult.success()` call pattern matches gemini.py:237-243 exactly
[x] No non-existent helpers referenced in the example
[x] `max_retries` added to example signature (was already in abstract signature block above)
