/**
 * WebSocket hook with TanStack Query cache integration.
 *
 * Connects to /ws/runs/{runId} and handles three server behaviors:
 * 1. **Not found** - server closes with 4004, hook sets error status
 * 2. **Replay** - server replays persisted events then sends replay_complete
 * 3. **Live streaming** - server streams events in real-time, ends with stream_complete
 *
 * Pipeline events are appended to the event query cache via setQueryData.
 * Control messages (heartbeat, stream_complete, replay_complete, error) update
 * the Zustand connection store instead.
 */

import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useWsStore } from '../stores/websocket'
import { queryKeys } from './query-keys'
import type { EventListResponse, EventItem } from './types'

/** Close codes that should NOT trigger reconnection. */
const NO_RECONNECT_CODES = new Set([1000, 4004])

/** Max reconnect delay in ms (capped exponential backoff). */
const MAX_RECONNECT_DELAY = 30_000

/** Base delay for reconnect backoff in ms. */
const BASE_RECONNECT_DELAY = 1_000

/**
 * Check whether an event_type is step-scoped (warrants steps list invalidation).
 *
 * Step-scoped events contain "step" in their type string, matching backend
 * event types like "step_started", "step_completed", "step_failed", etc.
 */
function isStepScopedEvent(eventType: string): boolean {
  return eventType.includes('step')
}

/**
 * Construct the WebSocket URL for a given run.
 *
 * Uses the current page origin with ws/wss protocol. In dev, Vite's
 * proxy config handles the upgrade to the backend port.
 */
function buildWsUrl(runId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/runs/${runId}`
}

/**
 * Connect to the WebSocket stream for a pipeline run.
 *
 * Returns `{ status, error }` from the Zustand store so consumers
 * can render connection state in the UI.
 *
 * @param runId - Pipeline run ID to stream, or null to stay idle
 */
export function useWebSocket(runId: string | null) {
  const queryClient = useQueryClient()
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hadConnectionRef = useRef(false)
  const mountedRef = useRef(true)

  const { status, error, setStatus, setError, incrementReconnect, reset } = useWsStore()

  const reconnectCountRef = useRef(0)

  /**
   * Append a pipeline event to the events query cache.
   * Only updates if there is existing cached data (avoids creating
   * cache entries before the REST query has populated them).
   */
  const appendEventToCache = useCallback(
    (event: EventItem) => {
      if (!runId) return
      queryClient.setQueryData<EventListResponse>(queryKeys.runs.events(runId, {}), (old) =>
        old ? { ...old, items: [...old.items, event], total: old.total + 1 } : undefined,
      )
    },
    [queryClient, runId],
  )

  /**
   * Connect (or reconnect) to the WebSocket endpoint.
   */
  const connect = useCallback(() => {
    if (!runId || !mountedRef.current) return

    // React 19 Strict Mode guard: skip if a connection already exists
    // and is not in a terminal state
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.CONNECTING ||
        wsRef.current.readyState === WebSocket.OPEN)
    ) {
      return
    }

    setStatus('connecting')
    setError(null)

    const ws = new WebSocket(buildWsUrl(runId))
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) {
        ws.close()
        return
      }
      hadConnectionRef.current = true
      reconnectCountRef.current = 0
      setStatus('connected')
    }

    ws.onmessage = (event) => {
      if (!mountedRef.current) return

      let raw: Record<string, unknown>
      try {
        raw = JSON.parse(event.data as string) as Record<string, unknown>
      } catch {
        return
      }

      // Control messages carry a `type` field; raw pipeline events do not
      // (they have `event_type` instead). Branch on presence of `type`.
      const msgType = raw.type as string | undefined

      if (msgType === 'heartbeat') {
        // keep-alive, no-op
        return
      }

      if (msgType === 'replay_complete') {
        setStatus('closed')
        return
      }

      if (msgType === 'stream_complete') {
        setStatus('closed')
        // refetch run detail to pick up final status/timing
        queryClient.invalidateQueries({
          queryKey: queryKeys.runs.detail(runId),
        })
        return
      }

      if (msgType === 'error') {
        setStatus('error')
        setError(raw.detail as string)
        return
      }

      // Raw pipeline event (EventItem shape with event_type)
      if (typeof raw.event_type === 'string') {
        const pipelineEvent = raw as unknown as EventItem
        appendEventToCache(pipelineEvent)

        // Invalidate steps list when event is step-scoped
        if (isStepScopedEvent(pipelineEvent.event_type)) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.runs.steps(runId),
          })
        }
      }
    }

    ws.onerror = () => {
      if (!mountedRef.current) return
      setStatus('error')
    }

    ws.onclose = (event) => {
      if (!mountedRef.current) return
      wsRef.current = null

      if (event.code === 4004) {
        setStatus('error')
        setError('Run not found')
        return
      }

      if (event.code === 1000) {
        // Normal closure (replay complete or stream complete)
        // Status already set by the control message handler
        return
      }

      // Unexpected disconnect -- attempt reconnection if we had
      // a successful connection previously
      if (hadConnectionRef.current && !NO_RECONNECT_CODES.has(event.code)) {
        reconnectCountRef.current += 1
        incrementReconnect()

        const delay = Math.min(
          BASE_RECONNECT_DELAY * 2 ** (reconnectCountRef.current - 1),
          MAX_RECONNECT_DELAY,
        )

        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null
          connect()
        }, delay)
      }
    }
  }, [runId, queryClient, setStatus, setError, incrementReconnect, appendEventToCache])

  // Main effect: connect when runId changes, clean up on unmount / runId change
  useEffect(() => {
    mountedRef.current = true
    hadConnectionRef.current = false
    reconnectCountRef.current = 0

    if (!runId) {
      reset()
      return
    }

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

      reset()
    }
  }, [runId, connect, reset])

  return { status, error }
}
