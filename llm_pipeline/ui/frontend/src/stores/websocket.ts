/**
 * Zustand store for WebSocket connection status.
 *
 * Holds ephemeral connection state (status, error, reconnect count).
 * Event data lives in the TanStack Query cache -- this store only
 * tracks the transport layer so any component can show connection
 * health without coupling to the event stream.
 */

import { create } from 'zustand'

export type WsConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'replaying'
  | 'closed'
  | 'error'

interface WsState {
  status: WsConnectionStatus
  error: string | null
  reconnectCount: number
  setStatus: (status: WsConnectionStatus) => void
  setError: (error: string | null) => void
  incrementReconnect: () => void
  reset: () => void
}

export const useWsStore = create<WsState>()((set) => ({
  status: 'idle',
  error: null,
  reconnectCount: 0,
  setStatus: (status) => set({ status }),
  setError: (error) => set({ error }),
  incrementReconnect: () => set((state) => ({ reconnectCount: state.reconnectCount + 1 })),
  reset: () => set({ status: 'idle', error: null, reconnectCount: 0 }),
}))
