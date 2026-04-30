/**
 * TanStack Query hooks for the Phoenix-backed Evals API.
 *
 * Datasets and examples cross every layer as the canonical Dataset /
 * Example shapes (mirrored from llm_pipeline/evals/models.py).
 * Translation from raw Phoenix dicts happens once, at the route
 * layer, so the frontend only sees the canonical model.
 *
 * Experiments / runs / evaluations stay Phoenix-shape passthroughs —
 * they're runtime artifacts, not authored content, so canonicalising
 * them would be premature.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from './client'
import { queryKeys } from './query-keys'
import { ApiError } from './types'

// ===========================================================================
// Variant + delta types (mirrors backend `evals/variants.py`)
// ===========================================================================

export type InstructionDeltaOp = 'add' | 'modify'

/**
 * Compile-time mirror of the backend type whitelist
 * (`evals.variants._TYPE_WHITELIST`). Runtime source is
 * `GET /evals/delta-type-whitelist`.
 */
export type DeltaTypeStr =
  | 'str'
  | 'int'
  | 'float'
  | 'bool'
  | 'list'
  | 'dict'
  | 'Optional[str]'
  | 'Optional[int]'
  | 'Optional[float]'
  | 'Optional[bool]'

export interface InstructionDeltaItem {
  op: InstructionDeltaOp
  field: string
  type_str?: DeltaTypeStr
  default?: unknown
}

/**
 * Variant payload mirroring backend `evals.variants.Variant`. Null /
 * empty fields = use production. Stored on the experiment's
 * `metadata.variant` and round-tripped by the variant editor.
 */
export interface Variant {
  model: string | null
  prompt_overrides: Record<string, string>
  instructions_delta: InstructionDeltaItem[]
}

export const BASELINE_VARIANT: Variant = {
  model: null,
  prompt_overrides: {},
  instructions_delta: [],
}

export interface TypeWhitelistResponse {
  types: DeltaTypeStr[]
}

// ===========================================================================
// Canonical Dataset / Example (mirrors llm_pipeline/evals/models.py)
// ===========================================================================

export interface Example {
  id: string | null
  input: Record<string, unknown>
  output: Record<string, unknown>
  metadata: Record<string, unknown>
}

export interface DatasetMetadata {
  target_type?: string | null
  target_name?: string | null
  // Forward-compat for Phoenix-side metadata fields.
  [key: string]: unknown
}

export interface Dataset {
  id: string | null
  name: string
  description: string | null
  metadata: DatasetMetadata
  examples: Example[]
  created_at: string | null
  example_count: number | null
}

// ===========================================================================
// Phoenix-shape passthroughs (experiments / runs / evaluations)
//
// These are intentionally NOT canonicalised — they're runtime artifacts,
// never authored or hashed. The flatten* helpers absorb Phoenix's
// shipped wire-shape variants.
// ===========================================================================

export interface PhoenixExperiment {
  id: string
  dataset_id: string
  name: string
  description?: string | null
  metadata: {
    variant?: Variant
    target_type?: 'step' | 'pipeline'
    target_name?: string
    full_report?: Record<string, unknown> | null
    [key: string]: unknown
  }
  created_at?: string
}

export interface PhoenixRun {
  id: string
  experiment_id: string
  dataset_example_id: string
  output: unknown
  error?: string | null
  start_time?: string | null
  end_time?: string | null
  repetition_number?: number
  trace_id?: string | null
}

export interface PhoenixEvaluation {
  id?: string
  run_id?: string
  name: string
  label?: string | null
  score?: number | null
  explanation?: string | null
  metadata?: Record<string, unknown> | null
}

// ===========================================================================
// pydantic-evals EvaluationReport passthrough (lives on
// `experiment.metadata.full_report` — written by the backend's
// `_safe_dump_report` in `llm_pipeline/evals/runner.py`).
// ===========================================================================

export interface EvaluationResultShape {
  value: unknown
  reason?: string | null
  [key: string]: unknown
}

export interface ReportCase {
  name: string
  inputs?: unknown
  output?: unknown
  expected_output?: unknown
  metadata?: Record<string, unknown> | null
  assertions?: Record<string, EvaluationResultShape>
  scores?: Record<string, EvaluationResultShape>
  labels?: Record<string, EvaluationResultShape>
  [key: string]: unknown
}

export interface EvaluationReportShape {
  name?: string | null
  cases: ReportCase[]
  [key: string]: unknown
}

/**
 * Pull `experiment.metadata.full_report` and return a `name -> case`
 * map keyed by the case `name` (which equals the dataset example id).
 */
