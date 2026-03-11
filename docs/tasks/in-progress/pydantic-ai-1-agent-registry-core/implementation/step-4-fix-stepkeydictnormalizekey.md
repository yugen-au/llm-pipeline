# IMPLEMENTATION - STEP 4: FIX STEPKEYDICT._NORMALIZE_KEY
**Status:** completed

## Summary
Replaced inline double-regex in `StepKeyDict._normalize_key()` with `to_snake_case()` from `llm_pipeline/naming.py`.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Added `from llm_pipeline.naming import to_snake_case` import and replaced inline `re.sub` calls in `_normalize_key()` with single `to_snake_case()` call.

```python
# Before
@staticmethod
def _normalize_key(key):
    if isinstance(key, type) and key.__name__.endswith("Step"):
        class_name = key.__name__[:-4]
        step_name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", class_name)
        step_name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", step_name)
        return step_name.lower()
    return key

# After
@staticmethod
def _normalize_key(key):
    if isinstance(key, type) and key.__name__.endswith("Step"):
        return to_snake_case(key.__name__, strip_suffix="Step")
    return key
```

## Decisions
### Keep `import re`
**Choice:** Retained `import re` in pipeline.py
**Rationale:** `re.sub` is still used at line 264 in `PipelineConfig.pipeline_name` property for pipeline name conversion. Only `_normalize_key` was in scope for this step.

## Verification
[x] `_normalize_key` uses `to_snake_case` with `strip_suffix="Step"` -- no inline `re.sub`
[x] Import added for `to_snake_case` from `llm_pipeline.naming`
[x] `import re` retained (used elsewhere in file at line 264)
[x] All 803 tests pass (1 pre-existing failure in test_ui.py unrelated to this change)
