# PLANNING

## Summary

Build a reusable `JsonDiff.tsx` component using microdiff v1.5.0, integrate it into `ContextEvolution.tsx` (per-step diffs in 320px panel) and `StepDetailPanel`'s `ContextDiffTab` (full-width sheet), and apply a one-line backend fix to store accumulated context per step instead of only the current step's output.

## Plugin & Agents

**Plugin:** javascript-typescript
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. Backend fix: change `pipeline.py:946` to store accumulated context snapshot
2. JsonDiff component: create reusable diff component with tree rendering and collapsible nodes
3. Integration: update ContextEvolution.tsx and StepDetailPanel ContextDiffTab
4. Tests: update ContextEvolution tests; update or add StepDetailPanel ContextDiffTab tests

## Architecture Decisions

### microdiff over alternatives
**Choice:** microdiff v1.5.0 as the diff engine
**Rationale:** 0.5KB gzip, native discriminated union TS types (`DifferenceCreate | DifferenceRemove | DifferenceChange`), ESM+CJS dual export (compatible with `verbatimModuleSyntax: true`), zero deps. deep-diff is CJS-only (disqualified). jsondiffpatch is 32x larger with opinionated HTML formatter. json-diff-ts is 15x larger with unnecessary array key matching.
**Alternatives:** deep-diff (CJS-only, disqualified), jsondiffpatch (too large), json-diff-ts (unnecessary complexity), custom implementation (~50 lines possible but adds maintenance burden)

### Tree reconstruction from flat diff output
**Choice:** Group microdiff's flat `path[]` output by first path segment into `DiffTreeNode` tree, then render recursively. Unchanged keys shown as muted text. Single `Set<string>` of expanded paths at `JsonDiff` root (not per-node state).
**Rationale:** Flat diff output loses structural hierarchy needed for context. Single Set state avoids cascade re-renders when toggling nodes. `useMemo` on diff computation and tree construction stabilises between renders.
**Alternatives:** Flat list rendering (loses structure), per-node useState (more re-renders), side-by-side columns (incompatible with w-80 constraint)

### Custom collapsible nodes (no shadcn Collapsible)
**Choice:** `useState` Set toggle with lucide `ChevronRight`/`ChevronDown` icons
**Rationale:** No shadcn Collapsible primitive installed. Installing a Radix primitive for simple open/close is unnecessary overhead. The custom pattern is already consistent with existing codebase style (StatusBadge, StepTimeline all use direct Tailwind classes).
**Alternatives:** shadcn Collapsible (Radix install overhead), native `<details>/<summary>` (limited Tailwind styling)

### Dual-theme color classes
**Choice:** `bg-green-500/10 text-green-600 dark:text-green-400` pattern for all diff colors
**Rationale:** Matches existing component pattern in StatusBadge.tsx and StepTimeline.tsx. Research step 2's dark-mode-only `diffColors` constant is incorrect; step 1's dual-theme approach is validated against actual codebase.
**Alternatives:** CSS custom properties (not used for status colors in this project), dark-only classes (breaks light mode)

### JsonDiff placement at `src/components/JsonDiff.tsx`
**Choice:** `src/components/JsonDiff.tsx` (not inside `runs/`)
**Rationale:** Used by two distinct component contexts: ContextEvolution (runs panel) and StepDetailPanel (sheet). Placing at `src/components/` signals intentional reusability outside the `runs/` domain.
**Alternatives:** `src/components/runs/JsonDiff.tsx` (limits reuse signal, would still work)

### Backend fix scope
**Choice:** One-line change to `pipeline.py:946`: `context_snapshot = dict(self._context)` instead of `{step.step_name: serialized}`
**Rationale:** Aligns PipelineStepState storage with `ContextUpdated` event semantics already at line 381. Frontend can then diff consecutive snapshots directly with no client-side accumulation. `result_data` continues to hold per-step output unchanged.
**Alternatives:** Client-side accumulation (more complex, fragile, requires sequential API calls per step)

## Implementation Steps

### Step 1: Backend context_snapshot fix
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open `llm_pipeline/pipeline.py` line 946
2. Change `context_snapshot = {step.step_name: serialized}` to `context_snapshot = dict(self._context)`
3. Verify `self._context` is of type `dict` at that point in execution (already confirmed by line 381 which uses `dict(self._context)`)
4. Confirm `result_data=serialized` line below (line 963) remains unchanged -- per-step output still stored separately

