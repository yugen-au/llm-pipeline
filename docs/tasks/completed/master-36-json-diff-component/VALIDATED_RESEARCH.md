# Research Summary

## Executive Summary

Cross-referenced Step 1 (UI architecture) and Step 2 (JSON diff library) findings against actual source code. Found one critical data shape mismatch (resolved: backend fix approved), one contradiction between research steps (library recommendation, resolved: microdiff), and one color class inconsistency (resolved: use dual-theme). All blocking questions answered by CEO. Ready for planning.

## Domain Findings

### Data Shape of context_snapshot (CRITICAL GAP)

**Source:** step-1-ui-component-research.md, step-2-json-diff-library-research.md, backend source code

Both research steps assume `context_snapshot` contains the accumulated pipeline context (10-50 top-level keys, 2-4 levels deep). This is **incorrect**.

Backend source (`llm_pipeline/pipeline.py` line 946):
```python
context_snapshot = {step.step_name: serialized}  # only current step's result
```

The API endpoint `GET /api/runs/{run_id}/context` returns `PipelineStepState.context_snapshot`, which is `{step_name: serialized_results}` -- a single key per snapshot. Each snapshot contains ONLY that step's output, not the accumulated context.

The `ContextUpdated` event (`pipeline.py` line 381) DOES contain the accumulated context (`dict(self._context)`), but this is only available via WebSocket/events, not the context API endpoint.

**Resolution (CEO approved):** One-line backend fix in `pipeline.py` line 946: change `context_snapshot = {step.step_name: serialized}` to `context_snapshot = dict(self._context)`. This aligns PipelineStepState storage with ContextUpdated event semantics (line 381 already stores accumulated context). After fix, the API returns accumulated context per step, and the frontend diffs consecutive snapshots directly -- no client-side accumulation needed. `result_data` continues to hold per-step output. This backend change is in scope for task 36 implementation.

### Library Recommendation Contradiction

**Source:** step-1-ui-component-research.md (section "Diff Libraries"), step-2-json-diff-library-research.md

Step 1 recommends `deep-diff`. Step 2 recommends `microdiff` and **disqualifies** `deep-diff` due to:
- CJS-only (no ESM) -- incompatible with `verbatimModuleSyntax: true` in tsconfig.app.json
- Stale @types/deep-diff (separate, 2+ years old)
- Last publish 2018 (abandoned)

**Validated:** Step 2 is correct. `deep-diff` is disqualified. `microdiff` (0.5KB gzip, native TS, discriminated union types, ESM+CJS) is the right choice. Confirmed `verbatimModuleSyntax: true` in `tsconfig.app.json` line 14.

### Color Class Inconsistency

**Source:** step-1-ui-component-research.md (section "Proposed diff colors"), step-2-json-diff-library-research.md (section 4.4)

Step 1 correctly proposes dual-theme colors: `bg-green-500/10 text-green-600 dark:text-green-400`
Step 2's `diffColors` constant only has dark-mode values: `bg-green-950/50 text-green-400`

**Validated:** The codebase uses `dark:` prefix pattern for all status colors (see StatusBadge.tsx, StepTimeline.tsx). Step 1's approach is correct. Step 2's constant needs light-mode variants.

### Component Patterns Verified

**Source:** step-1-ui-component-research.md, actual source files

Verified against actual code:
- Named function exports (not default): Confirmed in ContextEvolution.tsx, StepDetailPanel.tsx
- Props interfaces inline above component: Confirmed
- Loading/error/empty/content 4-state pattern: Confirmed in ContextEvolution.tsx (lines 24-38)
- `cn()` from `@/lib/utils` for conditional classes: Confirmed
- ScrollArea wrapping: Confirmed in ContextEvolution.tsx line 41
- `w-80` panel constraint (320px): Confirmed in `$runId.tsx` line 190

### TypeScript Config Verified

**Source:** step-2-json-diff-library-research.md, tsconfig.app.json

- `verbatimModuleSyntax: true`: Confirmed (line 14) -- CJS-only packages won't work
- `noFallthroughCasesInSwitch: true`: Confirmed (line 24) -- exhaustive switch on Difference.type works
- `strict: true`: Confirmed (line 21)
- Path alias `@/*` -> `./src/*`: Confirmed

### Collapsible Component Availability

**Source:** step-1-ui-component-research.md

Confirmed no collapsible/accordion component in `src/components/ui/`. Available primitives: badge, button, card, scroll-area, select, separator, sheet, table, tabs, tooltip.

Research recommendation of custom `useState` toggle with lucide chevron icons is appropriate and avoids adding a Radix primitive for a simple open/close toggle.

### StepDetailPanel ContextDiffTab Structure

**Source:** step-1-ui-component-research.md, StepDetailPanel.tsx (lines 228-290)

