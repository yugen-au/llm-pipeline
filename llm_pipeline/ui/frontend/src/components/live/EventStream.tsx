import { useEffect, useRef, useState } from 'react'
import type { EventItem } from '@/api/types'
import type { WsConnectionStatus } from '@/stores/websocket'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip'
import { JsonViewer } from '@/components/JsonViewer'
import { ChevronRight, ChevronDown } from 'lucide-react'
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
    return { variant: 'outline', className: 'border-status-running text-status-running' }
  }
  if (eventType.startsWith('step_completed')) {
    return { variant: 'outline', className: 'border-status-completed text-status-completed' }
  }
  if (eventType.startsWith('step_failed') || eventType.startsWith('pipeline_failed')) {
    return { variant: 'outline', className: 'border-status-failed text-status-failed' }
  }
  if (eventType.startsWith('step_skipped')) {
    return { variant: 'outline', className: 'border-status-skipped text-status-skipped' }
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
  if (eventType.startsWith('tool_call')) {
    return { variant: 'outline', className: 'border-cyan-500 text-cyan-600 dark:text-cyan-400' }
  }
  if (eventType.startsWith('pipeline_started') || eventType.startsWith('pipeline_completed')) {
    return { variant: 'default', className: '' }
  }
  // fallback
  return { variant: 'secondary', className: '' }
}

// ---------------------------------------------------------------------------
// Event summary for tooltip (type-aware)
// ---------------------------------------------------------------------------

/** Keys already visible in the row -- filter from expanded display. */
const REDUNDANT_KEYS = new Set([
  'event_type', 'run_id', 'pipeline_name', 'timestamp', 'step_name',
])

type SummarySpec = Record<string, string[]>

const SUMMARY_FIELDS: SummarySpec = {
  step_started: ['step_number', 'system_key', 'user_key'],
  step_completed: ['step_number', 'execution_time_ms', 'total_tokens', 'cost_usd'],
  step_skipped: ['step_number', 'reason'],
  llm_call_starting: ['call_index'],
  llm_call_completed: ['call_index', 'model_name', 'total_tokens', 'cost_usd', 'attempt_count'],
  llm_call_retry: ['attempt', 'max_retries', 'error_message'],
  llm_call_failed: ['max_retries', 'last_error'],
  extraction_completed: ['extraction_class', 'instance_count', 'execution_time_ms'],
  extraction_error: ['extraction_class', 'error_message'],
  tool_call_starting: ['tool_name'],
  tool_call_completed: ['tool_name', 'execution_time_ms', 'error'],
  context_updated: ['new_keys'],
  pipeline_completed: ['execution_time_ms', 'steps_executed'],
  pipeline_error: ['error_type', 'error_message'],
  cache_hit: ['input_hash', 'cached_at'],
}

function formatSummaryValue(v: unknown): string {
  if (v === null || v === undefined) return 'null'
  if (typeof v === 'object') {
    if (Array.isArray(v)) return `[${v.length}]`
    const keys = Object.keys(v)
    return `{${keys.length}}`
  }
  return String(v)
}

/** Return tooltip summary lines for an event. */
export function getEventSummary(event: EventItem): string[] {
  const data = event.event_data
  if (!data || Object.keys(data).length === 0) return []

  // Check for validation_errors count (special case for llm_call_completed)
  const addValidationErrors = event.event_type === 'llm_call_completed'
    && data.validation_errors
    && Array.isArray(data.validation_errors)

  const fields = SUMMARY_FIELDS[event.event_type]
  if (fields) {
    const lines: string[] = []
    for (const key of fields) {
      if (key in data && data[key] !== undefined) {
        lines.push(`${key}: ${formatSummaryValue(data[key])}`)
      }
    }
    if (addValidationErrors) {
      lines.push(`validation_errors: ${(data.validation_errors as unknown[]).length}`)
    }
    return lines
  }

  // Fallback: first 4 non-redundant keys
  const lines: string[] = []
  for (const [key, val] of Object.entries(data)) {
    if (REDUNDANT_KEYS.has(key)) continue
    lines.push(`${key}: ${formatSummaryValue(val)}`)
    if (lines.length >= 4) break
  }
  return lines
}

