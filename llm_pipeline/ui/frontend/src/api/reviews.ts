/**
 * TanStack Query hooks for the Reviews API.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from './client'
import { queryKeys } from './query-keys'

export interface ReviewListItem {
  token: string
  run_id: string
  pipeline_name: string
  step_name: string
  step_number: number
  status: string
  decision: string | null
  notes: string | null
  created_at: string
  completed_at: string | null
}

export interface ReviewListResponse {
  items: ReviewListItem[]
  total: number
}

export interface ReviewListParams {
  status?: string
  pipeline_name?: string
  limit?: number
  offset?: number
}

export interface ReviewDetail {
  token: string
  run_id: string
  pipeline_name: string
  step_name: string
  step_number: number
  status: string
  review_data: {
    display_data: Array<{ label: string; value: unknown; type: string }>
    raw_data: Record<string, unknown> | null
  } | null
  decision: string | null
  notes: string | null
  created_at: string
  completed_at: string | null
}

export interface ReviewSubmitRequest {
  decision: 'approved' | 'minor_revision' | 'major_revision' | 'restart'
  notes?: string | null
  resume_from?: string | null
}

export interface ReviewSubmitResponse {
  run_id: string
  decision: string
  status: string
}

function toSearchParams(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== '')
  if (entries.length === 0) return ''
  return '?' + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()
}

export function useReviews(filters: Partial<ReviewListParams> = {}) {
  return useQuery({
    queryKey: ['reviews', filters] as const,
    queryFn: () => apiClient<ReviewListResponse>('/reviews' + toSearchParams(filters)),
  })
}

export function useReview(token: string) {
  return useQuery({
    queryKey: ['reviews', token] as const,
    queryFn: () => apiClient<ReviewDetail>(`/reviews/${token}`),
    enabled: Boolean(token),
  })
}

export function useSubmitReview(runId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: ReviewSubmitRequest) =>
      apiClient<ReviewSubmitResponse>(`/runs/${runId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: (data) => {
      toast.success(`Review submitted: ${data.decision}`)
      qc.invalidateQueries({ queryKey: queryKeys.runs.detail(runId) })
      qc.invalidateQueries({ queryKey: queryKeys.runs.all })
    },
  })
}
