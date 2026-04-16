# IMPLEMENTATION - STEP 3: YAML SYNC + EVAL RUNNER + CLI
**Status:** completed

## Summary
Created YAML dataset sync service, eval runner using pydantic-evals, and CLI eval subcommand. All 27 tests pass.

## Files
**Created:** llm_pipeline/evals/yaml_sync.py, llm_pipeline/evals/runner.py, tests/test_eval_yaml_sync.py, tests/test_eval_runner.py
**Modified:** llm_pipeline/ui/cli.py
**Deleted:** none

## Changes
### File: `llm_pipeline/evals/yaml_sync.py`
New file. `sync_evals_yaml_to_db()` scans dirs for *.yaml, parses eval dataset format, inserts EvaluationDataset + EvaluationCase rows if not exists (by name). `write_dataset_to_yaml()` loads from DB and writes atomically via tempfile + Path.replace().

### File: `llm_pipeline/evals/runner.py`
New file. `EvalRunner` class with `run_dataset()` and `run_dataset_by_name()`. Creates EvaluationRun row, builds pydantic-evals Dataset with Cases, calls `evaluate_sync()`, persists EvaluationCaseResult rows with pass/fail from assertions. Handles both step and pipeline target_type. `_find_step_def()` searches across all registered pipelines. `_resolve_evaluators()` uses step_def.evaluators or falls back to `build_auto_evaluators()`. `_build_step_task_fn()` uses `build_step_agent` + `agent.run_sync`. `_build_pipeline_task_fn()` calls `pipeline.execute(input_data=...)` and collects instructions outputs.

### File: `llm_pipeline/ui/cli.py`
Added `eval` subparser with positional `dataset_name`, `--db`, `--model`, `--pipelines` args. Added `_run_eval()` function that inits DB, runs convention discovery, syncs eval YAML from CWD, instantiates EvalRunner, runs dataset by name, prints summary.

### File: `tests/test_eval_yaml_sync.py`
8 tests: insert new dataset+cases, no duplicate on re-sync, empty/nonexistent dir handling, metadata storage, writeback produces parseable YAML, roundtrip, nonexistent dataset raises.

### File: `tests/test_eval_runner.py`
6 tests: run with correct counts, run with custom pydantic-evals Evaluator (1 pass/1 fail), run_dataset_by_name, not found error, no cases error, resolve_task failure marks run as failed.

## Decisions
### Case evaluators parameter
**Choice:** Pass `tuple(evaluators)` when evaluators present, `()` when None
**Rationale:** pydantic-evals Case.__init__ calls `list(evaluators)` which fails on None. The API expects a tuple/sequence, not None.

### Report serialization fallback
**Choice:** Try `report.model_dump_json()` first, fall back to summary dict
**Rationale:** EvaluationReport is a dataclass, not guaranteed to have model_dump_json in all versions. Fallback ensures report_data always populated.

### Task failure handling
**Choice:** pydantic-evals catches task_fn exceptions internally per-case; only pre-evaluate errors (resolve_task, Case construction) trigger run-level failure
**Rationale:** pydantic-evals evaluate_sync handles task errors gracefully at case level. Runner wraps the entire evaluate call in try/except for infrastructure-level failures.

## Verification
[x] 27 tests pass (8 yaml_sync + 6 runner + 13 evaluators)
[x] No hardcoded values
[x] Error handling: run marked failed on exception, atomic YAML write with cleanup
[x] CLI dispatches correctly to _run_eval
