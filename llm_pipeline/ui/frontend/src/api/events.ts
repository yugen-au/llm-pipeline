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

/**
 * Fetch events scoped to a single pipeline step.
 *
 * Thin wrapper around {@link useEvents} that passes `step_name` as a
 * server-side filter. Disabled until both `runId` and `stepName` are
 * truthy (step name is unknown until `useStep` resolves).
 *
 * @param runId - Pipeline run ID
 * @param stepName - Step name to filter events by
 * @param runStatus - Current run status for dynamic staleTime/polling
 */
export function useStepEvents(
  runId: string,
  stepName: string,
  runStatus?: RunStatus | string,
) {
  // Guard: disable query when stepName is falsy (unknown until useStep resolves).
  // Pass empty runId to trigger useEvents' own `enabled: Boolean(runId)` guard.
  const effectiveRunId = stepName ? runId : ''
  return useEvents(
    effectiveRunId,
    { step_name: stepName },
    runStatus,
  )
}
