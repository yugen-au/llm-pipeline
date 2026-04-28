import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys, isTerminalStatus } from './query-keys'
import type { RunTraceResponse, RunStatus, TraceObservation } from './types'

/**
 * Merge two trace responses: WS-pushed observations (live, no cost) +
 * HTTP-fetched observations (Langfuse, canonical with cost).
 *
 * Rule: HTTP is the system of record for any observation Langfuse has
 * already ingested (it carries cost and any prompt linkage). WS-only
 * observations (Langfuse hasn't seen them yet) are preserved so the
 * live UI doesn't flicker between renders.
 */
function mergeTrace(
  http: RunTraceResponse,
  prev: RunTraceResponse | undefined,
): RunTraceResponse {
  const httpObs = http.observations ?? []
  const prevObs = prev?.observations ?? []
  if (prevObs.length === 0) return http
  const httpIds = new Set(httpObs.map((o) => o.id))
  const wsOnly = prevObs.filter((o) => !httpIds.has(o.id))
  // Where IDs overlap, prefer HTTP fields but keep WS-only fields the
  // server returned as null (cost is the only one Langfuse fills in;
  // input/output should match).
  const merged: TraceObservation[] = [...httpObs, ...wsOnly]
  merged.sort((a, b) => (a.start_time ?? '').localeCompare(b.start_time ?? ''))
  return { ...http, observations: merged }
}

/**
 * Fetch the trace + observations for a pipeline run.
 *
 * Two data paths feed this cache:
 *
 *   1. **HTTP** (`/api/runs/{run_id}/trace`): canonical, Langfuse-backed.
 *      Carries cost (Langfuse computes it server-side) and historical
 *      data for terminal runs. This hook owns this fetch.
 *
 *   2. **WebSocket** (`WebSocketBroadcastProcessor`): pushes full
 *      ``TraceObservation`` payloads at OTEL ``on_start`` / ``on_end``,
 *      mutated into this same cache by the WS handler. No Langfuse
 *      round-trip — the UI sees spans the instant they happen.
 *
 * On HTTP fetch, we merge with the existing (WS-built) cache so live
 * data the server hasn't ingested yet doesn't get clobbered.
 *
 * Polling cadence:
 *   - Terminal runs (completed / failed / restarted): `staleTime: Infinity`,
 *     no background refetch — the trace is immutable.
 *   - Active runs: 10s reconcile poll. WS does the heavy lifting; HTTP
 *     is the safety net + how cost lands once Langfuse computes it.
 *
 * Empty traces with `langfuse_configured: false` indicate the backend
 * has no Langfuse credentials configured. The UI still renders WS-built
 * observations live; just no historical/canonical reconciliation.
 */
export function useTrace(runId: string, runStatus?: RunStatus | string) {
  const qc = useQueryClient()
  return useQuery({
    queryKey: queryKeys.runs.trace(runId),
    queryFn: async () => {
      const fresh = await apiClient<RunTraceResponse>('/runs/' + runId + '/trace')
      const prev = qc.getQueryData<RunTraceResponse>(queryKeys.runs.trace(runId))
      return mergeTrace(fresh, prev)
    },
    enabled: Boolean(runId),
    staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 10_000,
    refetchInterval:
      runStatus && isTerminalStatus(runStatus) ? false : 10_000,
  })
}
