# Architecture Review

## Overall Assessment
**Status:** complete
Evals v2 variant implementation is architecturally sound. ACE-hygiene rules from PLAN Security Constraints are enforced at every persistence entry point (runner, API create, API update), the delta-application function is pure and Docker-relocatable, delta storage is JSON-only with no Python class references leaking across the sandbox boundary, evaluator resolution is correctly reordered after delta application, and API contracts follow REST conventions (201/204/404/422). A handful of MEDIUM/LOW design-consistency items surfaced around session/transaction boundaries, frontend/backend delta-shape drift (`variable_definitions` not exposed in UI types), and minor error-path edge cases. None are blockers for the Docker-sandbox migration; the architectural seams are clean.

## Project Guidelines Compliance
**CLAUDE.md:** d:\Documents\claude-projects\llm-pipeline\.claude\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| Pydantic v2 + SQLModel + SQLAlchemy 2.0 | pass | `EvaluationVariant` uses `SQLModel` + `Column(JSON)`; `apply_instruction_delta` uses `pydantic.create_model`. |
| TDD strict | pass | 120/120 variant tests reported green by testing phase. |
| ACE risk awareness (Security Constraints) | pass | Whitelist-only type resolution; regex-gated field names; dunder rejection; op set `{add, modify}`; JSON-scalar default validation; length caps 50/1000; dry-run validation wired into POST/PUT variant routes returning 422. |
| Docker-sandbox readiness | pass | `apply_instruction_delta` has no I/O, no session, no globals. `delta_snapshot` deep-copied JSON. No Python class refs or host paths persisted. `create_sandbox_engine` remains the single seam. |
| No hardcoded values | pass | Caps (`_MAX_DELTA_ITEMS`, `_MAX_STRING_LEN`) centralised as module constants; whitelist is a literal dict with an intentional minimal surface area. |
| Error handling present | pass | API returns 404/409/422 correctly; runner wraps pipeline execution in try/except and marks run as failed; frontend surfaces 422 from dry-run via `ApiError` branch in `handleSave`. |
| DRY / YAGNI | mostly-pass | `_coerce_var_defs` and `_encode_var_defs` duplicate logic between system/user prompt branches — could be a single helper. Not a blocker. |

## Issues Found

### Critical
None.

### High
None.

### Medium

#### Frontend / backend drift: `variable_definitions` silently consumed by runner but not exposed in `VariantDelta` TS type
**Step:** 3 (runner) / 5 (frontend API layer)
**Details:** `_apply_variant_to_sandbox` reads `variant_delta.get("variable_definitions")` and merges it into sandbox `Prompt.variable_definitions`, but the `VariantDelta` TS interface (`llm_pipeline/ui/frontend/src/api/evals.ts` lines 122-127) only declares `model | system_prompt | user_prompt | instructions_delta`. PLAN Step 3.4 introduces `merge_variable_definitions`, Step 1 delta JSON keys listed as `{model, system_prompt, user_prompt, instructions_delta}`. The field is undocumented on either surface yet persists and flows into the sandbox. Result: a consumer can only populate it via direct JSON edit, and the editor UI has no affordance for it. Either remove the runner branch (explicitly scoped out in v2) or extend the TS type + editor to cover it. Recommend removing the runtime branch to match the documented contract.

#### Cascade deletion leaves orphaned `EvaluationRun.variant_id` after `DELETE /variants/{id}`
**Step:** 4
**Details:** `delete_variant` (routes/evals.py L900-919) removes only the variant row. Existing `EvaluationRun` rows retain their `variant_id` pointer (nullable FK, SQLite does not enforce FKs without `PRAGMA foreign_keys=ON`). PLAN Risks table line 165 says "application-level cascade delete in `delete_dataset` and `delete_variant` endpoints" — `delete_variant` does not null-out run refs. Compare view recovers gracefully (404 on variant lookup, renders `#N`) so runtime is safe, but architectural contract in PLAN is incomplete. Suggested fix: set `run.variant_id = NULL` for all runs pointing at the variant before deleting it (or document the dangling-pointer behaviour as intentional).

