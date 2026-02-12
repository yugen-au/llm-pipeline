# IMPLEMENTATION - STEP 2: UPDATE GEMINIPROVIDER
**Status:** completed

## Summary
Updated GeminiProvider.call_structured() to return LLMCallResult at all 3 exit points (not-found, success, exhaustion) instead of Optional[Dict]. Added state tracking for last_raw_response and accumulated_errors across retry loop.

## Files
**Created:** none
**Modified:** llm_pipeline/llm/gemini.py
**Deleted:** none

## Changes
### File: `llm_pipeline/llm/gemini.py`

Added import for LLMCallResult, changed return type, added tracking vars, updated all 3 exit points with error accumulation.

```
# Before - import section
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.rate_limiter import RateLimiter
from llm_pipeline.llm.schema import format_schema_for_llm

# After - import section
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.rate_limiter import RateLimiter
from llm_pipeline.llm.result import LLMCallResult
from llm_pipeline.llm.schema import format_schema_for_llm
```

```
# Before - return type + loop init
) -> Optional[Dict[str, Any]]:
    ...
    for attempt in range(max_retries):

# After - return type + tracking vars
) -> LLMCallResult:
    ...
    last_raw_response: str | None = None
    accumulated_errors: list[str] = []
    for attempt in range(max_retries):
```

```
# Before - not-found exit
return None

# After - not-found exit
return LLMCallResult(parsed=None, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=[])
```

```
# Before - success exit
return response_json

# After - success exit
return LLMCallResult.success(parsed=response_json, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=accumulated_errors)
```

```
# Before - exhaustion exit
return None

# After - exhaustion exit
return LLMCallResult(parsed=None, raw_response=last_raw_response, model_name=self.model_name, attempt_count=max_retries, validation_errors=accumulated_errors)
```

Error accumulation added at 3 points: structural validation errors (extend), array validation errors (extend), Pydantic validation errors (append str).

`last_raw_response` assigned after each `response.text` capture so exhaustion exit has the last successful raw response even if validation failed.

## Decisions
### Constructor vs Factory for exit points
**Choice:** Plain constructor for not-found and exhaustion, success() factory for success
**Rationale:** Per PLAN.md - plain constructor accepts str|None for raw_response (exhaustion may have None if all attempts threw exceptions before response.text). success() validates parsed is non-None.

### Error accumulation strategy
**Choice:** extend() for list[str] errors from validation functions, append(str()) for Pydantic exceptions
**Rationale:** validate_structured_output and validate_array_response return list[str] - extend is natural. Pydantic raises a single exception - stringify and append.

## Verification
[x] Syntax check passes (ast.parse)
[x] All 3 exit points return LLMCallResult
[x] Return type annotation changed to LLMCallResult
[x] last_raw_response tracked across retry loop
[x] accumulated_errors populated at all validation failure points
[x] Not-found exit uses empty validation_errors (no validation was attempted)
[x] Success exit uses success() factory with accumulated_errors from prior attempts
[x] Exhaustion exit uses plain constructor with last_raw_response (str|None) and accumulated_errors
