import { useMemo, useState } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import {
  ArrowLeft,
  Check,
  X,
  Minus,
  TrendingUp,
  TrendingDown,
  ChevronRight,
  ChevronDown,
} from 'lucide-react'
import {
  useDataset,
  useDatasetProdModel,
  useDatasetProdPrompts,
  useEvalRun,
  useVariant,
} from '@/api/evals'
import type {
  CaseItem,
  CaseResultItem,
  ProdPromptsResponse,
  RunDetail,
  VariableDefinitions,
  VariantDelta,
} from '@/api/evals'
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

function isErrored(result: CaseResultItem | undefined): boolean {
  return !!result?.error_message
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
// Effective-config diff helpers (for Delta summary card)
// ---------------------------------------------------------------------------

/**
 * Shape of the before/after objects fed to JsonViewer's diff mode. Keys must
 * match on both sides so unchanged fields render muted and overrides render
 * as CHANGE.
 */
interface EffectiveConfig {
  model: string | null
  system_prompt: string | null
  user_prompt: string | null
  variable_definitions: VariableDefinitions | null
  instructions_delta: unknown[]
}

/**
 * Tolerate both map and list shapes from the backend prompt column, matching
 * the `readVarDefs` helper in the variant editor. Returns null for empty.
 */
function normalizeVarDefs(
  defs: VariableDefinitions | null | undefined,
): VariableDefinitions | null {
  if (!defs) return null
  if (Array.isArray(defs)) {
    const out: VariableDefinitions = {}
    for (const d of defs as Array<Record<string, unknown>>) {
      if (!d || typeof d !== 'object') continue
      const name = typeof d.name === 'string' ? d.name : ''
      if (!name) continue
      const type = typeof d.type === 'string' ? d.type : 'str'
      const entry: VariableDefinitions[string] = { type }
      if (typeof d.description === 'string') entry.description = d.description
      if (typeof d.auto_generate === 'string') entry.auto_generate = d.auto_generate
      out[name] = entry
    }
    return Object.keys(out).length === 0 ? null : out
  }
  return Object.keys(defs).length === 0 ? null : defs
}

/** Union of prod system + user variable_definitions. Variant-editor uses same merge. */
function mergeProdVarDefs(
  prod: ProdPromptsResponse | undefined,
): VariableDefinitions | null {
  const sys = normalizeVarDefs(
    (prod?.system?.variable_definitions ?? null) as VariableDefinitions | null,
  )
  const user = normalizeVarDefs(
    (prod?.user?.variable_definitions ?? null) as VariableDefinitions | null,
  )
  if (!sys && !user) return null
  return { ...(sys ?? {}), ...(user ?? {}) }
}

/** Apply variant variable_definitions override on top of prod baseline. */
function applyVarDefsDelta(
  prodDefs: VariableDefinitions | null,
  variantDefs: VariableDefinitions | null | undefined,
): VariableDefinitions | null {
  const v = normalizeVarDefs(variantDefs)
  if (!prodDefs && !v) return null
  if (!prodDefs) return v
  if (!v) return prodDefs
  return { ...prodDefs, ...v }
}

function buildBefore(
  prodModel: string | null,
  prod: ProdPromptsResponse | undefined,
): EffectiveConfig {
  return {
    model: prodModel,
    system_prompt: prod?.system?.content ?? null,
    user_prompt: prod?.user?.content ?? null,
    variable_definitions: mergeProdVarDefs(prod),
    instructions_delta: [],
  }
}

function buildAfter(
  delta: VariantDelta | null | undefined,
  before: EffectiveConfig,
): EffectiveConfig {
  const d = delta ?? null
  return {
    model: d?.model ?? before.model,
    system_prompt: d?.system_prompt ?? before.system_prompt,
    user_prompt: d?.user_prompt ?? before.user_prompt,
    variable_definitions: applyVarDefsDelta(
      before.variable_definitions,
      d?.variable_definitions ?? null,
    ),
    instructions_delta: Array.isArray(d?.instructions_delta)
      ? (d!.instructions_delta as unknown[])
      : [],
  }
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
// Per-case detail panels
// ---------------------------------------------------------------------------

function ErrorBlock({ message }: { message: string }) {
  return (
    <pre className="text-xs text-destructive bg-destructive/5 p-2 rounded overflow-auto max-h-[200px] whitespace-pre-wrap break-words">
      {message}
    </pre>
  )
}

function JsonScroll({ children }: { children: React.ReactNode }) {
  return <div className="max-h-[300px] overflow-auto min-w-0">{children}</div>
}

function InputExpectedPanel({ caseDef }: { caseDef: CaseItem | undefined }) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide mb-1">
          Input
        </p>
        {caseDef ? (
          <JsonScroll>
            <JsonViewer data={caseDef.inputs} maxDepth={2} />
          </JsonScroll>
        ) : (
          <p className="text-xs text-muted-foreground italic">Not available</p>
        )}
      </div>
      <div>
        <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide mb-1">
          Expected output
        </p>
        {caseDef?.expected_output ? (
          <JsonScroll>
            <JsonViewer data={caseDef.expected_output} maxDepth={2} />
          </JsonScroll>
        ) : (
          <p className="text-xs text-muted-foreground italic">
            {caseDef ? 'No expected output defined' : 'Not available'}
          </p>
        )}
      </div>
    </div>
  )
}

