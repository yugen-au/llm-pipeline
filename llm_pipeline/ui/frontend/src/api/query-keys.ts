import type { RunListParams, EventListParams, PromptListParams, RunStatus } from './types'

/**
 * Centralized query key factory for TanStack Query.
 *
 * Hierarchical keys enable targeted cache invalidation:
 * - `queryKeys.runs.all` -> invalidates ALL run-related queries
 * - `queryKeys.runs.detail(id)` -> invalidates one run + its children (context, steps, events)
 *
 * All factory functions return `as const` tuples for strict type inference.
 */
export const queryKeys = {
  runs: {
    all: ['runs'] as const,
    list: (filters: Partial<RunListParams>) => ['runs', filters] as const,
    detail: (runId: string) => ['runs', runId] as const,
    context: (runId: string) => ['runs', runId, 'context'] as const,
    steps: (runId: string) => ['runs', runId, 'steps'] as const,
    step: (runId: string, stepNumber: number) =>
      ['runs', runId, 'steps', stepNumber] as const,
    events: (runId: string, filters: Partial<EventListParams>) =>
      ['runs', runId, 'events', filters] as const,
  },
  prompts: {
    all: ['prompts'] as const,
    list: (filters: Partial<PromptListParams>) => ['prompts', filters] as const,
    detail: (key: string) => ['prompts', key] as const,
  },
  pipelines: {
    all: ['pipelines'] as const,
    detail: (name: string) => ['pipelines', name] as const,
    stepPrompts: (name: string, stepName: string) =>
      ['pipelines', name, 'steps', stepName, 'prompts'] as const,
  },
  creator: {
    all: ['creator'] as const,
    drafts: () => ['creator', 'drafts'] as const,
    draft: (id: number) => ['creator', 'drafts', id] as const,
  },
} as const

/**
 * Returns true when a run has reached a terminal state (completed or failed).
 *
 * Terminal runs are immutable -- their steps, events, and context will never change.
 * Hooks use this to set `staleTime: Infinity` and disable polling for finished runs,
 * avoiding unnecessary network requests.
 */
export const isTerminalStatus = (status: RunStatus | string): boolean =>
  status === 'completed' || status === 'failed'
