# IMPLEMENTATION - STEP 3: RUNNER INTEGRATION - DELTA + PROMPT OVERRIDE
**Status:** completed

## Summary
Wired variants into the evaluation runner. `run_dataset` + `run_dataset_by_name` now accept optional `variant_id`; when present, the `EvaluationVariant` row is loaded (with dataset-ownership validation), its delta deep-copied to a snapshot, and the 4 delta types applied:
- `instructions_delta` → `apply_instruction_delta(step_def.instructions, ...)` BEFORE evaluator resolution (CEO-required ordering), replacing `step_def` via `dataclasses.replace`.
- `model` → precedence over caller-supplied `model` and step-def default; also upserts a `StepModelConfig` row with `pipeline_name="sandbox"`.
- `system_prompt` / `user_prompt` → UPDATE sandbox `Prompt` rows matching `step_def.system_instruction_key` / `user_prompt_key` AFTER `create_sandbox_engine` seeds them from prod.
- `variable_definitions` → `merge_variable_definitions(prod, variant)` by name (variant wins), written back to sandbox Prompt rows preserving original column shape.

`variant_id` + `delta_snapshot` (deep-copied JSON) persisted on the `EvaluationRun` row.

Auto-discovery path (system/user key None): logs a warning and skips prompt override silently — documented as v2 limitation.

Security (PLAN.md Docker-sandbox-readiness): no host paths, no Python class objects, no closures cross the variant boundary. `merge_variable_definitions` is pure data-structure merge with zero expression evaluation — `auto_generate` strings pass through untouched.

## Files
**Created:** none
**Modified:**
- d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\delta.py
- d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\__init__.py
- d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\runner.py
- d:\Documents\claude-projects\llm-pipeline\tests\test_eval_variants.py
**Deleted:** none

## Changes

### File: `llm_pipeline/evals/delta.py`
Added `merge_variable_definitions(prod_defs, variant_defs) -> list`. Pass-through merge by variable name; variant wins on collision; None handled; no expression evaluation.

### File: `llm_pipeline/evals/__init__.py`
Exported `merge_variable_definitions` alongside `apply_instruction_delta`.

