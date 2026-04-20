# Research Summary

## Executive Summary

Evals v2 variant comparison is architecturally feasible with minimal disruption to existing codebase. Three research areas validated: (1) existing evals/sandbox arch has clean extension points for variant injection, (2) frontend patterns are highly reusable with established diff/editor components, (3) pydantic create_model works as Agent output_type for dynamic instruction deltas. Five critical assumptions surfaced and resolved with CEO -- notably choosing `__base__=LLMResultMixin` over flat approach (reversing research recommendation), moving evaluator resolution after delta application, and scoping delta to minimal fields for v2.

## Domain Findings

### Existing Evals & Sandbox Architecture
**Source:** step-1-existing-evals-sandbox-arch.md

- EvaluationRun needs nullable `variant_id` FK. Baseline runs = NULL.
- New `EvaluationVariant` table required (not in codebase).
- Runner modification: `_resolve_step_task()` is insertion point -- between `_find_step_def()` (prod) and `_build_step_task_fn()`, apply variant delta.
- Sandbox prompt override: create sandbox engine, then UPDATE Prompt rows for variant content using `step_def.system_instruction_key`/`user_prompt_key`.
- Model override: upsert `StepModelConfig` row in sandbox DB (respects existing priority chain).
- DB registration: add `EvaluationVariant.__table__` to `init_pipeline_db()` tables list + migration for `variant_id` column on `eval_runs`.
- Cascade: delete variants when deleting dataset; nullable FK on runs handles variant deletion gracefully.

### Frontend Evals UI Patterns
**Source:** step-2-frontend-evals-patterns.md

- TanStack Router file-based routing; new routes: `evals.$datasetId.variants.$variantId.tsx`, `evals.$datasetId.compare.tsx`.
- Query key factory extends naturally: `variants(datasetId)`, `variant(datasetId, variantId)`.
- Reusable components: JsonViewer (DiffView mode with microdiff), PromptContentEditor (Monaco), FieldInput (schema-driven), useCaseEditor pattern (dirty tracking).
- Variant editor: split-pane layout (prod read-only | variant editable), Save/Discard/Run buttons.
- Comparison page: JsonViewer for delta diff, side-by-side stat cards and result rows.
- Dataset detail: add "Variants" as third tab alongside Cases and Run History.

### Pydantic create_model for Instruction Deltas
**Source:** step-3-pydantic-createmodel-delta.md

- `create_model()` confirmed working as pydantic-ai Agent `output_type`.
- `model_fields` introspection provides full FieldInfo metadata for reconstruction.
- Thread-safe: stateless, each call returns independent class.
- Type string resolution via whitelist (no eval) covers practical types.
- `apply_instruction_delta()` function handles add/modify/remove operations.
- Integration point: `pipeline.py:889` where `instructions_type = step.instructions`.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Flat vs `__base__=LLMResultMixin` for create_model? Flat allows field removal but loses `create_failure()`. | Use `__base__=LLMResultMixin`. Tradeoff accepted: cannot remove inherited fields (confidence_score, notes) but preserves create_failure(). | Reverses research recommendation. Delta `remove` operations limited to non-inherited fields only. Must document this constraint in variant editor UI. |
| Should evaluator resolution happen before or after delta application? Currently resolves from prod instructions. | Move evaluator resolution AFTER delta application so auto-evaluators match variant schema. | `_resolve_evaluators()` call must be reordered in runner to consume variant-modified instructions class. Evaluator fields auto-adapt to added/removed fields. |
| Where to store delta snapshot for reproducibility -- nested in report_data or dedicated column? | Dedicated `delta_snapshot` JSON column on EvaluationRun. | Cleaner querying, no nested JSON extraction. Column is nullable (NULL for baseline runs). Migration adds column alongside `variant_id`. |
| Can variants add/change prompt template variables or only swap content? | Allow new variables -- variant can add/change template variables. | Variant prompt override must also update `variable_definitions` in sandbox. More complex but enables richer experimentation (e.g., adding a new variable to system prompt). |
| Delta scope for v2 -- minimal or broad StepDefinition fields? | Minimal: `{model, system_prompt, user_prompt, instructions_delta}`. Other StepDefinition fields later. | Constrains v2 implementation surface. No strategy changes, no tool changes, no extraction config changes in v2. Simplifies variant editor UI to 4 sections. |

## Assumptions Validated

- [x] pydantic create_model works as pydantic-ai Agent output_type (empirically confirmed)
- [x] Sandbox engine prompt override via UPDATE on Prompt rows works (existing seed-then-modify pattern)
- [x] Model override via StepModelConfig upsert in sandbox DB respects priority chain
- [x] Thread safety of create_model for concurrent eval runs (tested with ThreadPoolExecutor)
- [x] JsonViewer DiffView component reusable for variant delta comparison
- [x] `__base__=LLMResultMixin` approach preserves create_failure() method (CEO decision)
- [x] Inherited fields (confidence_score, notes) cannot be removed with __base__ approach (accepted tradeoff)
- [x] Evaluator resolution must follow delta application (CEO decision)
- [x] delta_snapshot stored as dedicated column on EvaluationRun (CEO decision)
- [x] Variant can introduce new prompt template variables (CEO decision)
- [x] v2 delta scope limited to {model, system_prompt, user_prompt, instructions_delta} (CEO decision)

## Open Items

- Variant editor UI must clearly indicate which instruction fields are inherited (non-removable) vs own fields
- Prompt variable_definitions update in sandbox needs design -- how to merge variant variables with production definitions
- Nested Pydantic model fields (e.g., `list[TopicItem]`) cannot have type changes via delta -- preserve original annotation only
- `prompt_key` auto-discovery (when system_instruction_key/user_prompt_key are None) needs handling in variant prompt override logic
- Pipeline-level variants (create_sandbox_from_factory) deferred to post-v2

## Recommendations for Planning

1. Start with EvaluationVariant model + migration + CRUD endpoints (lowest risk, unblocks frontend work in parallel)
2. Implement `apply_instruction_delta()` with `__base__=LLMResultMixin` and unit test thoroughly before integrating into runner
3. Reorder `_resolve_evaluators()` in runner to execute after delta application -- test with field-add and field-modify scenarios
4. Add `delta_snapshot` column in same migration as `variant_id` on EvaluationRun to avoid multiple migrations
5. Frontend: start with Variants tab (list + CRUD) then variant editor, comparison view last (depends on having run data)
6. Prompt variable handling: design a `merge_variable_definitions(prod_vars, variant_vars)` utility before tackling prompt override
7. Add integration test: create variant with all 4 delta types (model, system_prompt, user_prompt, instructions_delta), run eval, verify sandbox receives correct overrides
