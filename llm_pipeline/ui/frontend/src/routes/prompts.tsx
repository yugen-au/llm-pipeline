import { useCallback, useMemo, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { useQueries } from '@tanstack/react-query'
import { z } from 'zod'
import { usePrompts } from '@/api/prompts'
import { usePipelines } from '@/api/pipelines'
import { apiClient } from '@/api/client'
import { queryKeys } from '@/api/query-keys'
import type { PipelineMetadata } from '@/api/types'
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

  // Data fetching
  const prompts = usePrompts({ limit: 200 })
  const pipelines = usePipelines()

  // Filter state
  const [selectedType, setSelectedType] = useState('')
  const [selectedPipeline, setSelectedPipeline] = useState('')
  const [searchText, setSearchText] = useState('')

  // Derive pipeline names for filter dropdown
  const pipelineNames = useMemo(
    () => pipelines.data?.pipelines.map((p) => p.name) ?? [],
    [pipelines.data],
  )

  // Build prompt_key -> pipeline_name[] map via combine (structurally shared)
  const combinePipelineMeta = useCallback(
    (results: { data: PipelineMetadata | undefined }[]) => {
      const map = new Map<string, string[]>()
      results.forEach((q, idx) => {
        if (!q.data) return
        const pipelineName = pipelineNames[idx]
        for (const strategy of q.data.strategies) {
          for (const step of strategy.steps) {
            for (const promptKey of [step.system_key, step.user_key]) {
              if (!promptKey) continue
              const existing = map.get(promptKey)
              if (existing) {
                if (!existing.includes(pipelineName)) {
                  existing.push(pipelineName)
                }
              } else {
                map.set(promptKey, [pipelineName])
              }
            }
          }
        }
      })
      return map
    },
    [pipelineNames],
  )

  const promptKeyToPipelines = useQueries({
    queries: pipelineNames.map((name) => ({
      queryKey: queryKeys.pipelines.detail(name),
      queryFn: () => apiClient<PipelineMetadata>('/pipelines/' + name),
      staleTime: Infinity,
    })),
    combine: combinePipelineMeta,
  })

  // Derive unique prompt types for filter dropdown
  const promptTypes = useMemo(
    () => [...new Set(prompts.data?.items.map((p) => p.prompt_type) ?? [])],
    [prompts.data],
  )

  // Filter and deduplicate prompts
  const filteredPrompts = useMemo(() => {
    const items = prompts.data?.items ?? []
    const lowerSearch = searchText.toLowerCase()

    const filtered = items.filter((p) => {
      // Type filter
      if (selectedType && p.prompt_type !== selectedType) return false

      // Pipeline filter
      if (selectedPipeline) {
        const pipelinesForKey = promptKeyToPipelines.get(p.prompt_key)
        if (!pipelinesForKey || !pipelinesForKey.includes(selectedPipeline)) return false
      }

      // Text search (case-insensitive on prompt_name and prompt_key)
      if (lowerSearch) {
        const matchesName = p.prompt_name.toLowerCase().includes(lowerSearch)
        const matchesKey = p.prompt_key.toLowerCase().includes(lowerSearch)
        if (!matchesName && !matchesKey) return false
      }

      return true
    })

    // Deduplicate by prompt_key (one row per unique key for the list)
    const seen = new Map<string, (typeof filtered)[0]>()
    for (const p of filtered) {
      if (!seen.has(p.prompt_key)) {
        seen.set(p.prompt_key, p)
      }
    }
    return [...seen.values()]
  }, [prompts.data, selectedType, selectedPipeline, searchText, promptKeyToPipelines])

  // Selection handler -- update URL search param
  function handleSelect(promptKey: string) {
    navigate({ search: { key: promptKey } })
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <h1 className="text-2xl font-semibold text-card-foreground">Prompts</h1>

      <div className="flex min-h-0 flex-1 gap-4">
        {/* Left panel: filter bar + prompt list */}
        <div className="flex w-80 shrink-0 flex-col overflow-hidden rounded-xl border">
          <PromptFilterBar
            promptTypes={promptTypes}
            pipelineNames={pipelineNames}
            selectedType={selectedType}
            selectedPipeline={selectedPipeline}
            onTypeChange={setSelectedType}
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

        {/* Right panel: prompt detail viewer */}
        <div className="flex-1 overflow-auto rounded-xl border">
          <PromptViewer promptKey={key || null} />
        </div>
      </div>
    </div>
  )
}
