import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { useCreateRun } from '@/api/runs'
import { usePipeline } from '@/api/pipelines'
import { useSteps } from '@/api/steps'
import { useEvents } from '@/api/events'
import { useWebSocket } from '@/api/websocket'
import { useRunNotifications } from '@/api/useRunNotifications'
import { useUIStore } from '@/stores/ui'
import { useWsStore } from '@/stores/websocket'
import type { WsConnectionStatus } from '@/stores/websocket'
import { queryKeys } from '@/api/query-keys'
import type { RunStatus, EventItem } from '@/api/types'
import { ApiError } from '@/api/types'
import { StepTimeline, deriveStepStatus } from '@/components/runs/StepTimeline'
import { StepDetailPanel } from '@/components/runs/StepDetailPanel'
import { PipelineSelector } from '@/components/live/PipelineSelector'
import { InputForm, validateForm } from '@/components/live/InputForm'
import { EventStream } from '@/components/live/EventStream'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

// ---------------------------------------------------------------------------
// Derive run status from WS connection state + event stream
// ---------------------------------------------------------------------------

/** Terminal pipeline event types that indicate the run has finished. */
const TERMINAL_EVENT_TYPES = new Set(['pipeline_completed', 'pipeline_failed'])

/**
 * Derive RunStatus from the WS connection status and the event stream.
 *
 * - `connected` / `connecting` / `replaying` -> run is `running`
 * - `closed` with terminal pipeline event (`pipeline_completed`) -> `completed`
 * - `closed` with `pipeline_failed` event -> `failed`
 * - `error` or `closed` without terminal event -> `failed` (abnormal disconnect)
 * - `idle` (no active run) -> undefined
 */
function deriveRunStatus(
  wsStatus: WsConnectionStatus,
  events: EventItem[],
): RunStatus | undefined {
  if (wsStatus === 'idle') return undefined

  // Active connection means the run is still executing
  if (wsStatus === 'connecting' || wsStatus === 'connected' || wsStatus === 'replaying') {
    return 'running'
  }

  // WS closed or errored -- check events for terminal status
  // Use reverse loop instead of findLast (tsconfig lib: ES2020, findLast needs ES2023)
  let lastTerminal: EventItem | undefined
  for (let i = events.length - 1; i >= 0; i--) {
    if (TERMINAL_EVENT_TYPES.has(events[i].event_type)) {
      lastTerminal = events[i]
      break
    }
  }
  if (lastTerminal) {
    return lastTerminal.event_type === 'pipeline_completed' ? 'completed' : 'failed'
  }

  // WS error or closed without a terminal pipeline event -> treat as failed
  if (wsStatus === 'error') return 'failed'

  // closed without terminal event (e.g. replay of a completed run that has
  // no pipeline_completed event in the stream -- shouldn't happen but safe default)
  return 'completed'
}

export const Route = createFileRoute('/live')({
  component: LivePage,
})

// ---------------------------------------------------------------------------
// LivePage
// ---------------------------------------------------------------------------

