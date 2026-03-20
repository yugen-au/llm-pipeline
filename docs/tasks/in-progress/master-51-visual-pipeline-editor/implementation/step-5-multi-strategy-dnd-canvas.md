# IMPLEMENTATION - STEP 5: MULTI-STRATEGY DND CANVAS
**Status:** completed

## Summary
Implemented the center panel of the 3-panel editor layout: a multi-strategy drag-and-drop canvas using @dnd-kit/core + @dnd-kit/sortable. Each strategy renders as a vertical sortable list with droppable container. Steps can be reordered within a strategy and added from the palette via drag or button. Cross-strategy drag is a no-op (v1 limitation). DndContext lifted to editor.tsx to wrap both palette and canvas panels in a shared context.

## Files
**Created:**
- `llm_pipeline/ui/frontend/src/components/editor/SortableStepCard.tsx`
- `llm_pipeline/ui/frontend/src/components/editor/StrategyList.tsx`
- `llm_pipeline/ui/frontend/src/components/editor/EditorStrategyCanvas.tsx`

**Modified:**
- `llm_pipeline/ui/frontend/src/routes/editor.tsx`
- `llm_pipeline/ui/frontend/src/components/editor/index.ts`

**Deleted:** none

## Changes

### File: `src/components/editor/SortableStepCard.tsx`
New component. Individual sortable step card using useSortable hook.
- Drag handle isolated to GripVertical button element (attributes + listeners only on handle, NOT on wrapper div)
- Wrapper div receives CSS.Transform.toString(transform) + transition from useSortable
- Card shows: step_ref (font-mono), source badge (registered=secondary, draft=outline), error dot indicator (red)
- Click on card body calls onSelectStep(step.id)
- Remove button (X icon, ghost variant) with stopPropagation calls onRemoveStep(step.id)
- isDragging state applies opacity-50 + shadow
- isSelected state applies primary border + ring
- Error state applies destructive border + ring (when not selected)
- data payload: `{ type: 'sortable-step', step }` for drag-end discrimination

### File: `src/components/editor/StrategyList.tsx`
New component. Single strategy column with droppable container + sortable context.
- useDroppable with id `strategy-<name>` and data `{ type: 'strategy', strategyName }` for palette drop targeting
- SortableContext with verticalListSortingStrategy, items = step UUIDs
- Strategy header shows name + step count
- isOver highlight (primary/5 bg + ring) for drop feedback
- Empty state "Drop steps here" when no steps
- Wrapped in ScrollArea for overflow

### File: `src/components/editor/EditorStrategyCanvas.tsx`
New component. Center panel rendering strategy lists horizontally.
- Does NOT own DndContext (lifted to editor.tsx for palette+canvas sharing)
- Renders strategies in a horizontal flex container with ScrollArea + horizontal ScrollBar
- handleRemoveStep: filters step from all strategies, deselects if removed step was selected
- Empty state when no strategies defined
- Exports `buildEditorDragEnd()` factory function:
  - palette-step drops: resolves target strategy from over.id (strategy droppable or step UUID parent), creates new EditorStepItem with crypto.randomUUID()
  - sortable-step reorder: arrayMove within same strategy only
  - cross-strategy drag: no-op with early return (v1 limitation)
  - resolveTargetStrategy helper handles both "strategy-<name>" droppable IDs and step UUID -> parent strategy lookup

### File: `src/routes/editor.tsx`
Modified to wire DndContext and real canvas component.
```
# Before
- Placeholder EditorStrategyCanvas function (static card)
- _selectedStepId, _compileResult prefixed (unused)
- No DndContext wrapper

# After
- Imports DndContext, sensors, closestCenter from @dnd-kit/core
- Imports sortableKeyboardCoordinates from @dnd-kit/sortable
- Imports real EditorStrategyCanvas + buildEditorDragEnd from editor components
- Un-prefixed selectedStepId, compileResult (now wired to canvas)
- useSensors: PointerSensor (distance: 8) + KeyboardSensor (sortableKeyboardCoordinates)
- handleDragEnd via useMemo(buildEditorDragEnd(strategies, setStrategies))
- compileErrors derived from compileResult?.errors
- DndContext wraps BOTH desktop grid and mobile tabs (palette + canvas share context)
- Real EditorStrategyCanvas receives strategies, onStrategiesChange, selectedStepId, onSelectStep, compileErrors
```

### File: `src/components/editor/index.ts`
Added exports for EditorStrategyCanvas, buildEditorDragEnd, StrategyList, SortableStepCard (components + prop types).

## Decisions

### DndContext ownership lifted to editor.tsx
**Choice:** DndContext lives in editor.tsx, not inside EditorStrategyCanvas
**Rationale:** PLAN step 5 point 6 specifies "Wire DndContext in editor.tsx (parent) to wrap both palette and canvas panels." The palette's useDraggable and the canvas's useSortable/useDroppable must share the same DndContext to enable cross-panel drag-from-palette. EditorStrategyCanvas exports buildEditorDragEnd as a factory function instead.

