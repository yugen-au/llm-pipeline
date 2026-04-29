import { useMemo } from 'react'
import { useStep } from '@/api/steps'
import { useTrace } from '@/api/trace'
import { useStepInstructions, usePipeline } from '@/api/pipelines'
import { useRunContext } from '@/api/runs'
import { formatDuration, formatAbsolute } from '@/lib/time'
import { JsonViewer } from '@/components/JsonViewer'
import { TraceTimeline } from '@/components/live/TraceTimeline'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { ExtractionDetail } from '@/components/runs/ExtractionDetail'
import {
  EmptyState,
  TabScrollArea,
  LabeledPre,
  BadgeSection,
  SkeletonLine,
  SkeletonBlock,
} from '@/components/shared'
import type {
  StepDetail,
  StepPromptItem,
  ContextSnapshot,
  TraceObservation,
  RunStatus,
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

/** Find the step span observation (parent of all step descendants). */
function findStepSpan(
  observations: TraceObservation[],
  stepName: string,
): TraceObservation | undefined {
  return observations.find(
    (o) => o.name === `step.${stepName}` && o.type === 'SPAN',
  )
}

/** Collect all observations descended from a given parent span. */
function descendantsOf(
  observations: TraceObservation[],
  rootId: string,
): TraceObservation[] {
  const byParent = new Map<string, TraceObservation[]>()
  for (const o of observations) {
    if (!o.parent_observation_id) continue
    if (!byParent.has(o.parent_observation_id)) byParent.set(o.parent_observation_id, [])
    byParent.get(o.parent_observation_id)!.push(o)
  }
  const result: TraceObservation[] = []
  const stack = [rootId]
  while (stack.length) {
    const id = stack.pop()!
    const children = byParent.get(id) ?? []
    for (const c of children) {
      result.push(c)
      stack.push(c.id)
    }
  }
  return result
}

/** Sum token + cost across generation observations under this step. */
function generationTotals(observations: TraceObservation[]) {
  let inputTokens = 0
  let outputTokens = 0
  let cost = 0
  let count = 0
  for (const o of observations) {
    if (o.type !== 'GENERATION' && !o.name.startsWith('gen_ai')) continue
    count += 1
    inputTokens += o.input_tokens ?? 0
    outputTokens += o.output_tokens ?? 0
    cost += o.total_cost ?? 0
  }
  return { count, inputTokens, outputTokens, cost }
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function InputTab({
  step,
  isLoading,
  isError,
  context,
  pipelineMetadata,
  pipelineLoading,
  isFinalStep,
}: {
  step: StepDetail | undefined
  isLoading: boolean
  isError: boolean
  context: ContextSnapshot | null
  pipelineMetadata: ReturnType<typeof usePipeline>['data']
  pipelineLoading: boolean
  isFinalStep: boolean
}) {
  void pipelineMetadata
  void pipelineLoading
  void isFinalStep
  if (isLoading) return <SkeletonBlock />
  if (isError || !step) return <EmptyState message="Failed to load step input" />
  return (
    <TabScrollArea>
      <BadgeSection>
        <Badge variant="outline">step #{step.step_number}</Badge>
        {step.execution_time_ms != null && (
          <Badge variant="outline">{formatDuration(step.execution_time_ms)}</Badge>
        )}
        {step.model && <Badge variant="outline">{step.model}</Badge>}
      </BadgeSection>
      {context?.context_snapshot ? (
        <div className="mt-3">
          <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
            Context snapshot at this step
          </p>
          <JsonViewer data={context.context_snapshot} />
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">
          No context snapshot recorded for this step.
        </p>
      )}
    </TabScrollArea>
  )
}

function PromptsTab({
  step,
  prompts,
  promptsLoading,
}: {
  step: StepDetail | undefined
  prompts: StepPromptItem[]
  promptsLoading: boolean
}) {
  if (!step) return <EmptyState message="Step not loaded" />
  if (promptsLoading) return <SkeletonBlock />
  if (prompts.length === 0) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        No prompt content registered for this step.
      </p>
    )
  }
  return (
    <TabScrollArea>
      {prompts.map((p) => (
        <LabeledPre
          key={p.prompt_key}
          label={`${p.prompt_type} — ${p.prompt_key} (v${p.version})`}
          content={p.content}
        />
      ))}
    </TabScrollArea>
  )
}

