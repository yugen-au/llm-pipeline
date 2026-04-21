import { useState } from 'react'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import {
  ArrowLeft,
  Check,
  X,
  Minus,
  ChevronDown,
  ChevronRight,
  GitCompare,
} from 'lucide-react'
import { useEvalRun, useEvalRuns } from '@/api/evals'
import type { CaseResultItem, RunListItem } from '@/api/evals'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ScrollArea } from '@/components/ui/scroll-area'
import { JsonViewer } from '@/components/JsonViewer'

export const Route = createFileRoute('/evals/$datasetId/runs/$runId')({
  component: EvalRunDetailPage,
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type EvalScore = { value: boolean | number | string | null } | boolean | number | string | null

function extractEvaluatorNames(results: CaseResultItem[]): string[] {
  const names = new Set<string>()
  for (const r of results) {
    if (r.evaluator_scores && typeof r.evaluator_scores === 'object') {
      for (const key of Object.keys(r.evaluator_scores)) {
        names.add(key)
      }
    }
  }
  return Array.from(names).sort()
}

function getScoreValue(raw: EvalScore): boolean | number | null {
  if (raw == null) return null
  if (typeof raw === 'boolean') return raw
  if (typeof raw === 'number') return raw
  if (typeof raw === 'object' && 'value' in raw) {
    const v = raw.value
    if (typeof v === 'boolean') return v
    if (typeof v === 'number') return v
    return null
  }
  return null
}

function ScoreCell({ raw }: { raw: EvalScore }) {
  const value = getScoreValue(raw)

  if (value === null || value === undefined) {
    return <Minus className="h-4 w-4 text-muted-foreground mx-auto" />
  }

  if (typeof value === 'boolean') {
    return value ? (
      <Check className="h-4 w-4 text-green-600 mx-auto" />
    ) : (
      <X className="h-4 w-4 text-red-600 mx-auto" />
    )
  }

  // Numeric score: color by threshold
  const color =
    value >= 0.8
      ? 'text-green-600'
      : value >= 0.5
        ? 'text-yellow-600'
        : 'text-red-600'
  return <span className={`text-xs font-mono font-medium ${color}`}>{value.toFixed(2)}</span>
}

function OverallCell({ result, evaluatorNames }: { result: CaseResultItem; evaluatorNames: string[] }) {
  if (!result.evaluator_scores || evaluatorNames.length === 0) {
    return <Minus className="h-4 w-4 text-muted-foreground mx-auto" />
  }

  // Use the pre-computed passed field from the backend
  return result.passed ? (
    <Check className="h-4 w-4 text-green-600 mx-auto" />
  ) : (
    <X className="h-4 w-4 text-red-600 mx-auto" />
  )
}

function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'completed':
      return 'default'
    case 'failed':
      return 'destructive'
    case 'running':
    case 'pending':
      return 'secondary'
    default:
      return 'outline'
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-green-600'
    case 'failed':
      return 'bg-red-600'
    case 'running':
      return 'bg-yellow-500'
    default:
      return 'bg-muted-foreground'
  }
}

// ---------------------------------------------------------------------------
// Expandable row
// ---------------------------------------------------------------------------

