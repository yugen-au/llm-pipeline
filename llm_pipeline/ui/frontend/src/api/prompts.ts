/**
 * TanStack Query hooks for the Prompts API.
 *
 * @remarks These hooks target /api/prompts endpoints implemented by Task 22.
 * They will return 404 until that task is complete.
 */

import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys } from './query-keys'
import { toSearchParams } from './types'
import type { PromptDetail, PromptListParams, PromptListResponse } from './types'

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
    queryFn: () => apiClient<PromptListResponse>('/prompts' + toSearchParams(filters)),
  })
}

/**
 * Fetch grouped prompt detail (all variants) for a single prompt key.
 *
 * Uses the default 30s staleTime -- prompt content is static reference data.
 * Disabled when `promptKey` is falsy so callers can pass an empty string
 * before a selection is made.
 *
 * @provisional - will 404 until backend task 22 lands.
 *
 * @param promptKey - The prompt_key to fetch (e.g. "rate_card_system")
 */
export function usePromptDetail(promptKey: string) {
  return useQuery({
    queryKey: queryKeys.prompts.detail(promptKey),
    queryFn: () => apiClient<PromptDetail>('/prompts/' + promptKey),
    enabled: Boolean(promptKey),
  })
}
