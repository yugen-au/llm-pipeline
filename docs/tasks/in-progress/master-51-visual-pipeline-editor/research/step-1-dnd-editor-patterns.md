# Research: DnD Editor Patterns for Visual Pipeline Editor

## 1. @dnd-kit Library Analysis

### Package Selection: @dnd-kit/core + @dnd-kit/sortable (stable)

Two API generations exist:
- **@dnd-kit/core v6.3.1 + @dnd-kit/sortable v10.0.0** -- stable, widely adopted, well-documented
- **@dnd-kit/react v0.3.2** -- new API, NOT stable (no v1 release), different paradigm

**Recommendation: Use the stable packages.** The task description already references this API (`DndContext`, `SortableContext`, `verticalListSortingStrategy`, `closestCenter`). The new @dnd-kit/react is pre-1.0 and would be a risk.

### Required Packages

```
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
```

### Core API Surface

```typescript
// From @dnd-kit/core
import {
  DndContext,
  closestCenter,       // collision detection algorithm
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'

// From @dnd-kit/sortable
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,           // utility to reorder arrays
} from '@dnd-kit/sortable'

// From @dnd-kit/utilities
import { CSS } from '@dnd-kit/utilities'
```

### Sensor Configuration

```typescript
const sensors = useSensors(
  useSensor(PointerSensor, {
    activationConstraint: { distance: 8 }, // prevent accidental drags
  }),
  useSensor(KeyboardSensor, {
    coordinateGetter: sortableKeyboardCoordinates,
  }),
)
```

The `distance: 8` constraint prevents accidental drags when clicking buttons/inputs inside step cards. `KeyboardSensor` with `sortableKeyboardCoordinates` provides a11y keyboard reordering.

### DragEnd Handler Pattern

```typescript
function handleDragEnd(event: DragEndEvent) {
  const { active, over } = event
  if (!over || active.id === over.id) return

  setSteps((prev) => {
    const oldIndex = prev.findIndex((s) => s.id === active.id)
    const newIndex = prev.findIndex((s) => s.id === over.id)
    return arrayMove(prev, oldIndex, newIndex)
  })
}
```

### SortableContext Requirements

- `items` prop must be sorted in same order as rendered items
- Must be a descendant of `DndContext`
- `verticalListSortingStrategy` is optimized for vertical lists and supports virtualized lists
- Items must have unique string or number `id` values

---

## 2. Step Card Component Pattern

### SortableStepCard

```typescript
interface StepCardProps {
  step: EditorStep
  isSelected: boolean
  error?: CompilationError
  onSelect: (id: string) => void
  onRemove: (id: string) => void
}

function SortableStepCard({ step, isSelected, error, onSelect, onRemove }: StepCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: step.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={cn(
        'relative cursor-pointer border-2 transition-colors',
        isSelected && 'border-primary',
        error && 'border-destructive',
        isDragging && 'z-50 shadow-lg',
      )}
      onClick={() => onSelect(step.id)}
    >
      {/* Drag handle */}
      <div
        {...attributes}
        {...listeners}
        className="absolute left-0 top-0 flex h-full w-8 cursor-grab items-center justify-center"
      >
        <GripVertical className="size-4 text-muted-foreground" />
      </div>

      {/* Step content */}
      <div className="pl-8 pr-8 py-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-sm font-medium">{step.name}</span>
          <Badge variant={step.source === 'draft' ? 'secondary' : 'outline'}>
            {step.source}
          </Badge>
        </div>
        {error && (
          <p className="mt-1 text-xs text-destructive">{error.message}</p>
        )}
      </div>

      {/* Remove button */}
      <Button
        variant="ghost"
        size="icon-sm"
        className="absolute right-2 top-2"
        onClick={(e) => { e.stopPropagation(); onRemove(step.id) }}
      >
        <X className="size-3" />
      </Button>
    </Card>
  )
}
```

### Key Patterns

1. **Drag handle isolation**: Use `{...attributes} {...listeners}` only on the handle element, not the whole card. This allows clicks on the card body for selection and buttons for actions.
2. **Visual feedback**: `isDragging` for opacity/shadow, `isSelected` for border highlight, `error` for destructive border.
3. **Expandable design**: The card can be expanded (accordion-style) to show step properties inline. Use shadcn Collapsible or a simple state toggle.
4. **Error highlighting**: When compile-to-validate returns errors for a specific step, the card shows destructive border + inline error message.

---

## 3. State Management for Step List

### Zustand Store Pattern

Following the existing codebase pattern (Zustand v5 + devtools + persist):

