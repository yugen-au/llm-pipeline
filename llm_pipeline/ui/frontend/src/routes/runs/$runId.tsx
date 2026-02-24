import { useMemo } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import { ArrowLeft } from 'lucide-react'
import { useRun, useRunContext } from '@/api/runs'
import { useSteps } from '@/api/steps'
import { useEvents } from '@/api/events'
import { useWebSocket } from '@/api/websocket'
import { useUIStore } from '@/stores/ui'
import { StepTimeline, deriveStepStatus } from '@/components/runs/StepTimeline'
import { ContextEvolution } from '@/components/runs/ContextEvolution'
import { StepDetailPanel } from '@/components/runs/StepDetailPanel'
import { StatusBadge } from '@/components/runs/StatusBadge'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { formatDuration, formatRelative, formatAbsolute } from '@/lib/time'
import type { RunStatus } from '@/api/types'

const RUN_STATUSES: readonly RunStatus[] = ['running', 'completed', 'failed'] as const

function isRunStatus(s: string | undefined): s is RunStatus {
  return s != null && (RUN_STATUSES as readonly string[]).includes(s)
}

const runDetailSearchSchema = z.object({
  tab: fallback(z.string(), 'steps').default('steps'),
})

export const Route = createFileRoute('/runs/$runId')({
  validateSearch: zodValidator(runDetailSearchSchema),
  component: RunDetailPage,
})

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function RunDetailSkeleton() {
  return (
    <div className="flex flex-col gap-4 p-6">
      {/* Header skeleton */}
      <div className="bg-card rounded-xl border p-6">
        <div className="flex items-center gap-4">
          <div className="h-5 w-5 animate-pulse rounded bg-muted" />
          <div className="h-6 w-48 animate-pulse rounded bg-muted" />
          <div className="h-5 w-20 animate-pulse rounded bg-muted" />
          <div className="ml-auto h-4 w-24 animate-pulse rounded bg-muted" />
        </div>
      </div>
      {/* Body skeleton */}
      <div className="flex gap-4">
        <div className="flex-1 space-y-2 rounded-xl border p-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="h-7 w-7 animate-pulse rounded-full bg-muted" />
              <div className="h-4 w-32 animate-pulse rounded bg-muted" />
              <div className="ml-auto h-5 w-16 animate-pulse rounded bg-muted" />
            </div>
          ))}
        </div>
        <div className="w-80 space-y-4 rounded-xl border p-4">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="space-y-2">
              <div className="h-5 w-32 animate-pulse rounded bg-muted" />
              <div className="h-24 animate-pulse rounded bg-muted" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 404 state
// ---------------------------------------------------------------------------

function RunNotFound() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 p-12">
      <h2 className="text-xl font-semibold">Run not found</h2>
      <p className="text-muted-foreground">
        The requested run does not exist or has been removed.
      </p>
      <Link
        to="/"
        className="text-sm text-primary underline underline-offset-4 hover:text-primary/80"
      >
        Back to runs
      </Link>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RunDetailPage
// ---------------------------------------------------------------------------

function RunDetailPage() {
  const { runId } = Route.useParams()

  // WebSocket for live updates
  useWebSocket(runId)

  // Data hooks
  const { data: run, isLoading: runLoading, isError: runError } = useRun(runId)
  const { data: steps, isLoading: stepsLoading, isError: stepsError } = useSteps(runId, run?.status)
  const { data: events, isLoading: eventsLoading, isError: eventsError } = useEvents(runId, {}, run?.status)
  const { data: context, isLoading: contextLoading, isError: contextError } = useRunContext(
    runId,
    isRunStatus(run?.status) ? run.status : undefined,
  )

  // UI state
  const { selectedStepId, stepDetailOpen, selectStep, closeStepDetail } = useUIStore()

  // Derive timeline items from DB steps + WS events
  const timelineItems = useMemo(
    () => deriveStepStatus(steps?.items ?? [], events?.items ?? []),
    [steps?.items, events?.items],
  )

  // Loading state
  if (runLoading) {
    return <RunDetailSkeleton />
  }

  // Not found / error
  if (runError || !run) {
    return <RunNotFound />
  }

  return (
    <TooltipProvider>
      <div className="flex h-full flex-col gap-4 p-6">
        {/* Run header */}
        <Card>
          <CardHeader className="flex-row items-center gap-4">
            <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="size-5" />
            </Link>

            <h1 className="text-lg font-semibold">{run.pipeline_name}</h1>

            <Separator orientation="vertical" className="h-5" />

            <Tooltip>
              <TooltipTrigger asChild>
                <code className="text-sm text-muted-foreground">{run.run_id.slice(0, 8)}</code>
              </TooltipTrigger>
              <TooltipContent>{run.run_id}</TooltipContent>
            </Tooltip>

            <StatusBadge status={run.status} />

            <div className="ml-auto flex items-center gap-4 text-sm text-muted-foreground">
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>{formatRelative(run.started_at)}</span>
                </TooltipTrigger>
                <TooltipContent>{formatAbsolute(run.started_at)}</TooltipContent>
              </Tooltip>

              <span className="tabular-nums">{formatDuration(run.total_time_ms)}</span>
            </div>
          </CardHeader>
        </Card>

        {/* Page body: StepTimeline + ContextEvolution */}
        <div className="flex min-h-0 flex-1 gap-4">
          {/* Step timeline - main column */}
          <CardContent className="flex-1 overflow-auto rounded-xl border p-0">
            <StepTimeline
              items={timelineItems}
              isLoading={stepsLoading || eventsLoading}
              isError={stepsError || eventsError}
              selectedStepId={selectedStepId}
              onSelectStep={selectStep}
            />
          </CardContent>

          {/* Context evolution - right column */}
          <div className="w-80 shrink-0 overflow-hidden rounded-xl border">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-semibold">Context Evolution</h2>
            </div>
            <ContextEvolution
              snapshots={context?.snapshots ?? []}
              isLoading={contextLoading}
              isError={contextError}
            />
          </div>
        </div>

        {/* Step detail panel overlay */}
        <StepDetailPanel
          runId={runId}
          stepNumber={selectedStepId}
          open={stepDetailOpen}
          onClose={closeStepDetail}
          runStatus={run.status}
        />
      </div>
    </TooltipProvider>
  )
}
