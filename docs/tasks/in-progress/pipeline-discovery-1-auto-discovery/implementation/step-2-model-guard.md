# IMPLEMENTATION - STEP 2: MODEL GUARD
**Status:** completed

## Summary
Added model None guard to trigger_run endpoint in runs.py. When no default model is configured (app.state.default_model is None), the endpoint returns HTTP 422 with an actionable error message before any pipeline execution attempt.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/runs.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/runs.py`
Added model None guard after factory lookup, before pipeline execution. Uses `getattr(request.app.state, "default_model", None)` to safely retrieve the model set by `create_app()` in step 1.

```
# Before (lines 207-209)
    run_id = str(uuid.uuid4())
    engine = request.app.state.engine

# After (lines 207-217)
    # Guard: model must be configured before pipeline execution
    default_model = getattr(request.app.state, "default_model", None)
    if default_model is None:
        raise HTTPException(
            status_code=422,
            detail="No model configured. Set LLM_PIPELINE_MODEL env var or pass --model flag.",
        )

    run_id = str(uuid.uuid4())
    engine = request.app.state.engine
```

## Decisions
### Guard placement after factory lookup
**Choice:** Guard placed after factory lookup (404 check) but before run_id generation and factory call
**Rationale:** Pipeline must exist before checking model config -- returning 422 for a nonexistent pipeline would be misleading. Guard sits at the execution boundary per CEO decision: missing model should not block UI startup/browsing, only fail at execution time.

### Use getattr with default None
**Choice:** `getattr(request.app.state, "default_model", None)` instead of direct attribute access
**Rationale:** Defensive access ensures backward compatibility if runs.py is used with an older create_app() that doesn't set default_model.

## Verification
[x] Guard is after factory lookup (404 for unknown pipeline takes priority)
[x] Guard is before factory call (no pipeline instantiation attempted without model)
[x] HTTP 422 status code matches PLAN.md specification
[x] Error message matches PLAN.md: actionable, references env var and --model flag
[x] app.state.default_model set by step 1 in create_app() (line 173 of app.py)