export function extractReportCases(
  experiment: PhoenixExperiment | null | undefined,
): Map<string, ReportCase> {
  const out = new Map<string, ReportCase>()
  const raw = experiment?.metadata?.full_report
  if (!raw || typeof raw !== 'object') return out
  const cases = (raw as Record<string, unknown>).cases
  if (!Array.isArray(cases)) return out
  for (const c of cases) {
    if (!c || typeof c !== 'object') continue
    const name = (c as Record<string, unknown>).name
    if (typeof name !== 'string') continue
    out.set(name, c as ReportCase)
  }
  return out
}

// ===========================================================================
// List + composite responses
// ===========================================================================

export interface DatasetListResponse {
  items: Dataset[]
  next_cursor: string | null
}

export interface ExperimentListResponse {
  data: PhoenixExperiment[]
}

export interface ExperimentDetailResponse {
  experiment: PhoenixExperiment
  runs: { data?: PhoenixRun[] } | { data?: { runs?: PhoenixRun[] } }
}

// ===========================================================================
// Production-config introspection (variant editor prefill)
// ===========================================================================

export interface ProdPromptsResponse {
  prompt_name: string
  step_name: string
  system: string | null
  user: string | null
  variable_definitions: unknown | null
}

export interface ProdModelResponse {
  pipeline_name: string
  step_name: string
  model: string | null
  request_limit?: number | null
}

// ===========================================================================
// Schema endpoint
// ===========================================================================

export interface SchemaResponse {
  schema_: Record<string, unknown>
}

// ===========================================================================
// Mutation request shapes that aren't the canonical model
// ===========================================================================

export interface RunTriggerRequest {
  variant?: Variant
  run_name?: string
  max_concurrency?: number
}

export interface RunTriggerResponse {
  status: 'accepted'
  experiment_id: string
  dataset_id: string
}

export interface AcceptRequest {
  accepted_by?: string
  notes?: string
}

export interface AcceptanceResponse {
  id: number
  experiment_id: string
  dataset_id: string
  pipeline_name: string
  step_name: string | null
  delta_summary: Variant
  accept_paths: Record<string, unknown>
  accepted_at: string
  accepted_by: string | null
  notes: string | null
}

// ===========================================================================
// Helpers
// ===========================================================================

function toSearchParams(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== '')
  if (entries.length === 0) return ''
  return '?' + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()
}

/**
 * Phoenix's run-list endpoint has shipped a few wrapper shapes
 * over time (`{data: [...]}`, `{data: {runs: [...]}}`). Squash to
 * a flat array.
 */
export function flattenRuns(payload: unknown): PhoenixRun[] {
  if (!payload || typeof payload !== 'object') return []
  const data = (payload as Record<string, unknown>).data
  if (Array.isArray(data)) return data as PhoenixRun[]
  if (data && typeof data === 'object') {
    const inner = (data as Record<string, unknown>).runs
      ?? (data as Record<string, unknown>).items
    if (Array.isArray(inner)) return inner as PhoenixRun[]
  }
  return []
}

export function flattenExperiments(payload: unknown): PhoenixExperiment[] {
  if (!payload || typeof payload !== 'object') return []
  const data = (payload as Record<string, unknown>).data
  if (Array.isArray(data)) return data as PhoenixExperiment[]
  if (data && typeof data === 'object') {
    const inner = (data as Record<string, unknown>).experiments
      ?? (data as Record<string, unknown>).items
    if (Array.isArray(inner)) return inner as PhoenixExperiment[]
  }
  return []
}

// ===========================================================================
// Read hooks
// ===========================================================================

export function useDatasets(filters: { limit?: number; cursor?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.evals.list(filters),
    queryFn: () =>
      apiClient<DatasetListResponse>('/evals/datasets' + toSearchParams(filters)),
  })
}

export function useDataset(datasetId: string) {
  return useQuery({
    queryKey: queryKeys.evals.detail(datasetId),
    queryFn: () => apiClient<Dataset>(`/evals/datasets/${datasetId}`),
    enabled: !!datasetId,
  })
}

export function useExperiments(datasetId: string) {
  return useQuery({
    queryKey: queryKeys.evals.experiments(datasetId),
    queryFn: () =>
      apiClient<ExperimentListResponse>(`/evals/datasets/${datasetId}/runs`),
    enabled: !!datasetId,
  })
}

/**
 * Fetch one experiment + its per-case runs. Polls while the
 * experiment is in flight (caller can pass `pollWhileIncomplete` to
 * enable refetch interval — see comments inline).
 */
