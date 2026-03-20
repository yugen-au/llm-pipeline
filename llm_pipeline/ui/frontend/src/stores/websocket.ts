/**
 * Zustand store for WebSocket connection status and global notifications.
 *
 * Holds ephemeral connection state (status, error, reconnect count) and
 * the latest run_created notification. Event data lives in the TanStack
 * Query cache -- this store only tracks the transport layer and global
 * notifications so any component can access them without coupling to
 * the event stream.
 */

import { create } from 'zustand'
import type { WsRunCreated } from '@/api/types'

export type WsConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'error'

interface WsState {
  status: WsConnectionStatus
  error: string | null
  reconnectCount: number
  latestRun: WsRunCreated | null
  setStatus: (status: WsConnectionStatus) => void
  setError: (error: string | null) => void
  incrementReconnect: () => void
  setLatestRun: (run: WsRunCreated) => void
  reset: () => void
}

export const useWsStore = create<WsState>()((set) => ({
  status: 'idle',
  error: null,
  reconnectCount: 0,
  latestRun: null,
  setStatus: (status) => set({ status }),
  setError: (error) => set({ error }),
  incrementReconnect: () => set((state) => ({ reconnectCount: state.reconnectCount + 1 })),
  setLatestRun: (run) => set({ latestRun: run }),
  reset: () => set({ status: 'idle', error: null, reconnectCount: 0 }),
}))