### Step 2: Install microdiff
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/frontend/`, run `npm install microdiff@1.5.0`
2. Verify `microdiff` appears in `package.json` dependencies (not devDependencies)
3. Confirm no peer-dep warnings (microdiff has zero dependencies)

### Step 3: Create JsonDiff.tsx
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/react_dev, /websites/tailwindcss, /vitest-dev/vitest
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/components/JsonDiff.tsx`
2. Define `JsonDiffProps` interface: `{ before: Record<string, unknown>, after: Record<string, unknown>, maxDepth?: number }` (default maxDepth: 3)
3. Define internal `DiffTreeNode` type: `{ key: string, diff?: Difference, children?: DiffTreeNode[], unchangedValue?: unknown }`
4. Implement `buildDiffTree(diffs: Difference[], after: Record<string, unknown>): DiffTreeNode[]`:
   - Group diffs by `path[0]`
   - For each group: if all have `path.length === 1`, create leaf node; if any have `path.length > 1`, create branch node and recurse with `path.slice(1)`
   - Add unchanged keys from `after` (keys not present in any diff) as `unchangedValue` nodes
5. Define dual-theme `diffColors` constant following existing pattern:
   - `CREATE`: `'bg-green-500/10 text-green-600 dark:text-green-400'`
   - `REMOVE`: `'bg-red-500/10 text-red-600 dark:text-red-400 line-through'`
   - `CHANGE`: `'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400'`
6. Implement `DiffNode` (memo-wrapped): renders either leaf (switch on `diff.type`) or branch with collapse toggle
   - Branch: show `ChevronRight`/`ChevronDown` icon, key label; if collapsed show `{N changes}` summary
   - Leaf CREATE: green `+ key: value`
   - Leaf REMOVE: red strikethrough `- key: oldValue`
   - Leaf CHANGE: yellow `key: oldValue → value`
   - Unchanged: muted `key: value`
7. Implement `JsonDiff` named export:
   - `useMemo` on `diff(before, after, { cyclesFix: false })` keyed on `[before, after]`
   - `useMemo` on `buildDiffTree(diffs, after)` keyed on `[diffs, after]`
   - `useState<Set<string>>` for expanded paths, initialised to all paths at depth < maxDepth
   - Render tree of `DiffNode` elements; pass `isExpanded(path)` and `toggleExpand(path)` callbacks
   - Empty diff state: `<p className="text-xs text-muted-foreground">No changes</p>`
8. Export format: named export `export function JsonDiff(...)`, props interface inline above component, no default export

### Step 4: Update ContextEvolution.tsx
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/react_dev, /websites/tailwindcss
**Group:** D

1. Open `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.tsx`
2. Add import: `import { JsonDiff } from '@/components/JsonDiff'`
3. Replace the `<pre>{JSON.stringify(snapshot.context_snapshot, null, 2)}</pre>` block with `<JsonDiff before={prev?.context_snapshot ?? {}} after={snapshot.context_snapshot} maxDepth={3} />`
   - Compute `prev` as `snapshots[index - 1]` inside the `snapshots.map((snapshot, index) => ...)` callback
   - First snapshot (index 0): `before={}` (empty object) so all keys render as green additions per CEO decision
4. Remove the `overflow-x-auto` wrapper div (no longer needed for pre-formatted text)
5. Preserve `ContextEvolutionProps` interface, `SkeletonBlocks`, loading/error/empty states, `ScrollArea`, and step header `<h4>` unchanged
6. Adjust step header `mb-2` spacing if needed given JsonDiff replaces the pre block

### Step 5: Update StepDetailPanel ContextDiffTab
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/react_dev, /websites/tailwindcss
**Group:** D

1. Open `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`
2. Add import: `import { JsonDiff } from '@/components/JsonDiff'`
3. In `ContextDiffTab` (lines 228-290), replace the `<div className="grid grid-cols-2 gap-3">` side-by-side pre blocks with:
   ```
   <JsonDiff
     before={beforeSnapshot?.context_snapshot ?? (step.step_number === 1 ? {} : {})}
     after={afterSnapshot?.context_snapshot ?? step.context_snapshot}
     maxDepth={3}
   />
   ```
