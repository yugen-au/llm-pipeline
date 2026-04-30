import { useMemo, useState } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Square,
  Sparkles,
  Database,
  Wrench,
  CheckCircle2,
  XCircle,
  Loader2,
  Box,
} from 'lucide-react'
import { JsonViewer } from '@/components/JsonViewer'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { formatDuration } from '@/lib/time'
import type { TraceObservation } from '@/api/types'

// ---------------------------------------------------------------------------
// Tree construction (parent_observation_id → children)
// ---------------------------------------------------------------------------

interface TreeNode {
  obs: TraceObservation
  children: TreeNode[]
  depth: number
}

function buildTree(observations: TraceObservation[]): TreeNode[] {
  const byId = new Map<string, TreeNode>()
  for (const obs of observations) {
    byId.set(obs.id, { obs, children: [], depth: 0 })
  }
  const roots: TreeNode[] = []
  for (const node of byId.values()) {
    const parentId = node.obs.parent_observation_id
    if (parentId && byId.has(parentId)) {
      const parent = byId.get(parentId)!
      parent.children.push(node)
      node.depth = parent.depth + 1
    } else {
      roots.push(node)
    }
  }
  // Sort each level by start_time
  const sortByStart = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      const at = a.obs.start_time ? new Date(a.obs.start_time).getTime() : 0
      const bt = b.obs.start_time ? new Date(b.obs.start_time).getTime() : 0
      return at - bt
    })
    for (const n of nodes) sortByStart(n.children)
  }
  sortByStart(roots)
  // Re-derive depth after sort (sortByStart preserves)
  const setDepth = (nodes: TreeNode[], d: number) => {
    for (const n of nodes) {
      n.depth = d
      setDepth(n.children, d + 1)
    }
  }
  setDepth(roots, 0)
  return roots
}

// ---------------------------------------------------------------------------
// Type icon
// ---------------------------------------------------------------------------

function TypeIcon({ type, name }: { type: string; name: string }) {
  const className = 'size-3.5 shrink-0'
  if (type === 'GENERATION' || name.startsWith('gen_ai')) {
    return <Sparkles className={cn(className, 'text-purple-500')} />
  }
  if (name.startsWith('extraction.')) {
    return <Database className={cn(className, 'text-blue-500')} />
  }
  if (type === 'TOOL' || name.startsWith('gen_ai.execute_tool')) {
    return <Wrench className={cn(className, 'text-amber-500')} />
  }
  if (name.startsWith('pipeline.')) {
    return <Box className={cn(className, 'text-green-600')} />
  }
  return <Square className={cn(className, 'text-muted-foreground')} />
}

// ---------------------------------------------------------------------------
// Status indicator
// ---------------------------------------------------------------------------

function StatusIndicator({ obs }: { obs: TraceObservation }) {
  // No end_time + has start_time → still running
  if (obs.start_time && !obs.end_time) {
    return <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
  }
  if (obs.level === 'ERROR') {
    return <XCircle className="size-3.5 shrink-0 text-destructive" />
  }
  return <CheckCircle2 className="size-3.5 shrink-0 text-green-600" />
}

// ---------------------------------------------------------------------------
// Generation metrics (model + tokens + cost)
// ---------------------------------------------------------------------------

function GenerationMetrics({ obs }: { obs: TraceObservation }) {
  if (obs.type !== 'GENERATION' && !obs.name.startsWith('gen_ai')) return null
  const parts: string[] = []
  if (obs.model) parts.push(obs.model)
  if (obs.input_tokens != null && obs.output_tokens != null) {
    parts.push(`${obs.input_tokens}→${obs.output_tokens} tok`)
  } else if (obs.total_tokens != null) {
    parts.push(`${obs.total_tokens} tok`)
  }
  if (obs.total_cost != null && obs.total_cost > 0) {
    parts.push(`$${obs.total_cost.toFixed(4)}`)
  }
  if (parts.length === 0) return null
  return <span className="text-xs text-muted-foreground">{parts.join('  ·  ')}</span>
}

