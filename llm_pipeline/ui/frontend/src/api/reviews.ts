/**
 * TanStack Query hooks for the Reviews API.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from './client'
import { queryKeys } from './query-keys'

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
