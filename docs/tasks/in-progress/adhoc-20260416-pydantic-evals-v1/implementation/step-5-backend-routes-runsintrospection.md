# IMPLEMENTATION - STEP 5: BACKEND ROUTES RUNS+INTROSPECTION
**Status:** completed

## Summary
Added eval run management (list, detail, trigger) and schema introspection endpoints to the evals router. Appended to existing evals.py (created by step 4) rather than creating separate file.

## Files
**Created:** `llm_pipeline/ui/routes/eval_runs.py` (stub only, endpoints merged into evals.py)
**Modified:** `llm_pipeline/ui/routes/evals.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/evals.py`
Added imports (BackgroundTasks, Request), 6 Pydantic response/request models (CaseResultItem, RunListItem, RunListResponse, RunDetail, TriggerRunRequest, TriggerRunResponse, SchemaResponse), 3 run endpoints (GET list, GET detail, POST trigger), 1 schema introspection endpoint (GET /schema), and 2 private helper functions (_pipeline_schema, _step_schema).

Run endpoints use direct Session(engine) for DB access (not ReadOnlySession dep) since trigger_eval_run needs write access and the run endpoints need fresh data including background-task updates. POST trigger uses BackgroundTasks + EvalRunner.run_dataset() pattern matching existing POST /runs.

Schema introspection searches introspection_registry for pipeline INPUT_DATA or step instructions/context Pydantic models and calls model_json_schema().

## Decisions
### Merge into evals.py vs separate file
**Choice:** Appended to evals.py after step 4's marker comment
**Rationale:** Step 4 agent created evals.py with same router prefix. Two routers with same prefix causes conflicts. Marker comment indicated where to append.

### Session management for run endpoints
**Choice:** Direct Session(engine) via request.app.state.engine instead of DBSession/WritableDBSession deps
**Rationale:** Consistent with how trigger_run works in runs.py. Background task needs engine reference, not a request-scoped session. Run list/detail need fresh reads including in-progress background updates.

### Schema fallback chain for steps
**Choice:** instructions type -> context type -> 404
**Rationale:** instructions is the primary structured output schema (what evals validate against). context is fallback for steps that define input via context type. If neither has model_json_schema, 404 with clear message.

## Verification
[x] Python syntax check passes (ast.parse)
[x] All imports resolve (BackgroundTasks, Request added to fastapi import)
[x] Route ordering safe (dataset_id typed as int, /schema won't match)
[x] Matches PLAN.md step 10 spec for all endpoints and models
[x] TriggerRunResponse returns run_id + status="accepted" per spec
