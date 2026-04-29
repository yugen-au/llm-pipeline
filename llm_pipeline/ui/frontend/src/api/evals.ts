/**
 * TanStack Query hooks for the Phoenix-backed Evals API.
 *
 * Phase-3 contract: Phoenix is the source of truth for datasets,
 * examples, experiments, runs, and per-case results. The framework
 * keeps only `EvaluationAcceptance` locally (audit row written by
 * `accept_experiment`).
 *
 * All identifiers are STRINGS (Phoenix uses string ids — UUID-like).
 * The legacy integer-id contract is gone.
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
// Phoenix shapes (datasets / examples / experiments / runs / evaluations)
// ===========================================================================

/** Single Phoenix dataset record. */
export interface PhoenixDataset {
  id: string
  name: string
  description?: string | null
  metadata: {
    target_type?: 'step' | 'pipeline'
    target_name?: string
    [key: string]: unknown
  }
  created_at?: string
  updated_at?: string
  example_count?: number
}

/** Phoenix example (== a "case" in the legacy vocabulary). */
export interface PhoenixExample {
  id: string
  input: Record<string, unknown>
  output?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
  // Phoenix may surface its own version id on the example.
  version_id?: string | null
}

/**
 * Phoenix experiment record. The experiment's `metadata.variant` is
 * the canonical "saved variant" — clicking a past experiment in the
 * UI prefills the variant editor from this.
 */
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

/** A single per-case run inside an experiment. */
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

/** A Phoenix evaluation score attached to a per-case run. */
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
// Composite responses (mirroring routes that bundle a record + its children)
// ===========================================================================

export interface DatasetListResponse {
  data: PhoenixDataset[]
  next_cursor?: string | null
}

export interface DatasetDetailResponse {
  dataset: PhoenixDataset
  examples: { data?: { examples?: PhoenixExample[] } | PhoenixExample[] } | { data?: PhoenixExample[] }
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
// Request shapes
// ===========================================================================

export interface DatasetUploadRequest {
  name: string
  target_type: 'step' | 'pipeline'
  target_name: string
  examples: Array<{
    input: Record<string, unknown>
    output?: Record<string, unknown>
    metadata?: Record<string, unknown>
  }>
  description?: string
}

export interface AddExamplesRequest {
  examples: Array<{
    input: Record<string, unknown>
    output?: Record<string, unknown>
    metadata?: Record<string, unknown>
  }>
}

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
 * Phoenix's example list endpoint has shipped a few wrapper shapes
 * over time (`{data: {examples: [...]}}`, `{data: [...]}`,
 * `{examples: [...]}`). Squash to a flat array so callers can rely on
 * a single shape.
 */
export function flattenExamples(payload: unknown): PhoenixExample[] {
  if (!payload || typeof payload !== 'object') return []
  const data = (payload as Record<string, unknown>).data
  if (Array.isArray(data)) return data as PhoenixExample[]
  if (data && typeof data === 'object') {
    const inner = (data as Record<string, unknown>).examples
      ?? (data as Record<string, unknown>).items
    if (Array.isArray(inner)) return inner as PhoenixExample[]
  }
  const flat = (payload as Record<string, unknown>).examples
  if (Array.isArray(flat)) return flat as PhoenixExample[]
  return []
}

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
    queryFn: () => apiClient<DatasetDetailResponse>(`/evals/datasets/${datasetId}`),
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
    mutationFn: (req: DatasetUploadRequest) =>
      apiClient<PhoenixDataset>('/evals/datasets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
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
    mutationFn: (req: AddExamplesRequest) =>
      apiClient<unknown>(`/evals/datasets/${datasetId}/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
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
