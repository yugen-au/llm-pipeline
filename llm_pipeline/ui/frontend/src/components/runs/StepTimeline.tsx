import type { StepListItem, TraceObservation } from '@/api/types'
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
// deriveStepStatus - merge DB steps with live trace observations
// ---------------------------------------------------------------------------

/**
 * Merge persisted step rows with live trace observations to produce
 * timeline items.
 *
 * Logic:
 * - All DB step rows are 'completed' by default (a row only gets
 *   written once a step finishes).
 * - For every trace observation whose name is "step.{name}":
 *   - has start_time but no end_time → 'running' (add to map if not in DB yet)
 *   - has end_time with level === 'ERROR' → override to 'failed'
 *
 * Span events for "step.skipped" don't surface as separate
 * observations on the trace endpoint. If we ever need that, surface
 * it via status_message on the step span and check here.
 */
export function deriveStepStatus(
  dbSteps: StepListItem[],
  observations: TraceObservation[],
): StepTimelineItem[] {
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

  const stepObservations = observations.filter((o) =>
    o.name.startsWith('step.') && o.type === 'SPAN',
  )

  let runningStepNumberCounter = (
    Math.max(0, ...dbSteps.map((s) => s.step_number)) + 1
  )

  for (const obs of stepObservations) {
    const stepName = obs.name.slice('step.'.length)
    const existing = map.get(stepName)

    // In-flight: started but not yet ended
    if (obs.start_time && !obs.end_time) {
      if (!existing) {
        map.set(stepName, {
          step_name: stepName,
          step_number: runningStepNumberCounter++,
          status: 'running',
          execution_time_ms: null,
          model: null,
        })
      } else if (existing.status !== 'completed' && existing.status !== 'failed') {
        existing.status = 'running'
      }
      continue
    }

    // Ended with error → failed
    if (obs.end_time && obs.level === 'ERROR') {
      if (existing) {
        existing.status = 'failed'
      } else {
        map.set(stepName, {
          step_name: stepName,
          step_number: runningStepNumberCounter++,
          status: 'failed',
          execution_time_ms: obs.duration_ms != null ? Math.round(obs.duration_ms) : null,
          model: null,
        })
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