### File: `llm_pipeline/evals/runner.py`
- `run_dataset`: added `variant_id` param; loads variant, validates dataset ownership, deep-copies delta to snapshot, stores `variant_id` + `delta_snapshot` on the run row.
- `run_dataset_by_name`: added `variant_id` param, forwards to `run_dataset`.
- `_resolve_task` / `_resolve_step_task`: accept `variant_delta`; apply `apply_instruction_delta` BEFORE `_resolve_evaluators`; model precedence = variant > kwarg > default.
- `_build_step_task_fn`: accepts `variant_delta`; builds sandbox engine up-front via `create_sandbox_engine`, patches via `_apply_variant_to_sandbox`, passes `engine=` into `create_single_step_pipeline` (so prompt seeding isn't repeated).
- `_apply_variant_to_sandbox` (module-level helper): updates sandbox `Prompt` content for system/user keys, merges `variable_definitions`, upserts `StepModelConfig` with `pipeline_name="sandbox"`. Defensive logging for missing keys / missing rows.
- `_coerce_var_defs` / `_encode_var_defs`: handle both list-of-dicts and {name: spec}-dict shapes of `Prompt.variable_definitions`.

### File: `tests/test_eval_variants.py`
Appended three test classes (Step 3 section):
- `TestMergeVariableDefinitions`: None handling, disjoint union, variant-wins-on-collision, `auto_generate` pass-through (no evaluation), items-without-name skipped.
- `TestApplyVariantToSandbox`: system/user prompt override, var-defs merge, model upsert (insert + update), missing-key warnings, missing-prompt-row warning.
- `TestRunnerVariantIntegration`: end-to-end integration test with all 4 delta types (assertions: `run.variant_id` set, `run.delta_snapshot` matches delta exactly, sandbox engine received model/prompt/var-defs overrides, `step_model` picked variant value); evaluator resolution ordering (variant-added `urgency` field appears in auto-evaluator set); ValueError when variant not owned by dataset; ValueError when variant_id not found; `run_dataset_by_name` forwards `variant_id`; baseline run has `variant_id` and `delta_snapshot` NULL.

## Decisions

### `merge_variable_definitions` placement
**Choice:** Added to `llm_pipeline/evals/delta.py`.
**Rationale:** Already holds the companion `apply_instruction_delta`; both are pure JSON-in / JSON-out helpers; keeping them co-located preserves the "delta toolkit" module boundary and avoids fragmenting the evals package for a 30-line helper. Alternative (new `llm_pipeline/evals/variants.py`) rejected — too small to justify.

### Sandbox engine creation moved up in task_fn
**Choice:** `_build_step_task_fn`'s task_fn now explicitly calls `create_sandbox_engine(prod_engine)` then `_apply_variant_to_sandbox(...)` then passes `engine=sandbox_engine` into `create_single_step_pipeline`.
**Rationale:** The prior code delegated sandbox creation to `create_single_step_pipeline`. Patching requires the engine before the pipeline instantiates (prompts loaded during execute). Explicit two-step pattern is cleaner and makes the patching seam visible.

### step_def mutation avoided via `dataclasses.replace`
**Choice:** After `apply_instruction_delta` the runner calls `dataclasses.replace(step_def, instructions=modified_cls)` rather than mutating `step_def.instructions` in place.
**Rationale:** `step_def` comes from the registered pipeline introspection chain — mutation would leak variant state into every subsequent run (including prod). `dataclasses.replace` is a copy-on-write pattern that preserves prod-path purity. Required for concurrent eval runs of the same step with different variants.

### Model precedence: variant > kwarg > default
**Choice:** Variant `model` beats the `model` parameter to `run_dataset` which beats `step_def.default_model`.
**Rationale:** Variants are explicit opt-in overrides of the step spec; users triggering a variant run expect the variant's model to apply. Keeping kwarg in second position lets evaluators still override model for non-variant runs.

### Missing prompt keys: warning, no raise
**Choice:** When `system_instruction_key` / `user_prompt_key` is None (auto-discovery path) or the sandbox Prompt row is missing, log a warning and continue with the un-overridden prompt.
**Rationale:** PLAN.md risks-table already flags this as a v2 limitation ("prompt overrides require named prompt keys"). Raising would block variant runs on many real pipelines that use auto-discovery; warning + skip preserves the other 3 delta types (model, instructions_delta, variable_definitions) and keeps the feature useful.

### `variable_definitions` column shape preservation
**Choice:** `_coerce_var_defs` + `_encode_var_defs` helpers detect whether the prod column stores a list-of-dicts or a {name: spec} dict and write back in the same shape.
**Rationale:** The ORM types the column as `dict` but existing pipelines persist both shapes in the wild. Changing the shape on variant runs would corrupt the sandbox copy and risk confusing downstream render code. Round-trip shape preservation is the safe default.

### End-to-end test via stubbed `_build_step_task_fn`
**Choice:** The integration test mocks `_find_step_def` (returns a synthetic StepDefinition-like dataclass) and `_build_step_task_fn` (captures arguments, then executes the sandbox-patch path manually inside the stub task). Real LLM call not exercised.
**Rationale:** Runner-layer integration is independently verifiable from LLM behaviour. The assertions cover the full surface: run row fields, runner → sandbox-patcher handoff, sandbox state after patching. A true E2E (with pydantic-ai TestModel) belongs in a higher-level test suite and is outside Step 3's scope.

## Verification
- [x] `uv run pytest tests/test_eval_variants.py` — 84 passed (20 new + 64 prior)
- [x] `uv run pytest tests/test_eval_runner.py` — 6 passed (pre-existing)
- [x] Full suite: 1440 passed, 15 failed — all 15 failures are pre-existing on clean tree (verified via `git stash` + run; test_evaluators, creator/test_sandbox, ui/test_cli, ui/test_runs are unrelated)
- [x] No Python class objects, host paths, closures or ORM rows cross into `delta_snapshot` / variant boundary — deep-copy of JSON dict only
- [x] `merge_variable_definitions` does not evaluate `auto_generate` expressions (test: `test_auto_generate_expressions_passed_through_unevaluated`)
- [x] Evaluator resolution uses the modified instructions class (test: `test_evaluator_resolution_uses_modified_instructions_class`)
- [x] Variant not owned by dataset raises ValueError (test: `test_variant_not_belonging_to_dataset_raises`)
- [x] Missing variant_id raises ValueError (test: `test_missing_variant_id_raises`)
- [x] Baseline run (no variant_id) leaves variant_id + delta_snapshot NULL (test: `test_no_variant_id_baseline_run_snapshot_null`)
- [x] Sandbox receives all 4 delta types correctly (test: `test_run_with_variant_persists_variant_id_and_snapshot` asserts sys_content, cfg_model, sys_var_defs post-patch)
- [x] `llm_pipeline/ui/routes/evals.py` NOT modified (Step 4 concurrent scope)


## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
- [x] LOW: `_coerce_var_defs` / `_encode_var_defs` duplicated between system/user prompt branches in `_apply_variant_to_sandbox` (runner.py L606-667)

### Changes Made
#### File: `llm_pipeline/evals/runner.py`
Extracted duplicated merge-and-write pattern into new private helper `_merge_variant_defs_into_prompt(session, prompt, content_override, variant_var_defs)`. Both system_prompt and user_prompt branches now delegate to it. Removed now-unused `merge_variable_definitions` import from `_apply_variant_to_sandbox` body (moved into helper). Pure refactor — no behavior change, variant still wins on name conflict, original column shape preserved, content override still only applied when string.

```
# Before (system branch, ~20 lines mirrored in user branch)
if prompt is not None:
    if isinstance(system_content_override, str):
        prompt.content = system_content_override
    merged = merge_variable_definitions(
        _coerce_var_defs(prompt.variable_definitions),
        _coerce_var_defs(variant_var_defs),
    )
    prompt.variable_definitions = (
        _encode_var_defs(prompt.variable_definitions, merged)
    )
    session.add(prompt)

# After (single helper call)
if prompt is not None:
    _merge_variant_defs_into_prompt(
        session,
        prompt,
        system_content_override,
        variant_var_defs,
    )
```

New helper:
```
def _merge_variant_defs_into_prompt(
    session: Session,
    prompt: Any,
    content_override: Any,
    variant_var_defs: Any,
) -> None:
    from llm_pipeline.evals.delta import merge_variable_definitions
    if isinstance(content_override, str):
        prompt.content = content_override
    merged = merge_variable_definitions(
        _coerce_var_defs(prompt.variable_definitions),
        _coerce_var_defs(variant_var_defs),
    )
    prompt.variable_definitions = _encode_var_defs(
        prompt.variable_definitions, merged
    )
    session.add(prompt)
```

### Verification
- [x] `uv run pytest tests/test_eval_variants.py` — 86 passed (1 pre-existing deprecation warning unrelated)
- [x] Both prompt branches still exercised: `test_system_prompt_override_applied`, `test_user_prompt_override_applied`, `test_variable_definitions_merged_variant_wins` (L831-883 in test_eval_variants.py) cover variant_var_defs merge paths for both system and user prompts
- [x] Helper is module-private (underscore prefix); not added to `__all__`
- [x] MEDIUM variable_definitions drift issue NOT touched — branch remains fully functional per user direction (UI extension owns that fix in Steps 5/6)
