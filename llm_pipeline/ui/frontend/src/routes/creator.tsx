import { useState, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  useGenerateStep,
  useTestDraft,
  useAcceptDraft,
  useDrafts,
  useDraft,
  useRenameDraft,
} from '@/api/creator'
import { apiClient } from '@/api/client'
import type {
  GenerateRequest,
  TestResponse,
  AcceptResponse,
  DraftItem,
  DraftDetail,
} from '@/api/creator'
import { useEvents } from '@/api/events'
import { useWebSocket } from '@/api/websocket'
import { useWsStore } from '@/stores/websocket'
import { queryKeys } from '@/api/query-keys'
import type { EventItem } from '@/api/types'
import { ApiError } from '@/api/types'
import { CreatorInputColumn } from '@/components/creator/CreatorInputColumn'
import { CreatorEditor } from '@/components/creator/CreatorEditor'
import { CreatorResultsPanel } from '@/components/creator/CreatorResultsPanel'
import type { WorkflowState } from '@/components/creator/CreatorResultsPanel'

export const Route = createFileRoute('/creator')({
  component: CreatorPage,
})

// ---------------------------------------------------------------------------
// CreatorPage
// ---------------------------------------------------------------------------

function CreatorPage() {
  // -- Workflow state machine --
  const [workflowState, setWorkflowState] = useState<WorkflowState>('idle')

  // -- Form state --
  const [description, setDescription] = useState('')
  const [targetPipeline, setTargetPipeline] = useState<string | null>(null)
  const [includeExtraction, setIncludeExtraction] = useState(true)
  const [includeTransformation, setIncludeTransformation] = useState(false)

  // -- Draft/run state --
  const [activeDraftId, setActiveDraftId] = useState<number | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [generatedCode, setGeneratedCode] = useState<Record<string, string>>({})
  const [activeTab, setActiveTab] = useState('step')
  const [editableName, setEditableName] = useState<string | null>(null)
  const [renameError, setRenameError] = useState<string | null>(null)

  // -- Results state --
  const [testResults, setTestResults] = useState<TestResponse | null>(null)
  const [acceptResults, setAcceptResults] = useState<AcceptResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // -- Hooks --
  const queryClient = useQueryClient()
  const generateStep = useGenerateStep()
  const testDraft = useTestDraft(activeDraftId)
  const acceptDraft = useAcceptDraft(activeDraftId)
  const renameDraft = useRenameDraft()
  const { data: draftsData, isLoading: draftsLoading } = useDrafts()
  const { data: draftDetail, refetch: refetchDraft } = useDraft(activeDraftId)

  // -- WebSocket for generation progress --
  useWebSocket(activeRunId)
  const wsStatus = useWsStore((s) => s.status)

  // -- Events for active run --
  const { data: eventsData } = useEvents(activeRunId ?? '', {})
  const events = eventsData?.items ?? []

  // ---------------------------------------------------------------------------
  // stream_complete detection: transition from generating -> draft
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (workflowState !== 'generating') return
    if (events.length === 0) return

    // Check for stream_complete in the event list
    const hasStreamComplete = events.some(
      (e: EventItem) => e.event_type === 'stream_complete',
    )
    if (!hasStreamComplete) return

    // Generation finished -- fetch draft detail to populate editor
    if (activeDraftId != null) {
      refetchDraft().then(({ data }) => {
        if (data) {
          populateFromDraft(data)
          setWorkflowState('draft')
        }
      })
    }
  }, [workflowState, events, activeDraftId, refetchDraft])

  // ---------------------------------------------------------------------------
  // Populate editor state from a DraftDetail
  // ---------------------------------------------------------------------------
  const populateFromDraft = useCallback((draft: DraftDetail) => {
    setGeneratedCode(draft.generated_code ?? {})
    setEditableName(draft.name)
    setRenameError(null)
    if (draft.test_results) {
      setTestResults(draft.test_results as unknown as TestResponse)
    } else {
      setTestResults(null)
    }
    setAcceptResults(null)
    setErrorMessage(null)
  }, [])

  // ---------------------------------------------------------------------------
  // handleGenerate
  // ---------------------------------------------------------------------------
  const handleGenerate = useCallback(() => {
    const trimmed = description.trim()
    if (!trimmed || trimmed.length < 10) return

    const req: GenerateRequest = {
      description: trimmed,
      target_pipeline: targetPipeline,
      include_extraction: includeExtraction,
      include_transformation: includeTransformation,
    }

    generateStep.mutate(req, {
      onSuccess: (data) => {
        // Seed event cache before setting activeRunId
        queryClient.setQueryData(queryKeys.runs.events(data.run_id, {}), {
          items: [],
          total: 0,
          offset: 0,
          limit: 50,
        })
        setActiveRunId(data.run_id)
        // Parse draft ID from draft_name or use the response
        // The draft list will refresh via invalidation in the hook
        // We need the draft ID -- refetch drafts to find it
        queryClient
          .invalidateQueries({ queryKey: queryKeys.creator.drafts() })
          .then(() => {
            const drafts = queryClient.getQueryData<{
              items: DraftItem[]
            }>(queryKeys.creator.drafts())
            if (drafts?.items.length) {
              // Most recent draft is first (ordered by created_at desc)
              const newest = drafts.items[0]
              setActiveDraftId(newest.id)
            }
          })
        setWorkflowState('generating')
        setGeneratedCode({})
        setTestResults(null)
        setAcceptResults(null)
        setErrorMessage(null)
      },
      onError: (error) => {
        setWorkflowState('error')
        setErrorMessage(
          error instanceof ApiError ? error.detail : String(error),
        )
      },
    })
  }, [
    description,
    targetPipeline,
    includeExtraction,
    includeTransformation,
    generateStep,
    queryClient,
  ])

  // ---------------------------------------------------------------------------
  // handleTest
  // ---------------------------------------------------------------------------
  const handleTest = useCallback(() => {
    if (activeDraftId == null) return

    // Build code_overrides from current editor state
    const codeOverrides =
      Object.keys(generatedCode).length > 0 ? generatedCode : null

    setWorkflowState('testing')
    setErrorMessage(null)

    testDraft.mutate(
      { code_overrides: codeOverrides, sample_data: null },
      {
        onSuccess: (data) => {
          setTestResults(data)
          setWorkflowState('tested')
        },
        onError: (error) => {
          setWorkflowState('error')
          setErrorMessage(
            error instanceof ApiError ? error.detail : String(error),
          )
        },
      },
    )
  }, [activeDraftId, generatedCode, testDraft])

  // ---------------------------------------------------------------------------
  // handleAccept
  // ---------------------------------------------------------------------------
  const handleAccept = useCallback(() => {
    if (activeDraftId == null) return

    setWorkflowState('accepting')
    setErrorMessage(null)

    acceptDraft.mutate(
      { pipeline_file: targetPipeline },
      {
        onSuccess: (data) => {
          setAcceptResults(data)
          setWorkflowState('accepted')
        },
        onError: (error) => {
          setWorkflowState('error')
          setErrorMessage(
            error instanceof ApiError ? error.detail : String(error),
          )
        },
      },
    )
  }, [activeDraftId, targetPipeline, acceptDraft])

  // ---------------------------------------------------------------------------
  // handleCodeChange
  // ---------------------------------------------------------------------------
  const handleCodeChange = useCallback(
    (filename: string, value: string) => {
      setGeneratedCode((prev) => ({ ...prev, [filename]: value }))
    },
    [],
  )

  // ---------------------------------------------------------------------------
  // Draft resume (onSelect from DraftPicker)
  // ---------------------------------------------------------------------------
  const handleSelectDraft = useCallback(
    (draft: DraftItem) => {
      setActiveDraftId(draft.id)
      setActiveRunId(draft.run_id)
      setActiveTab('step')
      setRenameError(null)
      setErrorMessage(null)

      // Fetch full detail to populate editor
      queryClient
        .fetchQuery({
          queryKey: queryKeys.creator.draft(draft.id),
          queryFn: () =>
            apiClient<DraftDetail>(`/creator/drafts/${draft.id}`),
        })
        .then((detail) => {
          populateFromDraft(detail)

          // Set workflow state based on draft status
          switch (detail.status) {
            case 'accepted':
              setWorkflowState('accepted')
              break
            case 'tested':
              setWorkflowState('tested')
              break
            case 'draft':
            case 'error':
              setWorkflowState('draft')
              break
            default:
              setWorkflowState('draft')
          }
        })
        .catch(() => {
          setWorkflowState('error')
          setErrorMessage('Failed to load draft details')
        })
    },
    [queryClient, populateFromDraft],
  )

  // ---------------------------------------------------------------------------
  // New draft (reset)
  // ---------------------------------------------------------------------------
  const handleNewDraft = useCallback(() => {
    setWorkflowState('idle')
    setActiveDraftId(null)
    setActiveRunId(null)
    setGeneratedCode({})
    setActiveTab('step')
    setEditableName(null)
    setRenameError(null)
    setTestResults(null)
    setAcceptResults(null)
    setErrorMessage(null)
    setDescription('')
    setTargetPipeline(null)
    setIncludeExtraction(true)
    setIncludeTransformation(false)
  }, [])

  // ---------------------------------------------------------------------------
  // handleRename
  // ---------------------------------------------------------------------------
  const handleRename = useCallback(() => {
    if (activeDraftId == null || !editableName?.trim()) return

    setRenameError(null)
    renameDraft.mutate(
      { draftId: activeDraftId, name: editableName.trim() },
      {
        onError: (error) => {
          if (error instanceof ApiError && error.status === 409) {
            try {
              const body = JSON.parse(error.detail) as {
                detail: string
                suggested_name: string
              }
              setRenameError(
                `Name conflict. Suggested: ${body.suggested_name}`,
              )
            } catch {
              setRenameError('Name already taken')
            }
          } else {
            setRenameError(
              error instanceof ApiError ? error.detail : 'Rename failed',
            )
          }
        },
      },
    )
  }, [activeDraftId, editableName, renameDraft])

  // -- Form disabled when not idle --
  const formDisabled = workflowState !== 'idle' && workflowState !== 'draft'

  // -- Shared column content --

  const inputColumn = (
    <CreatorInputColumn
      drafts={draftsData?.items ?? []}
      draftsLoading={draftsLoading}
      selectedDraftId={activeDraftId}
      onSelectDraft={handleSelectDraft}
      onNewDraft={handleNewDraft}
      description={description}
      onDescriptionChange={setDescription}
      targetPipeline={targetPipeline}
      onTargetPipelineChange={setTargetPipeline}
      includeExtraction={includeExtraction}
      onIncludeExtractionChange={setIncludeExtraction}
      includeTransformation={includeTransformation}
      onIncludeTransformationChange={setIncludeTransformation}
      onGenerate={handleGenerate}
      isGenerating={generateStep.isPending}
      formDisabled={formDisabled}
    />
  )

  const editorColumn = (
    <Card className="flex h-full flex-col overflow-hidden p-4">
      {/* Editable name field (post-generation) */}
      {editableName != null && (
        <div className="mb-2 shrink-0 space-y-1">
          <Input
            value={editableName}
            onChange={(e) => {
              setEditableName(e.target.value)
              setRenameError(null)
            }}
            onBlur={handleRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRename()
            }}
            className="font-mono text-sm"
            placeholder="Step name"
            aria-label="Draft name"
            aria-invalid={!!renameError || undefined}
          />
          {renameError && (
            <p className="text-[11px] text-destructive">{renameError}</p>
          )}
        </div>
      )}
      <CreatorEditor
        generatedCode={generatedCode}
        draftName={editableName}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onCodeChange={handleCodeChange}
        onTest={handleTest}
        onAccept={handleAccept}
        workflowState={workflowState}
        hasExtraction={includeExtraction}
      />
    </Card>
  )

  const resultsColumn = (
    <CreatorResultsPanel
      workflowState={workflowState}
      activeRunId={activeRunId}
      testResults={testResults}
      acceptResults={acceptResults}
      wsStatus={wsStatus}
      events={events}
      errorMessage={errorMessage}
    />
  )

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-card-foreground">
          Step Creator
        </h1>
        <p className="text-sm text-muted-foreground">
          Generate pipeline steps from natural language descriptions
        </p>
      </div>

      {/* Desktop layout (lg+): 3-column grid */}
      <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-[280px_1fr_350px] lg:gap-4">
        {/* Col 1: DraftPicker + CreatorInputForm */}
        <div className="overflow-auto">{inputColumn}</div>

        {/* Col 2: CreatorEditor */}
        <div className="overflow-hidden">{editorColumn}</div>

        {/* Col 3: CreatorResultsPanel */}
        <div className="overflow-hidden">{resultsColumn}</div>
      </div>

      {/* Mobile/tablet layout (below lg): tab-based */}
      <div className="flex min-h-0 flex-1 flex-col lg:hidden">
        <Tabs defaultValue="input" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="shrink-0">
            <TabsTrigger value="input">Input</TabsTrigger>
            <TabsTrigger value="editor">Editor</TabsTrigger>
            <TabsTrigger value="results">Results</TabsTrigger>
          </TabsList>

          <TabsContent
            value="input"
            className="min-h-0 flex-1 overflow-auto"
          >
            {inputColumn}
          </TabsContent>
          <TabsContent
            value="editor"
            className="min-h-0 flex-1 overflow-hidden"
          >
            {editorColumn}
          </TabsContent>
          <TabsContent
            value="results"
            className="min-h-0 flex-1 overflow-hidden"
          >
            {resultsColumn}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