export function useExperiment(
  datasetId: string,
  experimentId: string,
  options: { pollWhileIncomplete?: boolean; expectedCaseCount?: number } = {},
) {
  return useQuery({
    queryKey: queryKeys.evals.experiment(datasetId, experimentId),
    queryFn: () =>
      apiClient<ExperimentDetailResponse>(
        `/evals/datasets/${datasetId}/runs/${experimentId}`,
      ),
    enabled: !!datasetId && !!experimentId,
    refetchInterval: options.pollWhileIncomplete
      ? (query) => {
          // Phoenix experiments don't carry an explicit status field;
          // treat the run as "in flight" while runs.length < expected.
          const data = query.state.data as ExperimentDetailResponse | undefined
          if (!data) return 2000
          const runs = flattenRuns(data.runs)
          if (
            options.expectedCaseCount != null
            && runs.length >= options.expectedCaseCount
          ) return false
          // Default to polling every 2s while we're not certain we're done.
          return 2000
        }
      : false,
  })
}

export async function fetchDatasetProdPrompts(
  datasetId: string,
): Promise<ProdPromptsResponse | null> {
  try {
    return await apiClient<ProdPromptsResponse>(
      `/evals/datasets/${datasetId}/prod-prompts`,
      { silent: true },
    )
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) return null
    throw err
  }
}

export function useDatasetProdPrompts(datasetId: string) {
  return useQuery({
    queryKey: queryKeys.evals.prodPrompts(datasetId),
    queryFn: () => fetchDatasetProdPrompts(datasetId),
    enabled: !!datasetId,
    staleTime: 5 * 60 * 1000,
  })
}

export async function fetchDatasetProdModel(
  datasetId: string,
): Promise<ProdModelResponse | null> {
  try {
    return await apiClient<ProdModelResponse>(
      `/evals/datasets/${datasetId}/prod-model`,
      { silent: true },
    )
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) return null
    throw err
  }
}

export function useDatasetProdModel(datasetId: string) {
  return useQuery({
    queryKey: queryKeys.evals.prodModel(datasetId),
    queryFn: () => fetchDatasetProdModel(datasetId),
    enabled: !!datasetId,
    staleTime: 5 * 60 * 1000,
  })
}

export function useInputSchema(targetType: string, targetName: string) {
  return useQuery({
    queryKey: queryKeys.evals.schema(targetType, targetName),
    queryFn: () =>
      apiClient<SchemaResponse>(
        '/evals/schema'
          + toSearchParams({ target_type: targetType, target_name: targetName }),
      ),
    enabled: Boolean(targetType) && Boolean(targetName),
  })
}

export function fetchDeltaTypeWhitelist(): Promise<TypeWhitelistResponse> {
  return apiClient<TypeWhitelistResponse>('/evals/delta-type-whitelist')
}

export function useDeltaTypeWhitelist() {
  return useQuery({
    queryKey: queryKeys.evals.deltaTypeWhitelist(),
    queryFn: fetchDeltaTypeWhitelist,
    staleTime: Infinity,
    gcTime: Infinity,
  })
}

// ===========================================================================
// Mutation hooks
// ===========================================================================

export function useCreateDataset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Dataset) =>
      apiClient<Dataset>('/evals/datasets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      toast.success(`Dataset "${data.name ?? data.id}" created`)
      qc.invalidateQueries({ queryKey: queryKeys.evals.all })
    },
  })
}

export function useDeleteDataset(datasetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient<void>(`/evals/datasets/${datasetId}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Dataset deleted')
      qc.invalidateQueries({ queryKey: queryKeys.evals.all })
    },
  })
}

export function useAddExamples(datasetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (examples: Example[]) =>
      apiClient<Dataset>(`/evals/datasets/${datasetId}/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(examples),
      }),
    onSuccess: () => {
      toast.success('Examples added')
      qc.invalidateQueries({ queryKey: queryKeys.evals.detail(datasetId) })
    },
  })
}

export function useDeleteExample(datasetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (exampleId: string) =>
      apiClient<void>(
        `/evals/datasets/${datasetId}/cases/${exampleId}`,
        { method: 'DELETE' },
      ),
    onSuccess: () => {
      toast.success('Example deleted')
      qc.invalidateQueries({ queryKey: queryKeys.evals.detail(datasetId) })
    },
  })
}

export function useTriggerRun(datasetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: RunTriggerRequest = {}) =>
      apiClient<RunTriggerResponse>(`/evals/datasets/${datasetId}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      toast.success('Evaluation triggered')
      qc.invalidateQueries({ queryKey: queryKeys.evals.experiments(datasetId) })
    },
  })
}

export function useAcceptExperiment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ experimentId, ...req }: AcceptRequest & { experimentId: string }) =>
      apiClient<AcceptanceResponse>(
        `/evals/experiments/${experimentId}/accept`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(req),
        },
      ),
    onSuccess: (data) => {
      toast.success(
        `Experiment accepted into ${data.pipeline_name}`
          + (data.step_name ? `.${data.step_name}` : ''),
      )
      qc.invalidateQueries({ queryKey: queryKeys.evals.all })
    },
  })
}
