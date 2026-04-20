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
// DATA MODE -- plain expandable JSON tree
// ---------------------------------------------------------------------------

function PrimitiveValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">null</span>
  }
  if (typeof value === 'string') {
    return <span className="text-green-600 dark:text-green-400 whitespace-pre-wrap break-words">"{value}"</span>
  }
  if (typeof value === 'number') {
    return <span className="text-blue-600 dark:text-blue-400">{String(value)}</span>
  }
  if (typeof value === 'boolean') {
    return <span className="text-orange-600">{String(value)}</span>
  }
  return <span className="text-muted-foreground">{String(value)}</span>
}

function DataNode({
  label,
  value,
  depth,
  maxDepth,
}: {
  label: string
  value: unknown
  depth: number
  maxDepth: number
}) {
  const [expanded, setExpanded] = useState(depth < maxDepth)

  if (isObject(value)) {
    const entries = Object.entries(value)
    return (
      <div>
        <button
          type="button"
          className="flex w-full items-center gap-1 py-0.5 font-mono text-xs hover:bg-muted/30 rounded"
          style={{ paddingLeft: `${depth * 16}px` }}
          onClick={() => setExpanded((p) => !p)}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0" />
          )}
          <span className="font-medium">{label}</span>
          {!expanded && (
            <span className="ml-1 text-muted-foreground">
              {'{'}...{entries.length}{'}'}
            </span>
          )}
        </button>
        {expanded && (
          <div>
            {entries.map(([k, v]) => (
              <DataNode key={k} label={k} value={v} depth={depth + 1} maxDepth={maxDepth} />
            ))}
          </div>
        )}
      </div>
    )
  }

  if (isArray(value)) {
    return (
      <div>
        <button
          type="button"
          className="flex w-full items-center gap-1 py-0.5 font-mono text-xs hover:bg-muted/30 rounded"
          style={{ paddingLeft: `${depth * 16}px` }}
          onClick={() => setExpanded((p) => !p)}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0" />
          )}
          <span className="font-medium">{label}</span>
          {!expanded && (
            <span className="ml-1 text-muted-foreground">
              [{value.length}]
            </span>
          )}
        </button>
        {expanded && (
          <div>
            {value.map((item, i) => (
              <DataNode key={i} label={String(i)} value={item} depth={depth + 1} maxDepth={maxDepth} />
            ))}
          </div>
        )}
      </div>
    )
  }

  // Primitive leaf
  return (
    <div
      className="flex items-start gap-1 py-0.5 font-mono text-xs"
      style={{ paddingLeft: `${depth * 16}px` }}
    >
      <span className="shrink-0 w-4" />
      <span className="text-muted-foreground">{label}:</span>{' '}
      <PrimitiveValue value={value} />
    </div>
  )
}

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

  if (isArray(data)) {
    return (
      <div className="space-y-0">
        {data.map((item, i) => (
          <DataNode key={i} label={String(i)} value={item} depth={0} maxDepth={maxDepth} />
        ))}
      </div>
    )
  }

  const entries = Object.entries(data)
  return (
    <div className="space-y-0">
      {entries.map(([k, v]) => (
        <DataNode key={k} label={k} value={v} depth={0} maxDepth={maxDepth} />
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

const diffColors = {
  CREATE: 'bg-green-500/10 text-green-600 dark:text-green-400',
  REMOVE: 'bg-red-500/10 text-red-600 dark:text-red-400 line-through',
  CHANGE: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
} as const

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

// ColoredSubtree -- renders any value as a collapsible tree with inherited color

function ColoredSubtree({
  label,
  value,
  depth,
  colorClass,
  prefix,
}: {
  label: string
  value: unknown
  depth: number
  colorClass: string
  prefix?: string
}) {
  const [expanded, setExpanded] = useState(depth < 4)

  if (isObject(value) || isArray(value)) {
    const entries = isArray(value)
      ? value.map((v, i) => [String(i), v] as const)
      : Object.entries(value)

    return (
      <div>
        <button
          type="button"
          className={cn(
            'flex w-full items-center gap-1 rounded px-1 py-0.5 font-mono text-xs hover:bg-muted/30',
            colorClass,
          )}
          style={{ paddingLeft: `${depth * 16}px` }}
          onClick={() => setExpanded((p) => !p)}
        >
          {prefix && <span className="shrink-0 w-4">{prefix}</span>}
          {!prefix && (
            expanded
              ? <ChevronDown className="h-3 w-3 shrink-0" />
              : <ChevronRight className="h-3 w-3 shrink-0" />
          )}
          <span className="font-medium">{label}</span>
          {!expanded && (
            <span className="ml-1 opacity-60">
              {isArray(value) ? `[${value.length}]` : `{${entries.length}}`}
            </span>
          )}
        </button>
        {expanded && (
          <div>
            {entries.map(([k, v]) => (
              <ColoredSubtree
                key={k}
                label={k}
                value={v}
                depth={depth + 1}
                colorClass={colorClass}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  // Primitive leaf
  return (
    <div
      className={cn('flex items-start gap-1 rounded px-1 py-0.5 font-mono text-xs', colorClass)}
      style={{ paddingLeft: `${depth * 16}px` }}
    >
      <span className="shrink-0 w-4" />
      <span>{label}: {formatValue(value)}</span>
    </div>
  )
}

// DiffNode (memo-wrapped recursive renderer)

interface DiffNodeProps {
  node: DiffTreeNode
  path: string
  depth: number
  isExpanded: (path: string) => boolean
  toggleExpand: (path: string) => void
}

const DiffNode = memo(function DiffNode({
  node,
  path,
  depth,
  isExpanded,
  toggleExpand,
}: DiffNodeProps) {
  // Unchanged leaf
  if (node.unchangedValue !== undefined && !node.diff && !node.children) {
    if (isComplex(node.unchangedValue)) {
      return (
        <ColoredSubtree
          label={node.key}
          value={node.unchangedValue}
          depth={depth}
          colorClass="text-muted-foreground"
        />
      )
    }
    return (
      <div
        className="flex items-start gap-1 py-0.5 font-mono text-xs text-muted-foreground"
        style={{ paddingLeft: `${depth * 16}px` }}
      >
        <span className="shrink-0 w-4" />
        <span className="min-w-0 break-words whitespace-pre-wrap">{node.key}: {formatValue(node.unchangedValue)}</span>
      </div>
    )
  }

  // Leaf with diff
  if (node.diff && !node.children) {
    const d = node.diff
    switch (d.type) {
      case 'CREATE':
        if (isComplex(d.value)) {
          return (
            <ColoredSubtree
              label={node.key}
              value={d.value}
              depth={depth}
              colorClass={diffColors.CREATE}
              prefix="+"
            />
          )
        }
        return (
          <div
            className={cn('flex items-start gap-1 rounded px-1 py-0.5 font-mono text-xs', diffColors.CREATE)}
            style={{ paddingLeft: `${depth * 16}px` }}
          >
            <span className="shrink-0 w-4">+</span>
            <span className="min-w-0 break-words whitespace-pre-wrap">{node.key}: {formatValue(d.value)}</span>
          </div>
        )
      case 'REMOVE':
        if (isComplex(d.oldValue)) {
          return (
            <ColoredSubtree
              label={node.key}
              value={d.oldValue}
              depth={depth}
              colorClass={diffColors.REMOVE}
              prefix="-"
            />
          )
        }
        return (
          <div
            className={cn('flex items-start gap-1 rounded px-1 py-0.5 font-mono text-xs', diffColors.REMOVE)}
            style={{ paddingLeft: `${depth * 16}px` }}
          >
            <span className="shrink-0 w-4">-</span>
            <span className="min-w-0 break-words whitespace-pre-wrap">{node.key}: {formatValue(d.oldValue)}</span>
          </div>
        )
      case 'CHANGE': {
        const oldComplex = isComplex(d.oldValue)
        const newComplex = isComplex(d.value)
        if (oldComplex || newComplex) {
          return (
            <div>
              {oldComplex ? (
                <ColoredSubtree
                  label={node.key}
                  value={d.oldValue}
                  depth={depth}
                  colorClass={diffColors.REMOVE}
                  prefix="-"
                />
              ) : (
                <div
                  className={cn('flex items-start gap-1 rounded px-1 py-0.5 font-mono text-xs', diffColors.REMOVE)}
                  style={{ paddingLeft: `${depth * 16}px` }}
                >
                  <span className="shrink-0 w-4">-</span>
                  <span className="min-w-0 break-words whitespace-pre-wrap">{node.key}: {formatValue(d.oldValue)}</span>
                </div>
              )}
              {newComplex ? (
                <ColoredSubtree
                  label={node.key}
                  value={d.value}
                  depth={depth}
                  colorClass={diffColors.CREATE}
                  prefix="+"
                />
              ) : (
                <div
                  className={cn('flex items-start gap-1 rounded px-1 py-0.5 font-mono text-xs', diffColors.CREATE)}
                  style={{ paddingLeft: `${depth * 16}px` }}
                >
                  <span className="shrink-0 w-4">+</span>
                  <span className="min-w-0 break-words whitespace-pre-wrap">{node.key}: {formatValue(d.value)}</span>
                </div>
              )}
            </div>
          )
        }
        return (
          <div
            className={cn('flex items-start gap-1 rounded px-1 py-0.5 font-mono text-xs', diffColors.CHANGE)}
            style={{ paddingLeft: `${depth * 16}px` }}
          >
            <span className="shrink-0 w-4" />
            <span>
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
          style={{ paddingLeft: `${depth * 16}px` }}
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
