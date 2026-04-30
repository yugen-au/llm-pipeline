/**
 * TanStack Query hooks for the Prompts API.
 *
 * One Prompt record carries both system + user messages (Phoenix shape).
 * Mutations send the canonical Prompt body; the backend accepts it for
 * both POST (create) and PUT (replace messages array).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from './client'
import { queryKeys } from './query-keys'
import { toSearchParams } from './types'
import type { Prompt, PromptListParams, PromptListResponse } from './types'

/**
 * Fetch a paginated list of prompts with optional filtering.
 *
 * Prompts are static reference data so the default 30s staleTime
 * from the global QueryClient config is sufficient.
 */
export function usePrompts(filters: Partial<PromptListParams> = {}) {
  return useQuery({
    queryKey: queryKeys.prompts.list(filters),
    queryFn: () => apiClient<PromptListResponse>('/prompts' + toSearchParams(filters)),
  })
}

/**
 * Fetch a single prompt by name.
 *
 * Disabled when ``name`` is falsy so callers can pass an empty string
 * before a selection is made.
 */
export function usePromptDetail(name: string) {
  return useQuery({
    queryKey: queryKeys.prompts.detail(name),
    queryFn: () => apiClient<Prompt>('/prompts/' + name),
    enabled: Boolean(name),
  })
}

/** Create a new prompt (or push a new version under an existing name). */
export function useCreatePrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Prompt) =>
      apiClient<Prompt>('/prompts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    onSuccess: (created) => {
      toast.success(`Prompt "${created.name}" created`)
      qc.invalidateQueries({ queryKey: queryKeys.prompts.all })
    },
  })
}

/** Replace a prompt's messages array atomically. */
export function useUpdatePrompt(name: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Prompt) =>
      apiClient<Prompt>(`/prompts/${name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      toast.success('Prompt saved')
      qc.invalidateQueries({ queryKey: queryKeys.prompts.detail(name) })
      qc.invalidateQueries({ queryKey: queryKeys.prompts.all })
    },
  })
}

/** Delete a prompt and all its versions. */
export function useDeletePrompt(name: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient(`/prompts/${name}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Prompt deleted')
      qc.invalidateQueries({ queryKey: queryKeys.prompts.all })
      qc.invalidateQueries({ queryKey: queryKeys.prompts.detail(name) })
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

export function usePromptVariableSchema(name: string) {
  return useQuery({
    queryKey: ['prompts', name, 'variables'] as const,
    queryFn: () => apiClient<VariableSchemaResponse>(`/prompts/${name}/variables`),
    enabled: Boolean(name),
    staleTime: Infinity,
  })
}

// ---------------------------------------------------------------------------
// Auto-generate registry
// ---------------------------------------------------------------------------

export interface EnumMember { name: string; value: string }

export interface AutoGenerateObject {
  name: string
  kind: 'enum' | 'constant'
  members?: EnumMember[]
  value_type?: string
  value?: unknown
}

export function useAutoGenerateObjects() {
  return useQuery({
    queryKey: ['auto-generate'] as const,
    queryFn: () => apiClient<{ objects: AutoGenerateObject[] }>('/auto-generate'),
    staleTime: Infinity,
  })
}