#### Runner's three-session pattern for a single logical run has non-atomic transaction boundaries
**Step:** 3
**Details:** `run_dataset` opens three separate `Session(self.engine)` blocks: one to create the pending run (L71-117), one to persist case results + mark completed (L249-263), one to mark failed on exception (L267-275). If the process dies between the two write sessions, the run stays `"running"` indefinitely. `case_results` accumulated in-memory are also lost on exception (L266 — only the run-row status is updated; in-flight case results are not flushed). This is a pre-existing architectural pattern not introduced by variant work, but the variant feature amplifies its visibility because Compare UI will show partial/stale variant runs. Suggest a follow-up to consolidate into a single try-with-session or add a startup "stuck-running" sweeper. Not blocking this PR.

#### `_dry_run_validate_delta` accepts `instructions_delta={}` (empty dict) as a no-op instead of rejecting type
**Step:** 2
**Details:** `apply_instruction_delta` checks `if instructions_delta is None or len(instructions_delta) == 0: return base_cls` on L179 BEFORE the `isinstance(..., list)` check on L182. An empty dict `{}` has `len == 0` and returns early, so non-list input is silently accepted as a no-op. Non-empty dicts are correctly rejected. Low risk (no ACE bypass — nothing is persisted or executed beyond schema confusion) but inconsistent with "reject non-list" guarantee. Suggest reordering: isinstance check first, then length.

