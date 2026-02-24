import type { StepListItem, EventItem } from '@/api/types'
import { StatusBadge } from '@/components/runs/StatusBadge'
import { formatDuration } from '@/lib/time'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type StepStatus = 'completed' | 'running' | 'failed' | 'skipped' | 'pending'

export interface StepTimelineItem {
  step_name: string
  step_number: number
  status: StepStatus
  execution_time_ms: number | null
  model: string | null
}

export interface StepTimelineProps {
  items: StepTimelineItem[]
  isLoading: boolean
  isError: boolean
  selectedStepId: number | null
  onSelectStep: (stepNumber: number) => void
}

// ---------------------------------------------------------------------------
// deriveStepStatus - merge DB steps with WS events
// ---------------------------------------------------------------------------

/**
 * Merge completed DB steps with live WS events to produce timeline items.
 *
 * Logic:
 * - All DB steps are treated as 'completed' by default.
 * - Events with event_type 'step_skipped' override to 'skipped'.
 * - Events with 'step_started' that have no matching 'step_completed' or
 *   'step_failed' produce a 'running' item (added if not already in DB).
 * - Events with 'step_failed' that match a DB step override to 'failed'.
 */
export function deriveStepStatus(
  dbSteps: StepListItem[],
  events: EventItem[],
): StepTimelineItem[] {
  // Build map keyed by step_name from DB steps (all completed)
  const map = new Map<string, StepTimelineItem>()

  for (const step of dbSteps) {
    map.set(step.step_name, {
      step_name: step.step_name,
      step_number: step.step_number,
      status: 'completed',
      execution_time_ms: step.execution_time_ms,
      model: step.model,
    })
  }

  // Track started steps and their completion/failure
  const startedSteps = new Set<string>()
  const completedOrFailed = new Set<string>()
  const skippedSteps = new Set<string>()
  const startedMeta = new Map<string, { step_number: number }>()

  for (const event of events) {
    const stepName = (event.event_data?.step_name as string) ?? ''
    if (!stepName) continue

    if (event.event_type === 'step_started') {
      startedSteps.add(stepName)
      const stepNum = (event.event_data?.step_number as number) ?? 0
      startedMeta.set(stepName, { step_number: stepNum })
    } else if (
      event.event_type === 'step_completed' ||
      event.event_type === 'step_failed'
    ) {
      completedOrFailed.add(stepName)
    } else if (event.event_type === 'step_skipped') {
      skippedSteps.add(stepName)
    }
  }

  // Override skipped steps
  for (const stepName of skippedSteps) {
    const existing = map.get(stepName)
    if (existing) {
      existing.status = 'skipped'
    }
  }

  // Override failed steps from events
  for (const event of events) {
    if (event.event_type === 'step_failed') {
      const stepName = (event.event_data?.step_name as string) ?? ''
      const existing = map.get(stepName)
      if (existing) {
        existing.status = 'failed'
      }
    }
  }

  // Add running steps (started but not completed/failed and not in DB)
  for (const stepName of startedSteps) {
    if (completedOrFailed.has(stepName)) continue

    const existing = map.get(stepName)
    if (existing) {
      // DB has it but events say still running
      existing.status = 'running'
    } else {
      // Not in DB yet - add as running
      const meta = startedMeta.get(stepName)
      map.set(stepName, {
        step_name: stepName,
        step_number: meta?.step_number ?? 0,
        status: 'running',
        execution_time_ms: null,
        model: null,
      })
    }
  }

  // Sort by step_number ascending
  return Array.from(map.values()).sort((a, b) => a.step_number - b.step_number)
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function SkeletonRows() {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="h-7 w-7 animate-pulse rounded-full bg-muted" />
          <div className="h-4 w-32 animate-pulse rounded bg-muted" />
          <div className="ml-auto h-5 w-16 animate-pulse rounded bg-muted" />
          <div className="h-4 w-12 animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// StepTimeline component
// ---------------------------------------------------------------------------

export function StepTimeline({
  items,
  isLoading,
  isError,
  selectedStepId,
  onSelectStep,
}: StepTimelineProps) {
  if (isLoading) {
    return <SkeletonRows />
  }

  if (isError) {
    return (
      <p className="p-4 text-center text-destructive">Failed to load steps</p>
    )
  }

  if (items.length === 0) {
    return (
      <p className="p-4 text-center text-muted-foreground">No steps recorded</p>
    )
  }

  return (
    <div className="space-y-1 p-2">
      {items.map((item) => {
        const isSelected = selectedStepId === item.step_number
        return (
          <button
            key={item.step_number}
            type="button"
            className={cn(
              'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors',
              item.status === 'running'
                ? 'cursor-not-allowed opacity-70'
                : 'cursor-pointer hover:bg-muted/30',
              isSelected && 'bg-muted/50',
            )}
            title={item.status === 'running' ? 'Step still in progress' : undefined}
            onClick={() => onSelectStep(item.step_number)}
          >
            {/* Step number badge */}
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-medium">
              {item.step_number}
            </span>

            {/* Step name */}
            <span className="min-w-0 flex-1 truncate text-sm font-medium">
              {item.step_name}
            </span>

            {/* Status badge */}
            <StatusBadge status={item.status} />

            {/* Duration */}
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
              {formatDuration(item.execution_time_ms)}
            </span>

            {/* Model */}
            {item.model && (
              <span className="shrink-0 text-xs text-muted-foreground">
                {item.model}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