### Drag-end handler as factory function
**Choice:** `buildEditorDragEnd(strategies, setStrategies)` returns the handler, memoized via useMemo in editor.tsx
**Rationale:** Keeps drag logic co-located with the canvas component while allowing the parent to own the DndContext. Factory pattern avoids prop-drilling the full DragEndEvent type through canvas.

### PointerSensor distance: 8px
**Choice:** 8px activation constraint on PointerSensor
**Rationale:** Prevents accidental drags when clicking step cards for selection or remove buttons. Research doc recommended this pattern. Combined with drag handle isolation, provides clean UX.

### Cross-strategy drag no-op
**Choice:** When a sortable-step is dragged over a step in a different strategy, the handler returns early (no-op)
**Rationale:** PLAN explicitly scopes cross-strategy drag out of v1. Documented in code comment.

## Verification
[x] TypeScript type-check passes (no errors in step-5 files; pre-existing creator.tsx error unrelated)
[x] @dnd-kit packages already installed from Step 4 (core 6.3.1, sortable 10.0.0, utilities 3.2.2)
[x] Drag handle isolation: attributes+listeners on GripVertical button only, not wrapper div
[x] SortableStepCard uses useSortable with data type discriminant for drag-end logic
[x] StrategyList uses useDroppable for palette drop targets
[x] EditorStrategyCanvas does not own DndContext (parent-owned)
[x] DndContext in editor.tsx wraps both palette and canvas (desktop + mobile layouts)
[x] All components exported from src/components/editor/index.ts
[x] Cross-strategy drag handled as no-op
[x] Error indicator (red dot + destructive border) on cards with compile errors

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] HIGH: Stale closure in buildEditorDragEnd via useMemo -- strategies closed over at creation time
[x] MEDIUM: Remove unused onStepsChange prop from StrategyList
[x] MEDIUM: handleRemoveStep in EditorStrategyCanvas not memoized

### Changes Made

#### File: `src/components/editor/EditorStrategyCanvas.tsx`
Refactored buildEditorDragEnd to use functional updater pattern. Memoized handleRemoveStep.
```
# Before
export function buildEditorDragEnd(
  strategies: EditorStrategyState[],
  onStrategiesChange: (strategies: EditorStrategyState[]) => void,
) {
  // ... closes over strategies, reads stale value during drag
  onStrategiesChange(strategies.map(...))

function handleRemoveStep(stepId: string) {  // not memoized

# After
export function buildEditorDragEnd(
  setStrategies: Dispatch<SetStateAction<EditorStrategyState[]>>,
): (event: DragEndEvent) => void {
  // ... all mutations use setStrategies(prev => ...), no closed-over strategies
  setStrategies((prev) => prev.map(...))

const handleRemoveStep = useCallback((stepId: string) => {
  onStrategiesChange((prev) => prev.map(...))
  onSelectStep((current) => (current === stepId ? null : current))
}, [onStrategiesChange, onSelectStep])
```
Also changed prop types: `onStrategiesChange` and `onSelectStep` now typed as `Dispatch<SetStateAction<...>>` to support functional updater form.

#### File: `src/components/editor/StrategyList.tsx`
Removed unused `onStepsChange` from StrategyListProps interface and removed unused `EditorStepItem` import.
```
# Before
export interface StrategyListProps {
  strategy: EditorStrategyState
  onStepsChange: (steps: EditorStepItem[]) => void
  selectedStepId: string | null
  ...
import type { EditorStepItem, EditorStrategyState } from '@/routes/editor'

# After
export interface StrategyListProps {
  strategy: EditorStrategyState
  selectedStepId: string | null
  ...
import type { EditorStrategyState } from '@/routes/editor'
```

#### File: `src/routes/editor.tsx`
Updated buildEditorDragEnd call to only pass setStrategies (no strategies arg). Empty deps array since setStrategies is stable.
```
# Before
const handleDragEnd = useMemo(
  () => buildEditorDragEnd(strategies, setStrategies),
  [strategies],
)

# After
const handleDragEnd = useMemo(
  () => buildEditorDragEnd(setStrategies),
  [],
)
```

### Verification
[x] TypeScript type-check passes (no errors in step-5 files)
[x] buildEditorDragEnd no longer closes over strategies -- uses setStrategies(prev => ...) throughout
[x] handleRemoveStep wrapped in useCallback with stable deps [onStrategiesChange, onSelectStep]
[x] onStepsChange removed from StrategyListProps and EditorStrategyCanvas call site
[x] Unused EditorStepItem import removed from StrategyList.tsx
[x] handleDragEnd useMemo has empty deps (setStrategies is stable React dispatch)