function BaselineOutputPanel({ result }: { result: CaseResultItem | undefined }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide">
          Baseline output
        </p>
        <PassFailBadge result={result} />
      </div>
      {result?.error_message ? (
        <ErrorBlock message={result.error_message} />
      ) : result?.output_data ? (
        <JsonScroll>
          <JsonViewer data={result.output_data} maxDepth={3} />
        </JsonScroll>
      ) : (
        <p className="text-xs text-muted-foreground italic">No output recorded</p>
      )}
    </div>
  )
}

function VariantOutputPanel({
  baselineResult,
  variantResult,
}: {
  baselineResult: CaseResultItem | undefined
  variantResult: CaseResultItem | undefined
}) {
  const baseOut = baselineResult?.output_data ?? null
  const varOut = variantResult?.output_data ?? null

  let body: React.ReactNode
  if (variantResult?.error_message) {
    body = <ErrorBlock message={variantResult.error_message} />
  } else if (varOut && baseOut && !isErrored(baselineResult)) {
    // Both sides have outputs and baseline didn't error -- show diff
    body = (
      <JsonScroll>
        <JsonViewer before={baseOut} after={varOut} maxDepth={3} />
      </JsonScroll>
    )
  } else if (varOut) {
    // Variant produced output but baseline did not (or errored) -- fall back to plain view
    body = (
      <JsonScroll>
        <JsonViewer data={varOut} maxDepth={3} />
      </JsonScroll>
    )
  } else {
    body = <p className="text-xs text-muted-foreground italic">No output recorded</p>
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide">
          Variant output
        </p>
        <PassFailBadge result={variantResult} />
      </div>
      {body}
    </div>
  )
}

