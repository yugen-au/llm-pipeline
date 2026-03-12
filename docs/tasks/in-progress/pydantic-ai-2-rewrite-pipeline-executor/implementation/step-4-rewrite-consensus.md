# IMPLEMENTATION - STEP 4: REWRITE CONSENSUS
**Status:** completed

## Summary
Rewrote `_execute_with_consensus()` in `pipeline.py` to use pydantic-ai `agent.run_sync()` instead of legacy `execute_llm_step()`. Updated signature to accept agent, user_prompt, step_deps, output_type params. Added UnexpectedModelBehavior error handling.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Changed `_execute_with_consensus` signature and body. Replaced legacy executor import and call with pydantic-ai agent pattern.

```
# Before
def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls, current_step_name):
    from llm_pipeline.llm.executor import execute_llm_step
    ...
    instruction = execute_llm_step(**call_kwargs)

# After
def _execute_with_consensus(self, agent, user_prompt, step_deps, output_type, consensus_threshold, maximum_step_calls, current_step_name):
    from pydantic_ai import UnexpectedModelBehavior
    ...
    try:
        run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
        instruction = run_result.output
    except UnexpectedModelBehavior as exc:
        instruction = output_type.create_failure(str(exc))
```

## Decisions
### Import placement
**Choice:** Local import of UnexpectedModelBehavior inside the method body
**Rationale:** Matches existing pattern in the file (execute_llm_step was also a local import). Step 3 may add module-level import; keeping local avoids merge conflicts.

### model= passed at run_sync time
**Choice:** Pass `model=self._model` in each `agent.run_sync()` call per PLAN.md
**Rationale:** Agent constructed with `defer_model_check=True`, so model set at run_sync time. Consistent with Step 3's execute() loop pattern.

## Verification
[x] Signature changed: call_kwargs replaced with agent, user_prompt, step_deps, output_type
[x] Legacy import removed: no reference to execute_llm_step
[x] UnexpectedModelBehavior import added
[x] agent.run_sync called with user_prompt, deps=step_deps, model=self._model
[x] Exception handler maps to output_type.create_failure(str(exc))
[x] Rest of consensus logic (grouping, matching, events) unchanged