function GenerationsTab({
  observations,
  isLoading,
  isError,
  traceBackendConfigured,
}: {
  observations: TraceObservation[]
  isLoading: boolean
  isError: boolean
  traceBackendConfigured: boolean
}) {
  const generations = observations.filter(
    (o) => o.type === 'GENERATION' || o.name.startsWith('gen_ai'),
  )
  if (isError) return <EmptyState message="Failed to load trace" />
  if (!traceBackendConfigured && !isLoading) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        No trace backend configured; LLM call detail is unavailable.
      </p>
    )
  }
  if (generations.length === 0 && !isLoading) {
    return <p className="p-4 text-sm text-muted-foreground">No LLM calls recorded.</p>
  }
  return (
    <TabScrollArea>
      <div className="flex flex-col gap-4">
        {generations.map((g) => (
          <div key={g.id} className="rounded-lg border p-3">
            <div className="mb-2 flex items-center gap-2 text-sm">
              <span className="font-mono">{g.name}</span>
              {g.model && <Badge variant="outline">{g.model}</Badge>}
              {g.duration_ms != null && (
                <span className="text-xs text-muted-foreground">
                  {formatDuration(Math.round(g.duration_ms))}
                </span>
              )}
              {g.input_tokens != null && g.output_tokens != null && (
                <span className="text-xs text-muted-foreground">
                  {g.input_tokens}→{g.output_tokens} tok
                </span>
              )}
              {g.total_cost != null && g.total_cost > 0 && (
                <span className="text-xs text-muted-foreground">
                  ${g.total_cost.toFixed(4)}
                </span>
              )}
            </div>
            {g.input != null && (
              <div className="mb-2">
                <div className="mb-1 text-xs font-medium text-muted-foreground">input</div>
                <JsonViewer data={g.input as object} />
              </div>
            )}
            {g.output != null && (
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">output</div>
                <JsonViewer data={g.output as object} />
              </div>
            )}
          </div>
        ))}
      </div>
    </TabScrollArea>
  )
}

function InstructionsTab({
  step,
  isLoading,
  isError,
}: {
  step: StepDetail | undefined
  isLoading: boolean
  isError: boolean
}) {
  if (isLoading) return <SkeletonBlock />
  if (isError || !step) return <EmptyState message="Failed to load instructions" />
  if (!step.result_data) {
    return <p className="p-4 text-sm text-muted-foreground">No result data persisted for this step.</p>
  }
  return (
    <TabScrollArea>
      <JsonViewer data={step.result_data} />
    </TabScrollArea>
  )
}

function ExtractionsTab({
  observations,
  isLoading,
}: {
  observations: TraceObservation[]
  isLoading: boolean
}) {
  const extractions = observations.filter((o) => o.name.startsWith('extraction.'))
  if (isLoading && extractions.length === 0) return <SkeletonBlock />
  if (extractions.length === 0) {
    return <p className="p-4 text-sm text-muted-foreground">No extractions recorded for this step.</p>
  }
  return (
    <TabScrollArea>
      <div className="flex flex-col gap-3">
        {extractions.map((e) => (
          <ExtractionDetail
            key={e.id}
            extractionClass={e.name.slice('extraction.'.length)}
            modelClass={
              (e.metadata as { model_class?: string } | null)?.model_class ?? '?'
            }
            instanceCount={
              (e.metadata as { instance_count?: number } | null)?.instance_count ?? 0
            }
            executionTimeMs={e.duration_ms != null ? Math.round(e.duration_ms) : 0}
            timestamp={e.start_time ?? ''}
            created={[]}
            updated={[]}
          />
        ))}
      </div>
    </TabScrollArea>
  )
}

function MetaTab({
  step,
  observations,
  isLoading,
  isError,
}: {
  step: StepDetail | undefined
  observations: TraceObservation[]
  isLoading: boolean
  isError: boolean
}) {
  const totals = useMemo(() => generationTotals(observations), [observations])
  if (isLoading) return <SkeletonBlock />
  if (isError || !step) return <EmptyState message="Failed to load step metadata" />
  return (
    <TabScrollArea>
      <BadgeSection>
        <Badge variant="outline">created {formatAbsolute(step.created_at)}</Badge>
        {step.execution_time_ms != null && (
          <Badge variant="outline">{formatDuration(step.execution_time_ms)}</Badge>
        )}
        {totals.count > 0 && (
          <>
            <Badge variant="outline">{totals.count} LLM call{totals.count > 1 ? 's' : ''}</Badge>
            <Badge variant="outline">
              {totals.inputTokens}→{totals.outputTokens} tok
            </Badge>
            {totals.cost > 0 && (
              <Badge variant="outline">${totals.cost.toFixed(4)}</Badge>
            )}
          </>
        )}
      </BadgeSection>
      <div className="mt-3 space-y-2 text-sm">
        {step.prompt_system_key && (
          <div>
            <span className="text-muted-foreground">system: </span>
            <code>{step.prompt_system_key}</code>
          </div>
        )}
        {step.prompt_user_key && (
          <div>
            <span className="text-muted-foreground">user: </span>
            <code>{step.prompt_user_key}</code>
          </div>
        )}
        {step.input_hash && (
          <div>
            <span className="text-muted-foreground">input_hash: </span>
            <code>{step.input_hash.slice(0, 16)}...</code>
          </div>
        )}
      </div>
    </TabScrollArea>
  )
}

