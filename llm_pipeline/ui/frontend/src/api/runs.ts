/**
 * TanStack Query hooks for the Runs API.
 *
 * Provides `useRuns`, `useRun`, `useCreateRun`, and `useRunContext`.
 *
 * @remarks
 * - `useRun` applies dynamic staleTime: `Infinity` for terminal runs
 *   (completed/failed) since their data is immutable, and `5_000`ms for
 *   active runs. Live updates come via WebSocket (no polling).
 * - `useRunContext` similarly uses `Infinity` for terminal status.
 * - `useRuns` uses the global 30s staleTime from QueryClient (list data
 *   is always considered fresh enough at the default interval).
 * - Response field is `data?.items` (not `data?.runs`) per task 33 deviation.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys, isTerminalStatus } from './query-keys'
import { toSearchParams } from './types'
import type {
  RunListParams,
  RunListResponse,
  RunDetail,
  RunStatus,
  TriggerRunRequest,
  TriggerRunResponse,
  ContextEvolutionResponse,
} from './types'

// ---------------------------------------------------------------------------
// useRuns
// ---------------------------------------------------------------------------

/**
 * Fetch paginated list of pipeline runs.
 *
 * Uses global QueryClient staleTime (30s). No per-hook override needed
 * since list data does not benefit from aggressive polling.
 *
 * @remarks Access run items via `data?.items` (not `data?.runs`).
 */
export function useRuns(filters: Partial<RunListParams> = {}) {
  return useQuery({
    queryKey: queryKeys.runs.list(filters),
    queryFn: () => apiClient<RunListResponse>(`/runs${toSearchParams(filters)}`),
  })
}

// ---------------------------------------------------------------------------
// useRun
// ---------------------------------------------------------------------------

/**
 * Fetch a single run by ID with dynamic staleTime.
 *
 * - Terminal runs (completed/failed): `staleTime: Infinity`, no polling.
 *   Their data is immutable and will never change.
 * - Active runs (running/pending): `staleTime: 5_000`ms. Live updates
 *   come via WebSocket; no polling needed.
 */
export function useRun(runId: string) {
  return useQuery({
    queryKey: queryKeys.runs.detail(runId),
    queryFn: () => apiClient<RunDetail>(`/runs/${runId}`),
    enabled: Boolean(runId),
    staleTime: (query) => {
      const status = query.state.data?.status
      if (!status) return 30_000
      return isTerminalStatus(status) ? Infinity : 5_000
    },
  })
}

// ---------------------------------------------------------------------------
// useCreateRun
// ---------------------------------------------------------------------------

/**
 * Mutation to trigger a new pipeline run.
 *
 * Invalidates all run queries on success so lists and any cached
 * run data refresh automatically.
 */
export function useCreateRun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (req: TriggerRunRequest) =>
      apiClient<TriggerRunResponse>('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.runs.all })
    },
  })
}

// ---------------------------------------------------------------------------
// useRunContext
// ---------------------------------------------------------------------------

/**
 * Fetch context evolution (snapshots per step) for a run.
 *
 * Accepts optional `status` so consumers who already have the run status
 * can benefit from dynamic staleTime without a separate fetch:
 * - Terminal: `Infinity` (context snapshots are immutable)
 * - Active/unknown: global 30s default
 */
export function useRunContext(runId: string, status?: RunStatus) {
  return useQuery({
    queryKey: queryKeys.runs.context(runId),
    queryFn: () => apiClient<ContextEvolutionResponse>(`/runs/${runId}/context`),
    enabled: Boolean(runId),
    staleTime: status && isTerminalStatus(status) ? Infinity : 30_000,
  })
}
