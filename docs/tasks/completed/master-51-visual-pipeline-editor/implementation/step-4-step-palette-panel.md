# IMPLEMENTATION - STEP 4: STEP PALETTE PANEL
**Status:** completed

## Summary
Created the EditorPalettePanel component (left panel of the 3-panel editor layout). Lists available steps from `useAvailableSteps()` hook with search filtering, source badges, draggable items via @dnd-kit `useDraggable`, and per-strategy "Add" buttons. Wired into editor.tsx replacing the placeholder. Installed @dnd-kit packages (core, sortable, utilities) required for drag-and-drop.

## Files
**Created:**
- `llm_pipeline/ui/frontend/src/components/editor/EditorPalettePanel.tsx`
- `llm_pipeline/ui/frontend/src/components/editor/index.ts`

**Modified:**
- `llm_pipeline/ui/frontend/src/routes/editor.tsx`
- `llm_pipeline/ui/frontend/package.json` (added @dnd-kit/core, @dnd-kit/sortable, @dnd-kit/utilities)
- `llm_pipeline/ui/frontend/package-lock.json`

**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/editor/EditorPalettePanel.tsx`
New component with:
- Props: `onAddStepToStrategy(strategyName, step)` + `strategyNames[]`
- `useAvailableSteps()` hook for data, loading skeleton on pending, error state
- Search input with lucide Search icon filters by step_ref substring
- Two sections: "Registered Steps" and "Draft Steps" with uppercase section headers
- Each step item: `DraggableStepItem` sub-component with GripVertical drag handle, step_ref name, source Badge, Plus button(s) per strategy
- Each item uses `useDraggable({ id, data: { type: 'palette-step', step } })` for drag-from-palette
- "Create new step" button at bottom opens `/creator` in new tab
- EmptyState for no results, ScrollArea for overflow

### File: `llm_pipeline/ui/frontend/src/components/editor/index.ts`
Barrel export for `EditorPalettePanel` and its props type.

### File: `llm_pipeline/ui/frontend/src/routes/editor.tsx`
```
# Before
- Placeholder EditorPalettePanel function component
- _strategies/_setStrategies (unused, underscore-prefixed)
- paletteColumn = <EditorPalettePanel /> (no props)

# After
- Import real EditorPalettePanel from @/components/editor
- Import AvailableStep type + useCallback
- strategies/setStrategies (active, no underscore)
- handleAddStepToStrategy callback: appends step with crypto.randomUUID() id to target strategy
- strategyNames derived from strategies state
- paletteColumn = <EditorPalettePanel onAddStepToStrategy={...} strategyNames={...} />
```

## Decisions
### @dnd-kit installation in Step 4 (not Step 5)
**Choice:** Installed @dnd-kit packages in Step 4 even though PLAN assigns install to Step 5
**Rationale:** Step 4 requires `useDraggable` from `@dnd-kit/core` for draggable palette items. Cannot import without installing. Step 5 can skip the install step.

### Classic @dnd-kit/core API (v1) over @dnd-kit/react (v2)
**Choice:** Used classic `useDraggable` with `attributes`, `listeners`, `setNodeRef`, `transform` pattern
**Rationale:** PLAN explicitly specifies `@dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities` (v1 packages). Step 5 references `CSS.Transform`, `useSortable`, `arrayMove` which are all v1 patterns. Consistency across steps.

### Drag handle on button element (not wrapper div)
**Choice:** `{...listeners} {...attributes}` on the GripVertical button, not the wrapper div
**Rationale:** PLAN Step 5 explicitly states "GripVertical element gets attributes+listeners (drag handle isolation -- NOT on wrapper)". Applied same pattern in palette for consistency. Allows clicks on Add buttons without triggering drag.

### strategyNames as additional prop
**Choice:** Added `strategyNames?: string[]` prop beyond the PLAN's specified props
**Rationale:** The palette needs to know which strategies exist to render per-strategy Add buttons. This prop is derived from the parent's `strategies` state. The PLAN's `onAddStepToStrategy(strategyName, step)` signature implies the palette knows strategy names.

## Verification
[x] `npx tsc --noEmit` passes with zero errors
[x] @dnd-kit packages install without React 19.2 compatibility errors (0 vulnerabilities)
[x] EditorPalettePanel uses `useAvailableSteps()` hook from src/api/editor.ts
[x] Search input filters by step_ref substring
[x] Two sections: Registered Steps and Draft Steps
[x] Each step has source badge (Badge component) with registered/draft variant
[x] Each step has Add button(s) per strategy
[x] "Create new step" button opens /creator in new tab via window.open
[x] Each step is draggable via @dnd-kit useDraggable with data payload { type: 'palette-step', step }
[x] Loading skeleton shown on pending state
[x] EmptyState component used for empty/no-results state
[x] Barrel export in src/components/editor/index.ts
[x] Placeholder in editor.tsx replaced with real component + wired props
