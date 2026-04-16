/**
 * TanStack Query hooks for the Evals API.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from './client'
import { queryKeys } from './query-keys'

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

export interface DatasetListItem {
  id: number
  name: string
  target_type: string
  target_name: string
  description: string | null
  case_count: number
  last_run_pass_rate: number | null
  created_at: string
  updated_at: string
}

export interface DatasetListResponse {
  items: DatasetListItem[]
  total: number
}

export interface CaseItem {
  id: number
  name: string
  inputs: Record<string, unknown>
  expected_output: Record<string, unknown> | null
  metadata_: Record<string, unknown> | null
}

export interface DatasetDetail extends DatasetListItem {
  cases: CaseItem[]
}

export interface RunListItem {
  id: number
  dataset_id: number
  status: string
  total_cases: number
  passed: number
  failed: number
  errored: number
  started_at: string
  completed_at: string | null
}

export interface CaseResultItem {
  id: number
  case_name: string
  passed: boolean
  evaluator_scores: Record<string, unknown>
  output_data: Record<string, unknown> | null
  error_message: string | null
}

export interface RunDetail extends RunListItem {
  case_results: CaseResultItem[]
}

export interface SchemaResponse {
  target_type: string
  target_name: string
  json_schema: Record<string, unknown>
}

export interface DatasetCreateRequest {
  name: string
  target_type: string
  target_name: string
  description?: string
}

export interface DatasetUpdateRequest {
  name?: string
  description?: string
}

export interface CaseCreateRequest {
  name: string
  inputs: Record<string, unknown>
  expected_output?: Record<string, unknown>
  metadata_?: Record<string, unknown>
}

export interface CaseUpdateRequest {
  name?: string
  inputs?: Record<string, unknown>
  expected_output?: Record<string, unknown> | null
  metadata_?: Record<string, unknown> | null
}

export interface TriggerRunRequest {
  model?: string | null
}

export interface DatasetListParams {
  target_type?: string
  target_name?: string
  limit?: number
  offset?: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toSearchParams(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== '')
  if (entries.length === 0) return ''
  return '?' + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()
}

// ---------------------------------------------------------------------------
// Query hooks
// ---------------------------------------------------------------------------

export function useDatasets(filters: Partial<DatasetListParams> = {}) {
  return useQuery({
    queryKey: queryKeys.evals.list(filters),
    queryFn: () => apiClient<DatasetListResponse>('/evals' + toSearchParams(filters)),
  })
}

export function useDataset(id: number) {
  return useQuery({
    queryKey: queryKeys.evals.detail(id),
    queryFn: () => apiClient<DatasetDetail>(`/evals/${id}`),
    enabled: id > 0,
  })
}

export function useEvalRuns(datasetId: number) {
  return useQuery({
    queryKey: queryKeys.evals.runs(datasetId),
    queryFn: () => apiClient<RunListItem[]>(`/evals/${datasetId}/runs`),
    enabled: datasetId > 0,
  })
}

export function useEvalRun(datasetId: number, runId: number) {
  return useQuery({
    queryKey: queryKeys.evals.run(datasetId, runId),
    queryFn: () => apiClient<RunDetail>(`/evals/${datasetId}/runs/${runId}`),
    enabled: datasetId > 0 && runId > 0,
  })
}

export function useInputSchema(targetType: string, targetName: string) {
  return useQuery({
    queryKey: queryKeys.evals.schema(targetType, targetName),
    queryFn: () =>
      apiClient<SchemaResponse>(
        '/evals/schema' + toSearchParams({ target_type: targetType, target_name: targetName }),
      ),
    enabled: Boolean(targetType) && Boolean(targetName),
  })
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useCreateDataset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: DatasetCreateRequest) =>
      apiClient<DatasetDetail>('/evals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: (data) => {
      toast.success(`Dataset "${data.name}" created`)
      qc.invalidateQueries({ queryKey: queryKeys.evals.all })
    },
  })
}

export function useUpdateDataset(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: DatasetUpdateRequest) =>
      apiClient<DatasetDetail>(`/evals/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: (data) => {
      toast.success(`Dataset "${data.name}" updated`)
      qc.invalidateQueries({ queryKey: queryKeys.evals.all })
      qc.invalidateQueries({ queryKey: queryKeys.evals.detail(id) })
    },
  })
}

export function useDeleteDataset(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient<void>(`/evals/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Dataset deleted')
      qc.invalidateQueries({ queryKey: queryKeys.evals.all })
    },
  })
}

export function useCreateCase(datasetId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: CaseCreateRequest) =>
      apiClient<CaseItem>(`/evals/${datasetId}/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      toast.success('Case created')
      qc.invalidateQueries({ queryKey: queryKeys.evals.detail(datasetId) })
      qc.invalidateQueries({ queryKey: queryKeys.evals.all })
    },
  })
}

export function useUpdateCase(datasetId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, ...req }: CaseUpdateRequest & { caseId: number }) =>
      apiClient<CaseItem>(`/evals/${datasetId}/cases/${caseId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      toast.success('Case updated')
      qc.invalidateQueries({ queryKey: queryKeys.evals.detail(datasetId) })
    },
  })
}

export function useDeleteCase(datasetId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (caseId: number) =>
      apiClient<void>(`/evals/${datasetId}/cases/${caseId}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Case deleted')
      qc.invalidateQueries({ queryKey: queryKeys.evals.detail(datasetId) })
      qc.invalidateQueries({ queryKey: queryKeys.evals.all })
    },
  })
}

export function useTriggerEvalRun(datasetId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: TriggerRunRequest = {}) =>
      apiClient<RunListItem>(`/evals/${datasetId}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      toast.success('Evaluation run triggered')
      qc.invalidateQueries({ queryKey: queryKeys.evals.runs(datasetId) })
      qc.invalidateQueries({ queryKey: queryKeys.evals.detail(datasetId) })
    },
  })
}
