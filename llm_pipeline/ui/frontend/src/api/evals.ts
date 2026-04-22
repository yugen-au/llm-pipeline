/**
 * TanStack Query hooks for the Evals API.
 */

import {
  useQueries,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from './client'
import { queryKeys } from './query-keys'
import { ApiError } from './types'

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
  variant_id: number | null
  delta_snapshot: Record<string, unknown> | null
  case_versions: Record<string, string> | null
  prompt_versions: Record<string, unknown> | null
  model_snapshot: Record<string, unknown> | null
  instructions_schema_snapshot: Record<string, unknown> | null
}

export interface CaseResultItem {
  id: number
  /**
   * DB id of the eval case, or null when the runner could not resolve the
   * case name to a case row (see backend `runner.py` lines 222, 237 —
   * `name_to_id.get(name, 0)`; the 0 sentinel is mapped to null by the
   * route handler). Consumers that key into `RunListItem.case_versions`
   * by `case_id` must treat null as "unmatched".
   */
  case_id: number | null
  case_name: string
  passed: boolean
  evaluator_scores: Record<string, unknown>
  output_data: Record<string, unknown> | null
  error_message: string | null
}

export interface RunDetail extends RunListItem {
  case_results: CaseResultItem[]
}

/**
 * A case row fetched by id, including historical (is_latest=False) rows.
 *
 * Used by the compare page to resolve the exact case content used by a past
 * run. Case versioning is append-only, so EvaluationCaseResult.case_id may
 * point at a row that is no longer the latest version.
 */
export interface HistoricalCaseItem {
  id: number
  dataset_id: number
  name: string
  version: string
  is_active: boolean
  is_latest: boolean
  inputs: Record<string, unknown>
  expected_output: Record<string, unknown> | null
  metadata_: Record<string, unknown> | null
  // Nullable -- legacy rows predating the versioning-snapshots migration
  // may lack these timestamps.
  created_at: string | null
  updated_at: string | null
}

export interface SchemaResponse {
  target_type: string
  target_name: string
  json_schema: Record<string, unknown>
  input_schema: Record<string, unknown> | null
  output_schema: Record<string, unknown> | null
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
  variant_id?: number | null
}

// ---------------------------------------------------------------------------
// Variant interfaces (mirror backend Pydantic models in routes/evals.py)
// ---------------------------------------------------------------------------

export type InstructionDeltaOp = 'add' | 'modify'

/**
 * Canonical literal union of allowed `type_str` values for instruction deltas.
 *
 * Mirrors backend `_TYPE_WHITELIST` in `llm_pipeline/evals/delta.py`. Runtime
 * source of truth is `GET /evals/delta-type-whitelist` (see
 * `useDeltaTypeWhitelist`) — this union is the compile-time mirror so callers
 * cannot construct deltas with invalid types without an explicit cast.
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
  type_str: DeltaTypeStr
  default?: unknown
}

/**
 * Shape of a single entry in `Prompt.variable_definitions`, keyed by variable
 * name. Mirrors the backend Prompt ORM column and the existing
 * `PromptVariant.variable_definitions` TS type in `api/types.ts`.
 *
 * Extra fields round-trip via the `[key: string]: unknown` index signature so
 * the UI does not silently drop unknown keys the backend might add later.
 */
export interface VariableDefinitionEntry {
  type: string
  description?: string
  auto_generate?: string
  [key: string]: unknown
}

/** Map of variable-name -> definition (matches backend JSON shape). */
export type VariableDefinitions = Record<string, VariableDefinitionEntry>

export interface VariantDelta {
  model: string | null
  system_prompt: string | null
  user_prompt: string | null
  instructions_delta: InstructionDeltaItem[] | null
  /**
   * Optional override/extension for Prompt.variable_definitions. When present
   * the runner merges this into the sandbox Prompt row (`system_prompt` and
   * `user_prompt` both read from the same Prompt record's variable_definitions
   * column). Omit / null to leave the production variable_definitions intact.
   */
  variable_definitions?: VariableDefinitions | null
}

export interface TypeWhitelistResponse {
  types: DeltaTypeStr[]
}

export interface VariantItem {
  id: number
  dataset_id: number
  name: string
  description: string | null
  delta: VariantDelta
  created_at: string
  updated_at: string
}

export interface VariantCreateRequest {
  name: string
  description?: string | null
  delta: VariantDelta
}

export type VariantUpdateRequest = Partial<VariantCreateRequest>

export interface VariantListResponse {
  items: VariantItem[]
  total: number
}

export interface DatasetListParams {
  target_type?: string
  target_name?: string
  limit?: number
  offset?: number
}

// ---------------------------------------------------------------------------
// Prod prompts (prefill source for variant editor)
// ---------------------------------------------------------------------------

