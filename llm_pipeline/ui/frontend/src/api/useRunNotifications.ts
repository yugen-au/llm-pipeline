/**
 * Global run-creation notification hook.
 *
 * Connects to /ws/runs and exposes `latestRun` whenever the backend
 * broadcasts a `run_created` message. Used by live.tsx to auto-attach
 * to Python-initiated (or externally-started) pipeline runs.
 *
 * Follows the same reconnect-with-exponential-backoff pattern as
 * useWebSocket in src/api/websocket.ts, but simpler: no TanStack Query
 * cache integration, no Zustand store -- just local useState.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import type { WsRunCreated } from './types'

/** Max reconnect delay in ms (capped exponential backoff). */
const MAX_RECONNECT_DELAY = 30_000

/** Base delay for reconnect backoff in ms. */
const BASE_RECONNECT_DELAY = 1_000

/**
 * Construct the WebSocket URL for the global /ws/runs endpoint.
 *
 * Uses the current page origin with ws/wss protocol. In dev, Vite's
 * proxy config handles the upgrade to the backend port.
 */
function buildGlobalWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/runs`
}

/**
 * Listen for global run-creation notifications over WebSocket.
 *
 * Returns `{ latestRun }` -- the most recently received `run_created`
 * message, or null if none received yet. Reconnects automatically on
 * unexpected disconnects with exponential backoff.
 */
export function useRunNotifications() {
  const [latestRun, setLatestRun] = useState<WsRunCreated | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hadConnectionRef = useRef(false)
  const mountedRef = useRef(true)
  const reconnectCountRef = useRef(0)
  // Stable ref to latest connect fn to avoid stale closure in onclose
  const connectRef = useRef<(() => void) | null>(null)

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    // Guard: skip if a connection already exists and is not terminal
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.CONNECTING ||
        wsRef.current.readyState === WebSocket.OPEN)
    ) {
      return
    }

    const ws = new WebSocket(buildGlobalWsUrl())
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) {
        ws.close()
        return
      }
      hadConnectionRef.current = true
      reconnectCountRef.current = 0
    }

    ws.onmessage = (event) => {
      if (!mountedRef.current) return

      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(event.data as string) as Record<string, unknown>
      } catch {
        return
      }

      if (msg.type === 'run_created') {
        setLatestRun(msg as unknown as WsRunCreated)
      }
      // Ignore heartbeats and any other message types
    }

    ws.onerror = () => {
      // onerror is always followed by onclose; reconnect logic lives there
    }

    ws.onclose = (event) => {
      if (!mountedRef.current) return
      wsRef.current = null

      // Normal closure (1000) -- do not reconnect
      if (event.code === 1000) return

      // Unexpected disconnect -- reconnect if we had a prior connection
      if (hadConnectionRef.current) {
        reconnectCountRef.current += 1
        const count = reconnectCountRef.current

        const delay = Math.min(BASE_RECONNECT_DELAY * 2 ** (count - 1), MAX_RECONNECT_DELAY)

        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null
          connectRef.current?.()
        }, delay)
      }
    }
  }, [])

  useEffect(() => {
    connectRef.current = connect
    mountedRef.current = true
    hadConnectionRef.current = false
    reconnectCountRef.current = 0

    connect()

    return () => {
      mountedRef.current = false

      // Clear any pending reconnect timer
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }

      // Close the WebSocket if still open
      if (wsRef.current) {
        wsRef.current.onopen = null
        wsRef.current.onmessage = null
        wsRef.current.onerror = null
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  return { latestRun }
}
