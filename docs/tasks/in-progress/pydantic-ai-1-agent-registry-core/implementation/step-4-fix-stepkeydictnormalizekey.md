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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] `PipelineConfig.pipeline_name` uses single-regex producing wrong results for consecutive capitals (e.g. `HTMLPipeline` -> `htmlpipeline` instead of `html`)

### Changes Made
#### File: `llm_pipeline/pipeline.py`
Replaced inline single-regex in `pipeline_name` property with `to_snake_case()` and removed now-unused `import re`.

```python
# Before
name = class_name[:-8]
snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
return snake_case

# After
return to_snake_case(class_name, strip_suffix="Pipeline")
```

```python
# Before (imports)
import re

# After (imports)
# removed -- no remaining re usages in pipeline.py
```

### Verification
[x] `pipeline_name` uses `to_snake_case` with `strip_suffix="Pipeline"` -- no inline `re.sub`
[x] `import re` removed -- grep confirms zero `re.` usages remain in pipeline.py
[x] No other inline regex callsites remain in pipeline.py
[x] All 854 tests pass (1 pre-existing failure in test_ui.py unrelated to this change)
