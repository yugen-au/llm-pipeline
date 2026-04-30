import { useCallback, useMemo, useState } from 'react'
import { Plus } from 'lucide-react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { useQueries } from '@tanstack/react-query'
import { z } from 'zod'
import { usePrompts } from '@/api/prompts'
import { usePipelines } from '@/api/pipelines'
import { apiClient } from '@/api/client'
import { queryKeys } from '@/api/query-keys'
import type { PipelineMetadata } from '@/api/types'
import { Button } from '@/components/ui/button'
import { PromptFilterBar } from '@/components/prompts/PromptFilterBar'
import { PromptList } from '@/components/prompts/PromptList'
import { PromptViewer } from '@/components/prompts/PromptViewer'

// ---------------------------------------------------------------------------
// Search params schema
// ---------------------------------------------------------------------------

const promptsSearchSchema = z.object({
  key: fallback(z.string(), '').default(''),
})

export const Route = createFileRoute('/prompts')({
  validateSearch: zodValidator(promptsSearchSchema),
  component: PromptsPage,
})

// ---------------------------------------------------------------------------
// PromptsPage
// ---------------------------------------------------------------------------

function PromptsPage() {
  const { key } = Route.useSearch()
  const navigate = useNavigate({ from: '/prompts' })
  const [isCreating, setIsCreating] = useState(false)

  const prompts = usePrompts({ limit: 200 })
  const pipelines = usePipelines()

  const [selectedPipeline, setSelectedPipeline] = useState('')
  const [searchText, setSearchText] = useState('')

  const pipelineNames = useMemo(
    () => pipelines.data?.pipelines.map((p) => p.name) ?? [],
    [pipelines.data],
  )

  // Build prompt name -> pipeline_name[] map via combine (structurally shared).
  const combinePipelineMeta = useCallback(
    (results: { data: PipelineMetadata | undefined }[]) => {
      const map = new Map<string, string[]>()
      results.forEach((q, idx) => {
        if (!q.data) return
        const pipelineName = pipelineNames[idx]
        for (const strategy of q.data.strategies) {
          for (const step of strategy.steps) {
            if (!step.prompt_name) continue
            const existing = map.get(step.prompt_name)
            if (existing) {
              if (!existing.includes(pipelineName)) {
                existing.push(pipelineName)
              }
            } else {
              map.set(step.prompt_name, [pipelineName])
            }
          }
        }
      })
      return map
    },
    [pipelineNames],
  )

  const promptNameToPipelines = useQueries({
    queries: pipelineNames.map((name) => ({
      queryKey: queryKeys.pipelines.detail(name),
      queryFn: () => apiClient<PipelineMetadata>('/pipelines/' + name),
      staleTime: Infinity,
    })),
    combine: combinePipelineMeta,
  })

  const filteredPrompts = useMemo(() => {
    const items = prompts.data?.items ?? []
    const lowerSearch = searchText.toLowerCase()

    return items.filter((p) => {
      if (selectedPipeline) {
        const pipelinesForName = promptNameToPipelines.get(p.name)
        if (!pipelinesForName || !pipelinesForName.includes(selectedPipeline)) return false
      }
      if (lowerSearch) {
        const label = p.metadata.display_name ?? p.name
        const matchesLabel = label.toLowerCase().includes(lowerSearch)
        const matchesName = p.name.toLowerCase().includes(lowerSearch)
        if (!matchesLabel && !matchesName) return false
      }
      return true
    })
  }, [prompts.data, selectedPipeline, searchText, promptNameToPipelines])

  function handleSelect(promptName: string) {
    setIsCreating(false)
    navigate({ search: { key: promptName } })
  }

  function handleNewPrompt() {
    setIsCreating(true)
    navigate({ search: { key: '' } })
  }

  function handleCreated(newName: string) {
    setIsCreating(false)
    navigate({ search: { key: newName } })
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold text-card-foreground">Prompts</h1>
        <Button size="sm" variant="outline" onClick={handleNewPrompt}>
          <Plus className="size-4" />
          New Prompt
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        <div className="flex w-80 shrink-0 flex-col overflow-hidden rounded-xl border">
          <PromptFilterBar
            pipelineNames={pipelineNames}
            selectedPipeline={selectedPipeline}
            onPipelineChange={setSelectedPipeline}
            searchText={searchText}
            onSearchChange={setSearchText}
          />
          <PromptList
            prompts={filteredPrompts}
            selectedKey={key}
            onSelect={handleSelect}
            isLoading={prompts.isLoading}
            error={prompts.error}
          />
        </div>

        <div className="flex-1 overflow-auto rounded-xl border">
          <PromptViewer
            promptKey={key || null}
            isCreating={isCreating}
            onCreated={handleCreated}
          />
        </div>
      </div>
    </div>
  )
}
