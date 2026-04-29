/**
 * Single always-on WebSocket connection to /ws/runs.
 *
 * useGlobalWebSocket() -- mount once at app root. Manages the WS
 * lifecycle, reconnects on failure, and dispatches incoming messages
 * to the TanStack Query cache and Zustand store.
 *
 * useSubscribeRun(runId) -- mount in any component that needs per-run
 * events. Sends subscribe/unsubscribe messages over the global WS.
 * No WS lifecycle management -- just subscription control.
 */

import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useWsStore } from '../stores/websocket'
import { queryKeys } from './query-keys'
import type {
  WsMessage,
  WsClientMessage,
  RunDetail,
  RunTraceResponse,
  TraceObservation,
} from './types'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Max reconnect delay in ms (capped exponential backoff). */
const MAX_RECONNECT_DELAY = 30_000

/** Base delay for reconnect backoff in ms. */
const BASE_RECONNECT_DELAY = 1_000

// ---------------------------------------------------------------------------
// Module-level WS singleton state
// ---------------------------------------------------------------------------

let globalWs: WebSocket | null = null
let pendingMessages: WsClientMessage[] = []
/** Cached QueryClient reference for imperative subscribeToRun calls. */
let cachedQueryClient: QueryClient | null = null

/** Tracks active subscriptions so they can be re-sent on reconnect. */
const activeSubscriptions = new Set<string>()

/** Guards StrictMode double-mount cleanup from tearing down a newer WS. */
let mountGeneration = 0

/**
 * Send a message over the global WS. If not yet open, queues for delivery.
 */
function sendWsMessage(msg: WsClientMessage): void {
  if (globalWs && globalWs.readyState === WebSocket.OPEN) {
    globalWs.send(JSON.stringify(msg))
  } else {
    pendingMessages.push(msg)
  }
}

/** Flush any messages queued while WS was connecting, then re-subscribe. */
function flushPending(): void {
  if (!globalWs || globalWs.readyState !== WebSocket.OPEN) return
  for (const msg of pendingMessages) {
    globalWs.send(JSON.stringify(msg))
  }
  pendingMessages = []

  // Re-subscribe all active runs on the new connection
  for (const runId of activeSubscriptions) {
    globalWs.send(JSON.stringify({ action: 'subscribe', run_id: runId }))
  }
}

// ---------------------------------------------------------------------------
// Message parsing
// ---------------------------------------------------------------------------

/**
 * Construct the WebSocket URL for the global /ws/runs endpoint.
 */
function buildWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/runs`
}

/**
 * Parse raw JSON into a WsMessage discriminated union member.
 *
 * All messages over the unified /ws/runs endpoint now carry a `type`
 * field (control messages + the OTEL span signals from
 * WebSocketBroadcastProcessor). No fallback normalization needed —
 * the legacy "raw pipeline_event" shape is gone.
 */
function parseWsMessage(data: string): WsMessage | null {
  let raw: Record<string, unknown>
  try {
    raw = JSON.parse(data) as Record<string, unknown>
  } catch {
    return null
  }
  if (typeof raw.type === 'string') {
    return raw as unknown as WsMessage
  }
  return null
}

// ---------------------------------------------------------------------------
// Cache helpers
// ---------------------------------------------------------------------------

/**
 * Insert or update a span observation in the trace cache directly.
 *
 * The OTEL broadcast processor pushes the full TraceObservation
 * payload over WS at on_start (start_time set, end_time null) and
 * on_end (full data). We mutate the trace query cache by id so the
 * UI rerenders immediately — no Langfuse round-trip on the live path.
 *
 * Merge rule: incoming observation wins when ``end_time`` is set
 * (final state) or the incoming type/level differs. Otherwise we keep
 * any richer existing version (e.g. one Langfuse already filled in
 * with cost via the reconcile poll).
 */
function applySpanEvent(
  qc: QueryClient,
  runId: string,
  obs: TraceObservation,
  spanName: string,
): void {
  qc.setQueryData<RunTraceResponse>(queryKeys.runs.trace(runId), (prev) => {
    const existing = prev?.observations ?? []
    const idx = existing.findIndex((o) => o.id === obs.id)
    let nextObservations: TraceObservation[]
    if (idx === -1) {
      nextObservations = [...existing, obs]
    } else {
      const current = existing[idx]
      // Prefer Langfuse-canonical fields when present (e.g. total_cost)
      const merged: TraceObservation = {
        ...current,
        ...obs,
        total_cost: obs.total_cost ?? current.total_cost,
        // Keep richer input/output if WS happens to push null on a
        // re-emit (defensive — shouldn't happen but cheap to guard)
        input: obs.input ?? current.input,
        output: obs.output ?? current.output,
      }
      nextObservations = [...existing]
      nextObservations[idx] = merged
    }
    nextObservations.sort((a, b) => {
      const at = a.start_time ?? ''
      const bt = b.start_time ?? ''
      return at.localeCompare(bt)
    })
    if (!prev) {
      return {
        run_id: runId,
        pipeline_name: '',
        status: 'running',
        trace_backend_configured: true,
        traces: [],
        observations: nextObservations,
      }
    }
    return { ...prev, observations: nextObservations }
  })

  // Step span boundaries also affect the operational steps query
  // (StepTimeline derives running/completed from these rows).
  if (spanName.startsWith('step.')) {
    qc.invalidateQueries({ queryKey: queryKeys.runs.steps(runId) })
  }
}

/**
 * Write run detail from enriched stream_complete message.
 */
function writeRunDetailFromComplete(
  qc: QueryClient,
  msg: Extract<WsMessage, { type: 'stream_complete' }>,
): void {
  qc.setQueryData<RunDetail>(queryKeys.runs.detail(msg.run_id), (old) => {
    if (!old) return undefined
    return {
      ...old,
      status: msg.status ?? old.status,
      completed_at: msg.completed_at ?? old.completed_at,
      total_time_ms: msg.total_time_ms ?? old.total_time_ms,
      step_count: msg.step_count ?? old.step_count,
    }
  })

  // Force refetch from DB to ensure status is accurate (fixes race condition)
  qc.invalidateQueries({ queryKey: queryKeys.runs.detail(msg.run_id) })
  qc.invalidateQueries({ queryKey: queryKeys.runs.all })

  // Toast on failure
  if (msg.status === 'failed') {
    toast.error(`Pipeline run failed (${msg.run_id.slice(0, 8)})`)
  }
}

// ---------------------------------------------------------------------------
// useGlobalWebSocket
// ---------------------------------------------------------------------------

/**
 * Mount once at app root. Manages the single WS connection lifecycle.
 * All incoming messages are dispatched to caches/stores as side effects.
 */
export function useGlobalWebSocket(): void {
  const queryClient = useQueryClient()
  const mountedRef = useRef(true)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hadConnectionRef = useRef(false)
  const connectRef = useRef<(() => void) | null>(null)

  const { setStatus, setError, setLatestRun, incrementReconnect } = useWsStore()

  cachedQueryClient = queryClient

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    // Guard: skip if already connecting/open
    if (
      globalWs &&
      (globalWs.readyState === WebSocket.CONNECTING ||
        globalWs.readyState === WebSocket.OPEN)
    ) {
      return
    }

    setStatus('connecting')
    setError(null)

    const ws = new WebSocket(buildWsUrl())
    globalWs = ws

    ws.onopen = () => {
      if (!mountedRef.current) {
        ws.close()
        return
      }
      hadConnectionRef.current = true
      setStatus('connected')
      flushPending()
    }

    ws.onmessage = (event) => {
      if (!mountedRef.current) return

      const msg = parseWsMessage(event.data as string)
      if (!msg) return

      switch (msg.type) {
        case 'heartbeat':
          break

        case 'run_created':
          setLatestRun(msg)
          queryClient.invalidateQueries({ queryKey: queryKeys.runs.all })
          // Toast for runs not triggered by this client
          if (!activeSubscriptions.has(msg.run_id)) {
            toast('New run started', {
              description: `${msg.pipeline_name} (${msg.run_id.slice(0, 8)})`,
              action: {
                label: 'Monitor',
                onClick: () => {
                  subscribeToRun(msg.run_id, msg.pipeline_name, queryClient)
                  useWsStore.getState().setFocusedRun(msg.run_id)
                },
              },
              duration: 8000,
            })
          }
          break

        case 'span_started':
        case 'span_ended':
          applySpanEvent(queryClient, msg.run_id, msg.observation, msg.observation.name)
          useWsStore.getState().updateSubscriptionStatus(msg.run_id, 'running')
          break

        case 'stream_complete':
          writeRunDetailFromComplete(queryClient, msg)
          useWsStore.getState().updateSubscriptionStatus(msg.run_id, msg.status ?? 'completed')
          break

        case 'replay_complete':
          useWsStore.getState().setReplayComplete(msg.run_id)
          break

        case 'review_requested':
          useWsStore.getState().updateSubscriptionStatus(msg.run_id, 'awaiting_review')
          queryClient.invalidateQueries({ queryKey: queryKeys.runs.detail(msg.run_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.runs.all })
          toast.info('Review requested', {
            description: `${msg.pipeline_name} step "${msg.step_name}" needs review`,
            action: {
              label: 'Review',
              onClick: () => { window.location.href = `/review/${msg.token}` },
            },
            duration: 15000,
          })
          break

        case 'review_completed':
          useWsStore.getState().updateSubscriptionStatus(msg.run_id, 'running')
          queryClient.invalidateQueries({ queryKey: queryKeys.runs.detail(msg.run_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.runs.all })
          toast.success('Review completed', {
            description: `${msg.pipeline_name} "${msg.step_name}": ${msg.decision.replace('_', ' ')}`,
          })
          break

        case 'error':
          // Per-run errors (e.g. "Run not found" on subscribe)
          break
      }
    }

    ws.onerror = () => {
      if (!mountedRef.current) return
      setStatus('error')
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      globalWs = null

      // Reconnect with exponential backoff
      if (hadConnectionRef.current) {
        incrementReconnect()
        const count = useWsStore.getState().reconnectCount
        const delay = Math.min(BASE_RECONNECT_DELAY * 2 ** (count - 1), MAX_RECONNECT_DELAY)

        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null
          connectRef.current?.()
        }, delay)
      }
    }
  }, [queryClient, setStatus, setError, setLatestRun, incrementReconnect])

  useEffect(() => {
    const gen = ++mountGeneration
    connectRef.current = connect
    mountedRef.current = true
    hadConnectionRef.current = false

    connect()

    return () => {
      // StrictMode guard: only tear down if no newer mount has taken over
      if (gen !== mountGeneration) return

      mountedRef.current = false

      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }

      if (globalWs) {
        globalWs.onopen = null
        globalWs.onmessage = null
        globalWs.onerror = null
        globalWs.onclose = null
        globalWs.close()
        globalWs = null
      }

      pendingMessages = []
      useWsStore.getState().reset()
    }
  }, [connect])
}

// ---------------------------------------------------------------------------
// Imperative subscription management
// ---------------------------------------------------------------------------

/**
 * Subscribe to a run's live updates. Updates store, sends WS message.
 *
 * The trace data itself is fetched via ``useTrace`` (HTTP). This
 * subscription just tells the server to push span_started / span_ended
 * notifications for this run, which invalidate the trace query and
 * trigger a refetch.
 */
export function subscribeToRun(
  runId: string,
  pipelineName: string,
  qc?: QueryClient,
): void {
  if (activeSubscriptions.has(runId)) return
  // queryClient parameter retained for forward compat but unused now
  // that there is no event cache to seed.
  void qc

  activeSubscriptions.add(runId)
  useWsStore.getState().addSubscription(runId, pipelineName)
  sendWsMessage({ action: 'subscribe', run_id: runId })
}

/**
 * Unsubscribe from a run. Sends WS message, removes from store.
 */
export function unsubscribeFromRun(runId: string): void {
  if (!activeSubscriptions.has(runId)) return
  activeSubscriptions.delete(runId)
  useWsStore.getState().removeSubscription(runId)
  sendWsMessage({ action: 'unsubscribe', run_id: runId })
}

// ---------------------------------------------------------------------------
// useSubscribeRun (hook wrapper for component lifecycle)
// ---------------------------------------------------------------------------

/**
 * Hook wrapper around subscribeToRun for use in components.
 * Does NOT auto-unsubscribe on unmount — subscriptions persist
 * until explicitly removed via unsubscribeFromRun.
 */
export function useSubscribeRun(runId: string | null, pipelineName?: string): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!runId) return
    subscribeToRun(runId, pipelineName ?? 'unknown', queryClient)
  }, [runId, pipelineName, queryClient])
}
