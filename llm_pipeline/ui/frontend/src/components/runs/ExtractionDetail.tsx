import { useState } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'
import { JsonDiff } from '@/components/JsonDiff'
import { formatDuration } from '@/lib/time'
import type { ExtractionCompletedData, UpdatedRecord } from '@/api/types'

// ---------------------------------------------------------------------------
// Single record row (collapsible)
// ---------------------------------------------------------------------------

function RecordRow({
  index,
  label,
  children,
}: {
  index: number
  label: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded border border-border/50">
      <button
        type="button"
        className="flex w-full items-center gap-1 px-2 py-1 text-xs font-mono hover:bg-muted/30 rounded"
        onClick={() => setOpen((p) => !p)}
      >
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <span className="text-muted-foreground">#{index + 1}</span>
        <span className="ml-1">{label}</span>
      </button>
      {open && <div className="px-2 pb-2">{children}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function recordLabel(record: Record<string, unknown>): string {
  for (const key of ['name', 'display_name', 'label', 'id']) {
    if (record[key] != null) return String(record[key])
  }
  return ''
}

function updatedLabel(record: UpdatedRecord): string {
  const id = record.id != null ? `id=${record.id}` : ''
  const name = recordLabel(record.after)
  return [id, name].filter(Boolean).join(' ')
}

// ---------------------------------------------------------------------------
// ExtractionDetail (public export)
// ---------------------------------------------------------------------------

export function ExtractionDetail({ data }: { data: ExtractionCompletedData }) {
  const created = data.created ?? []
  const updated = data.updated ?? []
  const hasDetail = created.length > 0 || updated.length > 0

  // Unified record list: created records become diffs against {}
  const records: { key: string; label: string; before: Record<string, unknown>; after: Record<string, unknown> }[] = [
    ...created.map((record, i) => ({
      key: `c-${i}`,
      label: recordLabel(record),
      before: {} as Record<string, unknown>,
      after: record,
    })),
    ...updated.map((record, i) => ({
      key: `u-${i}`,
      label: updatedLabel(record),
      before: record.before,
      after: record.after,
    })),
  ]

  // Summary parts
  const summaryParts: string[] = []
  if (created.length > 0) summaryParts.push(`${created.length} created`)
  if (updated.length > 0) summaryParts.push(`${updated.length} updated`)

  return (
    <div className="rounded-md border p-3 text-sm space-y-2">
      {/* Header */}
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-medium text-xs">
          {data.extraction_class} <span className="text-muted-foreground font-normal">&rarr; {data.model_class}</span>
        </span>
        <span className="text-xs text-muted-foreground">{formatDuration(data.execution_time_ms)}</span>
      </div>

      {/* Summary line */}
      <div className="flex gap-3 text-xs text-muted-foreground">
        {summaryParts.length > 0
          ? summaryParts.map((part) => <span key={part}>{part}</span>)
          : <span>{data.instance_count} instance{data.instance_count !== 1 ? 's' : ''}</span>
        }
      </div>

      {/* Unified record list */}
      {hasDetail && (
        <div className="space-y-1">
          {records.map((rec, i) => (
            <RecordRow key={rec.key} index={i} label={rec.label}>
              <JsonDiff before={rec.before} after={rec.after} maxDepth={3} />
            </RecordRow>
          ))}
        </div>
      )}
    </div>
  )
}
