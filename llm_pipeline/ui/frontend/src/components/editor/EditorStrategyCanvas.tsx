/**
 * EditorStrategyCanvas -- center panel of the 3-panel editor layout.
 *
 * Renders one StrategyList per strategy, arranged horizontally.
 * Does NOT own the DndContext -- that lives in editor.tsx so the palette
 * panel's useDraggable and the canvas's useSortable/useDroppable share the
 * same context. The parent provides onDragEnd via buildEditorDragEnd.
 */

import { useCallback, type Dispatch, type SetStateAction } from 'react'
import type { DragEndEvent } from '@dnd-kit/core'
import { arrayMove } from '@dnd-kit/sortable'

import type { CompileError, AvailableStep } from '@/api/editor'
import type { EditorStepItem, EditorStrategyState } from '@/routes/editor'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'

import { StrategyList } from './StrategyList'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EditorStrategyCanvasProps {
  strategies: EditorStrategyState[]
  onStrategiesChange: Dispatch<SetStateAction<EditorStrategyState[]>>
  selectedStepId: string | null
  onSelectStep: Dispatch<SetStateAction<string | null>>
  compileErrors: CompileError[]
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EditorStrategyCanvas({
  strategies,
  onStrategiesChange,
  selectedStepId,
  onSelectStep,
  compileErrors,
}: EditorStrategyCanvasProps) {
  // -------------------------------------------------------------------
  // Remove step handler (memoized to avoid re-rendering all cards)
  // -------------------------------------------------------------------

  const handleRemoveStep = useCallback(
    (stepId: string) => {
      onStrategiesChange((prev) =>
        prev.map((s) => ({
          ...s,
          steps: s.steps.filter((st) => st.id !== stepId),
        })),
      )
      // Deselect if removed step was selected
      onSelectStep((current) => (current === stepId ? null : current))
    },
    [onStrategiesChange, onSelectStep],
  )

  // -------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------

  if (strategies.length === 0) {
    return (
      <div className="flex h-full items-center justify-center rounded-lg border border-dashed bg-muted/20">
        <p className="text-sm text-muted-foreground">
          No strategies defined. Add a strategy to begin.
        </p>
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="flex h-full gap-3 p-1">
        {strategies.map((strategy) => (
          <StrategyList
            key={strategy.strategy_name}
            strategy={strategy}
            selectedStepId={selectedStepId}
            onSelectStep={onSelectStep}
            onRemoveStep={handleRemoveStep}
            errors={compileErrors}
          />
        ))}
      </div>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  )
}

// ---------------------------------------------------------------------------
// Drag-end logic -- used by the parent DndContext in editor.tsx
// ---------------------------------------------------------------------------

/** Find which strategy a step belongs to by step UUID. */
function findStrategyForStep(
  strategies: EditorStrategyState[],
  stepId: string,
): EditorStrategyState | undefined {
  return strategies.find((s) => s.steps.some((st) => st.id === stepId))
}

/**
 * Resolve target strategy name from an over.id.
 * over.id can be:
 *   - "strategy-<name>" (dropped on strategy droppable container)
 *   - a step UUID (dropped on a sortable step within a strategy)
 */
function resolveTargetStrategy(
  strategies: EditorStrategyState[],
  overId: string,
): string | null {
  if (overId.startsWith('strategy-')) {
    return overId.replace('strategy-', '')
  }
  const strategy = findStrategyForStep(strategies, overId)
  return strategy?.strategy_name ?? null
}

/**
 * Build the onDragEnd handler for the editor's DndContext.
 *
 * Uses functional updater (setStrategies(prev => ...)) to avoid stale
 * closures -- the handler never reads strategies from its creation scope.
 *
 * Handles:
 *   - palette-step drops: add to target strategy with new UUID
 *   - sortable-step reorder: arrayMove within same strategy
 *   - cross-strategy drag: no-op (v1 limitation)
 */
export function buildEditorDragEnd(
  setStrategies: Dispatch<SetStateAction<EditorStrategyState[]>>,
): (event: DragEndEvent) => void {
  return function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over) return

    const activeData = active.data.current as
      | { type: 'palette-step'; step: AvailableStep }
      | { type: 'sortable-step'; step: EditorStepItem }
      | undefined

    if (!activeData) return

    // ----- Palette drop: add new step to target strategy -----
    if (activeData.type === 'palette-step') {
      const paletteStep = activeData.step
      const overId = over.id as string

      setStrategies((prev) => {
        const targetStrategyName = resolveTargetStrategy(prev, overId)
        if (!targetStrategyName) return prev

        const newStep: EditorStepItem = {
          id: crypto.randomUUID(),
          step_ref: paletteStep.step_ref,
          source: paletteStep.source,
        }

        return prev.map((s) =>
          s.strategy_name === targetStrategyName
            ? { ...s, steps: [...s.steps, newStep] }
            : s,
        )
      })
      return
    }

    // ----- Sortable reorder within same strategy -----
    if (activeData.type === 'sortable-step') {
      if (active.id === over.id) return

      const activeId = active.id as string
      const overId = over.id as string

      setStrategies((prev) => {
        const sourceStrategy = findStrategyForStep(prev, activeId)
        if (!sourceStrategy) return prev

        // Check if over target is in the same strategy
        const overIsStep = sourceStrategy.steps.some(
          (st) => st.id === overId,
        )

        if (!overIsStep) {
          // Cross-strategy drag: no-op (v1 limitation)
          return prev
        }

        const oldIndex = sourceStrategy.steps.findIndex(
          (st) => st.id === activeId,
        )
        const newIndex = sourceStrategy.steps.findIndex(
          (st) => st.id === overId,
        )
        if (oldIndex === -1 || newIndex === -1) return prev

        const reordered = arrayMove(sourceStrategy.steps, oldIndex, newIndex)

        return prev.map((s) =>
          s.strategy_name === sourceStrategy.strategy_name
            ? { ...s, steps: reordered }
            : s,
        )
      })
    }
  }
}
