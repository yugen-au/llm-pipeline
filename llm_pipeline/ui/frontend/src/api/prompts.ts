/**
 * TanStack Query hooks for the Prompts API.
 *
 * @remarks These hooks target /api/prompts endpoints implemented by Task 22.
 * They will return 404 until that task is complete.
 */

import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys } from './query-keys'
import type { PromptListParams, PromptListResponse } from './types'

/**
 * Build URLSearchParams from filter object, omitting undefined/null values.
 */
function buildPromptParams(filters: Partial<PromptListParams>): string {
  const params = new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v != null)
      .map(([k, v]) => [k, String(v)])
  )
  const str = params.toString()
  return str ? '?' + str : ''
}

/**
 * Fetch a paginated list of prompts with optional filtering.
 *
 * Prompts are static reference data so the default 30s staleTime
 * from the global QueryClient config is sufficient -- no per-hook
 * override or polling needed.
 *
 * @provisional - will 404 until backend task 22 lands.
 *
 * @param filters - Optional prompt_type, category, step_name,
 *   is_active, offset, limit filters
 */
export function usePrompts(filters: Partial<PromptListParams> = {}) {
  return useQuery({
    queryKey: queryKeys.prompts.list(filters),
    queryFn: () =>
      apiClient<PromptListResponse>(
        '/prompts' + buildPromptParams(filters)
      ),
  })
}
