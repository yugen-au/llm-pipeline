# IMPLEMENTATION - STEP 2: ADD CONTEXT EVOLUTION TO RUNS.PY
**Status:** completed

## Summary
Appended ContextSnapshot, ContextEvolutionResponse models and GET /{run_id}/context endpoint to runs.py. No existing code modified.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/runs.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/runs.py`
Appended after trigger_run endpoint (line 229+): 2 new Pydantic response models and 1 new endpoint.

```python
# Before
# (file ended at line 229 with trigger_run return)

# After (appended)
class ContextSnapshot(BaseModel):
    step_name: str
    step_number: int
    context_snapshot: dict

class ContextEvolutionResponse(BaseModel):
    run_id: str
    snapshots: List[ContextSnapshot]

@router.get("/{run_id}/context", response_model=ContextEvolutionResponse)
def get_context_evolution(run_id: str, db: DBSession) -> ContextEvolutionResponse:
    # validates run exists (404), queries steps ordered by step_number, returns snapshots
```

## Decisions
### context_snapshot type as dict (not Optional[dict])
**Choice:** `context_snapshot: dict` in ContextSnapshot model
**Rationale:** PipelineStepState.context_snapshot is `dict` (non-optional) in state.py. No nullable column, so dict is safe.

## Verification
[x] Imports verified: `from llm_pipeline.ui.routes.runs import ContextSnapshot, ContextEvolutionResponse, get_context_evolution`
[x] All 23 existing test_runs.py tests pass (no regressions)
[x] No existing code modified -- only appended after line 229
[x] Uses sync def, DBSession dependency, plain BaseModel -- matches runs.py conventions
[x] Uses existing imports: List (line 5), PipelineStepState (line 12), PipelineRun (line 12)