function LivePage() {
  // -- Local state --
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [inputValues, setInputValues] = useState<Record<string, unknown>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // -- Hooks --
  const queryClient = useQueryClient()
  const createRun = useCreateRun()
  const { data: pipelineDetail } = usePipeline(selectedPipeline ?? '')
  const inputSchema = pipelineDetail?.pipeline_input_schema ?? null

  useWebSocket(activeRunId)
  const wsStoreStatus = useWsStore((s) => s.status)
  const { latestRun } = useRunNotifications()
  const { selectedStepId, stepDetailOpen, selectStep, closeStepDetail } = useUIStore()

  // -- Derived run status from WS + events (used by useEvents, useSteps, StepDetailPanel) --
  // Must be computed before useEvents/useSteps so they receive the status on first render.
  // On initial render (no events yet), wsStoreStatus drives the status; once events arrive
  // the terminal event_type refines it to completed/failed.
  // Reading cache inside useMemo to avoid creating a new array ref each render.
  const runStatus = useMemo(() => {
    const cached = queryClient.getQueryData<{ items: EventItem[] }>(
      queryKeys.runs.events(activeRunId ?? '', {}),
    )
    return deriveRunStatus(wsStoreStatus, cached?.items ?? [])
  }, [wsStoreStatus, activeRunId, queryClient])

  const { data: events } = useEvents(activeRunId ?? '', {}, runStatus)
  const { data: steps } = useSteps(activeRunId ?? '', runStatus)

  // -- Event cache seeding + run creation --
  const handleRunPipeline = useCallback(() => {
    if (!selectedPipeline) return

    // Frontend required-field validation
    const errors = validateForm(inputSchema, inputValues)
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      return
    }
    setFieldErrors({})

    createRun.mutate(
      {
        pipeline_name: selectedPipeline,
        input_data: inputSchema ? inputValues : undefined,
      },
      {
        onSuccess: (data) => {
          // Seed event cache BEFORE setting activeRunId (order matters).
          // appendEventToCache in websocket.ts only updates if cache exists;
          // without seeding, WS events arriving before REST fetch would be dropped.
          queryClient.setQueryData(queryKeys.runs.events(data.run_id, {}), {
            items: [],
            total: 0,
            offset: 0,
            limit: 50,
          })
          setActiveRunId(data.run_id)
          setInputValues({})
          setFieldErrors({})
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === 422) {
            try {
              const details = JSON.parse(error.detail) as Array<{
                loc: string[]
                msg: string
              }>
              const mapped: Record<string, string> = {}
              for (const item of details) {
                const field = item.loc[item.loc.length - 1]
                mapped[field] = item.msg
              }
              if (Object.keys(mapped).length > 0) {
                setFieldErrors(mapped)
              }
            } catch {
              // detail was not structured JSON, nothing to map
            }
          }
        },
      },
    )
  }, [selectedPipeline, createRun, queryClient, inputSchema, inputValues])

  // -- Python-initiated run detection --
  // Auto-attach to runs started externally (e.g. another client, CLI).
  // Uses a ref to track the last handled run_id and subscribes to
  // latestRun changes without calling setState synchronously in effect body.
  const handledRunRef = useRef<string | null>(null)

  useEffect(() => {
    if (!latestRun || latestRun.run_id === handledRunRef.current) return
    handledRunRef.current = latestRun.run_id

    // Seed cache for the new run before attaching
    queryClient.setQueryData(queryKeys.runs.events(latestRun.run_id, {}), {
      items: [],
      total: 0,
      offset: 0,
      limit: 50,
    })

    // Defer state updates to avoid synchronous setState in effect body
    queueMicrotask(() => {
      setActiveRunId(latestRun.run_id)
      setSelectedPipeline(latestRun.pipeline_name)
    })
  }, [latestRun, queryClient])

  // -- Reset form when pipeline selection changes --
  useEffect(() => {
    setInputValues({})
    setFieldErrors({})
  }, [selectedPipeline])

  // -- Timeline items from DB steps + WS events --
  const timelineItems = useMemo(
    () => deriveStepStatus(steps?.items ?? [], events?.items ?? []),
    [steps?.items, events?.items],
  )

  // -- In-progress step click guard --
  // Clicking a running step would show error/loading in StepDetailPanel
  // because PipelineStepState rows are written only after step completion.
  const handleSelectStep = useCallback(
    (stepNum: number) => {
      const item = timelineItems.find((i) => i.step_number === stepNum)
      if (item?.status === 'running') {
        console.info('[LivePage] Step %d (%s) still in progress -- detail unavailable', stepNum, item.step_name)
        return
      }
      selectStep(stepNum)
    },
    [timelineItems, selectStep],
  )

  // -- Shared column content (reused in desktop grid + mobile tabs) --

  const pipelineColumn = (
    <Card className="flex h-full flex-col overflow-hidden">
      {/* Fixed header: selector + run button */}
      <CardContent className="shrink-0 flex flex-col gap-4 p-4">
        <PipelineSelector
          selectedPipeline={selectedPipeline}
          onSelect={setSelectedPipeline}
          disabled={createRun.isPending}
        />

        <Button
          onClick={handleRunPipeline}
          disabled={!selectedPipeline || createRun.isPending}
          className="w-full"
        >
          <Play className="size-4" />
          {createRun.isPending ? 'Starting...' : 'Run Pipeline'}
        </Button>
      </CardContent>

      {/* Scrollable form area */}
      {inputSchema && (
        <ScrollArea thin className="min-h-0 flex-1">
          <div className="px-4 pb-4">
            <InputForm
              schema={inputSchema}
              values={inputValues}
              onChange={(field, value) =>
                setInputValues((prev) => ({ ...prev, [field]: value }))
              }
              fieldErrors={fieldErrors}
              isSubmitting={createRun.isPending}
            />
          </div>
        </ScrollArea>
      )}
    </Card>
  )

  const eventsColumn = (
    <Card className="flex h-full flex-col overflow-hidden">
      <EventStream
        events={events?.items ?? []}
        wsStatus={wsStoreStatus}
        runId={activeRunId}
      />
    </Card>
  )

  const stepsColumn = (
    <div className="flex h-full flex-col gap-4 overflow-hidden">
      <Card className="min-h-0 flex-1 overflow-auto">
        <StepTimeline
          items={timelineItems}
          isLoading={false}
          isError={false}
          selectedStepId={selectedStepId}
          onSelectStep={handleSelectStep}
        />
      </Card>
    </div>
  )

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-card-foreground">Live</h1>
        <p className="text-sm text-muted-foreground">Live pipeline monitoring</p>
      </div>

      {/* Desktop layout (lg+): 3-column grid */}
      <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-3 lg:gap-4">
        {/* Col 1: Pipeline selector + run button + InputForm */}
        <div className="overflow-auto">{pipelineColumn}</div>

        {/* Col 2: Event stream */}
        <div className="overflow-hidden">{eventsColumn}</div>

        {/* Col 3: Step timeline + detail panel */}
        <div className="overflow-hidden">{stepsColumn}</div>
      </div>

      {/* Mobile/tablet layout (below lg): tab-based */}
      <div className="flex min-h-0 flex-1 flex-col lg:hidden">
        <Tabs defaultValue="pipeline" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="shrink-0">
            <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
            <TabsTrigger value="events">Events</TabsTrigger>
            <TabsTrigger value="steps">Steps</TabsTrigger>
          </TabsList>

          <TabsContent value="pipeline" className="min-h-0 flex-1 overflow-auto">
            {pipelineColumn}
          </TabsContent>
          <TabsContent value="events" className="min-h-0 flex-1 overflow-hidden">
            {eventsColumn}
          </TabsContent>
          <TabsContent value="steps" className="min-h-0 flex-1 overflow-hidden">
            {stepsColumn}
          </TabsContent>
        </Tabs>
      </div>

      {/* Step detail panel overlay */}
      <StepDetailPanel
        runId={activeRunId ?? ''}
        stepNumber={selectedStepId}
        open={stepDetailOpen}
        onClose={closeStepDetail}
        runStatus={runStatus}
      />
    </div>
  )
}