#### `_resolve_type` whitelist uses `Optional[T]` as dict keys — maintenance fragility
**Step:** 2
**Details:** `_TYPE_WHITELIST` (delta.py L38-49) uses `Optional[str]` (i.e. `Union[str, None]`) as dict VALUES — correct. But relies on exact string match `"Optional[str]"` to key them. If a future contributor adds `"Optional[list]"` without updating the frontend `TYPE_WHITELIST` in `evals.$datasetId.variants.$variantId.tsx` L42-53, drift is silent (backend accepts, UI can't select). Suggest exporting the canonical whitelist from a single source (e.g., a GET `/evals/delta-type-whitelist` endpoint or a build-time codegen). Not urgent.

#### Variant `trigger_eval_run` uses `DBSession` (read-only) to validate variant ownership — correct, but validation logic duplicated between route and runner
**Step:** 3 / 4
**Details:** `trigger_eval_run` (routes/evals.py L745-753) checks `variant.dataset_id != dataset_id` and returns 422. `EvalRunner.run_dataset` re-validates the same invariant (runner.py L88-92) and raises ValueError. Two error surfaces for the same condition: 422 synchronously at route, ValueError asynchronously in the background task (logged via `logger.exception`, no user surface). If the variant is deleted between POST and background execution, the runner ValueError fires. Acceptable defensive depth, but worth a comment noting the double-check is intentional (TOCTOU window on variant deletion).

### Low

#### `_coerce_var_defs` / `_encode_var_defs` duplicated between system/user prompt branches
**Step:** 3
**Details:** `_apply_variant_to_sandbox` (runner.py L606-667) duplicates the identical merge-and-write pattern for system and user prompts. Extract into a helper like `_merge_variant_defs_into_prompt(session, prompt, variant_var_defs, content_override)`. Cosmetic — tests cover both paths.

#### Frontend `InstructionDeltaItem.type_str` is required but editor allows empty string
**Step:** 5 / 6
**Details:** TS type declares `type_str: string` (evals.ts L118), but the editor row state is initialised with `type_str: 'str'` and the select is never empty. A programmatic caller could send `type_str: ""` and trigger a backend 422 — handled correctly, but type system is technically untruthful. Consider `type_str: string` → union of the `TYPE_WHITELIST` literal type for compile-time safety.

#### `NewVariantPage` retry forces a full navigation round-trip instead of resetting local state
**Step:** 6
**Details:** `evals.$datasetId.variants.new.tsx` L95-103 retries by `navigate(...replace: true)` to the same route, relying on route-level remount to reset `attemptedRef`. Works, but feels like a side-effect. A clearer approach: local `setRetryKey(k => k+1)` in the effect dep list. Pre-existing pattern concern only.

#### `dataclasses.replace(step_def, instructions=modified_cls)` assumes `StepDefinition` remains a non-frozen dataclass
**Step:** 3
**Details:** `strategy.py` L23 `@dataclass` (not frozen). If a future refactor freezes `StepDefinition`, `dataclasses.replace` still works (it's designed for frozen dataclasses). However, the in-place mutation concern the comment calls out (runner.py L366-368) only matters if someone swaps `dataclasses.replace` back for direct attribute assignment. Comment is sufficient; low-risk.

#### `delta_snapshot` column uses TEXT in migration but JSON in ORM definition — intentional per SQLite pattern, but worth an ADR
**Step:** 1
**Details:** `_MIGRATIONS` (db/__init__.py L52-53) adds `("eval_runs", "delta_snapshot", "TEXT")` while the ORM (`EvaluationRun.delta_snapshot`) uses `Column(JSON)`. SQLite stores JSON as TEXT under the hood so this works, and Postgres's `ADD COLUMN IF NOT EXISTS ... TEXT` is a compatible shape. This is a project-wide convention (`prompts.variable_definitions` also uses TEXT) and consistent. Flag for documentation-only: a future Postgres-native eval audit might want `JSONB`. Note, don't fix.

#### Comment on runner.py L179-180 documents "remove" as unsupported but `op` whitelist makes it a ValueError — message phrasing
**Step:** 2
**Details:** delta.py docstring L12-15 says `remove` is "explicitly NOT supported". Error path raises ValueError with `"op must be one of {'add', 'modify'}"` which technically includes `remove` in the implicit-rejection set. For an ops-team reading a 422 with `"op must be one of ['add', 'modify']; got 'remove'"` the message is clear enough, but the docstring's "remove is explicitly NOT supported" suggests a dedicated error. Low. Message is fine.

#### Frontend `parseBackendFieldError` is substring-based and can mis-match fields with overlapping prefixes
**Step:** 6
**Details:** `evals.$datasetId.variants.$variantId.tsx` L640-644 matches backend error messages by `msg.includes(\`'${f}'\`)`. If two rows have fields `foo` and `foobar`, a message `"field 'foobar' is invalid"` matches the `foo` row first if it appears earlier. Low impact (rows are typically unique) but could mis-highlight. Consider matching by exact word boundary or returning a structured error envelope (e.g., `{ row_idx, message }`) from the backend — a cleaner long-term contract.

## Review Checklist
[x] Architecture patterns followed (pure function for delta, single seam for sandbox, frozen-JSON snapshot)
[x] Code quality and maintainability (clear module docstrings; security invariants called out inline)
[x] Error handling present (422 dry-run at API, ValueError at runner, graceful variant-lookup 404 in compare)
[x] No hardcoded values (caps as module constants; whitelist as literal dict)
[x] Project conventions followed (_migrate_add_columns pattern, SQLModel tables in `init_pipeline_db`, TanStack Query hooks + queryKeys factory)
[x] Security considerations (ACE whitelist, field regex, dunder rejection, JSON round-trip on defaults, length caps — all enforced at every entry point)
[x] Properly scoped (DRY, YAGNI, no over-engineering) (variable_definitions runtime branch is the only scope smudge — see MEDIUM issue)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\delta.py | pass | Whitelist-only; no eval/exec/importlib/get_type_hints. Field regex, dunder rejection, JSON default round-trip, length caps. Pure function — Docker-relocatable. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\models.py | pass | `EvaluationVariant` table well-scoped; `delta` JSON column; nullable `variant_id` and `delta_snapshot` on `EvaluationRun`. Index on `dataset_id`. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\runner.py | pass | Delta applied BEFORE evaluator resolution (L359-368). `dataclasses.replace` avoids mutating registered step_def — prod path stays pristine. Sandbox override mutates sandbox DB only. Snapshot is deep-copied JSON (L96, L483). MEDIUM: `variable_definitions` branch undocumented in TS / PLAN. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\routes\evals.py | pass | 201 on variant create, 204 on variant delete, 404/422 semantics correct, dry-run validation on POST + PUT. Cascade delete for dataset removes variants. MEDIUM: variant delete doesn't null out run FKs. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\db\__init__.py | pass | `EvaluationVariant.__table__` registered; migration adds `variant_id`+`delta_snapshot`. Idempotent via PRAGMA/information_schema check. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\api\evals.ts | pass | TS interfaces mirror backend; variant hooks correctly wired; `useTriggerEvalRun` extended with `variant_id`. LOW: `type_str` could be literal union. MEDIUM: `variable_definitions` absent from `VariantDelta`. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\api\query-keys.ts | pass | `variants`/`variant` keys follow factory pattern; tuple-typed via `as const`. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\routes\evals.$datasetId.index.tsx | pass | Third tab added; VariantsTab with create + delete; delete confirmation guard; navigation to editor. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\routes\evals.$datasetId.variants.$variantId.tsx | pass | Split-pane editor; dirty tracking; 422 surfaced via `ApiError` branch and parsed into row-level error; inherited-field warning banner. LOW: substring field matching. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\routes\evals.$datasetId.variants.new.tsx | pass | StrictMode-safe via `attemptedRef`; 422 surfaced with retry. LOW: retry uses navigate instead of local state key. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\routes\evals.$datasetId.compare.tsx | pass | Zod search-param validation with fallback; graceful handling of missing variant_id lookup; side-by-side stat cards and per-case union. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\routes\evals.$datasetId.runs.$runId.tsx | pass | Compare-with-baseline link correctly gated on `variant_id != null`; disabled state with tooltip when no baseline available; most-recent-baseline selection logic sound. |

## New Issues Introduced
- MEDIUM: `variable_definitions` key read by runner but absent from TS type and PLAN delta shape (drift).
- MEDIUM: `delete_variant` does not null-out `EvaluationRun.variant_id` FK references, leaving dangling pointers (PLAN says application-level cascade should handle it).
- MEDIUM: Empty-dict `instructions_delta` silently treated as no-op before type check.
- LOW: `type_str` not a literal-union TS type (compile-time laxness).
- LOW: Row-error matching by substring could mis-attribute.

## Recommendation
**Decision:** APPROVE
ACE-hygiene is watertight: no `eval`/`exec`/`importlib`/`get_type_hints`; hard-coded whitelist; regex-gated field names with dunder rejection; JSON round-trip default validation; length caps. Every persistence entry point (API POST, API PUT, runner) runs the same validation. Evaluator resolution is reordered per CEO decision so variant-added fields are visible to auto-evaluators (runner.py L359-384). `delta_snapshot` is a deep-copied JSON dict — no Python class references, no host paths, nothing that wouldn't round-trip through a container boundary. `apply_instruction_delta` is a pure function. `create_sandbox_engine` remains the clean seam for a future Docker swap. Docker migration is unblocked architecturally.

MEDIUM items are quality-of-life and contract-hygiene, not correctness or security. Recommend addressing the `variable_definitions` drift (either extend UI or remove runner branch) and `delete_variant` FK nullification in a follow-up patch before production deploy, but these do not block merge of this PR.

---

# Architecture Review (Re-Review: fixes applied)

## Overall Assessment
**Status:** complete
Re-reviewed the fixes for the 5 MEDIUM + 3 LOW items flagged in the initial review. All eight addressed fixes match the original finding's intent, maintain the PLAN Security Constraints (ACE hygiene), and introduce no new architectural drift. Testing phase already reported +4 tests green, no regressions, TypeScript clean. The `variable_definitions` UI-extension path (MEDIUM #1) is sound: the TS `VariableDefinitions` map-shape mirrors the backend JSON contract, and the runner's list/dict coercion (`_coerce_var_defs` / `_encode_var_defs`) tolerates either input shape, preserving round-trip fidelity. The new `delta-type-whitelist` endpoint establishes a single source of truth for the `type_str` dropdown and keeps the offline fallback constant as a graceful-degradation safety net. `delete_variant` FK nullification is atomic within one session/transaction, and `delta_snapshot` preservation is explicitly documented as intentional for run reproducibility.

## Project Guidelines Compliance
**CLAUDE.md:** d:\Documents\claude-projects\llm-pipeline\.claude\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| Pydantic v2 + SQLModel + SQLAlchemy 2.0 | pass | No changes to persistence layer shape; FK nullification uses same-session ORM pattern. |
| TDD strict | pass | +4 tests (empty-dict rejection, string rejection, delete cascades FK, whitelist endpoint). No regressions. |
| ACE risk awareness (Security Constraints) | pass | Type-check-first reorder in `apply_instruction_delta` closes empty-dict bypass; whitelist endpoint exposes the same hardcoded map with no additional surface area; no new eval/exec/importlib/get_type_hints. |
| Docker-sandbox readiness | pass | `get_type_whitelist()` is a pure accessor; helper `_merge_variant_defs_into_prompt` is session-scoped and JSON-data-only; no new host paths or Python class crossings. |
| No hardcoded values | pass | Frontend fallback whitelist is explicitly documented as offline-only; runtime source is backend endpoint. |
| Error handling present | pass | `parseBackendFieldError` longest-match eliminates mis-attribution; new-variant retry guarded by `attemptedRef` + `retryKey`. |
| DRY / YAGNI | pass | `_merge_variant_defs_into_prompt` extracted; no speculative abstractions in UI VarDef editor. |

## Issues Found

### Critical
None.

### High
None.

### Medium
None.

### Low

#### `variable_definitions` editor overwrites unknown spec keys on save (documented trade-off but worth flagging)
**Step:** 6 (frontend variant editor)
**Details:** `varDefsToRows` reads only `name`, `type`, `auto_generate` from each spec entry and `rowsToVarDefs` re-serialises only those three fields. Comment at L102-104 acknowledges this. Impact: if a hand-edited variant JSON has an extra key like `description` on a variable def spec, the key is preserved on load but silently dropped the first time the user saves. Low because (a) the UI is the write path for 99% of cases, (b) the TS type already declares `[key: string]: unknown` for round-trip hinting, and (c) the runner only consumes `name` + `type` + `auto_generate`. Consider: either storing raw entries as opaque `unknown` on the row shape and merging known fields for editing, or adding a visible "unknown keys preserved" badge. Documentation is adequate for now.

#### Frontend fallback whitelist can drift from backend
**Step:** 5 (frontend API layer)
**Details:** `FALLBACK_TYPE_WHITELIST` (variants editor L49-60) is maintained in sync with `_TYPE_WHITELIST` in `llm_pipeline/evals/delta.py` by convention (comment L47). The `DeltaTypeStr` literal union (evals.ts L123-134) similarly duplicates the 10 whitelist entries. Both duplicate what `GET /evals/delta-type-whitelist` now serves authoritatively. If a future contributor adds `"Optional[list]"` to the backend whitelist, they must update three locations: `_TYPE_WHITELIST`, `DeltaTypeStr`, and `FALLBACK_TYPE_WHITELIST`. The original MEDIUM #5 finding is resolved at runtime (runtime source is backend); the compile-time type and the offline fallback remain manual-sync points. Low risk — the backend endpoint is the runtime authority, and a drift would be caught by any dev smoke test. Consider a codegen step in a follow-up.

#### `varDefsToRows` / `rowsToVarDefs` round-trip can reorder rows across save
**Step:** 6
**Details:** `rowsToVarDefs` builds a `VariableDefinitions` map (insertion-ordered), and `varDefsToRows` iterates via `Object.entries` on the next load. JavaScript preserves insertion order for string keys, so practical row order is preserved. If the backend ever materialises the dict through a non-order-preserving layer (it does not today — FastAPI/Pydantic v2 preserves dict ordering), rows could reshuffle on reload. Low — note for future Python-side serializer swaps.

## Review Checklist
[x] Architecture patterns followed (pure `get_type_whitelist` accessor; single-transaction FK cascade; helper extraction for DRY without over-abstraction)
[x] Code quality and maintainability (reorder comment in `apply_instruction_delta` documents the why; `delete_variant` docstring explains delta_snapshot preservation)
[x] Error handling present (longest-match field error mapping; state-key retry preserves component state without URL round-trip)
[x] No hardcoded values (fallback whitelist documented as graceful-degradation; runtime source is backend)
[x] Project conventions followed (queryKeys factory extended; `fetchDeltaTypeWhitelist` + hook pattern consistent with other evals hooks)
[x] Security considerations (type-check-first reorder closes empty-dict non-list bypass; no new ACE surface)
[x] Properly scoped (DRY, YAGNI, no over-engineering) (variable_definitions UI is the minimal editor surface; helper extraction is behavior-preserving)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\delta.py | pass | Reorder at L179-186 places isinstance check before length check — correctly rejects `{}`. `get_type_whitelist()` is a sorted-list accessor over `_TYPE_WHITELIST.keys()`. Exported in `__all__`. No new unsafe surface. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\__init__.py | pass | Re-exports `get_type_whitelist` alongside `apply_instruction_delta` + `merge_variable_definitions`. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\evals\runner.py | pass | `_merge_variant_defs_into_prompt` extracted (L683-708); identical logic preserved from system/user branches. `_coerce_var_defs` / `_encode_var_defs` still handle list-vs-dict shape preservation. Behaviour-preserving refactor. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\routes\evals.py | pass | `/delta-type-whitelist` registered before `/{dataset_id}` to avoid path-param shadowing (L357-370). `delete_variant` (L927-966) UPDATEs run.variant_id=NULL and DELETEs variant in one commit — atomic. Delta_snapshot preservation documented. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\api\evals.ts | pass | `DeltaTypeStr` literal union (L123-134); `InstructionDeltaItem.type_str` now typed as union. `VariableDefinitions` map type with index-signature for forward-compat. `useDeltaTypeWhitelist` with staleTime/gcTime Infinity — correct for static data. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\api\query-keys.ts | pass | `deltaTypeWhitelist()` key added to evals factory — consistent tuple-typed pattern. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\routes\evals.$datasetId.variants.$variantId.tsx | pass | Variable-definitions editor with row cap (20), backend whitelist consumption with fallback, dirty tracking covers varDef rows. `parseBackendFieldError` (L892-913) uses longest-match with word-quoted boundary. |
| d:\Documents\claude-projects\llm-pipeline\llm_pipeline\ui\frontend\src\routes\evals.$datasetId.variants.new.tsx | pass | `retryKey` state triggers effect re-run via deps; `attemptedRef` reset inline. No URL navigation round-trip. |
| d:\Documents\claude-projects\llm-pipeline\tests\test_eval_variants.py | pass | `test_empty_dict_delta_rejected` + `test_string_delta_rejected` cover the reorder fix. |
| d:\Documents\claude-projects\llm-pipeline\tests\ui\test_evals_routes.py | pass | `test_delete_variant_nulls_run_fk_preserves_snapshot` covers FK cascade + snapshot preservation. `TestDeltaTypeWhitelist` covers endpoint shape + sort order. |

## New Issues Introduced
- None detected. All three surfaced items are LOW (doc-grade / future-codegen candidates), not regressions.

## Recommendation
**Decision:** APPROVE
All five MEDIUM and three LOW fixes correctly address the original findings. The `variable_definitions` UI extension is the stronger path over removing the runner branch — it matches the runner contract, exposes the capability to end users, and the list/dict coercion in the runner means backend storage variability doesn't leak into the UI. The FK nullification is atomic and preserves audit data; the whitelist endpoint collapses three compile-time duplicates (backend dict, TS union, fallback const) into a single runtime authority with two graceful-degradation mirrors. No regressions, no new architectural smells, no new ACE surface. Ready for PM summary.