4. Keep the `new_keys` badges section above the JsonDiff (supplementary info as confirmed by CEO)
5. Keep the loading skeleton (`snapshotsLoading` check) unchanged
6. Remove the Before/After header labels and `formatJson` helper calls that are replaced by JsonDiff's inline rendering
7. Verify `formatJson` helper is no longer referenced after replacement; remove if unused (check full file first)

### Step 6: Update ContextEvolution tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest
**Group:** E

1. Open `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx`
2. Update `mockSnapshots` to use accumulated context shape (each snapshot contains all prior keys plus new ones):
   - Step 1: `context_snapshot: { input: 'raw data', extracted: true }`
   - Step 2: `context_snapshot: { input: 'raw data', extracted: true, result: 42, tags: ['a', 'b'] }` (accumulated)
3. Remove test `'renders JSON snapshots as formatted text'` (asserts on raw JSON strings -- no longer valid)
4. Add test `'renders addition for first step keys'`: verify step 1 renders key names as additions (e.g. `input` appears with green styling or as text)
5. Add test `'renders changes between steps'`: verify step 2 shows new keys (`result`, `tags`) visually distinguished from unchanged keys
6. Retain unchanged tests: `'renders step names as headers'`, `'shows loading skeleton with animate-pulse elements'`, `'shows error text when isError'`, `'shows empty state message'`
7. Verify loading skeleton test still passes (6 animate-pulse elements from SkeletonBlocks)

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Backend fix changes API response shape, breaking existing frontend tests | Medium | `result_data` unchanged; `context_snapshot` shape changes from `{step_name: [...]}` to full accumulated dict. Review test_steps.py assertions on context_snapshot field before merging. |
| microdiff flat path output requires non-trivial tree reconstruction | Medium | Algorithm fully specified in step 3.4. Use recursive grouping by path[0]; test with 2-level and 3-level nested objects in unit tests. |
| ContextDiffTab uses `formatJson` helper that may be shared elsewhere in file | Low | Step 5.7 explicitly checks full file before removing. If used elsewhere, leave helper in place. |
| Collapsed node `{N changes}` count logic must recurse into subtree | Low | Count all leaf diffs (type CREATE/REMOVE/CHANGE) recursively in the subtree -- implement `countDiffs(node)` helper. |
| `useMemo` keyed on object references re-runs on each TanStack Query refetch | Low | Terminal runs have `staleTime: Infinity` (no refetch). Active runs have append-only snapshots; only the latest snapshot changes per refetch. Impact is minimal. |
| Color classes `bg-green-500/10` not scanned by Tailwind v4 purge if not present in other files | Low | These classes follow the same pattern as existing components. Tailwind v4 scans all source files including .tsx. Add explicit class strings (no template literals for Tailwind classes). |

## Success Criteria

- [ ] `pipeline.py:946` stores `dict(self._context)` (accumulated context, not `{step_name: results}`)
- [ ] `microdiff@1.5.0` present in `package.json` dependencies
- [ ] `src/components/JsonDiff.tsx` exists as named export with `before`, `after`, `maxDepth` props
- [ ] JsonDiff renders CREATE in green, REMOVE in red with strikethrough, CHANGE in yellow before->after
- [ ] JsonDiff collapses nodes at depth >= maxDepth by default; user can toggle
- [ ] JsonDiff shows unchanged keys in muted style
- [ ] ContextEvolution.tsx imports and uses JsonDiff; no `<pre>JSON.stringify</pre>` remains
- [ ] First step in ContextEvolution renders all keys as green additions (before={})
- [ ] StepDetailPanel ContextDiffTab uses JsonDiff replacing side-by-side pre blocks
- [ ] new_keys badges remain in ContextDiffTab above the JsonDiff
- [ ] ContextEvolution.test.tsx updated: old raw-JSON assertion removed, new diff-aware assertions added
- [ ] All existing vitest tests pass (`npm test` in frontend/)

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Backend data shape change (pipeline.py fix) must land before frontend is testable with real data. Tree reconstruction algorithm for microdiff output is moderately complex but fully specified. Integration touches 3 files plus tests. No novel dependencies on external services or schema migrations.
**Suggested Exclusions:** review