```typescript
// src/stores/editor.ts
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

interface EditorStep {
  id: string           // unique ID for DnD (uuid or `step-${index}`)
  stepName: string     // references a pipeline step or draft step name
  source: 'pipeline' | 'draft'  // where the step came from
  config: Record<string, unknown>  // step-specific config overrides
}

interface CompilationError {
  stepId: string
  field?: string
  message: string
}

interface EditorState {
  // Pipeline identity
  draftPipelineId: number | null
  pipelineName: string

  // Step list
  steps: EditorStep[]
  selectedStepId: string | null

  // Compilation
  compilationErrors: CompilationError[]
  lastCompiledAt: string | null

  // Dirty tracking
  isDirty: boolean
  lastSavedAt: string | null

  // Actions
  addStep: (step: Omit<EditorStep, 'id'>) => void
  removeStep: (id: string) => void
  reorderSteps: (activeId: string, overId: string) => void
  selectStep: (id: string | null) => void
  updateStepConfig: (id: string, config: Record<string, unknown>) => void
  setCompilationErrors: (errors: CompilationError[]) => void
  clearErrors: () => void
  markSaved: (draftPipelineId: number) => void
  loadDraftPipeline: (id: number, name: string, steps: EditorStep[]) => void
  reset: () => void
}
```

### Operations

```typescript
// Reorder (called from DragEnd)
reorderSteps: (activeId, overId) => set((state) => {
  const oldIndex = state.steps.findIndex((s) => s.id === activeId)
  const newIndex = state.steps.findIndex((s) => s.id === overId)
  if (oldIndex === -1 || newIndex === -1) return state
  return {
    steps: arrayMove(state.steps, oldIndex, newIndex),
    isDirty: true,
    compilationErrors: [], // clear errors on structural change
  }
}),

// Add step (at end or at specific index)
addStep: (step) => set((state) => ({
  steps: [...state.steps, { ...step, id: crypto.randomUUID() }],
  isDirty: true,
  compilationErrors: [],
})),

// Remove step
removeStep: (id) => set((state) => ({
  steps: state.steps.filter((s) => s.id !== id),
  selectedStepId: state.selectedStepId === id ? null : state.selectedStepId,
  isDirty: true,
  compilationErrors: [],
})),
```

### Persistence Strategy

Two layers:
1. **Zustand persist middleware** with localStorage -- auto-saves current editor state for tab recovery
2. **Server-side DraftPipeline** via TanStack Query mutation -- explicit save or debounced auto-save

```typescript
// localStorage persistence (subset of state)
persist(
  (set) => ({ ... }),
  {
    name: 'llm-pipeline-editor',
    partialize: (state) => ({
      draftPipelineId: state.draftPipelineId,
      pipelineName: state.pipelineName,
      steps: state.steps,
    }),
  },
)
```

---

## 4. Compile-to-Validate Pattern

### Concept

The editor maintains a visual step arrangement. "Compile" converts this arrangement into a pipeline structure object and sends it to the backend for validation against the PipelineConfig schema.

### Frontend Flow

```
User arranges steps -> clicks "Compile" (or auto-compile on change)
  -> Convert EditorStep[] to PipelineStructure
  -> POST /api/editor/compile { structure }
  -> Backend validates:
     - All referenced steps exist
     - Step order is valid
     - Required steps present
     - No circular dependencies
     - Schema compatibility between steps
  -> Returns { success: boolean, errors: CompilationError[] }
  -> Errors mapped back to step cards via stepId
```

### Structure Conversion

```typescript
interface PipelineStructure {
  name: string
  steps: Array<{
    step_name: string
    order: number
    config?: Record<string, unknown>
  }>
  strategy?: string
}

function compileToPipelineStructure(
  name: string,
  steps: EditorStep[],
): PipelineStructure {
  return {
    name,
    steps: steps.map((step, index) => ({
      step_name: step.stepName,
      order: index + 1,
      config: Object.keys(step.config).length > 0 ? step.config : undefined,
    })),
  }
}
```

### TanStack Query Mutation

```typescript
function useCompilePipeline() {
  return useMutation({
    mutationFn: (structure: PipelineStructure) =>
      apiClient<CompileResponse>('/editor/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(structure),
      }),
  })
}
```

### Backend Endpoint Needed (NOT YET IMPLEMENTED)

The backend does not currently have a compile/validate endpoint. This needs to be created:
- `POST /api/editor/compile` -- validate structure against PipelineConfig schema
- `POST /api/editor/drafts` -- CRUD for DraftPipeline
- `GET /api/editor/drafts` -- list draft pipelines
- `GET /api/editor/drafts/{id}` -- get draft pipeline detail
- `PUT /api/editor/drafts/{id}` -- update draft pipeline
- `DELETE /api/editor/drafts/{id}` -- delete draft pipeline

**QUESTION**: Is backend endpoint creation in scope for Task 51, or is it a separate task?

---

## 5. Draft Persistence (Auto-Save)

### Debounced Auto-Save Pattern

