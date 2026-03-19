import { memo, useMemo, useState, useCallback } from 'react'
import diff from 'microdiff'
import type { Difference } from 'microdiff'
import { ChevronRight, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface JsonDiffProps {
  before: Record<string, unknown>
  after: Record<string, unknown>
  maxDepth?: number
}

interface DiffTreeNode {
  key: string
  diff?: Difference
  children?: DiffTreeNode[]
  unchangedValue?: unknown
}

// ---------------------------------------------------------------------------
// Color classes (dual-theme, matches StatusBadge / StepTimeline patterns)
// ---------------------------------------------------------------------------

const diffColors = {
  CREATE: 'bg-green-500/10 text-green-600 dark:text-green-400',
  REMOVE: 'bg-red-500/10 text-red-600 dark:text-red-400 line-through',
  CHANGE: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
} as const

// ---------------------------------------------------------------------------
// Tree construction from microdiff flat output
// ---------------------------------------------------------------------------

function buildDiffTree(
  diffs: Difference[],
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): DiffTreeNode[] {
  // Group diffs by first path segment
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

  // Process changed keys (normalize to string -- Object.keys returns strings
  // but microdiff path segments can be numeric for array indices)
  const changedKeys = new Set<string>()
  for (const [key, group] of grouped) {
    changedKeys.add(String(key))
    const strKey = String(key)

    // Check if all diffs in group are leaf-level (path.length === 1)
    const allLeaf = group.every((d) => d.path.length === 1)

    if (allLeaf) {
      // Leaf node -- use the single diff directly
      nodes.push({ key: strKey, diff: group[0] })
    } else {
      // Branch node -- recurse with shifted paths
      const shifted: Difference[] = group.map((d) => ({
        ...d,
        path: d.path.slice(1),
      })) as Difference[]

      // Resolve nested before/after objects for recursion
      const nestedBefore = (before[strKey] ?? {}) as Record<string, unknown>
      const nestedAfter = (after[strKey] ?? {}) as Record<string, unknown>

      // Mix of leaf and nested diffs: separate them
      const leafDiffs = group.filter((d) => d.path.length === 1)
      const nestedDiffs = group.filter((d) => d.path.length > 1)

      if (leafDiffs.length > 0 && nestedDiffs.length > 0) {
        // Key itself changed AND has nested changes -- treat whole key as leaf
        nodes.push({ key: strKey, diff: leafDiffs[0] })
      } else {
        const children = buildDiffTree(
          shifted,
          nestedBefore,
          nestedAfter,
        )
        nodes.push({ key: strKey, children })
      }
    }
  }

  // Add unchanged keys from `after`
  const allAfterKeys = Object.keys(after)
  for (const key of allAfterKeys) {
    if (!changedKeys.has(key)) {
      nodes.push({ key, unchangedValue: after[key] })
    }
  }

  // Sort: changed keys first, then unchanged, alphabetical within each group
  nodes.sort((a, b) => {
    const aChanged = a.diff != null || a.children != null
    const bChanged = b.diff != null || b.children != null
    if (aChanged !== bChanged) return aChanged ? -1 : 1
    return a.key.localeCompare(b.key)
  })

  return nodes
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function countDiffs(node: DiffTreeNode): number {
  if (node.diff) return 1
  if (node.children) {
    return node.children.reduce((sum, child) => sum + countDiffs(child), 0)
  }
  return 0
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
// ColoredSubtree -- renders any value as a collapsible tree with inherited color
// ---------------------------------------------------------------------------

const isObject = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === 'object' && !Array.isArray(v)
const isArray = (v: unknown): v is unknown[] => Array.isArray(v)
const isComplex = (v: unknown): boolean => isObject(v) || isArray(v)

interface ColoredSubtreeProps {
  label: string
  value: unknown
  depth: number
  colorClass: string
  prefix?: string
}

function ColoredSubtree({ label, value, depth, colorClass, prefix }: ColoredSubtreeProps) {
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

// ---------------------------------------------------------------------------
// DiffNode (memo-wrapped recursive renderer)
// ---------------------------------------------------------------------------

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
        <span>{node.key}: {formatValue(node.unchangedValue)}</span>
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
            <span>{node.key}: {formatValue(d.value)}</span>
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
            <span>{node.key}: {formatValue(d.oldValue)}</span>
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
                  <span>{node.key}: {formatValue(d.oldValue)}</span>
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
                  <span>{node.key}: {formatValue(d.value)}</span>
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

// ---------------------------------------------------------------------------
// JsonDiff (public named export)
// ---------------------------------------------------------------------------

export function JsonDiff({ before, after, maxDepth = 3 }: JsonDiffProps) {
  const diffs = useMemo(
    () => diff(before, after, { cyclesFix: false }),
    [before, after],
  )

  const tree = useMemo(
    () => buildDiffTree(diffs, before, after),
    [diffs, before, after],
  )

  // Initialize expanded paths: all branch paths at depth < maxDepth
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