function CaseDetailCard({
  caseDef,
  baselineResult,
  variantResult,
}: {
  caseDef: CaseItem | undefined
  baselineResult: CaseResultItem | undefined
  variantResult: CaseResultItem | undefined
}) {
  return (
    <Card className="bg-muted/20 border-0 rounded-none">
      <CardContent className="p-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <InputExpectedPanel caseDef={caseDef} />
          <BaselineOutputPanel result={baselineResult} />
          <VariantOutputPanel
            baselineResult={baselineResult}
            variantResult={variantResult}
          />
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Case row
// ---------------------------------------------------------------------------

function CaseRow({
  name,
  caseDef,
  baselineResult,
  variantResult,
  isExpanded,
  onToggle,
}: {
  name: string
  caseDef: CaseItem | undefined
  baselineResult: CaseResultItem | undefined
  variantResult: CaseResultItem | undefined
  isExpanded: boolean
  onToggle: () => void
}) {
  const delta = caseDelta(baselineResult, variantResult)
  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/50"
        onClick={onToggle}
      >
        <TableCell className="w-8 px-2">
          {isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell className="font-medium text-sm">{name}</TableCell>
        <TableCell>
          <PassFailBadge result={baselineResult} />
        </TableCell>
        <TableCell>
          <ScoresCell result={baselineResult} />
        </TableCell>
        <TableCell>
          <PassFailBadge result={variantResult} />
        </TableCell>
        <TableCell>
          <ScoresCell result={variantResult} />
        </TableCell>
        <TableCell>
          <DeltaIndicator kind={delta} />
        </TableCell>
      </TableRow>
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={7} className="p-0 border-b">
            <CaseDetailCard
              caseDef={caseDef}
              baselineResult={baselineResult}
              variantResult={variantResult}
            />
          </TableCell>
        </TableRow>
      )}
    </>
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
  const datasetQ = useDataset(datasetId)

  const isLoading = baseRunQ.isLoading || variantRunQ.isLoading || datasetQ.isLoading
  // Dataset-fetch errors degrade gracefully (no inputs/expected); don't block.
  const error = baseRunQ.error || variantRunQ.error

  const baseRun = baseRunQ.data
  const variantRun = variantRunQ.data

  // Look up variant name if variant run has variant_id
  const variantIdForLookup = variantRun?.variant_id ?? 0
  const variantQ = useVariant(datasetId, variantIdForLookup)

  // Prod-config fetches feed the Delta summary diff view. Non-blocking:
  // the main page and per-case table render regardless of these results;
  // the Delta card falls back to the raw delta_snapshot render if either
  // fetch errors.
  const prodPromptsQ = useDatasetProdPrompts(datasetId)
  const prodModelQ = useDatasetProdModel(datasetId)

  // Build dataset case map (by case name -> CaseItem). Empty when dataset
  // errored or hasn't loaded yet.
  const caseByName = useMemo(() => {
    const m = new Map<string, CaseItem>()
    for (const c of datasetQ.data?.cases ?? []) m.set(c.name, c)
    return m
  }, [datasetQ.data])

  // Build per-case run-result maps + union of all case names. Memoed so the
  // auto-expand initializer downstream is stable.
  const { baseByName, variantByName, allCaseNames } = useMemo(() => {
    const baseMap = new Map<string, CaseResultItem>()
    const varMap = new Map<string, CaseResultItem>()
    for (const r of baseRun?.case_results ?? []) baseMap.set(r.case_name, r)
    for (const r of variantRun?.case_results ?? []) varMap.set(r.case_name, r)
    const names = Array.from(
      new Set([...baseMap.keys(), ...varMap.keys()]),
    ).sort()
    return { baseByName: baseMap, variantByName: varMap, allCaseNames: names }
  }, [baseRun, variantRun])

  // Seed expanded set with regressed + errored cases. useState initializer
  // runs once; when runs load async, we re-seed via useMemo + state merge in
  // the effect below. Simpler: derive initial set lazily once `allCaseNames`
  // is populated.
  const initialExpanded = useMemo(() => {
    const s = new Set<string>()
    for (const name of allCaseNames) {
      const b = baseByName.get(name)
      const v = variantByName.get(name)
      if (caseDelta(b, v) === 'regressed' || isErrored(b) || isErrored(v)) {
        s.add(name)
      }
    }
    return s
  }, [allCaseNames, baseByName, variantByName])

  // Track which cases are expanded. Initialized from initialExpanded via a
  // useState initializer that references the memo; once user interacts we
  // keep their state (no resets on re-render).
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const [seededFor, setSeededFor] = useState<string>('')

  // Once run data has loaded, seed expanded set exactly once per (baseRun,
  // variantRun) pair. Key on run ids so reloading a different compare URL
  // re-seeds correctly.
  const seedKey = `${baseRun?.id ?? 0}-${variantRun?.id ?? 0}`
  if (baseRun && variantRun && seedKey !== seededFor) {
    setExpanded(new Set(initialExpanded))
    setSeededFor(seedKey)
  }

  function toggleCase(name: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  function expandAll() {
    setExpanded(new Set(allCaseNames))
  }

  function collapseAll() {
    setExpanded(new Set())
  }

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

  const deltaSnapshot = variantRun.delta_snapshot
  const allExpanded =
    allCaseNames.length > 0 && expanded.size === allCaseNames.length

  // Delta summary diff state. Prefer rendering the diff when at least one
  // prod fetch settled (success or error) — a single failed prod fetch still
  // yields an informative diff with nulls on the missing side. Only fall
  // back to the raw snapshot when BOTH prod fetches errored.
  const prodPromptsSettled =
    !prodPromptsQ.isLoading && (prodPromptsQ.data !== undefined || prodPromptsQ.isError)
  const prodModelSettled =
    !prodModelQ.isLoading && (prodModelQ.data !== undefined || prodModelQ.isError)
  const summaryLoading = !prodPromptsSettled || !prodModelSettled
  const bothProdErrored = prodPromptsQ.isError && prodModelQ.isError
  const summaryReady =
    !summaryLoading && !bothProdErrored && deltaSnapshot != null

  const summaryBefore: EffectiveConfig | null = summaryReady
    ? buildBefore(prodModelQ.data?.model ?? null, prodPromptsQ.data)
    : null
  const summaryAfter: EffectiveConfig | null = summaryReady && summaryBefore
    ? buildAfter(deltaSnapshot as unknown as VariantDelta | null, summaryBefore)
    : null

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
            {deltaSnapshot == null ? (
              <p className="text-xs text-muted-foreground">
                No delta_snapshot recorded for this variant run.
              </p>
            ) : summaryReady && summaryBefore && summaryAfter ? (
              <div className="rounded border bg-background p-2 max-h-[400px] overflow-auto">
                <JsonViewer
                  before={summaryBefore as unknown as Record<string, unknown>}
                  after={summaryAfter as unknown as Record<string, unknown>}
                  maxDepth={3}
                />
              </div>
            ) : summaryLoading ? (
              <p className="text-xs text-muted-foreground">Loading diff...</p>
            ) : (
              // Both prod fetches errored — fall back to raw snapshot view.
              <div className="rounded border bg-background p-2">
                <JsonViewer
                  data={deltaSnapshot as Record<string, unknown>}
                  maxDepth={3}
                />
              </div>
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
          <CardHeader className="pb-3 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Per-case comparison</CardTitle>
            {allCaseNames.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={allExpanded ? collapseAll : expandAll}
                className="h-7 text-xs"
              >
                {allExpanded ? 'Collapse all' : 'Expand all'}
              </Button>
            )}
          </CardHeader>
          <CardContent className="p-0">
            {allCaseNames.length === 0 ? (
              <p className="p-4 text-xs text-muted-foreground">No case results recorded.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>Case</TableHead>
                    <TableHead>Baseline</TableHead>
                    <TableHead>Baseline scores</TableHead>
                    <TableHead>Variant</TableHead>
                    <TableHead>Variant scores</TableHead>
                    <TableHead>Delta</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allCaseNames.map((name) => (
                    <CaseRow
                      key={name}
                      name={name}
                      caseDef={caseByName.get(name)}
                      baselineResult={baseByName.get(name)}
                      variantResult={variantByName.get(name)}
                      isExpanded={expanded.has(name)}
                      onToggle={() => toggleCase(name)}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  )
}
