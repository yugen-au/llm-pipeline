import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import type {
  AvailableStep,
  CompileRequest,
  CompileResponse,
  EditorStrategy,
} from '@/api/editor'
import {
  useAvailableSteps,
  useCompilePipeline,
  useCreateDraftPipeline,
  useUpdateDraftPipeline,
  useDraftPipelines,
  useDraftPipeline,
} from '@/api/editor'
import {
  EditorPalettePanel,
  EditorStrategyCanvas,
  EditorPropertiesPanel,
  buildEditorDragEnd,
} from '@/components/editor'

export const Route = createFileRoute('/editor')({
  component: EditorPage,
})

// ---------------------------------------------------------------------------
// Editor-local types
// ---------------------------------------------------------------------------

/** UI step item -- id is a UUID for DnD key, distinct from step_ref */
export interface EditorStepItem {
  id: string
  step_ref: string
  source: 'draft' | 'registered'
}

export interface EditorStrategyState {
  strategy_name: string
  steps: EditorStepItem[]
}

type CompileStatus = 'idle' | 'pending' | 'error'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert editor state to CompileRequest with position numbering */
function buildCompileRequest(
  strategies: EditorStrategyState[],
): CompileRequest {
  return {
    strategies: strategies.map(
      (s): EditorStrategy => ({
        strategy_name: s.strategy_name,
        steps: s.steps.map((step, i) => ({
          step_ref: step.step_ref,
          source: step.source,
          position: i,
        })),
      }),
    ),
  }
}

/** Serialize editor state to DraftPipeline structure JSON */
function buildDraftStructure(
  strategies: EditorStrategyState[],
): Record<string, unknown> {
  return {
    schema_version: 1,
    strategies: strategies.map((s) => ({
      strategy_name: s.strategy_name,
      steps: s.steps.map((step, i) => ({
        step_ref: step.step_ref,
        source: step.source,
        position: i,
      })),
    })),
  }
}

// ---------------------------------------------------------------------------
// EditorPage
// ---------------------------------------------------------------------------

