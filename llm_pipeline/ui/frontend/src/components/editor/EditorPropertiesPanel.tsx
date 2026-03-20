/**
 * EditorPropertiesPanel -- right panel of the 3-panel editor layout.
 *
 * When no step is selected: shows pipeline-level info (name input, save
 * button, compile status badge, load/new pipeline controls).
 * When a step is selected: shows step_ref, source, and compile errors for
 * that step.
 *
 * Includes "Fork pipeline" section (Step 7) to load a registered pipeline
 * into the editor for modification.
 */

import { useState, useCallback } from 'react'
import { Loader2, CheckCircle2, AlertCircle, Save, FilePlus, FolderOpen, GitFork } from 'lucide-react'

import { usePipelines, usePipeline } from '@/api/pipelines'
import type { PipelineMetadata } from '@/api/types'
import type { AvailableStep, CompileResponse, CompileError, DraftPipelineItem } from '@/api/editor'
import type { EditorStepItem, EditorStrategyState } from '@/routes/editor'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// ---------------------------------------------------------------------------
// Conversion: PipelineMetadata -> EditorStrategyState[]
// ---------------------------------------------------------------------------

/**
 * Convert a registered PipelineMetadata into editor state.
 *
 * Each strategy's steps get fresh UUIDs (for DnD keys) and source='registered'.
 */
