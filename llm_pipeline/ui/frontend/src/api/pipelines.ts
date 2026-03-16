/**
 * TanStack Query hooks for the Pipelines API.
 *
 * @remarks These hooks target /api/pipelines endpoints implemented by Task 24.
 * They will return 404 until that task is complete.
 *
 * @provisional - types and endpoint shapes may change when task 24 lands.
 * Tasks 37 (Live Execution) and 40 (Pipeline Structure) import from this file.
 */

import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys } from './query-keys'
import type { PipelineListItem, PipelineMetadata, StepPromptsResponse } from './types'

/**
 * Fetch all registered pipelines.
 *
 * Pipelines are static configuration data -- the default QueryClient
 * staleTime (30s) is sufficient since pipeline definitions rarely change
 * at runtime.
 *
 * @provisional - will 404 until backend task 24 is complete.
 */
export function usePipelines() {
  return useQuery({
    queryKey: queryKeys.pipelines.all,
    queryFn: () =>
      apiClient<{ pipelines: PipelineListItem[] }>('/pipelines'),
  })
}

/**
 * Fetch detailed metadata for a single pipeline by name.
 *
 * Disabled when `name` is falsy to support conditional fetching
 * (e.g. no pipeline selected yet).
 *
 * @param name - Pipeline name to look up
 * @provisional - will 404 until backend task 24 is complete.
 */
export function usePipeline(name: string | undefined) {
  return useQuery({
    queryKey: queryKeys.pipelines.detail(name ?? ''),
    queryFn: () =>
      apiClient<PipelineMetadata>('/pipelines/' + name),
    enabled: Boolean(name),
  })
}

/**
 * Fetch prompt/instruction content for a specific pipeline step.
 *
 * Pipeline definitions are static -- `staleTime: Infinity` prevents
 * refetching since prompt content does not change at runtime.
 * Disabled until both `pipelineName` and `stepName` are truthy
 * (values are unknown until parent queries resolve).
 *
 * @param pipelineName - Pipeline name
 * @param stepName - Step name within the pipeline
 */
export function useStepInstructions(pipelineName: string, stepName: string) {
  return useQuery({
    queryKey: queryKeys.pipelines.stepPrompts(pipelineName, stepName),
    queryFn: () =>
      apiClient<StepPromptsResponse>(
        '/pipelines/' + pipelineName + '/steps/' + stepName + '/prompts',
      ),
    enabled: Boolean(pipelineName && stepName),
    staleTime: Infinity,
  })
}