function ExpandableDetail({ result }: { result: CaseResultItem }) {
  return (
    <div className="space-y-3 p-4 bg-muted/30">
      {result.error_message && (
        <div className="space-y-1">
          <span className="text-xs font-medium text-destructive">Error</span>
          <pre className="text-xs font-mono text-destructive bg-destructive/10 rounded p-2 whitespace-pre-wrap">
            {result.error_message}
          </pre>
        </div>
      )}
      {result.output_data && (
        <div className="space-y-1">
          <span className="text-xs font-medium text-muted-foreground">Output</span>
          <div className="rounded border bg-background p-2">
            <JsonViewer data={result.output_data} maxDepth={3} />
          </div>
        </div>
      )}
      {!result.error_message && !result.output_data && (
        <p className="text-xs text-muted-foreground">No additional data available.</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function findMostRecentBaseline(
  runs: RunListItem[] | undefined,
  currentRunId: number,
): RunListItem | null {
  if (!runs) return null
  // Runs endpoint typically returns in chronological order; filter variant_id==null
  // excluding the current run itself. Pick the one with the latest started_at.
  const baselines = runs.filter(
    (r) => r.variant_id == null && r.id !== currentRunId,
  )
  if (baselines.length === 0) return null
  return baselines.reduce((best, r) => {
    if (!best) return r
    const bestTs = best.started_at ? Date.parse(best.started_at) : 0
    const rTs = r.started_at ? Date.parse(r.started_at) : 0
    return rTs > bestTs ? r : best
  }, null as RunListItem | null)
}

function EvalRunDetailPage() {
  const { datasetId: rawDatasetId, runId: rawRunId } = Route.useParams()
  const datasetId = Number(rawDatasetId)
  const runId = Number(rawRunId)
  const { data: run, isLoading, error } = useEvalRun(datasetId, runId)
  const navigate = useNavigate()
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  // Only load run list when current run is a variant run. We use `enabled`
  // semantics indirectly: the hook is keyed by datasetId and safe to mount
  // unconditionally; filtering logic ignores it when run is not a variant.
  const runsQ = useEvalRuns(datasetId)
  const isVariantRun = run?.variant_id != null
  const baseline = isVariantRun
    ? findMostRecentBaseline(runsQ.data, runId)
    : null
  const canCompare = isVariantRun && baseline != null
  const compareDisabled = isVariantRun && !canCompare

  function handleCompare() {
    if (!baseline) return
    navigate({
      to: '/evals/$datasetId/compare',
      params: { datasetId: String(datasetId) },
      search: { baseRunId: baseline.id, compareRunId: runId },
    })
  }

  function toggleRow(id: number) {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading run...</p>
      </div>
    )
  }

  if (error || !run) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-destructive">
          {(error as { detail?: string })?.detail ?? 'Run not found'}
        </p>
      </div>
    )
  }

  const evaluatorNames = extractEvaluatorNames(run.case_results ?? [])

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-5xl space-y-6 p-6">
        {/* Back + breadcrumb */}
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon-sm" asChild>
            <Link to="/evals/$datasetId" params={{ datasetId: String(datasetId) }}>
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link
              to="/evals/$datasetId"
              params={{ datasetId: String(datasetId) }}
              className="hover:underline"
            >
              Dataset #{datasetId}
            </Link>
            <span>/</span>
            <span className="font-medium text-foreground">Run #{run.id}</span>
          </div>
        </div>

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold">Evaluation Run #{run.id}</h1>
            <p className="text-xs text-muted-foreground font-mono">
              Started {run.started_at ? new Date(run.started_at).toLocaleString() : 'N/A'}
              {run.completed_at && ` -- completed ${new Date(run.completed_at).toLocaleString()}`}
            </p>
            {run.variant_id != null && (
              <p className="text-xs text-muted-foreground">
                Variant run (variant #{run.variant_id})
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {isVariantRun && (
              compareDisabled ? (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled
                          className="gap-1.5"
                        >
                          <GitCompare className="h-4 w-4" />
                          Compare with baseline
                        </Button>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>No baseline run available</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCompare}
                  disabled={runsQ.isLoading || !baseline}
                  className="gap-1.5"
                >
                  <GitCompare className="h-4 w-4" />
                  Compare with baseline
                </Button>
              )
            )}
            <Badge variant={statusVariant(run.status)} className="gap-1.5">
              <span className={`h-2 w-2 rounded-full ${statusColor(run.status)}`} />
              {run.status}
            </Badge>
          </div>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card>
            <CardContent className="pt-4 pb-3 text-center">
              <p className="text-2xl font-bold">{run.total_cases}</p>
              <p className="text-xs text-muted-foreground">Total Cases</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3 text-center">
              <p className="text-2xl font-bold text-green-600">{run.passed}</p>
              <p className="text-xs text-muted-foreground">Passed</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3 text-center">
              <p className="text-2xl font-bold text-red-600">{run.failed}</p>
              <p className="text-xs text-muted-foreground">Failed</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3 text-center">
              <p className="text-2xl font-bold text-yellow-600">{run.errored}</p>
              <p className="text-xs text-muted-foreground">Errored</p>
            </CardContent>
          </Card>
        </div>

        {/* Results grid */}
        {(run.case_results ?? []).length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Results</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>Case</TableHead>
                    {evaluatorNames.map((name) => (
                      <TableHead key={name} className="text-center whitespace-nowrap">
                        {name}
                      </TableHead>
                    ))}
                    <TableHead className="text-center">Overall</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(run.case_results ?? []).map((result) => {
                    const isExpanded = expandedRows.has(result.id)
                    const colSpan = evaluatorNames.length + 3
                    return (
                      <CaseResultRow
                        key={result.id}
                        result={result}
                        evaluatorNames={evaluatorNames}
                        isExpanded={isExpanded}
                        colSpan={colSpan}
                        onToggle={() => toggleRow(result.id)}
                      />
                    )
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {(run.case_results ?? []).length === 0 && run.status === 'running' && (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              Run in progress...
            </CardContent>
          </Card>
        )}
      </div>
    </ScrollArea>
  )
}

// ---------------------------------------------------------------------------
// Case result row (extracted for clarity)
// ---------------------------------------------------------------------------

function CaseResultRow({
  result,
  evaluatorNames,
  isExpanded,
  colSpan,
  onToggle,
}: {
  result: CaseResultItem
  evaluatorNames: string[]
  isExpanded: boolean
  colSpan: number
  onToggle: () => void
}) {
  const hasDetail = result.output_data != null || result.error_message != null
  return (
    <>
      <TableRow
        className={hasDetail ? 'cursor-pointer hover:bg-muted/50' : ''}
        onClick={hasDetail ? onToggle : undefined}
      >
        <TableCell className="w-8 px-2">
          {hasDetail &&
            (isExpanded ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            ))}
        </TableCell>
        <TableCell className="font-medium text-sm">{result.case_name}</TableCell>
        {evaluatorNames.map((name) => (
          <TableCell key={name} className="text-center">
            <ScoreCell
              raw={
                result.evaluator_scores?.[name] as EvalScore
              }
            />
          </TableCell>
        ))}
        <TableCell className="text-center">
          <OverallCell result={result} evaluatorNames={evaluatorNames} />
        </TableCell>
      </TableRow>
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={colSpan} className="p-0 border-b">
            <ExpandableDetail result={result} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}
