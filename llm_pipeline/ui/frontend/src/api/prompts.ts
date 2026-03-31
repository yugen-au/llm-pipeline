/**
 * TanStack Query hooks for the Prompts API.
 *
 * @remarks These hooks target /api/prompts endpoints implemented by Task 22.
 * They will return 404 until that task is complete.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from './client'
import { queryKeys } from './query-keys'
import { toSearchParams } from './types'
import type { PromptDetail, PromptListParams, PromptListResponse, PromptVariant } from './types'

/** Request body for POST /api/prompts */
export interface PromptCreateRequest {
  prompt_key: string
  prompt_name: string
  prompt_type: string
  content: string
  category?: string | null
  step_name?: string | null
  description?: string | null
  version?: string
  created_by?: string | null
  variable_definitions?: Record<string, { type: string; description: string; auto_generate?: string }> | null
}

/** Request body for PUT /api/prompts/{key}/{type} */
export interface PromptUpdateRequest {
  prompt_name?: string | null
  content?: string | null
  category?: string | null
  step_name?: string | null
  description?: string | null
  version?: string | null
  created_by?: string | null
  variable_definitions?: Record<string, { type: string; description: string; auto_generate?: string }> | null
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

/** Create a new prompt. */
export function useCreatePrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: PromptCreateRequest) =>
      apiClient<PromptVariant>('/prompts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    onSuccess: (created) => {
      toast.success(`Prompt "${created.prompt_key}" created`)
      qc.invalidateQueries({ queryKey: queryKeys.prompts.all })
    },
  })
}

/** Update an existing prompt variant. */
export function useUpdatePrompt(promptKey: string, promptType: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: PromptUpdateRequest) =>
      apiClient<PromptVariant>(`/prompts/${promptKey}/${promptType}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      toast.success('Prompt saved')
      qc.invalidateQueries({ queryKey: queryKeys.prompts.detail(promptKey) })
      qc.invalidateQueries({ queryKey: queryKeys.prompts.all })
    },
  })
}

/** Soft-delete a prompt variant. */
export function useDeletePrompt(promptKey: string, promptType: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient(`/prompts/${promptKey}/${promptType}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Prompt deactivated')
      qc.invalidateQueries({ queryKey: queryKeys.prompts.all })
      qc.invalidateQueries({ queryKey: queryKeys.prompts.detail(promptKey) })
    },
  })
}

// ---------------------------------------------------------------------------
// Variable schema
// ---------------------------------------------------------------------------

interface VariableField {
  name: string
  type: string
  description: string
  required: boolean
  has_default: boolean
  source: 'db' | 'code' | 'both'
  auto_generate: string
}

interface VariableSchemaResponse {
  fields: VariableField[]
  has_code_class: boolean
  code_class_name: string | null
}

export function usePromptVariableSchema(promptKey: string, promptType: string) {
  return useQuery({
    queryKey: ['prompts', promptKey, promptType, 'variables'] as const,
    queryFn: () => apiClient<VariableSchemaResponse>(`/prompts/${promptKey}/${promptType}/variables`),
    enabled: Boolean(promptKey && promptType),
    staleTime: Infinity,
  })
}
