# IMPLEMENTATION - STEP 2: PASS MODEL_NAME AT CALL SITE
**Status:** completed

## Summary
Extracted model_name from self._provider via getattr at the _save_step_state call site in execute(), passing it as the model_name argument. Step 1 (signature change) was already applied.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Added model_name extraction via getattr before _save_step_state call at line 560.

```python
# Before
                execution_time_ms = int(
                    (datetime.now(timezone.utc) - step_start).total_seconds() * 1000
                )
                self._save_step_state(
                    step, step_num, instructions, input_hash, execution_time_ms
                )

# After
                execution_time_ms = int(
                    (datetime.now(timezone.utc) - step_start).total_seconds() * 1000
                )
                model_name = getattr(self._provider, 'model_name', None)
                self._save_step_state(
                    step, step_num, instructions, input_hash, execution_time_ms, model_name
                )
```

## Decisions
None -- followed plan exactly.

## Verification
- [x] getattr(self._provider, 'model_name', None) used for safe extraction
- [x] model_name passed as final positional arg to _save_step_state
- [x] self._provider confirmed in scope (assigned line 152, used line 535)
- [x] Syntax check passed (ast.parse)
- [x] All 76 tests pass