// ---------------------------------------------------------------------------
// StepContent
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
  const { data: step, isLoading: stepLoading, isError: stepError } = useStep(
    runId,
    stepNumber,
    runStatus,
  )
  const { data: trace, isLoading: traceLoading, isError: traceError } = useTrace(
    runId,
    runStatus as RunStatus | undefined,
  )
  const { data: context } = useRunContext(runId, runStatus as RunStatus | undefined)
  const pipelineName = step?.pipeline_name ?? ''
  const stepName = step?.step_name ?? ''
  const { data: pipelineMetadata, isLoading: pipelineLoading } = usePipeline(pipelineName)
  const { data: stepInstructions, isLoading: promptsLoading } = useStepInstructions(
    pipelineName,
    stepName,
  )

  // Filter observations to those descended from this step's span.
  const observations = trace?.observations ?? []
  const stepObservations = useMemo(() => {
    if (!stepName) return []
    const stepSpan = findStepSpan(observations, stepName)
    if (!stepSpan) return []
    return [stepSpan, ...descendantsOf(observations, stepSpan.id)]
  }, [observations, stepName])

  const contextSnapshot =
    context?.snapshots?.find((s) => s.step_number === stepNumber) ?? null
  const isFinalStep =
    pipelineMetadata != null &&
    pipelineMetadata.execution_order.length > 0 &&
    pipelineMetadata.execution_order[pipelineMetadata.execution_order.length - 1] === stepName

  return (
    <Tabs defaultValue="input" className="flex h-full flex-col">
      <TabsList>
        <TabsTrigger value="input">Input</TabsTrigger>
        <TabsTrigger value="prompts">Prompts</TabsTrigger>
        <TabsTrigger value="generations">Generations</TabsTrigger>
        <TabsTrigger value="instructions">Instructions</TabsTrigger>
        <TabsTrigger value="extractions">Extractions</TabsTrigger>
        <TabsTrigger value="trace">Trace</TabsTrigger>
        <TabsTrigger value="meta">Meta</TabsTrigger>
      </TabsList>

      <TabsContent value="input" className="min-h-0 flex-1">
        <InputTab
          step={step}
          isLoading={stepLoading}
          isError={stepError}
          context={contextSnapshot}
          pipelineMetadata={pipelineMetadata}
          pipelineLoading={pipelineLoading}
          isFinalStep={isFinalStep}
        />
      </TabsContent>
      <TabsContent value="prompts" className="min-h-0 flex-1">
        <PromptsTab
          step={step}
          prompts={stepInstructions?.prompts ?? []}
          promptsLoading={promptsLoading}
        />
      </TabsContent>
      <TabsContent value="generations" className="min-h-0 flex-1">
        <GenerationsTab
          observations={stepObservations}
          isLoading={traceLoading}
          isError={traceError}
          traceBackendConfigured={trace?.trace_backend_configured ?? false}
        />
      </TabsContent>
      <TabsContent value="instructions" className="min-h-0 flex-1">
        <InstructionsTab step={step} isLoading={stepLoading} isError={stepError} />
      </TabsContent>
      <TabsContent value="extractions" className="min-h-0 flex-1">
        <ExtractionsTab observations={stepObservations} isLoading={traceLoading} />
      </TabsContent>
      <TabsContent value="trace" className="min-h-0 flex-1">
        <TraceTimeline
          observations={stepObservations}
          isLoading={traceLoading}
          isError={traceError}
          emptyMessage="No observations for this step"
        />
      </TabsContent>
      <TabsContent value="meta" className="min-h-0 flex-1">
        <MetaTab
          step={step}
          observations={stepObservations}
          isLoading={stepLoading}
          isError={stepError}
        />
      </TabsContent>
    </Tabs>
  )
}

// ---------------------------------------------------------------------------
// Top-level
// ---------------------------------------------------------------------------

export function StepDetailPanel({
  runId,
  stepNumber,
  open,
  onClose,
  runStatus,
}: StepDetailPanelProps) {
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-3 p-4 sm:max-w-3xl"
      >
        <SheetHeader>
          <SheetTitle>Step detail</SheetTitle>
          <SheetDescription>
            {stepNumber == null
              ? <SkeletonLine />
              : <span>Step #{stepNumber}</span>}
          </SheetDescription>
        </SheetHeader>
        {stepNumber != null && (
          <div className="min-h-0 flex-1">
            <StepContent
              runId={runId}
              stepNumber={stepNumber}
              runStatus={runStatus}
            />
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
