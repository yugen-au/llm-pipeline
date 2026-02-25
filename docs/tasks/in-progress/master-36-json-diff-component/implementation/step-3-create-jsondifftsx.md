# IMPLEMENTATION - STEP 3: CREATE JSONDIFF.TSX
**Status:** completed

## Summary
Created reusable `JsonDiff.tsx` component that computes diffs between two JSON objects using microdiff, builds a recursive tree from flat path output, and renders color-coded additions/removals/changes with collapsible branch nodes.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/JsonDiff.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/JsonDiff.tsx`
New file. Key implementation details:

- **Props:** `{ before: Record<string, unknown>, after: Record<string, unknown>, maxDepth?: number }` (default 3)
- **DiffTreeNode type:** `{ key, diff?, children?, unchangedValue? }`
- **buildDiffTree():** Groups microdiff flat `path[]` output by `path[0]`, recurses for nested paths with `path.slice(1)`, adds unchanged keys from `after`
- **diffColors constant:** Dual-theme classes matching StatusBadge/StepTimeline patterns
  - CREATE: `bg-green-500/10 text-green-600 dark:text-green-400`
  - REMOVE: `bg-red-500/10 text-red-600 dark:text-red-400 line-through`
  - CHANGE: `bg-yellow-500/10 text-yellow-600 dark:text-yellow-400`
- **DiffNode (memo-wrapped):** Recursive renderer handling leaf CREATE/REMOVE/CHANGE, unchanged values, and collapsible branch nodes with ChevronRight/ChevronDown icons
- **JsonDiff:** Named export, `useMemo` on diff computation and tree construction, `useState<Set<string>>` for expanded paths initialized at depth < maxDepth
- **Empty diff:** `<p className="text-xs text-muted-foreground">No changes</p>`

## Decisions
### Sorting order in tree
**Choice:** Changed keys (diffs/branches) sorted before unchanged keys, alphabetical within each group
**Rationale:** Draws attention to actual changes first; unchanged context available below

### Mixed leaf+nested diffs for same key
**Choice:** When a key has both leaf-level and nested diffs (e.g. type change from primitive to object), render as leaf using the leaf diff
**Rationale:** This edge case means the key itself was replaced entirely; showing nested structure of the new value would be misleading

### useState initializer for expanded paths
**Choice:** Single `useState` initializer computing paths from initial tree; no re-sync on prop changes
**Rationale:** Component unmounts/remounts when step selection changes (keyed by step), so fresh init runs naturally. Avoids unnecessary `useEffect` sync.

## Verification
[x] TypeScript compiles with zero errors (`npx tsc --noEmit`)
[x] Named export only, no default export
[x] Props match spec: `before`, `after`, `maxDepth` with default 3
[x] Uses `microdiff` diff() with `{ cyclesFix: false }`
[x] Dual-theme color classes match existing StatusBadge/StepTimeline patterns
[x] Collapsible nodes with lucide ChevronRight/ChevronDown
[x] Collapsed shows `{N changes}` summary via recursive `countDiffs()`
[x] useMemo on diff computation keyed on [before, after]
[x] useMemo on tree construction keyed on [diffs, before, after]
[x] Empty diff renders muted "No changes" text
[x] `verbatimModuleSyntax` compatible imports (import type for Difference)
