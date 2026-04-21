# IMPLEMENTATION - STEP 9: RUNNER SNAPSHOT POPULATION
**Status:** completed

## Summary
Implemented `_build_run_snapshot` function and integrated it into `EvalRunner.run_dataset` to populate the four snapshot JSON columns on `EvaluationRun` at run creation time. Handles both step-target (flat) and pipeline-target (keyed by step_name) shapes.

## Files
**Created:** none
**Modified:** `llm_pipeline/evals/runner.py`, `tests/test_eval_runner.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/evals/runner.py`
Added `_build_run_snapshot`, `_build_step_target_snapshot`, `_build_pipeline_target_snapshot` helper functions. Called `_build_run_snapshot` in `run_dataset` before `EvaluationRun(...)` construction; passes returned tuple into the four snapshot fields.

### File: `tests/test_eval_runner.py`
Added `TestRunSnapshotPopulation` class with tests #9 and #10:
- `test_run_populates_snapshots_step_target` — asserts flat prompt_versions, single-entry model_snapshot, flat instructions_schema_snapshot
- `test_run_populates_snapshots_pipeline_target` — asserts nested prompt_versions/model_snapshot/instructions_schema_snapshot keyed by step_name

## Decisions
### Snapshot function as module-level helpers
**Choice:** Three module-level functions (`_build_run_snapshot`, `_build_step_target_snapshot`, `_build_pipeline_target_snapshot`) rather than methods on EvalRunner
**Rationale:** Keeps EvalRunner class focused on orchestration; snapshot logic is a pre-pass utility. Consistent with existing `_apply_variant_to_sandbox` pattern.

### Runner reference passed to helpers
**Choice:** Pass `runner` instance to helpers for access to `_find_step_def` and `introspection_registry`
**Rationale:** Avoids duplicating step/pipeline lookup logic; reuses existing resolution patterns.

## Verification
[x] `uv run pytest tests/test_eval_runner.py` — 11 tests pass
[x] Step-target snapshot shape matches spec (case_versions, flat prompt_versions, single-entry model_snapshot, schema dict)
[x] Pipeline-target snapshot shape matches spec (nested by step_name)
[x] EvaluationCaseResult.case_id unchanged (append-only, no FK change)
