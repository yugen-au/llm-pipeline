import { createFileRoute, Link } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import { ArrowLeft, Check, X, Minus, TrendingUp, TrendingDown } from 'lucide-react'
import { useEvalRun, useVariant } from '@/api/evals'
import type { CaseResultItem, RunDetail } from '@/api/evals'
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

// ---------------------------------------------------------------------------
// Search-param schema
// ---------------------------------------------------------------------------

const compareSearchSchema = z.object({
  baseRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
  variantRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
})

export const Route = createFileRoute('/evals/$datasetId/compare')({
  validateSearch: zodValidator(compareSearchSchema),
  component: CompareRunsPage,
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function passRate(run: RunDetail | undefined): number | null {
  if (!run) return null
  if (run.total_cases === 0) return null
  return run.passed / run.total_cases
}

function formatPct(v: number | null): string {
  if (v == null) return 'N/A'
  return `${(v * 100).toFixed(1)}%`
}

function DeltaBadge({
  baseValue,
  variantValue,
  invertColor = false,
}: {
  baseValue: number | null
  variantValue: number | null
  invertColor?: boolean
}) {
  if (baseValue == null || variantValue == null) {
    return <span className="text-xs text-muted-foreground">-</span>
  }
  const delta = variantValue - baseValue
  if (delta === 0) {
    return <span className="text-xs text-muted-foreground font-mono">0</span>
  }
  const isImprovement = invertColor ? delta < 0 : delta > 0
  const color = isImprovement ? 'text-green-600' : 'text-red-600'
  const Icon = delta > 0 ? TrendingUp : TrendingDown
  const sign = delta > 0 ? '+' : ''
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-mono ${color}`}>
      <Icon className="h-3 w-3" />
      {sign}
      {Number.isInteger(delta) ? delta : delta.toFixed(3)}
    </span>
  )
}

function DeltaPctBadge({
  baseValue,
  variantValue,
}: {
  baseValue: number | null
  variantValue: number | null
}) {
  if (baseValue == null || variantValue == null) {
    return <span className="text-xs text-muted-foreground">-</span>
  }
  const delta = variantValue - baseValue
  if (delta === 0) {
    return <span className="text-xs text-muted-foreground font-mono">0%</span>
  }
  const isImprovement = delta > 0
  const color = isImprovement ? 'text-green-600' : 'text-red-600'
  const Icon = isImprovement ? TrendingUp : TrendingDown
  const sign = delta > 0 ? '+' : ''
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-mono ${color}`}>
      <Icon className="h-3 w-3" />
      {sign}
      {(delta * 100).toFixed(1)}%
    </span>
  )
}

function PassFailBadge({ result }: { result: CaseResultItem | undefined }) {
  if (!result) {
    return (
      <Badge variant="outline" className="gap-1 text-xs">
        <Minus className="h-3 w-3" /> N/A
      </Badge>
    )
  }
  if (result.error_message) {
    return (
      <Badge variant="destructive" className="gap-1 text-xs">
        <X className="h-3 w-3" /> errored
      </Badge>
    )
  }
  return result.passed ? (
    <Badge variant="default" className="gap-1 text-xs bg-green-600 hover:bg-green-700">
      <Check className="h-3 w-3" /> pass
    </Badge>
  ) : (
    <Badge variant="destructive" className="gap-1 text-xs">
      <X className="h-3 w-3" /> fail
    </Badge>
  )
}

type DeltaKind = 'improved' | 'regressed' | 'unchanged' | 'n/a'

function caseDelta(
  baseResult: CaseResultItem | undefined,
  variantResult: CaseResultItem | undefined,
): DeltaKind {
  if (!baseResult || !variantResult) return 'n/a'
  const basePassed = !baseResult.error_message && baseResult.passed
  const variantPassed = !variantResult.error_message && variantResult.passed
  if (basePassed === variantPassed) return 'unchanged'
  return variantPassed ? 'improved' : 'regressed'
}

function DeltaIndicator({ kind }: { kind: DeltaKind }) {
  switch (kind) {
    case 'improved':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-green-600">
          <TrendingUp className="h-3 w-3" />
          improved
        </span>
      )
    case 'regressed':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-red-600">
          <TrendingDown className="h-3 w-3" />
          regressed
        </span>
      )
    case 'unchanged':
      return <span className="text-xs text-muted-foreground">unchanged</span>
    default:
      return <span className="text-xs text-muted-foreground">N/A</span>
  }
}