function EditorPage() {
  // -- Editor state --
  const [strategies, setStrategies] = useState<EditorStrategyState[]>([])
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [activeDraftPipelineId, setActiveDraftPipelineId] = useState<
    number | null
  >(null)
  const [draftPipelineName, setDraftPipelineName] = useState('')
  const [compileResult, setCompileResult] = useState<CompileResponse | null>(
    null,
  )
  const [compileStatus, setCompileStatus] = useState<CompileStatus>('idle')
  // Track which draft ID to load (triggers useDraftPipeline fetch)
  const [loadingDraftId, setLoadingDraftId] = useState<number | null>(null)

  // -- API hooks --
  const { data: availableStepsData } = useAvailableSteps()
  const availableSteps = availableStepsData?.steps ?? []
  const compileMutation = useCompilePipeline()
  const createDraftMutation = useCreateDraftPipeline()
  const updateDraftMutation = useUpdateDraftPipeline()
  const { data: draftsData } = useDraftPipelines()
  const draftPipelines = draftsData?.items ?? []
  const { data: loadedDraftDetail } = useDraftPipeline(loadingDraftId)

  // -- Load draft detail when fetched --
  useEffect(() => {
    if (!loadedDraftDetail || loadingDraftId == null) return
    // Populate editor state from draft structure
    const structure = loadedDraftDetail.structure as {
      schema_version?: number
      strategies?: Array<{
        strategy_name: string
        steps: Array<{
          step_ref: string
          source: 'draft' | 'registered'
          position: number
        }>
      }>
    }
    if (structure?.strategies) {
      setStrategies(
        structure.strategies.map((s) => ({
          strategy_name: s.strategy_name,
          steps: s.steps
            .sort((a, b) => a.position - b.position)
            .map((step) => ({
              id: crypto.randomUUID(),
              step_ref: step.step_ref,
              source: step.source,
            })),
        })),
      )
    } else {
      setStrategies([])
    }
    setDraftPipelineName(loadedDraftDetail.name)
    setActiveDraftPipelineId(loadedDraftDetail.id)
    setSelectedStepId(null)
    setCompileResult(null)
    setCompileStatus('idle')
    setLoadingDraftId(null)
  }, [loadedDraftDetail, loadingDraftId])

  // -- Auto-compile with debounce + AbortController --
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    // Skip compile when no strategies or all strategies empty
    const hasSteps = strategies.some((s) => s.steps.length > 0)
    if (!hasSteps) {
      setCompileResult(null)
      setCompileStatus('idle')
      return
    }

    // Cancel any in-flight compile
    abortRef.current?.abort()
    setCompileStatus('idle')

    const timer = setTimeout(async () => {
      const ac = new AbortController()
      abortRef.current = ac
      setCompileStatus('pending')
      try {
        const result = await compileMutation.mutateAsync(
          buildCompileRequest(strategies),
          // TanStack Query v5 doesn't pass signal through mutateAsync options,
          // but we use ac.signal.aborted check to discard stale results
        )
        if (ac.signal.aborted) return
        setCompileResult(result)
        setCompileStatus(result.valid ? 'idle' : 'error')
      } catch {
        if (!ac.signal.aborted) setCompileStatus('error')
      }
    }, 300)

    return () => {
      clearTimeout(timer)
      abortRef.current?.abort()
    }
    // compileMutation is stable (useMutation returns stable ref)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategies])

  // -- DnD sensors --
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  // -- DnD drag-end handler (stable: no closed-over strategies) --
  const handleDragEnd = useMemo(
    () => buildEditorDragEnd(setStrategies),
    [],
  )

  // Compile errors from latest result
  const compileErrors = compileResult?.errors ?? []

  // -- Handlers --

  /** Add step from palette to strategy */
  const handleAddStepToStrategy = useCallback(
    (strategyName: string, step: AvailableStep) => {
      setStrategies((prev) =>
        prev.map((s) =>
          s.strategy_name === strategyName
            ? {
                ...s,
                steps: [
                  ...s.steps,
                  {
                    id: crypto.randomUUID(),
                    step_ref: step.step_ref,
                    source: step.source,
                  },
                ],
              }
            : s,
        ),
      )
    },
    [],
  )

  /** Save: create new draft or update existing */
  const handleSave = useCallback(async () => {
    const structure = buildDraftStructure(strategies)
    if (activeDraftPipelineId) {
      const result = await updateDraftMutation.mutateAsync({
        id: activeDraftPipelineId,
        name: draftPipelineName,
        structure,
      })
      setActiveDraftPipelineId(result.id)
    } else {
      const result = await createDraftMutation.mutateAsync({
        name: draftPipelineName,
        structure,
      })
      setActiveDraftPipelineId(result.id)
    }
  }, [
    strategies,
    activeDraftPipelineId,
    draftPipelineName,
    updateDraftMutation,
    createDraftMutation,
  ])

  /** Load a draft pipeline into editor state */
  const handleLoadDraft = useCallback((id: number) => {
    setLoadingDraftId(id)
  }, [])

  /** Reset to empty editor state */
  const handleNewPipeline = useCallback(() => {
    setStrategies([])
    setSelectedStepId(null)
    setActiveDraftPipelineId(null)
    setDraftPipelineName('')
    setCompileResult(null)
    setCompileStatus('idle')
  }, [])

  /** Fork a registered pipeline into editor state (Step 7) */
  const handleForkPipeline = useCallback(
    (forkedStrategies: EditorStrategyState[], name: string) => {
      setStrategies(forkedStrategies)
      setDraftPipelineName(name)
      setActiveDraftPipelineId(null)
      setSelectedStepId(null)
      setCompileResult(null)
      setCompileStatus('idle')
    },
    [],
  )

  // -- Resolve selected step object from ID --
  const selectedStep = useMemo(() => {
    if (!selectedStepId) return null
    for (const s of strategies) {
      const found = s.steps.find((st) => st.id === selectedStepId)
      if (found) return found
    }
    return null
  }, [selectedStepId, strategies])

  // -- Shared column content --

  const strategyNames = strategies.map((s) => s.strategy_name)

  const paletteColumn = (
    <EditorPalettePanel
      onAddStepToStrategy={handleAddStepToStrategy}
      strategyNames={strategyNames}
    />
  )

  const canvasColumn = (
    <EditorStrategyCanvas
      strategies={strategies}
      onStrategiesChange={setStrategies}
      selectedStepId={selectedStepId}
      onSelectStep={setSelectedStepId}
      compileErrors={compileErrors}
    />
  )

  const isSaving =
    createDraftMutation.isPending || updateDraftMutation.isPending

  const propertiesColumn = (
    <EditorPropertiesPanel
      selectedStep={selectedStep}
      availableSteps={availableSteps}
      compileResult={compileResult}
      compileStatus={compileStatus}
      draftPipelineId={activeDraftPipelineId}
      draftPipelineName={draftPipelineName}
      onNameChange={setDraftPipelineName}
      onSave={handleSave}
      isSaving={isSaving}
      draftPipelines={draftPipelines}
      onLoadDraft={handleLoadDraft}
      onNewPipeline={handleNewPipeline}
      onForkPipeline={handleForkPipeline}
    />
  )

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-card-foreground">
          Pipeline Editor
        </h1>
        <p className="text-sm text-muted-foreground">
          Assemble and validate pipeline strategies from available steps
        </p>
      </div>

      {/* DndContext wraps both palette (useDraggable) and canvas
          (useSortable + useDroppable) so they share the same context */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        {/* Desktop layout (lg+): 3-column grid */}
        <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-[280px_1fr_350px] lg:gap-4">
          {/* Col 1: Step Palette */}
          <div className="overflow-auto">{paletteColumn}</div>

          {/* Col 2: Strategy Canvas */}
          <div className="overflow-hidden">{canvasColumn}</div>

          {/* Col 3: Properties Panel */}
          <div className="overflow-hidden">{propertiesColumn}</div>
        </div>

        {/* Mobile/tablet layout (below lg): tab-based */}
        <div className="flex min-h-0 flex-1 flex-col lg:hidden">
          <Tabs
            defaultValue="palette"
            className="flex min-h-0 flex-1 flex-col"
          >
            <TabsList className="shrink-0">
              <TabsTrigger value="palette">Palette</TabsTrigger>
              <TabsTrigger value="editor">Editor</TabsTrigger>
              <TabsTrigger value="properties">Properties</TabsTrigger>
            </TabsList>

            <TabsContent
              value="palette"
              className="min-h-0 flex-1 overflow-auto"
            >
              {paletteColumn}
            </TabsContent>
            <TabsContent
              value="editor"
              className="min-h-0 flex-1 overflow-hidden"
            >
              {canvasColumn}
            </TabsContent>
            <TabsContent
              value="properties"
              className="min-h-0 flex-1 overflow-hidden"
            >
              {propertiesColumn}
            </TabsContent>
          </Tabs>
        </div>
      </DndContext>
    </div>
  )
}
