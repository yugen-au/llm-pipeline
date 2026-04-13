import { useMemo, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useEvents } from '@/api/events'
import { useSteps } from '@/api/steps'
import { useWsStore } from '@/stores/websocket'
import type { WsConnectionStatus } from '@/stores/websocket'
import { queryKeys } from '@/api/query-keys'
import type { EventItem, RunStatus } from '@/api/types'
import { useUIStore } from '@/stores/ui'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { EventStream } from '@/components/live/EventStream'
import { ActiveRunsBar } from '@/components/live/ActiveRunsBar'
import { StepTimeline, deriveStepStatus } from '@/components/runs/StepTimeline'
import { StepDetailPanel } from '@/components/runs/StepDetailPanel'

const TERMINAL_EVENT_TYPES = new Set(['pipeline_completed', 'pipeline_failed'])

function deriveRunStatus(
  wsStatus: WsConnectionStatus,
  events: EventItem[],
): RunStatus | undefined {
  if (wsStatus === 'connecting' || wsStatus === 'connected') {
    for (let i = events.length - 1; i >= 0; i--) {
      if (TERMINAL_EVENT_TYPES.has(events[i].event_type)) {
        return events[i].event_type === 'pipeline_completed' ? 'completed' : 'failed'
      }
    }
    return 'running'
  }
  if (wsStatus === 'error') return 'failed'
  for (let i = events.length - 1; i >= 0; i--) {
    if (TERMINAL_EVENT_TYPES.has(events[i].event_type)) {
      return events[i].event_type === 'pipeline_completed' ? 'completed' : 'failed'
    }
  }
  return undefined
}

interface MonitoringPanelProps {
  onOpenPicker: () => void
}

export function MonitoringPanel({ onOpenPicker }: MonitoringPanelProps) {
  const queryClient = useQueryClient()
  const focusedRunId = useWsStore((s) => s.focusedRunId)
  const subscribedRuns = useWsStore((s) => s.subscribedRuns)
  const focusedInfo = focusedRunId ? subscribedRuns[focusedRunId] : null
  const wsStatus = useWsStore((s) => s.status)

  const { selectedStepId, stepDetailOpen, selectStep, closeStepDetail } = useUIStore()

  const runStatus = useMemo(() => {
    if (!focusedRunId) return undefined
    const cached = queryClient.getQueryData<{ items: EventItem[] }>(
      queryKeys.runs.events(focusedRunId, {}),
    )
    return deriveRunStatus(wsStatus, cached?.items ?? [])
  }, [wsStatus, focusedRunId, queryClient])

  const { data: events } = useEvents(focusedRunId ?? '', {}, runStatus)
  const { data: steps } = useSteps(focusedRunId ?? '', runStatus)

  const timelineItems = useMemo(
    () => deriveStepStatus(steps?.items ?? [], events?.items ?? []),
    [steps?.items, events?.items],
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
        {/* Event stream */}
        <Card className="flex min-w-0 flex-[2] flex-col overflow-hidden">
          <EventStream
            events={events?.items ?? []}
            wsStatus={wsStatus}
            runId={focusedRunId}
            isReplaying={focusedInfo?.isReplaying}
          />
        </Card>

        {/* Step timeline */}
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