/**
 * Single prod prompt payload returned from GET /evals/{dataset_id}/prod-prompts.
 *
 * `variable_definitions` is typed as the shared `VariableDefinitions | null`
 * but the backend column is permissive (`dict | list`) so callers should feed
 * the raw value through `readVarDefs` (or equivalent) before consuming.
 */
export interface ProdPromptContent {
  prompt_key: string
  content: string
  variable_definitions: VariableDefinitions | null
  version: string | null
}

export interface ProdPromptsResponse {
  system: ProdPromptContent | null
  user: ProdPromptContent | null
}

// ---------------------------------------------------------------------------
// Prod model (prefill source for variant editor)
// ---------------------------------------------------------------------------

/**
 * Resolution source for a dataset's prod model. Mirrors the backend literal
 * union in GET /evals/{dataset_id}/prod-model:
 *   - "db"               — user-saved StepModelConfig override
 *   - "step_definition"  — model declared on the step's @step_definition
 *   - "pipeline_default" — pipeline-level default model
 *   - "none"             — no model resolvable (e.g. pipeline target, no config)
 */
export type ProdModelSource =
  | 'db'
  | 'step_definition'
  | 'pipeline_default'
  | 'none'

export interface ProdModelResponse {
  model: string | null
  source: ProdModelSource
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
    queryFn: async () => {
      const res = await apiClient<{ items: RunListItem[] }>(
        `/evals/${datasetId}/runs`,
      )
      return res.items
    },
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

/**
 * Fetch a case row by id, including historical (non-latest) versions.
 *
 * Case rows are immutable once persisted (append-only versioning), so results
 * are cached indefinitely. Used on the compare page to resolve the exact case
 * content used by a past run when cases have drifted between runs.
 */
export function useHistoricalCase(datasetId: number, caseId: number | null) {
  const id = caseId ?? 0
  return useQuery({
    queryKey: queryKeys.evals.historicalCase(datasetId, id),
    queryFn: () =>
      apiClient<HistoricalCaseItem>(
        `/evals/${datasetId}/cases/${id}/historical`,
      ),
    enabled: datasetId > 0 && id > 0,
    staleTime: Infinity,
  })
}

/**
 * Batch-fetch historical cases by id. Used by the compare page export to
 * resolve every case row referenced by either run in one pass. Returns a
 * map keyed by case_id, plus an overall loading flag.
 */
export function useHistoricalCases(
  datasetId: number,
  caseIds: number[],
): { byId: Map<number, HistoricalCaseItem>; isLoading: boolean } {
  const dedupedSorted = Array.from(new Set(caseIds.filter((id) => id > 0))).sort(
    (a, b) => a - b,
  )
  const results = useQueries({
    queries: dedupedSorted.map((id) => ({
      queryKey: queryKeys.evals.historicalCase(datasetId, id),
      queryFn: () =>
        apiClient<HistoricalCaseItem>(
          `/evals/${datasetId}/cases/${id}/historical`,
        ),
      enabled: datasetId > 0,
      staleTime: Infinity,
    })),
  })
  const byId = new Map<number, HistoricalCaseItem>()
  dedupedSorted.forEach((id, i) => {
    const data = results[i].data
    if (data) byId.set(id, data)
  })
  return {
    byId,
    isLoading: results.some((r) => r.isLoading),
  }
}

/**
 * Fetch the resolved prod (system, user) prompts for a dataset's step target.
 *
 * Returns `{ system: null, user: null }` when the backend returns 422 (which
 * happens for pipeline-target datasets — the endpoint only supports
 * step-targets in v2). Other errors propagate so TanStack Query can retry or
 * surface them via the toast layer.
 */
export async function fetchDatasetProdPrompts(
  datasetId: number,
): Promise<ProdPromptsResponse> {
  try {
    return await apiClient<ProdPromptsResponse>(
      `/evals/${datasetId}/prod-prompts`,
      { silent: true },
    )
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) {
      return { system: null, user: null }
    }
    throw err
  }
}

/**
 * TanStack Query hook for dataset prod prompts. 5-minute stale time since
 * prod prompts rarely change within a single editing session.
 */
