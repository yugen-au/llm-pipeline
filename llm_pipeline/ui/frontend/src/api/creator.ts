/**
 * TanStack Query hooks for the Creator API.
 *
 * Provides mutations for generate/test/accept/rename and queries for
 * draft listing and detail. Matches backend models in
 * llm_pipeline/ui/routes/creator.py.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys } from './query-keys'

// ---------------------------------------------------------------------------
// TypeScript interfaces matching backend Pydantic models
// ---------------------------------------------------------------------------

export interface GenerateRequest {
  description: string
  target_pipeline: string | null
  include_extraction: boolean
  include_transformation: boolean
}

export interface GenerateResponse {
  run_id: string
  draft_name: string
  status: string
}

export interface TestRequest {
  code_overrides: Record<string, string> | null
  sample_data: Record<string, unknown> | null
}

export interface TestResponse {
  import_ok: boolean
  security_issues: string[]
  sandbox_skipped: boolean
  output: string
  errors: string[]
  modules_found: string[]
  draft_status: string
}

export interface AcceptRequest {
  pipeline_file: string | null
}

export interface AcceptResponse {
  files_written: string[]
  prompts_registered: number
  pipeline_file_updated: boolean
  target_dir: string
}

export interface DraftItem {
  id: number
  name: string
  description: string | null
  status: string
  run_id: string | null
  created_at: string
  updated_at: string
}

export interface DraftDetail extends DraftItem {
  generated_code: Record<string, string>
  test_results: Record<string, unknown> | null
}

export interface DraftListResponse {
  items: DraftItem[]
  total: number
}

export interface RenameRequest {
  name: string
}

// ---------------------------------------------------------------------------
// Draft status helpers
// ---------------------------------------------------------------------------

/** Draft statuses that are terminal (data won't change). */
const isTerminalDraftStatus = (status: string): boolean =>
  status === 'accepted'

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

/**
 * Trigger step generation in the background.
 *
 * POST /creator/generate -> 202 Accepted with run_id + draft_name.
 * On success: invalidates draft list so DraftPicker refreshes.
 */
export function useGenerateStep() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (req: GenerateRequest) =>
      apiClient<GenerateResponse>('/creator/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.creator.drafts() })
    },
  })
}

/**
 * Run sandbox validation on a draft step.
 *
 * POST /creator/test/{draftId} with code_overrides + sample_data.
 * On success: invalidates draft detail so generated_code + test_results refresh.
 */
export function useTestDraft(draftId: number | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (req: TestRequest) =>
      apiClient<TestResponse>('/creator/test/' + draftId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      if (draftId != null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.creator.draft(draftId) })
      }
    },
  })
}

/**
 * Accept a draft step: write files, register prompts, update pipeline.
 *
 * POST /creator/accept/{draftId} with optional pipeline_file.
 * On success: invalidates both draft list and detail.
 */
export function useAcceptDraft(draftId: number | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (req: AcceptRequest) =>
      apiClient<AcceptResponse>('/creator/accept/' + draftId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      if (draftId != null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.creator.drafts() })
        queryClient.invalidateQueries({ queryKey: queryKeys.creator.draft(draftId) })
      }
    },
  })
}

/**
 * Rename a draft step.
 *
 * PATCH /creator/drafts/{draftId} with { name }.
 * Returns updated DraftDetail on success, 409 with suggested_name on collision.
 * On success: invalidates draft detail and list.
 */
export function useRenameDraft() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (vars: { draftId: number; name: string }) =>
      apiClient<DraftDetail>('/creator/drafts/' + vars.draftId, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: vars.name } satisfies RenameRequest),
      }),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.creator.draft(vars.draftId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.creator.drafts() })
    },
  })
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * Fetch all draft steps, ordered by created_at desc.
 *
 * GET /creator/drafts -> DraftListResponse.
 * Uses default 30s staleTime (matches QueryClient default).
 */
export function useDrafts() {
  return useQuery({
    queryKey: queryKeys.creator.drafts(),
    queryFn: () => apiClient<DraftListResponse>('/creator/drafts'),
    staleTime: 30_000,
  })
}

/**
 * Fetch a single draft by ID (includes generated_code + test_results).
 *
 * GET /creator/drafts/{draftId} -> DraftDetail.
 * Disabled when draftId is null (no draft selected).
 * Accepted drafts get staleTime Infinity (immutable); active drafts 10s.
 */
export function useDraft(draftId: number | null) {
  return useQuery({
    queryKey: queryKeys.creator.draft(draftId ?? 0),
    queryFn: () => apiClient<DraftDetail>('/creator/drafts/' + draftId),
    enabled: draftId != null,
    staleTime: (query) => {
      const status = query.state.data?.status
      if (status && isTerminalDraftStatus(status)) return Infinity
      return 10_000
    },
  })
}
