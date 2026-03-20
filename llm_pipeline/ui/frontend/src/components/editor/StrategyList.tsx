/**
 * StrategyList -- a single strategy column in the center canvas.
 *
 * Wraps its steps in a SortableContext with verticalListSortingStrategy.
 * The strategy container is a droppable area (via useDroppable) so palette
 * items can be dropped onto it to add a step to this strategy.
 */

import { useDroppable } from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'

import type { CompileError } from '@/api/editor'
import type { EditorStepItem, EditorStrategyState } from '@/routes/editor'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

import { SortableStepCard } from './SortableStepCard'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface StrategyListProps {
  strategy: EditorStrategyState
  onStepsChange: (steps: EditorStepItem[]) => void
  selectedStepId: string | null
  onSelectStep: (id: string | null) => void
  onRemoveStep: (stepId: string) => void
  errors: CompileError[]
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StrategyList({
  strategy,
  selectedStepId,
  onSelectStep,
  onRemoveStep,
  errors,
}: StrategyListProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: `strategy-${strategy.strategy_name}`,
    data: { type: 'strategy', strategyName: strategy.strategy_name },
  })

  const stepIds = strategy.steps.map((s) => s.id)

  return (
    <div className="flex min-w-[220px] flex-1 flex-col rounded-lg border bg-muted/30">
      {/* Strategy header */}
      <div className="border-b px-3 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {strategy.strategy_name}
        </h3>
        <span className="text-[11px] text-muted-foreground">
          {strategy.steps.length} step{strategy.steps.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Droppable + sortable container */}
      <ScrollArea className="min-h-0 flex-1" thin>
        <div
          ref={setNodeRef}
          className={cn(
            'flex min-h-[80px] flex-col gap-1.5 p-2 transition-colors',
            isOver && 'bg-primary/5 ring-1 ring-inset ring-primary/20',
          )}
        >
          <SortableContext
            items={stepIds}
            strategy={verticalListSortingStrategy}
          >
            {strategy.steps.map((step) => {
              const error = errors.find(
                (e) =>
                  e.step_ref === step.step_ref &&
                  e.strategy_name === strategy.strategy_name,
              )
              return (
                <SortableStepCard
                  key={step.id}
                  step={step}
                  isSelected={selectedStepId === step.id}
                  error={error}
                  onSelectStep={onSelectStep}
                  onRemoveStep={onRemoveStep}
                />
              )
            })}
          </SortableContext>

          {/* Empty state */}
          {strategy.steps.length === 0 && (
            <p className="py-6 text-center text-xs text-muted-foreground">
              Drop steps here
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
