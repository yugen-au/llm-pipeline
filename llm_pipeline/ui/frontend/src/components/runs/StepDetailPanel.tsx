import { useStep } from '@/api/steps'
import { useStepEvents } from '@/api/events'
import { useStepInstructions, usePipeline } from '@/api/pipelines'
import { useRunContext } from '@/api/runs'
import { formatDuration, formatAbsolute } from '@/lib/time'
import { JsonViewer } from '@/components/JsonViewer'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ExtractionDetail } from '@/components/runs/ExtractionDetail'
import type {
  EventItem,
  StepDetail,
  StepPromptItem,
  ContextSnapshot,
  RunStatus,
  LLMCallCompletedData,
  ContextUpdatedData,
  ExtractionCompletedData,
} from '@/api/types'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface StepDetailPanelProps {
  runId: string
  stepNumber: number | null
  open: boolean
  onClose: () => void
  runStatus?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Type-narrow event_data as T (no runtime validation -- task 35 scope). */
function eventData<T>(event: EventItem): T {
  return event.event_data as T
}

/** Filter events by type and cast event_data. */
function filterEvents<T>(events: EventItem[], type: string): { event: EventItem; data: T }[] {
  return events
    .filter((e) => e.event_type === type)
    .map((e) => ({ event: e, data: eventData<T>(e) }))
}

// ---------------------------------------------------------------------------
// Tab content components (private)
// ---------------------------------------------------------------------------

function InputTab({
  step,
  snapshots,
  snapshotsLoading,
}: {
  step: StepDetail
  snapshots: ContextSnapshot[]
  snapshotsLoading: boolean
}) {
  if (step.step_number === 1) {
    return <p className="text-sm text-muted-foreground">No prior context (first step)</p>
  }

  if (snapshotsLoading) {
    return <div className="h-24 animate-pulse rounded bg-muted" />
  }

  const prevSnapshot = snapshots.find((s) => s.step_number === step.step_number - 1)

  if (!prevSnapshot) {
    return <p className="text-sm text-muted-foreground">Previous step context not available</p>
  }

  return (
    <ScrollArea className="h-[calc(100vh-220px)]">
      <div className="space-y-2">
        <h4 className="text-sm font-medium text-muted-foreground">
          Context after step {prevSnapshot.step_number} ({prevSnapshot.step_name})
        </h4>
        <JsonViewer data={prevSnapshot.context_snapshot} />
      </div>
    </ScrollArea>
  )
}

function PromptsTab({
  prompts,
  isLoading,
  isError,
}: {
  prompts: StepPromptItem[] | undefined
  isLoading: boolean
  isError: boolean
}) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="h-5 w-40 animate-pulse rounded bg-muted" />
        <div className="h-20 animate-pulse rounded bg-muted" />
        <div className="h-20 animate-pulse rounded bg-muted" />
      </div>
    )
  }

  if (isError) {
    return <p className="text-sm text-destructive">Failed to load prompts</p>
  }

  if (!prompts || prompts.length === 0) {
    return <p className="text-sm text-muted-foreground">No prompt templates registered</p>
  }

  return (
    <ScrollArea className="h-[calc(100vh-220px)]">
      <div className="space-y-4">
        {prompts.map((item) => (
          <div key={item.prompt_key} className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{item.prompt_type}</Badge>
              <span className="text-sm font-medium">{item.prompt_key}</span>
            </div>
            <pre className="whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs">
              {item.content}
            </pre>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}

function ResponseTab({ events }: { events: EventItem[] }) {
  const calls = filterEvents<LLMCallCompletedData>(events, 'llm_call_completed')
  const total = calls.length

  if (total === 0) {
    return <p className="text-sm text-muted-foreground">No LLM responses recorded</p>
  }

  return (
    <ScrollArea className="h-[calc(100vh-220px)]">
      <div className="space-y-4">
        {calls.map(({ data }, i) => (
          <div key={i} className="space-y-2">
            {total > 1 && (
              <h4 className="text-sm font-semibold">
                Call {data.call_index + 1} of {total}
              </h4>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Raw Response</p>
                <pre className="whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs">
                  {data.raw_response ?? '(null)'}
                </pre>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Parsed Result</p>
                {data.parsed_result
                  ? <JsonViewer data={data.parsed_result as Record<string, unknown>} />
                  : <span className="text-xs text-muted-foreground">(null)</span>
                }
              </div>
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}

function InstructionsTab({
  instructionsSchema,
  instructionsClass,
}: {
  instructionsSchema: Record<string, unknown> | null
  instructionsClass: string | null
}) {
  if (!instructionsSchema) {
    return <p className="text-sm text-muted-foreground">No schema available</p>
  }

  return (
    <ScrollArea className="h-[calc(100vh-220px)]">
      <div className="space-y-3">
        {instructionsClass && (
          <Badge variant="secondary">{instructionsClass}</Badge>
        )}
        <JsonViewer data={instructionsSchema} />
      </div>
    </ScrollArea>
  )
}

function ContextDiffTab({
  step,
  events,
  snapshots,
  snapshotsLoading,
}: {
  step: StepDetail
  events: EventItem[]
  snapshots: ContextSnapshot[]
  snapshotsLoading: boolean
}) {
  // Get new_keys from context_updated events for this step
  const ctxEvents = filterEvents<ContextUpdatedData>(events, 'context_updated')
  const newKeys = ctxEvents.flatMap(({ data }) => data.new_keys)

  if (snapshotsLoading) {
    return <div className="h-24 animate-pulse rounded bg-muted" />
  }

  const beforeSnapshot = snapshots.find((s) => s.step_number === step.step_number - 1)
  const afterSnapshot = snapshots.find((s) => s.step_number === step.step_number)

  return (
    <ScrollArea className="h-[calc(100vh-220px)]">
      <div className="space-y-3">
        {newKeys.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">New Keys</p>
            <div className="flex flex-wrap gap-1">
              {newKeys.map((key) => (
                <Badge key={key} variant="outline">{key}</Badge>
              ))}
            </div>
          </div>
        )}
        <JsonViewer
          before={beforeSnapshot?.context_snapshot ?? {}}
          after={afterSnapshot?.context_snapshot ?? step.context_snapshot}
          maxDepth={3}
        />
      </div>
    </ScrollArea>
  )
}

function ExtractionsTab({ events }: { events: EventItem[] }) {
  const extractions = filterEvents<ExtractionCompletedData>(events, 'extraction_completed')
  const errors = events.filter((e) => e.event_type === 'extraction_error')

  if (extractions.length === 0 && errors.length === 0) {
    return <p className="text-sm text-muted-foreground">No extractions for this step</p>
  }

  return (
    <ScrollArea className="h-[calc(100vh-220px)]">
      <div className="space-y-3">
        {extractions.map(({ data }, i) => (
          <ExtractionDetail key={i} data={data} />
        ))}
        {errors.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-destructive">Extraction Errors</h4>
            {errors.map((e, i) => (
              <div key={i} className="rounded-md bg-destructive/10 p-3 text-destructive">
                <JsonViewer data={e.event_data as Record<string, unknown>} />
              </div>
            ))}
          </div>
        )}
      </div>
    </ScrollArea>
  )
}

function MetaTab({
  step,
  events,
}: {
  step: StepDetail
  events: EventItem[]
}) {
  const completedCalls = filterEvents<LLMCallCompletedData>(events, 'llm_call_completed')
  const cacheHit = events.find((e) => e.event_type === 'cache_hit')
  const cacheMiss = events.find((e) => e.event_type === 'cache_miss')
  const stepSelected = events.find((e) => e.event_type === 'step_selected')

  // Aggregate validation errors and token usage across all calls
  const validationErrors = completedCalls.flatMap(({ data }) => data.validation_errors ?? [])
  const maxAttempts = completedCalls.length > 0
    ? Math.max(...completedCalls.map(({ data }) => data.attempt_count))
    : null
  const inputTokens = completedCalls.reduce((sum, { data }) => sum + (data.input_tokens ?? 0), 0)
  const outputTokens = completedCalls.reduce((sum, { data }) => sum + (data.output_tokens ?? 0), 0)
  const hasTokens = completedCalls.some(({ data }) => data.input_tokens != null || data.output_tokens != null)

  return (
    <ScrollArea className="h-[calc(100vh-220px)]">
      <div className="space-y-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Step Name</dt>
          <dd>{step.step_name}</dd>
          <dt className="text-muted-foreground">Step Number</dt>
          <dd>{step.step_number}</dd>
          <dt className="text-muted-foreground">Model</dt>
          <dd>{step.model ?? '\u2014'}</dd>
          <dt className="text-muted-foreground">Duration</dt>
          <dd>{formatDuration(step.execution_time_ms)}</dd>
          {hasTokens && (
            <>
              <dt className="text-muted-foreground">Tokens In</dt>
              <dd>{inputTokens.toLocaleString()}</dd>
              <dt className="text-muted-foreground">Tokens Out</dt>
              <dd>{outputTokens.toLocaleString()}</dd>
              <dt className="text-muted-foreground">Tokens Total</dt>
              <dd>{(inputTokens + outputTokens).toLocaleString()}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Created</dt>
          <dd>{formatAbsolute(step.created_at)}</dd>
          {step.prompt_system_key && (
            <>
              <dt className="text-muted-foreground">System Key</dt>
              <dd className="font-mono text-xs">{step.prompt_system_key}</dd>
            </>
          )}
          {step.prompt_user_key && (
            <>
              <dt className="text-muted-foreground">User Key</dt>
              <dd className="font-mono text-xs">{step.prompt_user_key}</dd>
            </>
          )}
          {maxAttempts != null && (
            <>
              <dt className="text-muted-foreground">Attempts</dt>
              <dd>{maxAttempts}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Cache</dt>
          <dd>
            {cacheHit ? (
              <Badge variant="secondary">hit</Badge>
            ) : cacheMiss ? (
              <Badge variant="outline">miss</Badge>
            ) : (
              '\u2014'
            )}
          </dd>
          {stepSelected && (
            <>
              <dt className="text-muted-foreground">Strategy</dt>
              <dd>{String((stepSelected.event_data as Record<string, unknown>).strategy_name ?? '\u2014')}</dd>
            </>
          )}
        </dl>

        {validationErrors.length > 0 && (
          <div className="space-y-1">
            <p className="text-sm font-medium text-destructive">Validation Errors</p>
            <ul className="list-inside list-disc text-xs text-destructive">
              {validationErrors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </ScrollArea>
  )
}

// ---------------------------------------------------------------------------
// StepContent (mounts only when open && stepNumber != null)
// ---------------------------------------------------------------------------

function StepContent({
  runId,
  stepNumber,
  runStatus,
}: {
  runId: string
  stepNumber: number
  runStatus?: string
}) {
  const { data: step, isLoading, isError } = useStep(runId, stepNumber, runStatus)

  const {
    data: eventsResponse,
    isLoading: eventsLoading,
  } = useStepEvents(runId, step?.step_name ?? '', runStatus)

  const {
    data: instructionsResponse,
    isLoading: instructionsLoading,
    isError: instructionsError,
  } = useStepInstructions(step?.pipeline_name ?? '', step?.step_name ?? '')

  const {
    data: pipelineResponse,
  } = usePipeline(step?.pipeline_name)

  const {
    data: contextResponse,
    isLoading: contextLoading,
  } = useRunContext(
    runId,
    runStatus === 'completed' || runStatus === 'failed' ? (runStatus as RunStatus) : undefined,
  )

  // Derive step metadata from pipeline introspection
  const stepMeta = pipelineResponse?.strategies
    ?.flatMap((s) => s.steps)
    .find((s) => s.step_name === step?.step_name) ?? null

  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        <div className="h-5 w-40 animate-pulse rounded bg-muted" />
        <div className="h-4 w-24 animate-pulse rounded bg-muted" />
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      </div>
    )
  }

  if (isError) {
    return <p className="p-4 text-sm text-destructive">Failed to load step</p>
  }

  if (!step) return null

  const events = eventsResponse?.items ?? []
  const snapshots = contextResponse?.snapshots ?? []

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Step header */}
      <div className="shrink-0 border-b px-4 py-3">
        <h3 className="text-base font-semibold">{step.step_name}</h3>
        <p className="text-xs text-muted-foreground">
          Step {step.step_number} &middot; {step.model ?? 'no model'} &middot; {formatDuration(step.execution_time_ms)}
        </p>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="meta" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="mx-4 mt-3 shrink-0 flex-wrap">
          <TabsTrigger value="meta">Meta</TabsTrigger>
          <TabsTrigger value="input">Input</TabsTrigger>
          <TabsTrigger value="prompts">Prompts</TabsTrigger>
          <TabsTrigger value="response">Response</TabsTrigger>
          <TabsTrigger value="instructions">Instructions</TabsTrigger>
          <TabsTrigger value="context">Context</TabsTrigger>
          <TabsTrigger value="extractions">Extractions</TabsTrigger>
        </TabsList>

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {eventsLoading ? (
            <div className="space-y-2">
              <div className="h-4 w-48 animate-pulse rounded bg-muted" />
              <div className="h-20 animate-pulse rounded bg-muted" />
            </div>
          ) : (
            <>
              <TabsContent value="meta">
                <MetaTab step={step} events={events} />
              </TabsContent>
              <TabsContent value="input">
                <InputTab step={step} snapshots={snapshots} snapshotsLoading={contextLoading} />
              </TabsContent>
              <TabsContent value="prompts">
                <PromptsTab
                  prompts={instructionsResponse?.prompts}
                  isLoading={instructionsLoading}
                  isError={instructionsError}
                />
              </TabsContent>
              <TabsContent value="response">
                <ResponseTab events={events} />
              </TabsContent>
              <TabsContent value="instructions">
                <InstructionsTab
                  instructionsSchema={stepMeta?.instructions_schema ?? null}
                  instructionsClass={stepMeta?.instructions_class ?? null}
                />
              </TabsContent>
              <TabsContent value="context">
                <ContextDiffTab
                  step={step}
                  events={events}
                  snapshots={snapshots}
                  snapshotsLoading={contextLoading}
                />
              </TabsContent>
              <TabsContent value="extractions">
                <ExtractionsTab events={events} />
              </TabsContent>
            </>
          )}
        </div>
      </Tabs>
    </div>
  )
}

// ---------------------------------------------------------------------------
// StepDetailPanel (public)
// ---------------------------------------------------------------------------

export function StepDetailPanel({
  runId,
  stepNumber,
  open,
  onClose,
  runStatus,
}: StepDetailPanelProps) {
  const visible = open && stepNumber != null

  return (
    <Sheet open={visible} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-[600px] max-w-full p-0 sm:max-w-[600px]">
        <SheetHeader className="sr-only">
          <SheetTitle>Step Detail</SheetTitle>
          <SheetDescription>Detailed view of pipeline step execution</SheetDescription>
        </SheetHeader>
        {visible ? (
          <StepContent
            runId={runId}
            stepNumber={stepNumber}
            runStatus={runStatus}
          />
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
