import { useState } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface JsonTreeProps {
  data: Record<string, unknown> | unknown[] | null
  depth?: number
}

interface JsonTreeNodeProps {
  label: string
  value: unknown
  depth: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

function isArray(v: unknown): v is unknown[] {
  return Array.isArray(v)
}

// ---------------------------------------------------------------------------
// PrimitiveValue (inline renderer for leaf values)
// ---------------------------------------------------------------------------

function PrimitiveValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">null</span>
  }
  if (typeof value === 'string') {
    return <span className="text-green-600 dark:text-green-400">"{value}"</span>
  }
  if (typeof value === 'number') {
    return <span className="text-blue-600 dark:text-blue-400">{String(value)}</span>
  }
  if (typeof value === 'boolean') {
    return <span className="text-orange-600">{String(value)}</span>
  }
  // Fallback for anything else
  return <span className="text-muted-foreground">{String(value)}</span>
}

// ---------------------------------------------------------------------------
// JsonTreeNode (private recursive renderer)
// ---------------------------------------------------------------------------

function JsonTreeNode({ label, value, depth }: JsonTreeNodeProps) {
  const [expanded, setExpanded] = useState(depth < 2)

  // Collapsible object
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
              <JsonTreeNode key={k} label={k} value={v} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    )
  }

  // Collapsible array
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
              <JsonTreeNode key={i} label={String(i)} value={item} depth={depth + 1} />
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

// ---------------------------------------------------------------------------
// JsonTree (public export)
// ---------------------------------------------------------------------------

export function JsonTree({ data, depth = 0 }: JsonTreeProps) {
  if (data === null || data === undefined) {
    return <span className="text-muted-foreground italic text-xs font-mono">null</span>
  }

  if (isArray(data)) {
    return (
      <div className="space-y-0">
        {data.map((item, i) => (
          <JsonTreeNode key={i} label={String(i)} value={item} depth={depth} />
        ))}
      </div>
    )
  }

  // Object
  const entries = Object.entries(data)
  return (
    <div className="space-y-0">
      {entries.map(([k, v]) => (
        <JsonTreeNode key={k} label={k} value={v} depth={depth} />
      ))}
    </div>
  )
}
