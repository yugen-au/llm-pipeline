import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys, isTerminalStatus } from './query-keys'
import { toSearchParams } from './types'
import type { EventListParams, EventListResponse, RunStatus } from './types'

/**
 * Fetch events for a pipeline run with optional filtering.
 *
 * Dynamic staleTime: terminal runs (completed/failed) get `Infinity`
 * since their events will never change. Active runs poll every 3s
 * with a 5s staleTime to keep the event log live.
 *
 * @param runId - Pipeline run ID
 * @param filters - Optional event_type, offset, limit filters
 * @param runStatus - Current run status for dynamic staleTime; avoids
 *   requiring consumers to fetch the run separately
 */
export function useEvents(
  runId: string,
  filters: Partial<EventListParams> = {},
  runStatus?: RunStatus | string,
) {
  return useQuery({
    queryKey: queryKeys.runs.events(runId, filters),
    queryFn: () =>
      apiClient<EventListResponse>('/runs/' + runId + '/events' + toSearchParams(filters)),
    enabled: Boolean(runId),
    staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 5_000,
    refetchInterval: runStatus && !isTerminalStatus(runStatus) ? 3_000 : false,
  })
}
