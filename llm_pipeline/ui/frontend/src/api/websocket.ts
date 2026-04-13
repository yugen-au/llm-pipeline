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
  EventListResponse,
  EventItem,
  StepListItem,
  StepListResponse,
  RunDetail,
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
 * Control messages have a `type` field. Raw pipeline events only have
 * `event_type`; this function tags them with `type: 'pipeline_event'`
 * and normalizes the shape to match EventItem (top-level keys extracted,
 * rest nested into event_data).
 */
function parseWsMessage(data: string): WsMessage | null {
  let raw: Record<string, unknown>
  try {
    raw = JSON.parse(data) as Record<string, unknown>
  } catch {
    return null
  }

  // Control messages already have `type`; pass through
  if (typeof raw.type === 'string') {
    return raw as unknown as WsMessage
  }

  // Raw pipeline events have `event_type` but no `type`; normalize
  if (typeof raw.event_type === 'string') {
    const { event_type, run_id, pipeline_name, timestamp, ...rest } = raw
    return {
      type: 'pipeline_event',
      event_type: event_type as string,
      run_id: (run_id as string) ?? '',
      pipeline_name: (pipeline_name as string) ?? '',
      timestamp: (timestamp as string) ?? '',
      event_data: rest as Record<string, unknown>,
    } as unknown as WsMessage
  }

  return null
}

// ---------------------------------------------------------------------------
// Cache helpers
// ---------------------------------------------------------------------------

/**
 * Append a pipeline event to the events query cache for a run.
 * Also writes to step-filtered cache if the event has a step_name.
 */
/** Deduplicated append -- skips if an event with same timestamp+type already cached. */
function appendIfNew(items: EventItem[], event: EventItem): EventItem[] | null {
  const isDup = items.some(
    (e) => e.timestamp === event.timestamp && e.event_type === event.event_type,
  )
  return isDup ? null : [...items, event]
}

function appendEventToCache(qc: QueryClient, runId: string, event: EventItem): void {
  // Append to unfiltered events cache
  qc.setQueryData<EventListResponse>(queryKeys.runs.events(runId, {}), (old) => {
    if (!old) return undefined
    const updated = appendIfNew(old.items, event)
    return updated ? { ...old, items: updated, total: old.total + 1 } : old
  })

  // Fan-out to step-filtered cache if event has step_name
  const stepName = event.event_data?.step_name as string | undefined
  if (stepName) {
    qc.setQueryData<EventListResponse>(
      queryKeys.runs.events(runId, { step_name: stepName }),
      (old) => {
        if (!old) return undefined
        const updated = appendIfNew(old.items, event)
        return updated ? { ...old, items: updated, total: old.total + 1 } : old
      },
    )
  }
}

/**
 * Upsert a step into the steps query cache from a step_completed event.
 * Preserves existing `model` field since it's not in the event payload.
 */
function upsertStepFromEvent(qc: QueryClient, runId: string, event: EventItem): void {
  const ed = event.event_data
  const stepName = ed.step_name as string | undefined
  const stepNumber = ed.step_number as number | undefined
  if (!stepName || stepNumber == null) return

  const newStep: StepListItem = {
    step_name: stepName,
    step_number: stepNumber,
    execution_time_ms: (ed.execution_time_ms as number) ?? null,
    model: null, // not available in event; preserve existing if present
    created_at: event.timestamp,
  }

  qc.setQueryData<StepListResponse>(queryKeys.runs.steps(runId), (old) => {
    if (!old) return { items: [newStep] }
    const idx = old.items.findIndex((s) => s.step_number === stepNumber)
    if (idx >= 0) {
      // Preserve model from existing entry
      const existing = old.items[idx]
      const updated = { ...newStep, model: existing.model }
      const items = [...old.items]
      items[idx] = updated
      return { ...old, items }
    }
    return { ...old, items: [...old.items, newStep] }
  })
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

        case 'pipeline_event':
          appendEventToCache(queryClient, msg.run_id, msg)
          // Update subscription status to running
          useWsStore.getState().updateSubscriptionStatus(msg.run_id, 'running')
          if (msg.event_type === 'step_completed') {
            upsertStepFromEvent(queryClient, msg.run_id, msg)
          }
          if (msg.event_type.includes('step') && msg.event_type !== 'step_completed') {
            queryClient.invalidateQueries({
              queryKey: queryKeys.runs.steps(msg.run_id),
            })
          }
          break

        case 'stream_complete':
          writeRunDetailFromComplete(queryClient, msg)
          useWsStore.getState().updateSubscriptionStatus(msg.run_id, msg.status ?? 'completed')
          break

        case 'replay_complete':
          useWsStore.getState().setReplayComplete(msg.run_id)
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
 * Subscribe to a run's events. Can be called from event handlers, toast
 * callbacks, etc. Seeds event cache, updates store, sends WS message.
 */
export function subscribeToRun(
  runId: string,
  pipelineName: string,
  qc?: QueryClient,
): void {
  if (activeSubscriptions.has(runId)) return

  // Seed event cache
  const queryClient = qc ?? cachedQueryClient
  if (queryClient) {
    queryClient.setQueryData(
      queryKeys.runs.events(runId, {}),
      (old: EventListResponse | undefined) =>
        old ?? { items: [], total: 0, offset: 0, limit: 50 },
    )
  }

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
