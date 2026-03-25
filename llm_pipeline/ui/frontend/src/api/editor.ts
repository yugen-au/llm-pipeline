/**
 * TanStack Query hooks for the Editor API.
 *
 * Provides queries for available steps and draft pipelines, plus mutations
 * for compile, create, update, and delete. Matches backend models in
 * llm_pipeline/ui/routes/editor.py.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys } from './query-keys'
import { ApiError } from './types'

// ---------------------------------------------------------------------------
// TypeScript interfaces matching backend Pydantic models
// ---------------------------------------------------------------------------

export interface EditorStep {
  step_ref: string
  source: 'draft' | 'registered'
  position: number
}

export interface EditorStrategy {
  strategy_name: string
  steps: EditorStep[]
}

export interface CompileRequest {
  strategies: EditorStrategy[]
}

export interface CompileError {
  strategy_name: string
  step_ref: string
  message: string
}

export interface CompileResponse {
  valid: boolean
  errors: CompileError[]
}

export interface AvailableStep {
  step_ref: string
  source: 'draft' | 'registered'
  status: string | null
  pipeline_names: string[]
}

export interface AvailableStepsResponse {
  steps: AvailableStep[]
}

export interface DraftPipelineItem {
  id: number
  name: string
  status: string
  created_at: string
  updated_at: string
}

export interface DraftPipelineDetail extends DraftPipelineItem {
  structure: Record<string, unknown>
  compilation_errors: Record<string, unknown> | null
}

export interface DraftPipelineListResponse {
  items: DraftPipelineItem[]
  total: number
}

export interface CreateDraftPipelineRequest {
  name: string
  structure: Record<string, unknown>
}

export interface UpdateDraftPipelineRequest {
  name?: string | null
  structure?: Record<string, unknown> | null
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * Fetch merged available steps (registered + non-errored drafts).
 *
 * GET /editor/available-steps -> AvailableStepsResponse.
 * Steps are static-ish config data; 30s staleTime is sufficient.
 */
export function useAvailableSteps() {
  return useQuery({
    queryKey: queryKeys.editor.availableSteps(),
    queryFn: () =>
      apiClient<AvailableStepsResponse>('/editor/available-steps'),
    staleTime: 30_000,
  })
}

/**
 * Fetch all draft pipelines, ordered by created_at desc.
 *
 * GET /editor/drafts -> DraftPipelineListResponse.
 */
export function useDraftPipelines() {
  return useQuery({
    queryKey: queryKeys.editor.drafts(),
    queryFn: () =>
      apiClient<DraftPipelineListResponse>('/editor/drafts'),
    staleTime: 30_000,
  })
}

/**
 * Fetch a single draft pipeline by ID (includes structure + compilation_errors).
 *
 * GET /editor/drafts/{id} -> DraftPipelineDetail.
 * Disabled when id is null (no draft selected).
 */
export function useDraftPipeline(id: number | null) {
  return useQuery({
    queryKey: queryKeys.editor.draft(id ?? 0),
    queryFn: () =>
      apiClient<DraftPipelineDetail>('/editor/drafts/' + id),
    enabled: id != null,
  })
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

/**
 * Compile (validate) a pipeline structure.
 *
 * POST /editor/compile -> CompileResponse.
 * Ephemeral validation only -- does NOT invalidate any cache.
 */
export function useCompilePipeline() {
  return useMutation({
    mutationFn: (req: CompileRequest) =>
      apiClient<CompileResponse>('/editor/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
  })
}

/**
 * Create a new draft pipeline.
 *
 * POST /editor/drafts -> DraftPipelineDetail (201).
 * On success: invalidates drafts list so the list refreshes.
 */
export function useCreateDraftPipeline() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (req: CreateDraftPipelineRequest) =>
      apiClient<DraftPipelineDetail>('/editor/drafts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.editor.drafts() })
    },
  })
}

/**
 * Update name and/or structure of a draft pipeline.
 *
 * PATCH /editor/drafts/{id} -> DraftPipelineDetail.
 * On success: invalidates both the specific draft detail and drafts list.
 */
export function useUpdateDraftPipeline() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (vars: { id: number } & UpdateDraftPipelineRequest) =>
      apiClient<DraftPipelineDetail>('/editor/drafts/' + vars.id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: vars.name,
          structure: vars.structure,
        }),
      }),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.editor.draft(vars.id) })
      queryClient.invalidateQueries({ queryKey: queryKeys.editor.drafts() })
    },
  })
}

/**
 * Delete a draft pipeline.
 *
 * DELETE /editor/drafts/{id} -> 204 No Content.
 * Uses raw fetch because apiClient calls response.json() which fails on
 * empty 204 bodies. On success: invalidates drafts list.
 */
export function useDeleteDraftPipeline() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: number): Promise<void> => {
      const response = await fetch('/api/editor/drafts/' + id, {
        method: 'DELETE',
      })
      if (!response.ok) {
        let detail = response.statusText
        try {
          const body = (await response.json()) as { detail?: string }
          if (body.detail) detail = body.detail
        } catch { /* keep statusText */ }
        throw new ApiError(response.status, detail)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.editor.drafts() })
    },
  })
}
