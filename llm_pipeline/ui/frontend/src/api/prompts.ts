/**
 * TanStack Query hooks for the Prompts API.
 *
 * @remarks These hooks target /api/prompts endpoints implemented by Task 22.
 * They will return 404 until that task is complete.
 */

import { useQueries, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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

/**
 * A prompt row fetched by (prompt_key, prompt_type, version), including
 * non-latest historical rows.
 *
 * Used by the compare page to resolve the exact prompt content used by a
 * past run. Prompt versioning is append-only, so a past run's
 * ``prompt_versions`` entry may reference a row that is no longer latest.
 */
export interface HistoricalPromptItem {
  id: number
  prompt_key: string
  prompt_name: string
  prompt_type: string
  category: string | null
  step_name: string | null
  content: string
  required_variables: string[] | null
  variable_definitions: Record<string, unknown> | null
  description: string | null
  version: string
  is_active: boolean
  is_latest: boolean
  // Nullable -- legacy rows predating the versioning-snapshots migration
  // may lack these timestamps.
  created_at: string | null
  updated_at: string | null
}

/**
 * Fetch a prompt row by (key, type, version), including non-latest rows.
 *
 * Prompt rows are immutable once persisted (append-only versioning), so
 * results are cached indefinitely. Used on the compare page to resolve the
 * exact prompt content used by a past run.
 */
export function useHistoricalPrompt(
  promptKey: string,
  promptType: string,
  version: string,
) {
  return useQuery({
    queryKey: queryKeys.prompts.historical(promptKey, promptType, version),
    queryFn: () =>
      apiClient<HistoricalPromptItem>(
        `/prompts/${promptKey}/${promptType}/versions/${version}`,
      ),
    enabled: Boolean(promptKey) && Boolean(promptType) && Boolean(version),
    staleTime: Infinity,
  })
}

/**
 * Flatten an ``EvaluationRun.prompt_versions`` snapshot into a list of
 * ``{prompt_key, prompt_type, version}`` triples.
 *
 * Handles both shapes produced by the runner:
 *  - Step-target: ``{prompt_key: {prompt_type: version}}``
 *  - Pipeline-target: ``{step_name: {prompt_key: {prompt_type: version}}}``
 *
 * Step-name wrappers (pipeline-target) are collapsed -- the output carries
 * ``prompt_key`` and ``prompt_type``, which is what the historical endpoint
 * needs. Step name is preserved as a secondary field for display grouping.
 */
export interface FlatPromptVersion {
  step_name: string | null
  prompt_key: string
  prompt_type: string
  version: string
}

export function flattenPromptVersions(
  versions: Record<string, unknown> | null | undefined,
): FlatPromptVersion[] {
  if (!versions) return []
  const out: FlatPromptVersion[] = []
  for (const [outerKey, outerVal] of Object.entries(versions)) {
    if (typeof outerVal !== 'object' || outerVal === null) continue
    const inner = outerVal as Record<string, unknown>
    const innerValues = Object.values(inner)
    // Step-target: inner is {prompt_type: version_string}
    if (innerValues.length > 0 && innerValues.every((v) => typeof v === 'string')) {
      for (const [promptType, version] of Object.entries(inner)) {
        if (typeof version !== 'string') continue
        out.push({
          step_name: null,
          prompt_key: outerKey,
          prompt_type: promptType,
          version,
        })
      }
    } else {
      // Pipeline-target: outerKey is step_name, inner is {prompt_key: {type: version}}
      for (const [promptKey, typeMap] of Object.entries(inner)) {
        if (typeof typeMap !== 'object' || typeMap === null) continue
        for (const [promptType, version] of Object.entries(
          typeMap as Record<string, unknown>,
        )) {
          if (typeof version !== 'string') continue
          out.push({
            step_name: outerKey,
            prompt_key: promptKey,
            prompt_type: promptType,
            version,
          })
        }
      }
    }
  }
  return out
}

/**
 * Resolve all historical prompts used by a run's ``prompt_versions`` snapshot.
 *
 * Returns a parallel array aligned with ``flattenPromptVersions(versions)``.
 * Each entry is a resolved ``HistoricalPromptItem`` or ``undefined`` while
 * the corresponding query is still loading. Results are cached indefinitely
 * since prompt rows are immutable.
 */
export function useRunPrompts(
  versions: Record<string, unknown> | null | undefined,
): {
  flat: FlatPromptVersion[]
  items: Array<HistoricalPromptItem | undefined>
  isLoading: boolean
} {
  const flat = flattenPromptVersions(versions)
  const results = useQueries({
    queries: flat.map((f) => ({
      queryKey: queryKeys.prompts.historical(
        f.prompt_key,
        f.prompt_type,
        f.version,
      ),
      queryFn: () =>
        apiClient<HistoricalPromptItem>(
          `/prompts/${f.prompt_key}/${f.prompt_type}/versions/${f.version}`,
        ),
      staleTime: Infinity,
    })),
  })
  return {
    flat,
    items: results.map((r) => r.data),
    isLoading: results.some((r) => r.isLoading),
  }
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
