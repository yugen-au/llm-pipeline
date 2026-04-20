import { memo, useMemo, useState, useCallback } from 'react'
import diff from 'microdiff'
import type { Difference } from 'microdiff'
import { ChevronRight, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function isObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

function isArray(v: unknown): v is unknown[] {
  return Array.isArray(v)
}

function isComplex(v: unknown): boolean {
  return isObject(v) || isArray(v)
}

function formatValue(value: unknown): string {
  if (value === null) return 'null'
  if (value === undefined) return 'undefined'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'object') {
    try {
      const s = JSON.stringify(value)
      return s.length > 80 ? JSON.stringify(value, null, 2) : s
    } catch {
      return String(value)
    }
  }
  return String(value)
}

// ---------------------------------------------------------------------------
// Shared style tokens
// ---------------------------------------------------------------------------

type DiffState = 'unchanged' | 'added' | 'removed' | 'changed' | 'muted'

const stateStyles: Record<DiffState, string> = {
  unchanged: '',
  added: 'bg-green-500/10 text-green-600 dark:text-green-400',
  removed: 'bg-red-500/10 text-red-600 dark:text-red-400 line-through',
  changed: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
  muted: 'text-muted-foreground',
}

const statePrefix: Partial<Record<DiffState, string>> = {
  added: '+',
  removed: '-',
}

const rowClasses = 'flex items-start gap-1 py-0.5 font-mono text-xs min-w-0'
const valueClasses = 'min-w-0 break-all whitespace-pre-wrap'
const INDENT_PX = 16

// ---------------------------------------------------------------------------
// PrimitiveValue -- used only for unchanged primitive leaves in data mode
// where each type gets its own color. Diff-state leaves use formatValue +
// the state color wholesale.
// ---------------------------------------------------------------------------

function PrimitiveValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">null</span>
  }
  if (typeof value === 'string') {
    return <span className={cn('text-green-600 dark:text-green-400', valueClasses)}>"{value}"</span>
  }
  if (typeof value === 'number') {
    return <span className="text-blue-600 dark:text-blue-400">{String(value)}</span>
  }
  if (typeof value === 'boolean') {
    return <span className="text-orange-600">{String(value)}</span>
  }
  return <span className="text-muted-foreground">{String(value)}</span>
}

// ---------------------------------------------------------------------------
// JsonNode -- the single recursive renderer used by both data and diff modes
// ---------------------------------------------------------------------------

interface JsonNodeProps {
  label: string
  value: unknown
  depth: number
  maxDepth: number
  state?: DiffState
  // Controlled-expansion hooks (used by DiffView to share expand state across
  // branch nodes keyed by path). When omitted, JsonNode manages its own
  // internal expand state.
  path?: string
  isExpanded?: (path: string) => boolean
  toggleExpand?: (path: string) => void
  // When rendering a branch node on the unchanged path of a diff, we still
  // want the "N changes" summary when collapsed. Callers can supply a count.
  collapsedSummary?: string
}