function extractScoreValues(raw: unknown): Record<string, number | boolean | null> {
  if (!raw || typeof raw !== 'object') return {}
  const out: Record<string, number | boolean | null> = {}
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof v === 'boolean' || typeof v === 'number') {
      out[k] = v
    } else if (v && typeof v === 'object' && 'value' in v) {
      const inner = (v as { value: unknown }).value
      if (typeof inner === 'boolean' || typeof inner === 'number') {
        out[k] = inner
      } else {
        out[k] = null
      }
    } else {
      out[k] = null
    }
  }
  return out
}

function formatScore(v: number | boolean | null | undefined): string {
  if (v == null) return '-'
  if (typeof v === 'boolean') return v ? 'pass' : 'fail'
  return v.toFixed(2)
}

function ScoresCell({ result }: { result: CaseResultItem | undefined }) {
  if (!result) {
    return <span className="text-xs text-muted-foreground">-</span>
  }
  const scores = extractScoreValues(result.evaluator_scores)
  const entries = Object.entries(scores)
  if (entries.length === 0) {
    return <span className="text-xs text-muted-foreground">-</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([name, value]) => (
        <span
          key={name}
          className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px]"
          title={`${name}: ${formatScore(value)}`}
        >
          <span className="text-muted-foreground">{name}</span>
          <span>{formatScore(value)}</span>
        </span>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

function ComparisonStatCard({
  label,
  baseValue,
  variantValue,
  color,
  invertColor = false,
  format = (v) => (v == null ? '-' : String(v)),
}: {
  label: string
  baseValue: number | null
  variantValue: number | null
  color?: string
  invertColor?: boolean
  format?: (v: number | null) => string
}) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3 text-center space-y-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <div className="flex items-baseline justify-center gap-3">
          <div>
            <p className="text-[10px] text-muted-foreground uppercase">Base</p>
            <p className={`text-xl font-bold ${color ?? ''}`}>{format(baseValue)}</p>
          </div>
          <div>
            <p className="text-[10px] text-muted-foreground uppercase">Variant</p>
            <p className={`text-xl font-bold ${color ?? ''}`}>{format(variantValue)}</p>
          </div>
        </div>
        <div>
          <DeltaBadge
            baseValue={baseValue}
            variantValue={variantValue}
            invertColor={invertColor}
          />
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function CompareRunsPage() {
  const { datasetId: rawDatasetId } = Route.useParams()
  const { baseRunId, variantRunId } = Route.useSearch()
  const datasetId = Number(rawDatasetId)

  const baseRunQ = useEvalRun(datasetId, baseRunId)
  const variantRunQ = useEvalRun(datasetId, variantRunId)

  const isLoading = baseRunQ.isLoading || variantRunQ.isLoading
  const error = baseRunQ.error || variantRunQ.error

  const baseRun = baseRunQ.data
  const variantRun = variantRunQ.data

  // Look up variant name if variant run has variant_id
  const variantIdForLookup = variantRun?.variant_id ?? 0
  const variantQ = useVariant(datasetId, variantIdForLookup)

  // Early param validation
  if (baseRunId === 0 || variantRunId === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="text-center space-y-2">
          <p className="text-destructive">
            Invalid compare URL. Both baseRunId and variantRunId search params are required.
          </p>
          <Button variant="outline" asChild>
            <Link to="/evals/$datasetId" params={{ datasetId: String(datasetId) }}>
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back to dataset
            </Link>
          </Button>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading runs...</p>
      </div>
    )
  }

  if (error || !baseRun || !variantRun) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="text-center space-y-2">
          <p className="text-destructive">
            {(error as { detail?: string })?.detail ?? 'One or both runs could not be loaded.'}
          </p>
          <Button variant="outline" asChild>
            <Link to="/evals/$datasetId" params={{ datasetId: String(datasetId) }}>
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back to dataset
            </Link>
          </Button>
        </div>
      </div>
    )
  }

  const basePassRate = passRate(baseRun)
  const variantPassRate = passRate(variantRun)

  // Build per-case union map
  const baseByName = new Map<string, CaseResultItem>()
  for (const r of baseRun.case_results ?? []) baseByName.set(r.case_name, r)
  const variantByName = new Map<string, CaseResultItem>()
  for (const r of variantRun.case_results ?? []) variantByName.set(r.case_name, r)
  const allCaseNames = Array.from(
    new Set([...baseByName.keys(), ...variantByName.keys()]),
  ).sort()

  const deltaSnapshot = variantRun.delta_snapshot

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-6xl space-y-6 p-6">
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
            <span className="font-medium text-foreground">Compare runs</span>
          </div>
        </div>

        {/* Header */}
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">Comparing runs</h1>
          <p className="text-xs text-muted-foreground">
            Baseline run #{baseRun.id}{' '}
            {baseRun.started_at && `(${new Date(baseRun.started_at).toLocaleString()})`}
            {' vs '}Variant run #{variantRun.id}{' '}
            {variantRun.started_at && `(${new Date(variantRun.started_at).toLocaleString()})`}
          </p>
          {variantRun.variant_id != null && (
            <p className="text-xs text-muted-foreground">
              Variant:{' '}
              <span className="font-medium text-foreground">
                {variantQ.data?.name ?? `#${variantRun.variant_id}`}
              </span>
            </p>
          )}
        </div>

        {/* Run headers (side by side) */}
        <div className="grid grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Baseline{' '}
                <Link
                  to="/evals/$datasetId/runs/$runId"
                  params={{ datasetId: String(datasetId), runId: String(baseRun.id) }}
                  className="font-mono text-muted-foreground hover:underline ml-1"
                >
                  #{baseRun.id}
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 space-y-1">
              <Badge variant="outline" className="text-xs">{baseRun.status}</Badge>
              <p className="text-xs text-muted-foreground">
                {baseRun.started_at
                  ? new Date(baseRun.started_at).toLocaleString()
                  : 'N/A'}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Variant{' '}
                <Link
                  to="/evals/$datasetId/runs/$runId"
                  params={{ datasetId: String(datasetId), runId: String(variantRun.id) }}
                  className="font-mono text-muted-foreground hover:underline ml-1"
                >
                  #{variantRun.id}
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 space-y-1">
              <Badge variant="outline" className="text-xs">{variantRun.status}</Badge>
              <p className="text-xs text-muted-foreground">
                {variantRun.started_at
                  ? new Date(variantRun.started_at).toLocaleString()
                  : 'N/A'}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Delta summary */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Delta summary</CardTitle>
          </CardHeader>
          <CardContent>
            {deltaSnapshot ? (
              <div className="rounded border bg-background p-2">
                <JsonViewer
                  data={deltaSnapshot as Record<string, unknown>}
                  maxDepth={3}
                />
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                No delta_snapshot recorded for this variant run.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Stats comparison */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <ComparisonStatCard
            label="Passed"
            baseValue={baseRun.passed}
            variantValue={variantRun.passed}
            color="text-green-600"
          />
          <ComparisonStatCard
            label="Failed"
            baseValue={baseRun.failed}
            variantValue={variantRun.failed}
            color="text-red-600"
            invertColor
          />
          <ComparisonStatCard
            label="Errored"
            baseValue={baseRun.errored}
            variantValue={variantRun.errored}
            color="text-yellow-600"
            invertColor
          />
          <Card>
            <CardContent className="pt-4 pb-3 text-center space-y-1">
              <p className="text-xs text-muted-foreground">Pass rate</p>
              <div className="flex items-baseline justify-center gap-3">
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase">Base</p>
                  <p className="text-xl font-bold">{formatPct(basePassRate)}</p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase">Variant</p>
                  <p className="text-xl font-bold">{formatPct(variantPassRate)}</p>
                </div>
              </div>
              <div>
                <DeltaPctBadge
                  baseValue={basePassRate}
                  variantValue={variantPassRate}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Per-case comparison */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Per-case comparison</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {allCaseNames.length === 0 ? (
              <p className="p-4 text-xs text-muted-foreground">No case results recorded.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case</TableHead>
                    <TableHead>Baseline</TableHead>
                    <TableHead>Baseline scores</TableHead>
                    <TableHead>Variant</TableHead>
                    <TableHead>Variant scores</TableHead>
                    <TableHead>Delta</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allCaseNames.map((name) => {
                    const b = baseByName.get(name)
                    const v = variantByName.get(name)
                    const d = caseDelta(b, v)
                    return (
                      <TableRow key={name}>
                        <TableCell className="font-medium text-sm">{name}</TableCell>
                        <TableCell>
                          <PassFailBadge result={b} />
                        </TableCell>
                        <TableCell>
                          <ScoresCell result={b} />
                        </TableCell>
                        <TableCell>
                          <PassFailBadge result={v} />
                        </TableCell>
                        <TableCell>
                          <ScoresCell result={v} />
                        </TableCell>
                        <TableCell>
                          <DeltaIndicator kind={d} />
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  )
}
