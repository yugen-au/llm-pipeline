/**
 * Zustand store for WebSocket connection status, subscriptions, and notifications.
 *
 * Holds ephemeral connection state (status, error, reconnect count),
 * multi-run subscription tracking, and the latest run_created notification.
 * Event data lives in the TanStack Query cache -- this store tracks the
 * transport layer and subscription state.
 */

import { create } from 'zustand'
import type { WsRunCreated } from '@/api/types'

export type WsConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'error'

export interface SubscribedRunInfo {
  pipelineName: string
  status: string
  subscribedAt: number
  isReplaying: boolean
}

interface WsState {
  // Connection
  status: WsConnectionStatus
  error: string | null
  reconnectCount: number
  latestRun: WsRunCreated | null

  // Multi-run subscriptions
  subscribedRuns: Record<string, SubscribedRunInfo>
  focusedRunId: string | null

  // Connection actions
  setStatus: (status: WsConnectionStatus) => void
  setError: (error: string | null) => void
  incrementReconnect: () => void
  setLatestRun: (run: WsRunCreated) => void
  reset: () => void

  // Subscription actions
  addSubscription: (runId: string, pipelineName: string) => void
  removeSubscription: (runId: string) => void
  updateSubscriptionStatus: (runId: string, status: string) => void
  setReplayComplete: (runId: string) => void
  setFocusedRun: (runId: string | null) => void
}

export const useWsStore = create<WsState>()((set) => ({
  status: 'idle',
  error: null,
  reconnectCount: 0,
  latestRun: null,
  subscribedRuns: {},
  focusedRunId: null,

  setStatus: (status) => set({ status }),
  setError: (error) => set({ error }),
  incrementReconnect: () => set((s) => ({ reconnectCount: s.reconnectCount + 1 })),
  setLatestRun: (run) => set({ latestRun: run }),
  reset: () => set({ status: 'idle', error: null, reconnectCount: 0 }),

  addSubscription: (runId, pipelineName) =>
    set((s) => ({
      subscribedRuns: {
        ...s.subscribedRuns,
        [runId]: {
          pipelineName,
          status: 'running',
          subscribedAt: Date.now(),
          isReplaying: true,
        },
      },
      focusedRunId: s.focusedRunId ?? runId,
    })),

  removeSubscription: (runId) =>
    set((s) => {
      const { [runId]: _, ...rest } = s.subscribedRuns
      const newFocused = s.focusedRunId === runId
        ? Object.keys(rest)[0] ?? null
        : s.focusedRunId
      return { subscribedRuns: rest, focusedRunId: newFocused }
    }),

  updateSubscriptionStatus: (runId, status) =>
    set((s) => {
      const existing = s.subscribedRuns[runId]
      if (!existing) return s
      return {
        subscribedRuns: {
          ...s.subscribedRuns,
          [runId]: { ...existing, status },
        },
      }
    }),

  setReplayComplete: (runId) =>
    set((s) => {
      const existing = s.subscribedRuns[runId]
      if (!existing) return s
      return {
        subscribedRuns: {
          ...s.subscribedRuns,
          [runId]: { ...existing, isReplaying: false },
        },
      }
    }),

  setFocusedRun: (runId) => set({ focusedRunId: runId }),
}))