function JsonNode({
  label,
  value,
  depth,
  maxDepth,
  state = 'unchanged',
  path,
  isExpanded,
  toggleExpand,
  collapsedSummary,
}: JsonNodeProps) {
  const [localExpanded, setLocalExpanded] = useState(depth < maxDepth)
  const controlled = path !== undefined && isExpanded !== undefined && toggleExpand !== undefined
  const expanded = controlled ? isExpanded(path) : localExpanded
  const toggle = controlled
    ? () => toggleExpand(path)
    : () => setLocalExpanded((p) => !p)

  const colorClass = stateStyles[state]
  const prefix = statePrefix[state]
  const paddingLeft = `${depth * INDENT_PX}px`

  if (isComplex(value)) {
    const entries = isArray(value)
      ? value.map((v, i) => [String(i), v] as const)
      : Object.entries(value as Record<string, unknown>)

    const summary = !expanded
      ? collapsedSummary
        ?? (isArray(value) ? `[${value.length}]` : `{...${entries.length}}`)
      : null

    return (
      <div>
        <button
          type="button"
          className={cn(
            'flex w-full items-center gap-1 rounded py-0.5 font-mono text-xs hover:bg-muted/30',
            prefix ? 'px-1' : '',
            colorClass,
          )}
          style={{ paddingLeft }}
          onClick={toggle}
        >
          {prefix ? (
            <span className="shrink-0 w-4">{prefix}</span>
          ) : expanded ? (
            <ChevronDown className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0" />
          )}
          <span className="font-medium">{label}</span>
          {summary && (
            <span className={cn('ml-1', state === 'unchanged' ? 'text-muted-foreground' : 'opacity-60')}>
              {summary}
            </span>
          )}
        </button>
        {expanded && (
          <div>
            {entries.map(([k, v]) => (
              <JsonNode
                key={k}
                label={k}
                value={v}
                depth={depth + 1}
                maxDepth={maxDepth}
                state={state}
                path={controlled ? `${path}.${k}` : undefined}
                isExpanded={isExpanded}
                toggleExpand={toggleExpand}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  // Primitive leaf
  if (state === 'unchanged') {
    return (
      <div
        className={rowClasses}
        style={{ paddingLeft }}
      >
        <span className="shrink-0 w-4" />
        <span className="text-muted-foreground">{label}:</span>{' '}
        <PrimitiveValue value={value} />
      </div>
    )
  }

  if (state === 'muted') {
    return (
      <div
        className={cn(rowClasses, colorClass)}
        style={{ paddingLeft }}
      >
        <span className="shrink-0 w-4" />
        <span className={valueClasses}>{label}: {formatValue(value)}</span>
      </div>
    )
  }

  return (
    <div
      className={cn(rowClasses, 'rounded px-1', colorClass)}
      style={{ paddingLeft }}
    >
      <span className="shrink-0 w-4">{prefix ?? ''}</span>
      <span className={valueClasses}>{label}: {formatValue(value)}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DATA MODE -- thin wrapper over JsonNode
// ---------------------------------------------------------------------------

function DataView({
  data,
  maxDepth,
}: {
  data: Record<string, unknown> | unknown[] | null
  maxDepth: number
}) {
  if (data === null || data === undefined) {
    return <span className="text-muted-foreground italic text-xs font-mono">null</span>
  }

  const entries = isArray(data)
    ? data.map((v, i) => [String(i), v] as const)
    : Object.entries(data)

  return (
    <div className="space-y-0">
      {entries.map(([k, v]) => (
        <JsonNode key={k} label={k} value={v} depth={0} maxDepth={maxDepth} />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// DIFF MODE -- microdiff-powered diff tree
// ---------------------------------------------------------------------------

interface DiffTreeNode {
  key: string
  diff?: Difference
  children?: DiffTreeNode[]
  unchangedValue?: unknown
}

function buildDiffTree(
  diffs: Difference[],
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): DiffTreeNode[] {
  const grouped = new Map<string | number, Difference[]>()
  for (const d of diffs) {
    const key = d.path[0]
    const existing = grouped.get(key)
    if (existing) {
      existing.push(d)
    } else {
      grouped.set(key, [d])
    }
  }

  const nodes: DiffTreeNode[] = []
  const changedKeys = new Set<string>()

  for (const [key, group] of grouped) {
    changedKeys.add(String(key))
    const strKey = String(key)
    const allLeaf = group.every((d) => d.path.length === 1)

    if (allLeaf) {
      nodes.push({ key: strKey, diff: group[0] })
    } else {
      const shifted: Difference[] = group.map((d) => ({
        ...d,
        path: d.path.slice(1),
      })) as Difference[]

      const nestedBefore = (before[strKey] ?? {}) as Record<string, unknown>
      const nestedAfter = (after[strKey] ?? {}) as Record<string, unknown>
      const leafDiffs = group.filter((d) => d.path.length === 1)
      const nestedDiffs = group.filter((d) => d.path.length > 1)

      if (leafDiffs.length > 0 && nestedDiffs.length > 0) {
        nodes.push({ key: strKey, diff: leafDiffs[0] })
      } else {
        const children = buildDiffTree(shifted, nestedBefore, nestedAfter)
        nodes.push({ key: strKey, children })
      }
    }
  }

  const allAfterKeys = Object.keys(after)
  for (const key of allAfterKeys) {
    if (!changedKeys.has(key)) {
      nodes.push({ key, unchangedValue: after[key] })
    }
  }

  nodes.sort((a, b) => {
    const aChanged = a.diff != null || a.children != null
    const bChanged = b.diff != null || b.children != null
    if (aChanged !== bChanged) return aChanged ? -1 : 1
    return a.key.localeCompare(b.key)
  })

  return nodes
}

function countDiffs(node: DiffTreeNode): number {
  if (node.diff) return 1
  if (node.children) {
    return node.children.reduce((sum, child) => sum + countDiffs(child), 0)
  }
  return 0
}

function collectPaths(nodes: DiffTreeNode[], prefix: string, maxDepth: number, depth: number): string[] {
  const paths: string[] = []
  for (const node of nodes) {
    if (!node.children) continue
    const path = prefix ? `${prefix}.${node.key}` : node.key
    if (depth < maxDepth) {
      paths.push(path)
    }
    paths.push(...collectPaths(node.children, path, maxDepth, depth + 1))
  }
  return paths
}

// ---------------------------------------------------------------------------
// DiffNode -- walks the diff tree and renders each node via JsonNode with the
// correct state. CHANGE renders stacked removed-above-added rows/subtrees.
// ---------------------------------------------------------------------------

interface DiffNodeProps {
  node: DiffTreeNode
  path: string
  depth: number
  maxDepth: number
  isExpanded: (path: string) => boolean
  toggleExpand: (path: string) => void
}

const DiffNode = memo(function DiffNode({
  node,
  path,
  depth,
  maxDepth,
  isExpanded,
  toggleExpand,
}: DiffNodeProps) {
  // Unchanged key (sibling of a change) -- render muted
  if (node.unchangedValue !== undefined && !node.diff && !node.children) {
    return (
      <JsonNode
        label={node.key}
        value={node.unchangedValue}
        depth={depth}
        maxDepth={maxDepth}
        state="muted"
      />
    )
  }

  // Leaf with diff
  if (node.diff && !node.children) {
    const d = node.diff
    switch (d.type) {
      case 'CREATE':
        return (
          <JsonNode
            label={node.key}
            value={d.value}
            depth={depth}
            maxDepth={maxDepth}
            state="added"
          />
        )
      case 'REMOVE':
        return (
          <JsonNode
            label={node.key}
            value={d.oldValue}
            depth={depth}
            maxDepth={maxDepth}
            state="removed"
          />
        )
      case 'CHANGE': {
        const oldComplex = isComplex(d.oldValue)
        const newComplex = isComplex(d.value)
        if (oldComplex || newComplex) {
          return (
            <div>
              <JsonNode
                label={node.key}
                value={d.oldValue}
                depth={depth}
                maxDepth={maxDepth}
                state="removed"
              />
              <JsonNode
                label={node.key}
                value={d.value}
                depth={depth}
                maxDepth={maxDepth}
                state="added"
              />
            </div>
          )
        }
        // Primitive change: inline old -> new on one row
        return (
          <div
            className={cn(rowClasses, 'rounded px-1', stateStyles.changed)}
            style={{ paddingLeft: `${depth * INDENT_PX}px` }}
          >
            <span className="shrink-0 w-4" />
            <span className={valueClasses}>
              {node.key}: {formatValue(d.oldValue)}{' '}
              <span className="opacity-60">&rarr;</span>{' '}
              {formatValue(d.value)}
            </span>
          </div>
        )
      }
    }
  }

  // Branch node with children
  if (node.children) {
    const expanded = isExpanded(path)
    const changeCount = countDiffs(node)

    return (
      <div>
        <button
          type="button"
          className="flex w-full items-center gap-1 py-0.5 font-mono text-xs hover:bg-muted/30 rounded"
          style={{ paddingLeft: `${depth * INDENT_PX}px` }}
          onClick={() => toggleExpand(path)}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0" />
          )}
          <span className="font-medium">{node.key}</span>
          {!expanded && changeCount > 0 && (
            <span className="ml-1 text-muted-foreground">
              {'{'}
              {changeCount} change{changeCount !== 1 ? 's' : ''}
              {'}'}
            </span>
          )}
        </button>
        {expanded && (
          <div>
            {node.children.map((child) => (
              <DiffNode
                key={child.key}
                node={child}
                path={path ? `${path}.${child.key}` : child.key}
                depth={depth + 1}
                maxDepth={maxDepth}
                isExpanded={isExpanded}
                toggleExpand={toggleExpand}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  return null
})

function DiffView({
  before,
  after,
  maxDepth,
}: {
  before: Record<string, unknown>
  after: Record<string, unknown>
  maxDepth: number
}) {
  const diffs = useMemo(
    () => diff(before, after, { cyclesFix: false }),
    [before, after],
  )

  const tree = useMemo(
    () => buildDiffTree(diffs, before, after),
    [diffs, before, after],
  )

  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const paths = collectPaths(tree, '', maxDepth, 0)
    return new Set(paths)
  })

  const isExpanded = useCallback(
    (path: string) => expanded.has(path),
    [expanded],
  )

  const toggleExpand = useCallback(
    (path: string) => {
      setExpanded((prev) => {
        const next = new Set(prev)
        if (next.has(path)) {
          next.delete(path)
        } else {
          next.add(path)
        }
        return next
      })
    },
    [],
  )

  if (diffs.length === 0) {
    return <p className="text-xs text-muted-foreground">No changes</p>
  }

  return (
    <div className="space-y-0">
      {tree.map((node) => (
        <DiffNode
          key={node.key}
          node={node}
          path={node.key}
          depth={0}
          maxDepth={maxDepth}
          isExpanded={isExpanded}
          toggleExpand={toggleExpand}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// JsonViewer (public export)
// ---------------------------------------------------------------------------

type JsonViewerProps =
  | { data: Record<string, unknown> | unknown[] | null; before?: never; after?: never; maxDepth?: number }
  | { data?: never; before: Record<string, unknown>; after: Record<string, unknown>; maxDepth?: number }

export function JsonViewer(props: JsonViewerProps) {
  if ('before' in props && props.before !== undefined) {
    return <DiffView before={props.before} after={props.after} maxDepth={props.maxDepth ?? 3} />
  }
  return <DataView data={props.data} maxDepth={props.maxDepth ?? 2} />
}