export function pipelineMetadataToEditorState(
  meta: PipelineMetadata,
): EditorStrategyState[] {
  return meta.strategies.map((s) => ({
    strategy_name: s.name,
    steps: s.steps.map((step) => ({
      id: crypto.randomUUID(),
      step_ref: step.step_name,
      source: 'registered' as const,
    })),
  }))
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EditorPropertiesPanelProps {
  selectedStep: EditorStepItem | null
  availableSteps: AvailableStep[]
  compileResult: CompileResponse | null
  compileStatus: 'idle' | 'pending' | 'error'
  draftPipelineId: number | null
  draftPipelineName: string
  onNameChange: (name: string) => void
  onSave: () => void
  isSaving: boolean
  /** Draft pipelines list for "Load Draft" selector */
  draftPipelines: DraftPipelineItem[]
  onLoadDraft: (id: number) => void
  onNewPipeline: () => void
  /** Callback when a registered pipeline is forked into editor state */
  onForkPipeline: (strategies: EditorStrategyState[], name: string) => void
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Compile status badge with spinner/check/error states */
function CompileStatusBadge({
  status,
  compileResult,
}: {
  status: 'idle' | 'pending' | 'error'
  compileResult: CompileResponse | null
}) {
  if (status === 'pending') {
    return (
      <Badge variant="secondary" className="gap-1">
        <Loader2 className="size-3 animate-spin" />
        Validating...
      </Badge>
    )
  }

  if (status === 'error' || (compileResult && !compileResult.valid)) {
    const count = compileResult?.errors.length ?? 0
    return (
      <Badge variant="destructive" className="gap-1">
        <AlertCircle className="size-3" />
        {count} error{count !== 1 ? 's' : ''}
      </Badge>
    )
  }

  if (compileResult?.valid) {
    return (
      <Badge
        variant="secondary"
        className="gap-1 border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-400"
      >
        <CheckCircle2 className="size-3" />
        Valid
      </Badge>
    )
  }

  // idle, no result yet
  return (
    <Badge variant="outline" className="text-muted-foreground">
      Not validated
    </Badge>
  )
}

/** Error list shown when compile result has errors */
function CompileErrorList({ errors }: { errors: CompileError[] }) {
  if (errors.length === 0) return null

  return (
    <div className="flex flex-col gap-1.5">
      <h3 className="text-xs font-medium text-destructive">
        Compile Errors
      </h3>
      <ScrollArea className="max-h-[200px]" thin>
        <div className="flex flex-col gap-1">
          {errors.map((err, i) => (
            <div
              key={`${err.strategy_name}-${err.step_ref}-${i}`}
              className="rounded border border-destructive/20 bg-destructive/5 px-2 py-1.5 text-xs"
            >
              <span className="font-mono font-medium text-destructive">
                {err.strategy_name}/{err.step_ref}
              </span>
              <p className="mt-0.5 text-muted-foreground">{err.message}</p>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Fork Pipeline Section (Step 7)
// ---------------------------------------------------------------------------

/** Select a registered pipeline and fork it into the editor */
function ForkPipelineSection({
  onForkPipeline,
}: {
  onForkPipeline: EditorPropertiesPanelProps['onForkPipeline']
}) {
  const [selectedPipeline, setSelectedPipeline] = useState<string>('')
  const { data: pipelinesData, isPending: pipelinesLoading } = usePipelines()
  const { data: pipelineMeta, isFetching: metaFetching } = usePipeline(
    selectedPipeline || undefined,
  )

  const pipelines = pipelinesData?.pipelines ?? []

  const handleFork = useCallback(() => {
    if (!pipelineMeta) return
    const strategies = pipelineMetadataToEditorState(pipelineMeta)
    const name = `forked_from_${pipelineMeta.pipeline_name}`
    onForkPipeline(strategies, name)
    setSelectedPipeline('')
  }, [pipelineMeta, onForkPipeline])

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-medium text-muted-foreground">
        <GitFork className="mr-1 inline size-3.5" />
        Fork Registered Pipeline
      </h3>

      <Select value={selectedPipeline} onValueChange={setSelectedPipeline}>
        <SelectTrigger size="sm" className="w-full">
          <SelectValue placeholder="Select pipeline..." />
        </SelectTrigger>
        <SelectContent>
          {pipelinesLoading ? (
            <SelectItem value="__loading" disabled>
              Loading...
            </SelectItem>
          ) : pipelines.length === 0 ? (
            <SelectItem value="__empty" disabled>
              No registered pipelines
            </SelectItem>
          ) : (
            pipelines.map((p) => (
              <SelectItem key={p.name} value={p.name}>
                {p.name}
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>

      <Button
        variant="outline"
        size="sm"
        className="w-full gap-1.5"
        disabled={!selectedPipeline || metaFetching || !pipelineMeta}
        onClick={handleFork}
      >
        {metaFetching ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <GitFork className="size-3.5" />
        )}
        Fork into editor
      </Button>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Step Detail
// ---------------------------------------------------------------------------

/** Step detail view shown when a step is selected */
function StepDetailView({
  step,
  availableSteps,
  compileResult,
}: {
  step: EditorStepItem
  availableSteps: AvailableStep[]
  compileResult: CompileResponse | null
}) {
  const meta = availableSteps.find((s) => s.step_ref === step.step_ref)
  const stepErrors =
    compileResult?.errors.filter((e) => e.step_ref === step.step_ref) ?? []

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-xs font-medium text-muted-foreground">
        Step Details
      </h3>

      {/* step_ref */}
      <div>
        <Label className="text-xs text-muted-foreground">Step Ref</Label>
        <p className="mt-0.5 font-mono text-sm font-medium">{step.step_ref}</p>
      </div>

      {/* source */}
      <div>
        <Label className="text-xs text-muted-foreground">Source</Label>
        <div className="mt-0.5">
          <Badge
            variant={step.source === 'registered' ? 'secondary' : 'outline'}
          >
            {step.source}
          </Badge>
        </div>
      </div>

      {/* pipeline_names for registered steps */}
      {meta?.pipeline_names && meta.pipeline_names.length > 0 && (
        <div>
          <Label className="text-xs text-muted-foreground">Used In</Label>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {meta.pipeline_names.map((name) => (
              <Badge key={name} variant="outline" className="text-xs">
                {name}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* status for draft steps */}
      {meta?.status && (
        <div>
          <Label className="text-xs text-muted-foreground">Status</Label>
          <p className="mt-0.5 text-sm">{meta.status}</p>
        </div>
      )}

      {/* compile errors for this step */}
      {stepErrors.length > 0 && (
        <>
          <Separator />
          <CompileErrorList errors={stepErrors} />
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function EditorPropertiesPanel({
  selectedStep,
  availableSteps,
  compileResult,
  compileStatus,
  draftPipelineId,
  draftPipelineName,
  onNameChange,
  onSave,
  isSaving,
  draftPipelines,
  onLoadDraft,
  onNewPipeline,
  onForkPipeline,
}: EditorPropertiesPanelProps) {
  return (
    <Card className="flex h-full flex-col overflow-hidden p-4 gap-3">
      <h2 className="text-xs font-medium text-muted-foreground">
        Properties
      </h2>

      <ScrollArea className="min-h-0 flex-1" thin>
        <div className="flex flex-col gap-4 pr-1">
          {/* Pipeline-level controls (always visible) */}
          <section className="flex flex-col gap-3">
            {/* Pipeline name */}
            <div>
              <Label htmlFor="pipeline-name" className="text-xs text-muted-foreground">
                Pipeline Name
              </Label>
              <Input
                id="pipeline-name"
                value={draftPipelineName}
                onChange={(e) => onNameChange(e.target.value)}
                placeholder="my-pipeline"
                className="mt-1 h-8 text-sm"
              />
            </div>

            {/* Compile status */}
            <div>
              <Label className="text-xs text-muted-foreground">
                Compile Status
              </Label>
              <div className="mt-1">
                <CompileStatusBadge
                  status={compileStatus}
                  compileResult={compileResult}
                />
              </div>
            </div>

            {/* Save button */}
            <Button
              size="sm"
              className="w-full gap-1.5"
              onClick={onSave}
              disabled={isSaving || !draftPipelineName.trim()}
            >
              {isSaving ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Save className="size-3.5" />
              )}
              {draftPipelineId ? 'Update Draft' : 'Save as Draft'}
            </Button>

            {/* Draft ID indicator */}
            {draftPipelineId && (
              <p className="text-[11px] text-muted-foreground">
                Draft #{draftPipelineId}
              </p>
            )}
          </section>

          <Separator />

          {/* New Pipeline / Load Draft */}
          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-medium text-muted-foreground">
              Pipeline Actions
            </h3>

            <Button
              variant="outline"
              size="sm"
              className="w-full gap-1.5"
              onClick={onNewPipeline}
            >
              <FilePlus className="size-3.5" />
              New Pipeline
            </Button>

            {/* Load Draft selector */}
            {draftPipelines.length > 0 && (
              <div>
                <Label className="text-xs text-muted-foreground">
                  Load Draft
                </Label>
                <Select
                  onValueChange={(val) => onLoadDraft(Number(val))}
                  value={draftPipelineId != null ? String(draftPipelineId) : undefined}
                >
                  <SelectTrigger size="sm" className="mt-1 w-full">
                    <FolderOpen className="size-3.5 text-muted-foreground" />
                    <SelectValue placeholder="Select draft..." />
                  </SelectTrigger>
                  <SelectContent>
                    {draftPipelines.map((draft) => (
                      <SelectItem key={draft.id} value={String(draft.id)}>
                        {draft.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </section>

          <Separator />

          {/* Fork registered pipeline (Step 7) */}
          <ForkPipelineSection onForkPipeline={onForkPipeline} />

          {/* Global compile errors (when no step selected) */}
          {!selectedStep && compileResult && !compileResult.valid && (
            <>
              <Separator />
              <CompileErrorList errors={compileResult.errors} />
            </>
          )}

          {/* Step detail (when step selected) */}
          {selectedStep && (
            <>
              <Separator />
              <StepDetailView
                step={selectedStep}
                availableSteps={availableSteps}
                compileResult={compileResult}
              />
            </>
          )}
        </div>
      </ScrollArea>
    </Card>
  )
}
