# IMPLEMENTATION - STEP 1: BACKEND RAW_RESPONSE
**Status:** completed

## Summary
Added `_extract_raw_response()` helper to extract raw LLM response from pydantic-ai `RunResult.new_messages()` and wired it into both `LLMCallCompleted` emission sites (non-consensus and consensus paths) in `pipeline.py`. Previously both sites hardcoded `raw_response=None`.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

Added module-level helper function `_extract_raw_response(run_result) -> str | None` between `StepKeyDict` class and `PipelineConfig` class (lines 87-120). Finds last `ModelResponse` in `run_result.new_messages()`, serializes `ToolCallPart.args` via `json.dumps` (with `str()` fallback) and `TextPart.content` as-is, joins multiple parts with `\n`.

```python
# Before (line ~857, non-consensus path)
raw_response=None,

# After
raw_response=_extract_raw_response(run_result) if run_result else None,
```

```python
# Before (line ~1281, consensus path)
raw_response=None,

# After
raw_response=_extract_raw_response(run_result) if run_result else None,
```

Both emission sites: initialized `run_result = None` before the try block to handle the `UnexpectedModelBehavior` exception path where `run_result` would be unbound.

## Decisions
### Guard against unbound run_result on exception path
**Choice:** Initialize `run_result = None` before try block; use `if run_result else None` at emission site
**Rationale:** Both emission sites are after the try/except. If `UnexpectedModelBehavior` is raised, `run_result` is never assigned. Guarding avoids `NameError` and correctly emits `raw_response=None` for failed LLM calls.

### Lazy import of pydantic_ai.messages types
**Choice:** Import `ModelResponse`, `ToolCallPart`, `TextPart` inside the helper function body
**Rationale:** Consistent with existing pattern in pipeline.py where pydantic_ai imports are deferred (e.g., `UnexpectedModelBehavior` imported inside methods). Avoids top-level import of pydantic_ai internals.

### Broad except on new_messages()
**Choice:** Wrap `run_result.new_messages()` in `try/except Exception`
**Rationale:** Defensive against unexpected pydantic-ai internal errors. Returns `None` gracefully, which is already a valid value for `raw_response`.

## Verification
[x] All 1048 tests pass (0 failures, 6 skipped)
[x] Smoke test: ToolCallPart args serialized to JSON string
[x] Smoke test: TextPart content returned as-is
[x] Smoke test: Empty messages returns None
[x] Smoke test: Multiple parts joined with \n
[x] No new imports at module level (consistent with existing patterns)
[x] json already imported at line 11
