# IMPLEMENTATION - STEP 3: FIX STEPDEFINITION SNAKE_CASE
**Status:** completed

## Summary
Replaced inline double-regex in StepDefinition.create_step() with to_snake_case utility from llm_pipeline/naming.py. Removed local `import re` from create_step() -- PipelineStrategy.__init_subclass__ retains its own local `import re` (separate scope, separate step).

## Files
**Created:** none
**Modified:** llm_pipeline/strategy.py
**Deleted:** none

## Changes
### File: `llm_pipeline/strategy.py`
Added top-level import of to_snake_case. Replaced 5-line inline regex block in create_step() with single call.

```
# Before (lines 56-61)
import re
step_class_name = self.step_class.__name__
step_name_prefix = step_class_name[:-4]  # Remove 'Step' suffix
snake_case = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', step_name_prefix)
snake_case = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', snake_case)
step_name = snake_case.lower()

# After (lines 57-59)
step_class_name = self.step_class.__name__
step_name = to_snake_case(step_class_name, strip_suffix='Step')
```

## Decisions
### Keep PipelineStrategy.__init_subclass__ `import re` untouched
**Choice:** Did not modify the `import re` in __init_subclass__ (line 188)
**Rationale:** Out of scope for Step 3. That method also uses re for display_name generation (line 195-196) which has different logic (space insertion, not snake_case). Step 4 in PLAN.md covers pipeline.py, and a future step could address __init_subclass__ if desired.

## Verification
[x] to_snake_case import added at module level
[x] create_step() no longer has local `import re`
[x] create_step() uses to_snake_case(step_class_name, strip_suffix='Step')
[x] PipelineStrategy.__init_subclass__ still has its own local `import re` (unaffected)
[x] All 583 tests pass (1 pre-existing UI failure unrelated)
