import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys, isTerminalStatus } from './query-keys'
import type { RunTraceResponse, RunStatus } from './types'

/**
 * Fetch the Langfuse-backed trace + observations for a pipeline run.
 *
 * The backend route (`/api/runs/{run_id}/trace`) queries Langfuse via
 * SDK using `session_id == run_id`, transforms to a flat shape, and
 * returns the trace metadata + nested observations. The frontend
 * builds the hierarchy client-side from `parent_observation_id`.
 *
 * Polling cadence:
 *   - Terminal runs (completed / failed / restarted): `staleTime: Infinity`,
 *     no background refetch — the trace is immutable from the user's
 *     perspective.
 *   - Active runs: 3s polling. The WS span-broadcast stream invalidates
 *     this query in real time, so polling is a fallback for missed
 *     signals + initial bootstrap before the first WS event.
 *
 * Empty traces with `langfuse_configured: false` indicate the backend
 * has no Langfuse credentials configured. The UI should render the
 * operational state from local DB and a hint that observability isn't
 * set up.
 */
export function useTrace(runId: string, runStatus?: RunStatus | string) {
  return useQuery({
    queryKey: queryKeys.runs.trace(runId),
    queryFn: () =>
      apiClient<RunTraceResponse>('/runs/' + runId + '/trace'),
    enabled: Boolean(runId),
    staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 5_000,
    refetchInterval:
      runStatus && isTerminalStatus(runStatus) ? false : 3_000,
  })
}
