# IMPLEMENTATION - STEP 3: CREATE JSONTREE
**Status:** completed

## Summary
Created recursive collapsible JSON tree component for rendering pipeline schemas (extraction models, instruction schemas, context schemas).

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/pipelines/JsonTree.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/pipelines/JsonTree.tsx`
New file. Recursive `JsonTreeNode` (private) renders objects as collapsible rows with chevron toggle, arrays as indexed collapsible rows, primitives as inline colored value spans. `JsonTree` (public export) is the entry point.

Key implementation details:
- `JsonTreeNode` uses `useState(depth < 2)` for default expand/collapse behavior (expanded at depth 0-1, collapsed at depth >= 2)
- `PrimitiveValue` helper renders null as italic muted text, strings green, numbers blue, booleans orange
- Objects show `{...N}` summary when collapsed, arrays show `[N]`
- ChevronRight/ChevronDown from lucide-react for toggle icons (same pattern as JsonDiff.tsx)
- Indentation via `paddingLeft: depth * 16px` (matches JsonDiff pattern)

## Decisions
### Followed JsonDiff.tsx patterns
**Choice:** Matched indentation, icon sizing, hover styles, and font-mono text-xs from existing JsonDiff.tsx
**Rationale:** Consistency with existing codebase patterns; JsonDiff already uses the same chevron toggle + recursive rendering approach

### useState per node vs centralized Set
**Choice:** Each JsonTreeNode owns its own `useState` for expanded/collapsed
**Rationale:** Simpler than centralized path-tracking Set (used by JsonDiff for different reasons -- it needs coordinated expand/collapse across diff-aware nodes). Per-node state is sufficient for a static schema viewer with no cross-node coordination needs.

## Verification
[x] TypeScript compilation passes with no errors (`npx tsc --noEmit`)
[x] ChevronRight/ChevronDown imported from 'lucide-react' (verified in codebase)
[x] No new dependencies added
[x] JsonTreeNode is not exported (private)
[x] JsonTree is the only public export
[x] Null/undefined renders italic muted span
[x] String/number/boolean values use specified color classes
[x] Default collapsed at depth >= 2, expanded at depth 0-1
