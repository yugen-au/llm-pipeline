# Task Summary

## Work Completed

Implemented a reusable `JsonDiff.tsx` component backed by microdiff v1.5.0 and integrated it into two existing UI surfaces. A one-line backend fix was applied first to align DB-persisted `context_snapshot` with the accumulated-context semantics already present in the `ContextUpdated` event, making meaningful diffs possible. The component renders color-coded additions (green), removals (red), and changes (yellow) with collapsible tree nodes and muted unchanged keys. Integration covered both the 320px `ContextEvolution` side panel (per-step diffs, first step shown as all-green additions) and the `StepDetailPanel` `ContextDiffTab` sheet (full-width diff replacing side-by-side pre blocks). A review cycle caught a medium-severity array index type mismatch in the tree reconstruction algorithm, which was fixed with a one-line `String(key)` coercion.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/frontend/src/components/JsonDiff.tsx` | Reusable diff component: microdiff engine, recursive `buildDiffTree`, collapsible `DiffNode`, dual-theme color coding |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/pipeline.py` | Line 946: `context_snapshot = dict(self._context)` instead of `{step.step_name: serialized}` -- stores accumulated context per step |
| `llm_pipeline/ui/frontend/package.json` | Added `microdiff@^1.5.0` to dependencies |
| `llm_pipeline/ui/frontend/package-lock.json` | Lock file updated for microdiff install |
| `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.tsx` | Replaced `<pre>JSON.stringify</pre>` blocks with `<JsonDiff before={prev?.context_snapshot ?? {}} after={snapshot.context_snapshot} maxDepth={3} />`; removed `overflow-x-auto` wrapper |
| `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx` | Replaced side-by-side pre blocks in `ContextDiffTab` with `<JsonDiff>`; removed Before/After header labels and `formatJson` calls in that tab; retained `new_keys` badges and `formatJson` helper (still used in InputTab, ResponseTab, ExtractionsTab) |
| `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx` | Updated `mockSnapshots` to accumulated-context shape; removed raw-JSON assertion; added diff-aware assertions for additions and cross-step changes |

## Commits Made

| Hash | Message |
| --- | --- |
| `d08185a` | `docs(implementation-A): master-36-json-diff-component` -- backend pipeline.py fix |
| `9ea52a0` | `docs(implementation-B): master-36-json-diff-component` -- microdiff install |
| `7c97790` | `docs(implementation-C): master-36-json-diff-component` -- JsonDiff.tsx created |
| `1009433` | `docs(implementation-D): master-36-json-diff-component` -- ContextEvolution + StepDetailPanel updated |
| `dec176f` | `docs(implementation-E): master-36-json-diff-component` -- ContextEvolution tests updated |
| `f0fb796` | `docs(testing-A): master-36-json-diff-component` -- build/test verification |
| `dbbbadb` | `docs(review-A): master-36-json-diff-component` -- architecture review (conditional approve) |
| `44bc723` | `docs(fixing-review-C): master-36-json-diff-component` -- array index type mismatch fix |
| `5b3c583` | `chore(state): master-36-json-diff-component -> testing` -- re-verify after fix |
| `cb56f63` | `chore(state): master-36-json-diff-component -> review` -- re-review approval |

## Deviations from Plan

- Steps 4 and 5 (ContextEvolution + StepDetailPanel) were committed together in a single commit (`1009433`) rather than separate commits; both were in group D and executed by the same agent concurrently.
- Review added a fixing cycle (step 3 revision) not anticipated in the original plan phases, due to the medium-severity array index bug found post-implementation.

## Issues Encountered

### Array index type mismatch in buildDiffTree recursion

When `microdiff` diffs an array-valued property at depth > 1, it emits path segments as `number` (e.g. `[0]`, `[1]`). The `changedKeys` set was typed `Set<string | number>` but was checked against `Object.keys(after)` which always returns strings. This caused changed array elements to also render as "unchanged" duplicates.

**Resolution:** Narrowed `changedKeys` to `Set<string>` and coerced all insertions with `changedKeys.add(String(key))` at `JsonDiff.tsx` line 61. The `grouped` Map retains `string | number` keys for correct microdiff path lookup; only the `changedKeys` filter set was normalized. Fix verified in re-review with no new issues.

### Context snapshot shape mismatch discovered in research

Research found `pipeline.py:946` stored only the current step's result (`{step_name: serialized}`) rather than the accumulated pipeline context, contradicting both research steps' assumptions. Without fixing this, meaningful diffs between consecutive snapshots would be impossible.

**Resolution:** CEO approved a one-line backend fix to store `dict(self._context)` (accumulated context), aligning DB storage with the existing `ContextUpdated` event semantics at line 381. `result_data` continues to hold per-step output unchanged.

### deep-diff library conflict with TypeScript config

Research step 1 recommended `deep-diff` but research step 2 disqualified it: CJS-only export is incompatible with `verbatimModuleSyntax: true` in `tsconfig.app.json`.

**Resolution:** `microdiff@1.5.0` selected instead -- 0.5KB gzip, native discriminated-union TypeScript types, ESM+CJS dual export, zero dependencies.

## Success Criteria

- [x] `pipeline.py:946` stores `dict(self._context)` (accumulated context, not `{step_name: results}`) -- verified in `d08185a`
- [x] `microdiff@^1.5.0` present in `package.json` dependencies (not devDependencies) -- verified in `9ea52a0`
- [x] `src/components/JsonDiff.tsx` exists as named export with `before`, `after`, `maxDepth` props -- verified in `7c97790`
- [x] JsonDiff renders CREATE in green, REMOVE in red with strikethrough, CHANGE in yellow before->after -- confirmed in review
- [x] JsonDiff collapses nodes at depth >= maxDepth by default; user can toggle -- confirmed in review
- [x] JsonDiff shows unchanged keys in muted style -- confirmed in review
- [x] ContextEvolution.tsx imports and uses JsonDiff; no `<pre>JSON.stringify</pre>` remains -- verified in `1009433`
- [x] First step in ContextEvolution renders all keys as green additions (`before={}`) -- verified in `1009433`
- [x] StepDetailPanel ContextDiffTab uses JsonDiff replacing side-by-side pre blocks -- verified in `1009433`
- [x] `new_keys` badges remain in ContextDiffTab above the JsonDiff -- verified in review
- [x] ContextEvolution.test.tsx updated: old raw-JSON assertion removed, new diff-aware assertions added -- verified in `dec176f`
- [x] All vitest tests pass (`npm test` in frontend/) -- verified in testing phase (`f0fb796`, `5b3c583`)

## Recommendations for Follow-up

1. Add a backend integration test that verifies `_save_step_state` persists accumulated context in `context_snapshot` -- currently `tests/ui/test_steps.py` uses a direct DB fixture that bypasses `_save_step_state`, so the pipeline.py fix is not regression-tested via the API.
2. The `useState` initializer for `expanded` paths only runs on mount. If a single step's context grows during an active run without unmounting the component, newly added branch nodes at depth < maxDepth will start collapsed. A `useEffect` sync keyed on `tree` could address this if live-run UX becomes a priority.
3. ContextEvolution tests use lower-bound count assertions (`>= 2`, `>= 4`) for diff markers rather than exact counts. Tightening these to exact values would catch regressions where fewer additions are rendered than expected.
4. `maxDepth=3` default was chosen without validation against real pipeline context data. Profile actual pipeline run context depth and adjust the default if deeply nested objects are common.
5. No dedicated test file exists for `StepDetailPanel`'s `ContextDiffTab`. Adding tests for the JsonDiff integration in that tab would improve coverage given it is the full-width view used for detailed step inspection.