// ---------------------------------------------------------------------------
// Single row
// ---------------------------------------------------------------------------

function ObservationRow({ node }: { node: TreeNode }) {
  const [expanded, setExpanded] = useState(false)
  const { obs, depth, children } = node
  const hasDetail = obs.input != null || obs.output != null
  const hasChildren = children.length > 0
  const expandable = hasDetail || hasChildren

  return (
    <>
      <div
        className={cn(
          'group flex items-center gap-2 rounded px-2 py-1 hover:bg-muted/40',
          expandable && 'cursor-pointer',
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => expandable && setExpanded(!expanded)}
      >
        {expandable ? (
          expanded ? (
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
          )
        ) : (
          <span className="w-3.5 shrink-0" />
        )}

        <TypeIcon type={obs.type} name={obs.name} />

        <span className="truncate text-sm font-mono">{obs.name}</span>

        <div className="ml-auto flex items-center gap-3">
          <GenerationMetrics obs={obs} />
          {obs.duration_ms != null && (
            <span className="tabular-nums text-xs text-muted-foreground">
              {formatDuration(Math.round(obs.duration_ms))}
            </span>
          )}
          <StatusIndicator obs={obs} />
        </div>
      </div>

      {expanded && hasDetail && (
        <div
          className="border-l border-muted/60 px-3 py-2 text-xs"
          style={{ marginLeft: `${depth * 16 + 22}px` }}
        >
          {obs.input != null && (
            <div className="mb-2">
              <div className="mb-1 font-medium text-muted-foreground">input</div>
              <JsonViewer data={obs.input as Record<string, unknown>} />
            </div>
          )}
          {obs.output != null && (
            <div>
              <div className="mb-1 font-medium text-muted-foreground">output</div>
              <JsonViewer data={obs.output as Record<string, unknown>} />
            </div>
          )}
        </div>
      )}

      {expanded && children.map((child) => (
        <ObservationRow key={child.obs.id} node={child} />
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Top-level component
// ---------------------------------------------------------------------------

export interface TraceTimelineProps {
  observations: TraceObservation[]
  isLoading?: boolean
  isError?: boolean
  emptyMessage?: string
  className?: string
}

/**
 * Hierarchical view of a Langfuse trace's observations.
 *
 * Builds the parent/child tree from `parent_observation_id` and renders
 * each row with type-specific iconography. Generation observations
 * surface model + token + cost metrics inline. Click any observation
 * with input/output to expand the detail panel.
 *
 * Designed to update in place when its `observations` prop changes —
 * paired with `useTrace` (HTTP polling) + WebSocket invalidation, the
 * timeline reflects live pipeline state without per-component
 * subscriptions.
 */
export function TraceTimeline({
  observations,
  isLoading,
  isError,
  emptyMessage = 'No observations yet',
  className,
}: TraceTimelineProps) {
  const tree = useMemo(() => buildTree(observations), [observations])

  if (isLoading && observations.length === 0) {
    return (
      <div className="flex flex-col gap-1 p-2">
        {Array.from({ length: 4 }, (_, i) => (
          <div
            key={i}
            className="h-7 animate-pulse rounded bg-muted/60"
            style={{ marginLeft: `${(i % 3) * 16}px` }}
          />
        ))}
      </div>
    )
  }
  if (isError) {
    return (
      <div className="p-3 text-sm text-destructive">
        Failed to load trace data.
      </div>
    )
  }
  if (tree.length === 0) {
    return (
      <div className="p-3 text-sm text-muted-foreground">{emptyMessage}</div>
    )
  }

  return (
    <ScrollArea className={cn('h-full', className)}>
      <div className="flex flex-col py-1 text-sm">
        {tree.map((root) => (
          <ObservationRow key={root.obs.id} node={root} />
        ))}
      </div>
    </ScrollArea>
  )
}
