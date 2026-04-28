import { useMemo, useCallback } from 'react'
import { useTrace } from '@/api/trace'
import { useSteps } from '@/api/steps'
import { useRun } from '@/api/runs'
import { useWsStore } from '@/stores/websocket'
import { useUIStore } from '@/stores/ui'
import type { RunStatus } from '@/api/types'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { TraceTimeline } from '@/components/live/TraceTimeline'
import { ActiveRunsBar } from '@/components/live/ActiveRunsBar'
import { StepTimeline, deriveStepStatus } from '@/components/runs/StepTimeline'
import { StepDetailPanel } from '@/components/runs/StepDetailPanel'

interface MonitoringPanelProps {
  onOpenPicker: () => void
}

export function MonitoringPanel({ onOpenPicker }: MonitoringPanelProps) {
  const focusedRunId = useWsStore((s) => s.focusedRunId)
  const subscribedRuns = useWsStore((s) => s.subscribedRuns)

  const { selectedStepId, stepDetailOpen, selectStep, closeStepDetail } = useUIStore()

  // Pull operational run state from local DB; trace observations from
  // Langfuse via the backend trace route. WebSocket span_started /
  // span_ended pushes invalidate the trace query in real time.
  const { data: run } = useRun(focusedRunId ?? '')
  const runStatus: RunStatus | undefined =
    (run?.status as RunStatus | undefined) ?? undefined

  const { data: trace, isLoading: traceLoading, isError: traceError } =
    useTrace(focusedRunId ?? '', runStatus)
  const { data: steps } = useSteps(focusedRunId ?? '', runStatus)

  const observations = trace?.observations ?? []

  const timelineItems = useMemo(
    () => deriveStepStatus(steps?.items ?? [], observations),
    [steps?.items, observations],
  )

  const handleSelectStep = useCallback(
    (stepNum: number) => {
      const item = timelineItems.find((i) => i.step_number === stepNum)
      if (item?.status === 'running') return
      selectStep(stepNum)
    },
    [timelineItems, selectStep],
  )

  if (Object.keys(subscribedRuns).length === 0) {
    return (
      <div className="flex h-full flex-col">
        <ActiveRunsBar onOpenPicker={onOpenPicker} />
        <div className="flex flex-1 items-center justify-center">
          <p className="text-muted-foreground text-sm">
            Subscribe to a run to start monitoring
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <ActiveRunsBar onOpenPicker={onOpenPicker} />

      <div className="flex min-h-0 flex-1 gap-4 p-3">
        {/* Trace timeline (Langfuse-backed) */}
        <Card className="flex min-w-0 flex-[2] flex-col overflow-hidden">
          <TraceTimeline
            observations={observations}
            isLoading={traceLoading}
            isError={traceError}
            emptyMessage={
              trace && !trace.langfuse_configured
                ? 'Langfuse is not configured on the backend; live trace data is unavailable.'
                : 'Waiting for the first observation...'
            }
          />
        </Card>

        {/* Step list (operational state) */}
        <Card className="hidden flex-1 flex-col overflow-hidden lg:flex">
          <ScrollArea className="min-h-0 flex-1">
            <StepTimeline
              items={timelineItems}
              isLoading={false}
              isError={false}
              selectedStepId={selectedStepId}
              onSelectStep={handleSelectStep}
            />
          </ScrollArea>
        </Card>
      </div>

      <StepDetailPanel
        runId={focusedRunId ?? ''}
        stepNumber={selectedStepId}
        open={stepDetailOpen}
        onClose={closeStepDetail}
        runStatus={runStatus}
      />
    </div>
  )
}
