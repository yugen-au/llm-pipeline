/**
 * SortableStepCard -- individual sortable step within a strategy list.
 *
 * Uses @dnd-kit/sortable useSortable hook. Drag handle is isolated to the
 * GripVertical element so clicks on the card body (select) and remove button
 * are not intercepted by the drag listener.
 */

import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, X } from 'lucide-react'

import type { CompileError } from '@/api/editor'
import type { EditorStepItem } from '@/routes/editor'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SortableStepCardProps {
  step: EditorStepItem
  isSelected: boolean
  error?: CompileError
  onSelectStep: (id: string) => void
  onRemoveStep: (id: string) => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SortableStepCard({
  step,
  isSelected,
  error,
  onSelectStep,
  onRemoveStep,
}: SortableStepCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: step.id,
    data: { type: 'sortable-step', step },
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'group relative flex items-center gap-1.5 rounded-md border bg-card px-1 py-1.5 text-sm transition-colors',
        isSelected && 'border-primary ring-1 ring-primary/30',
        error && !isSelected && 'border-destructive ring-1 ring-destructive/30',
        isDragging && 'z-50 opacity-50 shadow-md',
      )}
      onClick={() => onSelectStep(step.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelectStep(step.id)
        }
      }}
    >
      {/* Drag handle -- listeners/attributes ONLY here */}
      <button
        type="button"
        className="shrink-0 cursor-grab touch-none rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
        aria-label={`Drag ${step.step_ref}`}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" />
      </button>

      {/* Step name + source badge */}
      <div className="flex min-w-0 flex-1 items-center gap-1.5">
        <span className="truncate font-mono text-xs font-medium">
          {step.step_ref}
        </span>
        <Badge
          variant={step.source === 'registered' ? 'secondary' : 'outline'}
          className="shrink-0 px-1.5 py-0 text-[10px] leading-tight"
        >
          {step.source}
        </Badge>
      </div>

      {/* Error indicator */}
      {error && (
        <span
          className="mr-0.5 size-2 shrink-0 rounded-full bg-destructive"
          title={error.message}
        />
      )}

      {/* Remove button */}
      <Button
        variant="ghost"
        size="icon-xs"
        className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
        onClick={(e) => {
          e.stopPropagation()
          onRemoveStep(step.id)
        }}
        aria-label={`Remove ${step.step_ref}`}
      >
        <X className="size-3" />
      </Button>
    </div>
  )
}
