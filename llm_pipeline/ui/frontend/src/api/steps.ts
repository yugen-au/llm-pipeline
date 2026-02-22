import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import { queryKeys, isTerminalStatus } from './query-keys'
import type { StepListResponse, StepDetail, RunStatus } from './types'

/**
 * Fetch all steps for a pipeline run.
 *
 * Dynamic staleTime: terminal runs (completed/failed) get `Infinity`
 * since their steps will never change. Active runs poll every 3s
 * with a 5s staleTime to keep the step list live.
 *
 * @param runId - Pipeline run ID
 * @param runStatus - Current run status for dynamic staleTime; avoids
 *   requiring consumers to fetch the run separately
 */
export function useSteps(runId: string, runStatus?: RunStatus | string) {
  return useQuery({
    queryKey: queryKeys.runs.steps(runId),
    queryFn: () =>
      apiClient<StepListResponse>('/runs/' + runId + '/steps'),
    enabled: Boolean(runId),
    staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 5_000,
    refetchInterval:
      runStatus && !isTerminalStatus(runStatus) ? 3_000 : false,
  })
}

/**
 * Fetch a single step detail by step number within a pipeline run.
 *
 * Dynamic staleTime: terminal runs get `Infinity` (immutable data).
 * Active runs use 30s staleTime (step detail changes less frequently
 * than the step list, no polling needed -- list polling triggers
 * refetch when steps appear).
 *
 * @param runId - Pipeline run ID
 * @param stepNumber - Step number within the run
 * @param runStatus - Current run status for dynamic staleTime; avoids
 *   requiring consumers to fetch the run separately
 */
export function useStep(
  runId: string,
  stepNumber: number,
  runStatus?: RunStatus | string
) {
  return useQuery({
    queryKey: queryKeys.runs.step(runId, stepNumber),
    queryFn: () =>
      apiClient<StepDetail>(
        '/runs/' + runId + '/steps/' + stepNumber
      ),
    enabled: Boolean(runId),
    staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 30_000,
  })
}