export function useDatasetProdPrompts(datasetId: number) {
  return useQuery({
    queryKey: queryKeys.evals.prodPrompts(datasetId),
    queryFn: () => fetchDatasetProdPrompts(datasetId),
    enabled: Number.isFinite(datasetId) && datasetId > 0,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Fetch the resolved prod model for a dataset's step target.
 *
 * Returns `{ model: null, source: 'none' }` when the backend returns 422
 * (pipeline-target datasets — endpoint only supports step-targets in v2),
 * matching the fetchDatasetProdPrompts degradation pattern. Other errors
 * propagate so TanStack Query can retry or surface via the toast layer.
 */
export async function fetchDatasetProdModel(
  datasetId: number,
): Promise<ProdModelResponse> {
  try {
    return await apiClient<ProdModelResponse>(
      `/evals/${datasetId}/prod-model`,
      { silent: true },
    )
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) {
      return { model: null, source: 'none' }
    }
    throw err
  }
}

/**
 * TanStack Query hook for dataset prod model. 5-minute stale time — matches
 * prodPrompts cadence since StepModelConfig changes are rare within an
 * editing session.
 */
export function useDatasetProdModel(datasetId: number) {
  return useQuery({
    queryKey: queryKeys.evals.prodModel(datasetId),
    queryFn: () => fetchDatasetProdModel(datasetId),
    enabled: Number.isFinite(datasetId) && datasetId > 0,
    staleTime: 5 * 60 * 1000,
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

// ---------------------------------------------------------------------------
// Variant fetch functions
// ---------------------------------------------------------------------------

export function fetchVariants(datasetId: number): Promise<VariantListResponse> {
  return apiClient<VariantListResponse>(`/evals/${datasetId}/variants`)
}

export function fetchVariant(
  datasetId: number,
  variantId: number,
): Promise<VariantItem> {
  return apiClient<VariantItem>(`/evals/${datasetId}/variants/${variantId}`)
}

export function createVariant(
  datasetId: number,
  body: VariantCreateRequest,
): Promise<VariantItem> {
  return apiClient<VariantItem>(`/evals/${datasetId}/variants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function updateVariant(
  datasetId: number,
  variantId: number,
  body: VariantUpdateRequest,
): Promise<VariantItem> {
  return apiClient<VariantItem>(`/evals/${datasetId}/variants/${variantId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteVariant(
  datasetId: number,
  variantId: number,
): Promise<void> {
  return apiClient<void>(`/evals/${datasetId}/variants/${variantId}`, {
    method: 'DELETE',
  })
}

// ---------------------------------------------------------------------------
// Variant query hooks
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Delta type whitelist (single-source-of-truth fetcher)
// ---------------------------------------------------------------------------

/** Fetch the canonical `type_str` whitelist served by the backend. */
export function fetchDeltaTypeWhitelist(): Promise<TypeWhitelistResponse> {
  return apiClient<TypeWhitelistResponse>('/evals/delta-type-whitelist')
}

/**
 * TanStack Query hook for the delta type whitelist. Types never change at
 * runtime so the result is effectively immutable — use `staleTime: Infinity`
 * to avoid refetches. Lets the variant editor drop its local hard-coded
 * `TYPE_WHITELIST` constant and source the dropdown options from the backend.
 */
export function useDeltaTypeWhitelist() {
  return useQuery({
    queryKey: queryKeys.evals.deltaTypeWhitelist(),
    queryFn: fetchDeltaTypeWhitelist,
    staleTime: Infinity,
    gcTime: Infinity,
  })
}

export function useVariants(datasetId: number) {
  return useQuery({
    queryKey: queryKeys.evals.variants(datasetId),
    queryFn: () => fetchVariants(datasetId),
    enabled: datasetId > 0,
  })
}

export function useVariant(datasetId: number, variantId: number) {
  return useQuery({
    queryKey: queryKeys.evals.variant(datasetId, variantId),
    queryFn: () => fetchVariant(datasetId, variantId),
    enabled: datasetId > 0 && variantId > 0,
  })
}

// ---------------------------------------------------------------------------
// Variant mutation hooks
// ---------------------------------------------------------------------------

export function useCreateVariant(datasetId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: VariantCreateRequest) => createVariant(datasetId, body),
    onSuccess: (data) => {
      toast.success(`Variant "${data.name}" created`)
      qc.invalidateQueries({ queryKey: queryKeys.evals.variants(datasetId) })
    },
  })
}

export function useUpdateVariant(datasetId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      variantId,
      ...body
    }: VariantUpdateRequest & { variantId: number }) =>
      updateVariant(datasetId, variantId, body),
    onSuccess: (data) => {
      toast.success(`Variant "${data.name}" updated`)
      qc.invalidateQueries({ queryKey: queryKeys.evals.variants(datasetId) })
      qc.invalidateQueries({
        queryKey: queryKeys.evals.variant(datasetId, data.id),
      })
    },
  })
}

export function useDeleteVariant(datasetId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (variantId: number) => deleteVariant(datasetId, variantId),
    onSuccess: () => {
      toast.success('Variant deleted')
      qc.invalidateQueries({ queryKey: queryKeys.evals.variants(datasetId) })
    },
  })
}