/** Filter redundant keys from event_data for expanded display. */
export function getDisplayData(event: EventItem): Record<string, unknown> {
  const data = event.event_data
  if (!data) return {}
  const filtered: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(data)) {
    if (!REDUNDANT_KEYS.has(key)) {
      filtered[key] = val
    }
  }
  return filtered
}

/** Whether an event has meaningful data to expand. */
function hasExpandableData(event: EventItem): boolean {
  return Object.keys(getDisplayData(event)).length > 0
}

// ---------------------------------------------------------------------------
// Connection status indicator
// ---------------------------------------------------------------------------

const statusDotColors: Record<WsConnectionStatus, string> = {
  idle: 'bg-gray-400',
  connecting: 'bg-yellow-400',
  connected: 'bg-green-500',
  error: 'bg-red-500',
}

const statusLabels: Record<WsConnectionStatus, string> = {
  idle: 'Idle',
  connecting: 'Connecting...',
  connected: 'Connected',
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
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null)

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

  // Reset expanded index when run changes
  useEffect(() => {
    setExpandedIndex(null)
  }, [runId])

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
      <ScrollArea className="min-h-0 flex-1">
        <TooltipProvider>
          <div ref={contentRef} className="space-y-0.5 p-2">
            {events.map((event, index) => {
              const stepName = (event.event_data?.step_name as string) ?? null
              const config = getEventBadgeConfig(event.event_type)
              const expandable = hasExpandableData(event)
              const isExpanded = expandedIndex === index
              const summaryLines = getEventSummary(event)

              const row = (
                <div
                  key={`${event.timestamp}-${index}`}
                  data-testid={`event-row-${index}`}
                >
                  <div
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                      expandable
                        ? 'cursor-pointer hover:bg-muted/50'
                        : 'hover:bg-muted/30',
                      isExpanded && 'bg-muted/40',
                    )}
                    onClick={expandable ? () => setExpandedIndex(isExpanded ? null : index) : undefined}
                    role={expandable ? 'button' : undefined}
                    tabIndex={expandable ? 0 : undefined}
                    onKeyDown={expandable ? (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        setExpandedIndex(isExpanded ? null : index)
                      }
                    } : undefined}
                  >
                    {/* Expand indicator */}
                    {expandable ? (
                      <span className="shrink-0 text-muted-foreground" aria-hidden="true">
                        {isExpanded
                          ? <ChevronDown className="h-3 w-3" />
                          : <ChevronRight className="h-3 w-3" />}
                      </span>
                    ) : (
                      <span className="shrink-0 w-3" aria-hidden="true" />
                    )}

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

                  {/* Expanded detail panel */}
                  {isExpanded && (
                    <div
                      className="ml-5 border-l-2 border-muted pl-3 py-2"
                      data-testid={`event-detail-${index}`}
                    >
                      <JsonViewer data={getDisplayData(event)} maxDepth={2} />
                    </div>
                  )}
                </div>
              )

              // Wrap in tooltip if there are summary lines
              if (summaryLines.length > 0) {
                return (
                  <Tooltip key={`${event.timestamp}-${index}`}>
                    <TooltipTrigger asChild>{row}</TooltipTrigger>
                    <TooltipContent side="right" className="max-w-xs font-mono text-[11px] leading-relaxed">
                      {summaryLines.map((line, i) => (
                        <div key={i}>{line}</div>
                      ))}
                    </TooltipContent>
                  </Tooltip>
                )
              }

              return row
            })}
            {/* Sentinel div for auto-scroll */}
            <div ref={sentinelRef} aria-hidden="true" />
          </div>
        </TooltipProvider>
      </ScrollArea>
    </div>
  )
}
