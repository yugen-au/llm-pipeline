import { useMemo } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import { AlertTriangle, ArrowLeft } from 'lucide-react'
import { useRun, useRunContext } from '@/api/runs'
import { useSteps } from '@/api/steps'
import { useTrace } from '@/api/trace'
import { useSubscribeRun } from '@/api/websocket'
import { useUIStore } from '@/stores/ui'
import { StepTimeline, deriveStepStatus } from '@/components/runs/StepTimeline'
import { ContextEvolution } from '@/components/runs/ContextEvolution'
import { StepDetailPanel } from '@/components/runs/StepDetailPanel'
import { StatusBadge } from '@/components/runs/StatusBadge'
import { TraceTimeline } from '@/components/live/TraceTimeline'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
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

  // Subscribe to live events for this run
  useSubscribeRun(runId)

  // Data hooks
  const { data: run, isLoading: runLoading, isError: runError } = useRun(runId)
  const runStatus = isRunStatus(run?.status) ? run.status : undefined
  const { data: steps, isLoading: stepsLoading, isError: stepsError } = useSteps(runId)
  const {
    data: trace,
    isLoading: traceLoading,
    isError: traceError,
  } = useTrace(runId, runStatus)
  const { data: context, isLoading: contextLoading, isError: contextError } = useRunContext(
    runId,
    runStatus,
  )

  // UI state
  const { selectedStepId, stepDetailOpen, selectStep, closeStepDetail } = useUIStore()

  // Derive timeline items from DB steps + live trace observations
  const observations = trace?.observations ?? []
  const timelineItems = useMemo(
    () => deriveStepStatus(steps?.items ?? [], observations),
    [steps?.items, observations],
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

        {/* Error banner */}
        {run.status === 'failed' && run.error_message && (
          <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-destructive">Pipeline failed</p>
              <p className="mt-1 text-sm text-destructive/80 break-words">{run.error_message}</p>
            </div>
          </div>
        )}

        {/* Page body: Steps + Trace + Context Evolution */}
        <div className="flex min-h-0 flex-1 gap-4">
          {/* Step list (left, narrow) — operational status from local DB */}
          <CardContent className="flex w-72 shrink-0 flex-col overflow-hidden rounded-xl border p-0">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-semibold">Steps</h2>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <StepTimeline
                items={timelineItems}
                isLoading={stepsLoading || traceLoading}
                isError={stepsError || traceError}
                selectedStepId={selectedStepId}
                onSelectStep={selectStep}
              />
            </ScrollArea>
          </CardContent>

          {/* Trace timeline (centre, main) — Langfuse observation tree */}
          <CardContent className="flex flex-1 flex-col overflow-hidden rounded-xl border p-0">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-semibold">Trace</h2>
            </div>
            <TraceTimeline
              observations={observations}
              isLoading={traceLoading}
              isError={traceError}
              emptyMessage={
                trace && !trace.trace_backend_configured
                  ? 'No trace backend configured; trace data is unavailable.'
                  : 'No observations yet'
              }
            />
          </CardContent>

          {/* Context evolution (right, narrow) */}
          <div className="flex w-72 shrink-0 flex-col overflow-hidden rounded-xl border">
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