Verified the ContextDiffTab component exists and currently renders side-by-side `<pre>` blocks. It also displays `new_keys` badges from `context_updated` events. CEO confirmed this is in scope for task 36: replace side-by-side `<pre>` blocks with the new JsonDiff component. With the backend fix (accumulated context), beforeSnapshot/afterSnapshot will contain meaningful data for diffing. The `new_keys` badges can be kept as supplementary info above the diff.

### Existing Tests

**Source:** step-1-ui-component-research.md, ContextEvolution.test.tsx

Verified 5 tests exist. Mock data uses simple flat objects (`{ input: "raw data", extracted: true }`), not the actual `{step_name: serialized}` shape from the backend. Tests will need updating regardless of approach.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Backend stores per-step `{step_name: results}` not accumulated context. Client-side accumulation or backend fix? | Backend fix approved: change `pipeline.py:946` from `{step.step_name: serialized}` to `dict(self._context)`. One-line change, in scope for task 36. | Eliminates need for client-side accumulation. Frontend diffs consecutive snapshots directly. Simplifies JsonDiff integration significantly. |
| Should task 36 update StepDetailPanel ContextDiffTab in addition to ContextEvolution.tsx? | Both components in scope. Create JsonDiff.tsx, update ContextEvolution.tsx, AND update ContextDiffTab in StepDetailPanel. | Broader scope than task description implied. Two integration points instead of one. JsonDiff must be flexible enough for both 320px panel and 600px sheet contexts. |
| First step with no "before" state: all-green additions or plain JSON? | All green additions. Consistent diff styling throughout. | First step renders `diff({}, snapshot)` treating all keys as additions with green highlighting. No special-case raw JSON rendering needed. |

## Assumptions Validated

- [x] Frontend stack is Vite+React19+TS+shadcn+Tailwind v4 (verified package.json, tsconfig)
- [x] No diff library currently installed (verified package.json)
- [x] No collapsible/accordion shadcn component installed (verified ui/ directory listing)
- [x] ContextEvolution currently renders raw JSON.stringify (verified source code)
- [x] w-80 panel constraint makes side-by-side diff unviable (verified $runId.tsx line 190)
- [x] deep-diff is incompatible with this project (CJS-only + verbatimModuleSyntax)
- [x] microdiff native TS types work with strict mode (discriminated union on `type` field)
- [x] noFallthroughCasesInSwitch enables exhaustive switch on microdiff Difference.type
- [x] ContextEvolutionProps interface should be preserved (confirmed by task 34 summary)
- [x] Component export pattern is named exports (not default)
- [x] Testing uses vitest + RTL without router/query wrappers for component tests
- [x] Backend fix for context_snapshot approved (CEO Q1: `dict(self._context)` instead of `{step.step_name: serialized}`)
- [x] Both ContextEvolution.tsx and StepDetailPanel ContextDiffTab in scope (CEO Q2)
- [x] First step renders all keys as green additions with `diff({}, snapshot)` (CEO Q3)

## Open Items

- Color classes: Step 2 diffColors needs light-mode variants added (not blocking, fix during implementation per step 1 pattern)
- maxDepth=3 default: reasonable but unvalidated against real pipeline data depths (non-blocking, adjustable)
- ContextDiffTab new_keys badges: keep as supplementary info above JsonDiff (implementation detail, not blocking)

## Recommendations for Planning

1. **Backend fix first** -- change `pipeline.py:946` from `context_snapshot = {step.step_name: serialized}` to `context_snapshot = dict(self._context)`. One-line change. Must happen before frontend work is testable with real data.
2. **Use microdiff** -- confirmed correct library. 0.5KB gzip, native TS, ESM, discriminated unions.
3. **Custom useState toggle for collapsible nodes** -- avoid installing shadcn collapsible for a simple open/close pattern.
4. **Dual-theme diffColors** -- follow existing `text-green-600 dark:text-green-400` pattern from StatusBadge/StepTimeline. Step 1's color proposals are correct.
5. **Place JsonDiff at `src/components/JsonDiff.tsx`** -- reusable across both ContextEvolution (w-80 panel) and ContextDiffTab (600px sheet).
6. **Two integration points** -- ContextEvolution.tsx (replace raw JSON with per-step diffs) and StepDetailPanel ContextDiffTab (replace side-by-side `<pre>` with JsonDiff). JsonDiff must be width-agnostic.
7. **First step: `diff({}, snapshot)`** -- treat empty object as "before" to render all keys as green additions.
8. **Update existing ContextEvolution tests** -- mock data must use accumulated context shape, tests rewritten for diff output.
9. **Update ContextDiffTab tests** if any exist (currently inline in StepDetailPanel, no separate test file found).
