import { useEffect, useRef } from 'react'
import type { EventItem } from '@/api/types'
import type { WsConnectionStatus } from '@/stores/websocket'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { formatRelative } from '@/lib/time'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EventStreamProps {
  events: EventItem[]
  wsStatus: WsConnectionStatus
  runId: string | null
}

// ---------------------------------------------------------------------------
// Event type -> badge config
// ---------------------------------------------------------------------------

type BadgeVariant = 'default' | 'secondary' | 'outline' | 'destructive'

interface EventBadgeConfig {
  variant: BadgeVariant
  className: string
}

/** Map event_type prefixes/names to badge styling. */
function getEventBadgeConfig(eventType: string): EventBadgeConfig {
  if (eventType.startsWith('step_started')) {
    return { variant: 'outline', className: 'border-blue-500 text-blue-600 dark:text-blue-400' }
  }
  if (eventType.startsWith('step_completed')) {
    return { variant: 'outline', className: 'border-green-500 text-green-600 dark:text-green-400' }
  }
  if (eventType.startsWith('step_failed') || eventType.startsWith('pipeline_failed')) {
    return { variant: 'destructive', className: '' }
  }
  if (eventType.startsWith('step_skipped')) {
    return { variant: 'secondary', className: 'text-muted-foreground' }
  }
  if (eventType.startsWith('llm_call')) {
    return { variant: 'outline', className: 'border-purple-500 text-purple-600 dark:text-purple-400' }
  }
  if (eventType.startsWith('extraction') || eventType.startsWith('transformation')) {
    return { variant: 'outline', className: 'border-amber-500 text-amber-600 dark:text-amber-400' }
  }
  if (eventType.startsWith('context')) {
    return { variant: 'outline', className: 'border-teal-500 text-teal-600 dark:text-teal-400' }
  }
  if (eventType.startsWith('pipeline_started') || eventType.startsWith('pipeline_completed')) {
    return { variant: 'default', className: '' }
  }
  // fallback
  return { variant: 'secondary', className: '' }
}

// ---------------------------------------------------------------------------
// Connection status indicator
// ---------------------------------------------------------------------------

const statusDotColors: Record<WsConnectionStatus, string> = {
  idle: 'bg-gray-400',
  connecting: 'bg-yellow-400',
  connected: 'bg-green-500',
  replaying: 'bg-green-500',
  closed: 'bg-muted-foreground',
  error: 'bg-red-500',
}

const statusLabels: Record<WsConnectionStatus, string> = {
  idle: 'Idle',
  connecting: 'Connecting...',
  connected: 'Connected',
  replaying: 'Replaying...',
  closed: 'Disconnected',
  error: 'Error',
}

function ConnectionIndicator({ status }: { status: WsConnectionStatus }) {
  return (
    <div className="flex items-center gap-2 border-b px-3 py-2">
      <span
        className={cn('inline-block h-2 w-2 rounded-full', statusDotColors[status])}
        aria-hidden="true"
      />
      <span className="text-xs text-muted-foreground">{statusLabels[status]}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Auto-scroll threshold (px from bottom to consider "at bottom")
// ---------------------------------------------------------------------------

const SCROLL_THRESHOLD = 40

// ---------------------------------------------------------------------------
// EventStream component
// ---------------------------------------------------------------------------

export function EventStream({ events, wsStatus, runId }: EventStreamProps) {
  const sentinelRef = useRef<HTMLDivElement>(null)
  /** Ref on the inner content wrapper; its parentElement is the scrollable viewport. */
  const contentRef = useRef<HTMLDivElement>(null)
  const autoScrollRef = useRef(true)

  // Handle scroll events to detect user scrolling up.
  // The Radix ScrollArea viewport is the direct parent of our content wrapper,
  // so we walk up one level via parentElement -- no internal selector needed.
  useEffect(() => {
    const viewport = contentRef.current?.parentElement
    if (!(viewport instanceof HTMLElement)) return

    function handleScroll() {
      if (!(viewport instanceof HTMLElement)) return
      const { scrollTop, scrollHeight, clientHeight } = viewport
      const atBottom = scrollHeight - scrollTop - clientHeight < SCROLL_THRESHOLD
      autoScrollRef.current = atBottom
    }

    viewport.addEventListener('scroll', handleScroll, { passive: true })
    return () => viewport.removeEventListener('scroll', handleScroll)
  }, [runId]) // re-attach when run changes (viewport may re-mount)

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (autoScrollRef.current && sentinelRef.current) {
      sentinelRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events.length])

  // -- Empty states --

  if (runId === null) {
    return (
      <div className="flex h-full flex-col">
        <ConnectionIndicator status={wsStatus} />
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-muted-foreground">Waiting for run...</p>
        </div>
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <ConnectionIndicator status={wsStatus} />
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-muted-foreground">No events yet</p>
        </div>
      </div>
    )
  }

  // -- Event list --

  return (
    <div className="flex h-full flex-col">
      <ConnectionIndicator status={wsStatus} />
      <ScrollArea className="flex-1">
        <div ref={contentRef} className="space-y-0.5 p-2">
          {events.map((event, index) => {
            const stepName = (event.event_data?.step_name as string) ?? null
            const config = getEventBadgeConfig(event.event_type)
            return (
              <div
                key={`${event.timestamp}-${index}`}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted/30"
              >
                {/* Timestamp */}
                <span
                  className="shrink-0 text-xs text-muted-foreground tabular-nums"
                  title={event.timestamp}
                >
                  {formatRelative(event.timestamp)}
                </span>

                {/* Event type badge */}
                <Badge variant={config.variant} className={cn('text-[10px]', config.className)}>
                  {event.event_type}
                </Badge>

                {/* Step name (if present) */}
                {stepName && (
                  <span className="min-w-0 truncate text-xs text-muted-foreground">
                    {stepName}
                  </span>
                )}
              </div>
            )
          })}
          {/* Sentinel div for auto-scroll */}
          <div ref={sentinelRef} aria-hidden="true" />
        </div>
      </ScrollArea>
    </div>
  )
}