```typescript
// Hook: useAutoSave
function useAutoSave(editorState: EditorState, delay = 2000) {
  const saveMutation = useSaveDraftPipeline()

  useEffect(() => {
    if (!editorState.isDirty) return

    const timer = setTimeout(() => {
      const structure = compileToPipelineStructure(
        editorState.pipelineName,
        editorState.steps,
      )

      if (editorState.draftPipelineId) {
        // Update existing
        saveMutation.mutate({
          id: editorState.draftPipelineId,
          structure,
        })
      } else {
        // Create new
        saveMutation.mutate({ structure })
      }
    }, delay)

    return () => clearTimeout(timer)
  }, [editorState.steps, editorState.isDirty, delay])
}
```

### Save Indicator UI

```
[Saved] | [Saving...] | [Unsaved changes]
```

Following the existing creator pattern -- show save state in the editor header.

### localStorage Fallback

Zustand persist middleware handles tab-crash recovery. On mount, check:
1. If localStorage has unsaved editor state with `isDirty: true`
2. Compare with server-side DraftPipeline (if `draftPipelineId` exists)
3. If localStorage is newer, offer to restore

---

## 6. Existing Codebase Patterns (for consistency)

### Route Definition

```typescript
// src/routes/editor.tsx
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/editor')({
  component: EditorPage,
})
```

### Sidebar Integration

Add to `navItems` in `src/components/Sidebar.tsx`:
```typescript
{ to: '/editor', label: 'Editor', icon: Blocks }, // or LayoutGrid from lucide-react
```

### Page Layout Pattern (from creator.tsx)

```typescript
function EditorPage() {
  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-card-foreground">Pipeline Editor</h1>
        <p className="text-sm text-muted-foreground">Visual pipeline step arrangement</p>
      </div>

      {/* Desktop: 2-panel layout */}
      <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-[1fr_350px] lg:gap-4">
        {/* Main: DnD step sequence */}
        <div className="overflow-auto">{stepSequence}</div>
        {/* Right: Step properties panel */}
        <div className="overflow-hidden">{propertiesPanel}</div>
      </div>

      {/* Mobile: tab-based */}
      <div className="flex min-h-0 flex-1 flex-col lg:hidden">
        <Tabs defaultValue="steps">
          <TabsList>
            <TabsTrigger value="steps">Steps</TabsTrigger>
            <TabsTrigger value="properties">Properties</TabsTrigger>
          </TabsList>
          ...
        </Tabs>
      </div>
    </div>
  )
}
```

### Component Organization

```
src/components/editor/
  SortableStepCard.tsx      -- individual sortable step card
  StepSequence.tsx           -- DndContext + SortableContext wrapper
  StepPropertiesPanel.tsx    -- right panel for selected step config
  AddStepDialog.tsx          -- dialog/popover to add a step
  CompileButton.tsx          -- compile + error display
  SaveIndicator.tsx          -- auto-save state indicator
  EditorToolbar.tsx          -- toolbar with compile, save, reset buttons
```

---

## 7. Accessibility Considerations

### @dnd-kit Built-in A11y

- KeyboardSensor provides arrow key navigation
- ARIA attributes via `useSortable` `attributes` spread
- Screen reader announcements via DndContext `announcements` prop

### Custom Announcements

```typescript
const announcements = {
  onDragStart({ active }) {
    return `Picked up step ${active.id}`
  },
  onDragOver({ active, over }) {
    if (over) return `Step ${active.id} is over ${over.id}`
    return `Step ${active.id} is no longer over a droppable area`
  },
  onDragEnd({ active, over }) {
    if (over) return `Step ${active.id} was placed after ${over.id}`
    return `Step ${active.id} was dropped`
  },
  onDragCancel({ active }) {
    return `Dragging ${active.id} was cancelled`
  },
}
```

---

## 8. Open Questions (Need CEO Input)

### Q1: Backend scope for compile-to-validate
Task 51 is described as frontend ("Visual Pipeline Editor View"), but compile-to-validate requires a backend endpoint that doesn't exist. Should Task 51 include creating `POST /api/editor/compile` + DraftPipeline CRUD endpoints, or is that a separate task? If frontend-only, should compile do client-side validation only (step name existence, ordering) or show "backend not implemented" state?

### Q2: Step source for "Add Step"
When user clicks "Add Step" in the editor, what pool of steps is available?
a. Existing registered pipeline steps (from introspection API `/api/pipelines/{name}`)
b. DraftSteps created via the Creator (`/api/creator/drafts`)
c. Both existing + draft steps
d. Blank step form (user types step name + config manually)

### Q3: Editor relationship to existing pipelines
Is the editor for:
a. Creating new pipelines from scratch (select steps, arrange, compile)
b. Editing/reordering steps of existing registered pipelines
c. Both (load existing, modify, save as draft)
The DraftPipeline model stores `structure` referencing step names, suggesting new pipeline creation. But "Visual Editor" could also mean editing existing ones.
