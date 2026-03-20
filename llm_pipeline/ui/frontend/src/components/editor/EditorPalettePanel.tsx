/**
 * Step Palette Panel -- left panel of the 3-panel editor layout.
 *
 * Lists available steps (registered + draft) with search filtering.
 * Each step is draggable via @dnd-kit useDraggable for drag-from-palette
 * into strategy lists (wired in Step 5). Also provides an "Add" button
 * callback per step.
 */

import { useState, useMemo } from 'react'
import { useDraggable } from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import { Search, GripVertical, Plus, ExternalLink } from 'lucide-react'

import { useAvailableSteps, type AvailableStep } from '@/api/editor'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SkeletonLine } from '@/components/shared/LoadingSkeleton'
import { EmptyState } from '@/components/shared/EmptyState'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EditorPalettePanelProps {
  onAddStepToStrategy: (strategyName: string, step: AvailableStep) => void
  /** Strategy names currently in the canvas -- needed for the "Add" dropdown */
  strategyNames?: string[]
}

// ---------------------------------------------------------------------------
// Draggable palette step item
// ---------------------------------------------------------------------------

interface DraggableStepItemProps {
  step: AvailableStep
  strategyNames: string[]
  onAdd: (strategyName: string, step: AvailableStep) => void
}

function DraggableStepItem({
  step,
  strategyNames,
  onAdd,
}: DraggableStepItemProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: `palette-${step.step_ref}`,
      data: { type: 'palette-step', step },
    })

  const style = transform
    ? {
        transform: CSS.Translate.toString(transform),
        zIndex: 10,
      }
    : undefined

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-sm transition-shadow ${
        isDragging
          ? 'shadow-md ring-2 ring-ring/30 opacity-50'
          : 'hover:shadow-sm'
      }`}
    >
      {/* Drag handle */}
      <button
        type="button"
        className="shrink-0 cursor-grab touch-none text-muted-foreground hover:text-foreground"
        aria-label={`Drag ${step.step_ref}`}
        {...listeners}
        {...attributes}
      >
        <GripVertical className="size-4" />
      </button>

      {/* Step name + source badge */}
      <div className="flex min-w-0 flex-1 items-center gap-1.5">
        <span className="truncate font-medium">{step.step_ref}</span>
        <Badge
          variant={step.source === 'registered' ? 'secondary' : 'outline'}
          className="shrink-0 text-[10px] leading-tight px-1.5 py-0"
        >
          {step.source}
        </Badge>
      </div>

      {/* Add button(s) */}
      {strategyNames.length === 1 ? (
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => onAdd(strategyNames[0], step)}
          aria-label={`Add ${step.step_ref} to ${strategyNames[0]}`}
        >
          <Plus className="size-3" />
        </Button>
      ) : strategyNames.length > 1 ? (
        <div className="flex shrink-0 items-center gap-0.5">
          {strategyNames.map((name) => (
            <Button
              key={name}
              variant="ghost"
              size="icon-xs"
              onClick={() => onAdd(name, step)}
              title={`Add to ${name}`}
              aria-label={`Add ${step.step_ref} to ${name}`}
            >
              <Plus className="size-3" />
            </Button>
          ))}
        </div>
      ) : (
        <Button
          variant="ghost"
          size="icon-xs"
          disabled
          aria-label="No strategies available"
        >
          <Plus className="size-3" />
        </Button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function PaletteSkeleton() {
  return (
    <div className="flex flex-col gap-2 p-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2 rounded-md border px-2 py-2">
          <SkeletonLine width="16px" className="h-4 shrink-0" />
          <SkeletonLine className="h-4 flex-1" />
          <SkeletonLine width="48px" className="h-4 shrink-0" />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function EditorPalettePanel({
  onAddStepToStrategy,
  strategyNames = [],
}: EditorPalettePanelProps) {
  const { data, isPending, isError } = useAvailableSteps()
  const [search, setSearch] = useState('')

  const steps = data?.steps ?? []

  // Filter by search
  const filtered = useMemo(() => {
    if (!search.trim()) return steps
    const q = search.toLowerCase()
    return steps.filter((s) => s.step_ref.toLowerCase().includes(q))
  }, [steps, search])

  // Split into sections
  const registered = useMemo(
    () => filtered.filter((s) => s.source === 'registered'),
    [filtered],
  )
  const draft = useMemo(
    () => filtered.filter((s) => s.source === 'draft'),
    [filtered],
  )

  return (
    <Card className="flex h-full flex-col overflow-hidden p-4 gap-3">
      {/* Header */}
      <h2 className="text-xs font-medium text-muted-foreground">
        Step Palette
      </h2>

      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search steps..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 pl-7 text-sm"
        />
      </div>

      {/* Step list */}
      <ScrollArea className="min-h-0 flex-1" thin>
        {isPending ? (
          <PaletteSkeleton />
        ) : isError ? (
          <p className="px-1 text-sm text-destructive">
            Failed to load steps.
          </p>
        ) : filtered.length === 0 ? (
          <EmptyState
            message={
              search.trim()
                ? `No steps matching "${search}".`
                : 'No steps available. Create one first.'
            }
          />
        ) : (
          <div className="flex flex-col gap-3 pr-1">
            {/* Registered steps section */}
            {registered.length > 0 && (
              <section>
                <h3 className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Registered Steps
                </h3>
                <div className="flex flex-col gap-1">
                  {registered.map((step) => (
                    <DraggableStepItem
                      key={step.step_ref}
                      step={step}
                      strategyNames={strategyNames}
                      onAdd={onAddStepToStrategy}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Draft steps section */}
            {draft.length > 0 && (
              <section>
                <h3 className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Draft Steps
                </h3>
                <div className="flex flex-col gap-1">
                  {draft.map((step) => (
                    <DraggableStepItem
                      key={step.step_ref}
                      step={step}
                      strategyNames={strategyNames}
                      onAdd={onAddStepToStrategy}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </ScrollArea>

      {/* Create new step link */}
      <Button
        variant="outline"
        size="sm"
        className="w-full gap-1.5"
        onClick={() => window.open('/creator', '_blank')}
      >
        <ExternalLink className="size-3.5" />
        Create new step
      </Button>
    </Card>
  )
}
