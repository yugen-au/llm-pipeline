# IMPLEMENTATION - STEP 2: FIX LLMSTEP.STEP_NAME
**Status:** completed

## Summary
Replaced buggy single-regex in `LLMStep.step_name` property with `to_snake_case()` from `llm_pipeline/naming.py`. Removed unused `import re`.

## Files
**Created:** none
**Modified:** llm_pipeline/step.py
**Deleted:** none

## Changes
### File: `llm_pipeline/step.py`
Removed `import re`, added `from llm_pipeline.naming import to_snake_case`, replaced inline single-regex with `to_snake_case(class_name, strip_suffix='Step')`.

```
# Before
import re
...
name = class_name[:-4]
snake_case = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
return snake_case

# After
from llm_pipeline.naming import to_snake_case
...
return to_snake_case(class_name, strip_suffix='Step')
```

## Decisions
### Delegate suffix stripping to to_snake_case
**Choice:** Pass `strip_suffix='Step'` instead of manually slicing `class_name[:-4]` before calling
**Rationale:** `to_snake_case` already handles `strip_suffix`; keeps the property body minimal. The `endswith('Step')` guard still runs before the call for the error message.

### Remove import re
**Choice:** Removed top-level `import re` from step.py
**Rationale:** No other `re` usage in the file after replacing the inline regex.

## Verification
[x] `to_snake_case('HTMLParserStep', strip_suffix='Step')` returns `'html_parser'` (previously `'htmlparserstep'`)
[x] `to_snake_case('ConstraintExtractionStep', strip_suffix='Step')` returns `'constraint_extraction'`
[x] No `re.sub` remaining in step_name property
[x] No `import re` remaining in step.py
[x] 803 tests pass, 1 pre-existing failure (test_ui.py events router prefix -- unrelated)
