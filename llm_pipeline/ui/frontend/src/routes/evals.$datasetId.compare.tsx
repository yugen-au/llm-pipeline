import { useMemo, useState } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import { toast } from 'sonner'
import {
  ArrowLeft,
  Check,
  X,
  Minus,
  TrendingUp,
  TrendingDown,
  ChevronRight,
  ChevronDown,
  Download,
} from 'lucide-react'
import {
  useDataset,
  useEvalRun,
  useHistoricalCase,
  useHistoricalCases,
  useVariant,
} from '@/api/evals'
import type {
  CaseItem,
  CaseResultItem,
  HistoricalCaseItem,
  RunDetail,
} from '@/api/evals'
import { useRunPrompts } from '@/api/prompts'
import type {
  FlatPromptVersion,
  HistoricalPromptItem,
} from '@/api/prompts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
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

// Note: variantRunId is accepted as a backward-compat alias for compareRunId.
// The .transform() drops variantRunId from the resolved shape, so TanStack
// Router will rewrite the URL (stripping variantRunId) on the next navigation.
// This is intentional - bookmarks continue to work on initial load.
const compareSearchSchema = z
  .object({
    baseRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
    compareRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
    variantRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
  })
  .transform(({ baseRunId, compareRunId, variantRunId }) => ({
    baseRunId,
    compareRunId: compareRunId || variantRunId || 0,
  }))

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
  compareValue,
  invertColor = false,
}: {
  baseValue: number | null
  compareValue: number | null
  invertColor?: boolean
}) {
  if (baseValue == null || compareValue == null) {
    return <span className="text-xs text-muted-foreground">-</span>
  }
  const delta = compareValue - baseValue
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
  compareValue,
}: {
  baseValue: number | null
  compareValue: number | null
}) {
  if (baseValue == null || compareValue == null) {
    return <span className="text-xs text-muted-foreground">-</span>
  }
  const delta = compareValue - baseValue
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

type VersionBucket = 'matched' | 'drifted' | 'unmatched'

/**
 * Determine the version-match bucket for a case across two runs.
 * - Missing on either side: unmatched
 * - Both runs lack case_versions (legacy): matched (shared name = same case)
 * - Only one run lacks case_versions: matched (can't determine, assume matched)
 * - Otherwise: compare version strings from each run's case_versions map
 */
function computeCaseBucket(
  baseResult: CaseResultItem | undefined,
  compareResult: CaseResultItem | undefined,
  baseRun: RunDetail,
  compareRun: RunDetail,
): VersionBucket {
  if (!baseResult || !compareResult) return 'unmatched'
  // case_id may be null if the runner couldn't resolve the case name to a DB id;
  // without an id we cannot key into case_versions -> treat as unmatched.
  if (baseResult.case_id === null || compareResult.case_id === null) return 'unmatched'
  const baseCv = baseRun.case_versions
  const compareCv = compareRun.case_versions
  if (baseCv === null && compareCv === null) return 'matched'
  if (baseCv === null || compareCv === null) return 'matched'
  const baseVersion = baseCv[String(baseResult.case_id)]
  const compareVersion = compareCv[String(compareResult.case_id)]
  if (baseVersion === undefined || compareVersion === undefined) return 'unmatched'
  return baseVersion === compareVersion ? 'matched' : 'drifted'
}

function VersionBucketBadge({
  bucket,
  baseVersion,
  compareVersion,
}: {
  bucket: VersionBucket
  baseVersion?: string
  compareVersion?: string
}) {
  if (bucket === 'matched') return null
  if (bucket === 'drifted') {
    const label =
      baseVersion && compareVersion
        ? `v${baseVersion} → v${compareVersion}`
        : 'drifted'
    return (
      <Badge
        variant="outline"
        className="text-[10px] px-1.5 py-0 border-amber-400 text-amber-600"
        title="Case version differs between runs"
      >
        {label}
      </Badge>
    )
  }
  // unmatched: indicate which side has the case when possible
  const label =
    baseVersion && !compareVersion
      ? `only in base (v${baseVersion})`
      : compareVersion && !baseVersion
        ? `only in compare (v${compareVersion})`
        : 'unmatched'
  return (
    <Badge
      variant="outline"
      className="text-[10px] px-1.5 py-0 border-muted text-muted-foreground"
      title="Case is missing from one of the runs"
    >
      {label}
    </Badge>
  )
}

type DeltaKind = 'improved' | 'regressed' | 'unchanged' | 'n/a'

function caseDelta(
  baseResult: CaseResultItem | undefined,
  compareResult: CaseResultItem | undefined,
): DeltaKind {
  if (!baseResult || !compareResult) return 'n/a'
  const basePassed = !baseResult.error_message && baseResult.passed
  const comparePassed = !compareResult.error_message && compareResult.passed
  if (basePassed === comparePassed) return 'unchanged'
  return comparePassed ? 'improved' : 'regressed'
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
// Variable-definition helpers (used by export payload builder)
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Export payload builders
// ---------------------------------------------------------------------------

interface ExportStats {
  total: number
  passed: number
  failed: number
  errored: number
  pass_rate: number | null
}

interface ExportRunPrompt {
  /** Pipeline step that owns this prompt (pipeline-target runs only); null
   * for step-target runs where the whole run is a single step. */
  step_name: string | null
  prompt_key: string
  prompt_type: string
  version: string
  content: string
  variable_definitions: Record<string, unknown> | null
}

interface ExportRunContext {
  /** Resolved model name (e.g. "openai:gpt-5") or null when not recorded. */
  model: string | null
  /** Raw model snapshot from the run for pipeline-target shapes that carry
   * multiple steps. For step-target this is just `{step_name: model}`. */
  model_snapshot: Record<string, unknown> | null
  /** Fully resolved prompts that were actually used by this run. */
  prompts: ExportRunPrompt[]
  /** Full instructions JSON schema captured at run time. */
  instructions_schema: Record<string, unknown> | null
  /** Delta overrides applied by a variant run; null for non-variant runs. */
  variant_delta: Record<string, unknown> | null
  /** Variant id if run was a variant run, null otherwise. */
  variant_id: number | null
}

interface ExportRun {
  id: number
  stats: ExportStats
  context: ExportRunContext
}

/** A case row at a specific version — the exact test definition a run used. */
interface ExportCaseVersion {
  case_id: number
  version: string
  inputs: Record<string, unknown>
  expected_output: Record<string, unknown> | null
  metadata_: Record<string, unknown> | null
}

/** A run's observed behavior on a case — what it produced, whether the
 * evaluation concluded pass/fail/error. Per the consistency principle we
 * intentionally omit named evaluator scores (e.g. `SentimentLabelEvaluator:
 * true`) because the reader has no definition of what each evaluator
 * checks; the aggregate pass/fail + actual output is enough to reason
 * about why a case did or didn't satisfy its criteria. */
interface ExportCaseRunResult {
  run_id: number
  passed: boolean
  output_data: Record<string, unknown> | null
  error_message: string | null
}

/** Everything about a single case across both runs — the version(s) of the
 * test definition each run used, and each run's observed behavior. Always
 * rendered in full regardless of whether there's a delta. */
interface ExportCase {
  name: string
  /** 'matched' = both runs used the same case version. 'drifted' = different
   * versions (a real content change between runs). 'unmatched' = the case
   * existed in only one of the two runs. */
  bucket: 'matched' | 'drifted' | 'unmatched'
  /** Pass/fail delta between base and compare (or 'n/a' when one side
   * lacks a result). Derived from `passed` + `error_message` on each side. */
  delta: 'improved' | 'regressed' | 'unchanged' | 'n/a'
  /** The case version used by the base run. Null when the case wasn't
   * present in the base run or the base result couldn't resolve a case id. */
  base_version: ExportCaseVersion | null
  /** The case version used by the compare run. Symmetric to base_version. */
  compare_version: ExportCaseVersion | null
  base_result: ExportCaseRunResult | null
  compare_result: ExportCaseRunResult | null
}

interface ExportPayload {
  step: {
    name: string
    target_type: string
  }
  dataset: {
    id: number
    name: string
    description: string | null
  }
  comparison: {
    base_run_id: number
    compare_run_id: number
  }
  runs: {
    base: ExportRun
    compare: ExportRun
  }
  /** Every case that appears in either run, with full test-definition and
   * result data for each side. Sorted by interest (regressed/errored first). */
  cases: ExportCase[]
}

function toExportStats(run: RunDetail): ExportStats {
  return {
    total: run.total_cases,
    passed: run.passed,
    failed: run.failed,
    errored: run.errored,
    pass_rate: passRate(run),
  }
}

/** Extract the primary resolved model from a model_snapshot. Step-target
 * snapshots are `{step_name: "model_string"}`; pipeline-target snapshots are
 * `{step_name: {model: "model_string"}}`. Returns the first model string
 * found, or null. */
function resolveModelFromSnapshot(
  snap: Record<string, unknown> | null | undefined,
): string | null {
  if (!snap) return null
  for (const v of Object.values(snap)) {
    if (typeof v === 'string') return v
    if (v && typeof v === 'object') {
      const inner = v as Record<string, unknown>
      if (typeof inner.model === 'string') return inner.model
    }
  }
  return null
}

function toExportRunPrompts(
  flat: FlatPromptVersion[],
  items: Array<HistoricalPromptItem | undefined>,
): ExportRunPrompt[] {
  return flat.map((f, i) => {
    const item = items[i]
    return {
      step_name: f.step_name,
      prompt_key: f.prompt_key,
      prompt_type: f.prompt_type,
      version: f.version,
      content: item?.content ?? '',
      variable_definitions: item?.variable_definitions ?? null,
    }
  })
}

function toExportRunContext(
  run: RunDetail,
  prompts: ExportRunPrompt[],
): ExportRunContext {
  return {
    model: resolveModelFromSnapshot(run.model_snapshot),
    model_snapshot: run.model_snapshot,
    prompts,
    instructions_schema: run.instructions_schema_snapshot,
    variant_delta: run.delta_snapshot,
    variant_id: run.variant_id,
  }
}

function toExportRun(run: RunDetail, prompts: ExportRunPrompt[]): ExportRun {
  return {
    id: run.id,
    stats: toExportStats(run),
    context: toExportRunContext(run, prompts),
  }
}

function toExportCaseVersion(
  row: HistoricalCaseItem | undefined,
): ExportCaseVersion | null {
  if (!row) return null
  return {
    case_id: row.id,
    version: row.version,
    inputs: row.inputs,
    expected_output: row.expected_output,
    metadata_: row.metadata_,
  }
}

function toExportCaseRunResult(
  runId: number,
  r: CaseResultItem | undefined,
): ExportCaseRunResult | null {
  if (!r) return null
  return {
    run_id: runId,
    passed: r.passed,
    output_data: r.output_data,
    error_message: r.error_message,
  }
}

/** Build the unified per-case export data. For each case that appeared in
 * either run, resolve the exact historical version each run used, pair it
 * with the run's observed result, and label the bucket + delta. */
function buildCases(
  baseRun: RunDetail,
  compareRun: RunDetail,
  historicalCases: Map<number, HistoricalCaseItem>,
): ExportCase[] {
  const baseByName = new Map(
    baseRun.case_results.map((r) => [r.case_name, r]),
  )
  const compareByName = new Map(
    compareRun.case_results.map((r) => [r.case_name, r]),
  )
  const names = Array.from(
    new Set([...baseByName.keys(), ...compareByName.keys()]),
  )

  const out: ExportCase[] = []
  for (const name of names) {
    const b = baseByName.get(name)
    const c = compareByName.get(name)
    const baseRow = b?.case_id != null ? historicalCases.get(b.case_id) : undefined
    const compareRow =
      c?.case_id != null ? historicalCases.get(c.case_id) : undefined
    const baseVersion = toExportCaseVersion(baseRow)
    const compareVersion = toExportCaseVersion(compareRow)

    let bucket: ExportCase['bucket']
    if (!b || !c) {
      bucket = 'unmatched'
    } else if (baseRow && compareRow) {
      bucket = baseRow.version === compareRow.version ? 'matched' : 'drifted'
    } else {
      // Missing historical data on at least one side; treat as matched if
      // both have the same case id, otherwise unmatched.
      bucket = b?.case_id === c?.case_id ? 'matched' : 'drifted'
    }

    const delta = caseDelta(b, c)
    out.push({
      name,
      bucket,
      delta,
      base_version: baseVersion,
      compare_version: compareVersion,
      base_result: toExportCaseRunResult(baseRun.id, b),
      compare_result: toExportCaseRunResult(compareRun.id, c),
    })
  }

  // Stable sort: regressed/errored first, then failing-in-compare, then
  // improved, then the rest. Alpha tiebreaker.
  function priority(ec: ExportCase): number {
    const k = ec.delta
    if (k === 'regressed') return 0
    if (ec.base_result?.error_message || ec.compare_result?.error_message)
      return 0
    const compareFailing = ec.compare_result
      ? !!ec.compare_result.error_message || !ec.compare_result.passed
      : false
    if (compareFailing) return 1
    if (k === 'improved') return 2
    return 3
  }
  out.sort((a, b) => priority(a) - priority(b) || a.name.localeCompare(b.name))
  return out
}

/** A base/compare prompt pair, keyed by step+key+type. Either side may be
 * absent if one run didn't use that prompt. */
interface PromptPair {
  key: string
  step_name: string | null
  prompt_key: string
  prompt_type: string
  base: ExportRunPrompt | null
  compare: ExportRunPrompt | null
}

function promptPairKey(p: {
  step_name: string | null
  prompt_key: string
  prompt_type: string
}): string {
  return `${p.step_name ?? ''}::${p.prompt_key}::${p.prompt_type}`
}

/** Pair up prompts from both runs by (step_name, prompt_key, prompt_type).
 * Returns a stable-ordered list with base-first then compare-only. */
function pairRunPrompts(
  base: ExportRunPrompt[],
  compare: ExportRunPrompt[],
): PromptPair[] {
  const pairs = new Map<string, PromptPair>()
  for (const p of base) {
    const k = promptPairKey(p)
    pairs.set(k, {
      key: k,
      step_name: p.step_name,
      prompt_key: p.prompt_key,
      prompt_type: p.prompt_type,
      base: p,
      compare: null,
    })
  }
  for (const p of compare) {
    const k = promptPairKey(p)
    const existing = pairs.get(k)
    if (existing) {
      existing.compare = p
    } else {
      pairs.set(k, {
        key: k,
        step_name: p.step_name,
        prompt_key: p.prompt_key,
        prompt_type: p.prompt_type,
        base: null,
        compare: p,
      })
    }
  }
  return Array.from(pairs.values())
}

interface BuildPayloadArgs {
  dataset: {
    id: number
    name: string
    description: string | null
    target_name: string
    target_type: string
  }
  baseRun: RunDetail
  compareRun: RunDetail
  basePrompts: ExportRunPrompt[]
  comparePrompts: ExportRunPrompt[]
  /** Resolved historical case rows keyed by case_id. Populated by the
   * compare page from every case_id referenced in either run's case_results. */
  historicalCases: Map<number, HistoricalCaseItem>
}

function buildPayloadJSON(args: BuildPayloadArgs): ExportPayload {
  const {
    dataset,
    baseRun,
    compareRun,
    basePrompts,
    comparePrompts,
    historicalCases,
  } = args

  return {
    step: {
      name: dataset.target_name,
      target_type: dataset.target_type,
    },
    dataset: {
      id: dataset.id,
      name: dataset.name,
      description: dataset.description,
    },
    comparison: {
      base_run_id: baseRun.id,
      compare_run_id: compareRun.id,
    },
    runs: {
      base: toExportRun(baseRun, basePrompts),
      compare: toExportRun(compareRun, comparePrompts),
    },
    cases: buildCases(baseRun, compareRun, historicalCases),
  }
}

// Meta-prompt prepended to markdown exports. JSON omits this.
const META_PROMPT = `# Eval run comparison

This document contains full data for two runs of an automated evaluation suite over a language-model step. Both runs execute the same suite of test cases; each test case has defined inputs, an expected output, and optional metadata. A pass/fail verdict is produced per case — the exact logic of that verdict is not included here, so treat ` + '`pass`' + ` and ` + '`fail`' + ` as opaque signals produced by the framework. Ask for the evaluator definition if the reasoning behind a verdict matters to your analysis.

Every case is shown in full regardless of whether its result changed between runs, because patterns can only be inferred from the complete picture. A proposed change that improves a failing case may break a currently-passing one; both must remain visible.

**Version drift:** when a case's definition (inputs, expected output, or metadata) was edited between the two runs, that case is labeled *drifted* and both versions are shown side by side. An apparent "improvement" on a drifted case may reflect the test being rewritten rather than the model changing behavior — compare the two versions carefully before attributing progress.

**What you can change:** the system prompt, the user prompt template, the instructions schema, per-case expected outputs, and the underlying model. Raise questions about anything else that would meaningfully inform your recommendations.
`

function fenced(lang: string, body: string): string {
  return '```' + lang + '\n' + body + '\n```'
}

function jsonFence(obj: unknown): string {
  return fenced('json', JSON.stringify(obj, null, 2))
}

/** Render a single case version's full content (inputs, expected, metadata). */
function renderCaseVersion(v: ExportCaseVersion): string {
  const parts: string[] = []
  parts.push(`**Inputs:**\n${jsonFence(v.inputs)}`)
  parts.push(
    v.expected_output
      ? `**Expected output:**\n${jsonFence(v.expected_output)}`
      : `**Expected output:** *none defined*`,
  )
  parts.push(
    v.metadata_ && Object.keys(v.metadata_).length > 0
      ? `**Metadata:**\n${jsonFence(v.metadata_)}`
      : `**Metadata:** *none*`,
  )
  return parts.join('\n\n')
}

/** Render a run's observed result on a case: status line + output or error. */
function renderCaseRunResult(
  label: string,
  runId: number,
  r: ExportCaseRunResult | null,
): string {
  if (!r) {
    return `**${label} run (#${runId}):** *case not present in this run*`
  }
  const status = r.error_message ? 'errored' : r.passed ? 'pass' : 'fail'
  const header = `**${label} run (#${runId}) — ${status}:**`
  if (r.error_message) {
    return `${header}\n${fenced('', `error: ${r.error_message}`)}`
  }
  if (r.output_data == null) {
    return `${header}\n*no output recorded*`
  }
  return `${header}\n${jsonFence(r.output_data)}`
}

/** Render a single case section in full detail.
 *
 * Structure:
 *   ### header (case name, base/compare status, delta, version drift tag)
 *   <case definition block — either a single version when matched, or both
 *    versions side by side when drifted/unmatched>
 *   <base run result: output or error>
 *   <compare run result: output or error>
 */
function renderCase(c: ExportCase, baseRunId: number, compareRunId: number): string {
  const baseStatus = c.base_result
    ? c.base_result.error_message
      ? 'errored'
      : c.base_result.passed
        ? 'pass'
        : 'fail'
    : 'n/a'
  const compareStatus = c.compare_result
    ? c.compare_result.error_message
      ? 'errored'
      : c.compare_result.passed
        ? 'pass'
        : 'fail'
    : 'n/a'

  // Version tag appended to the header.
  let versionTag = ''
  if (c.bucket === 'drifted') {
    versionTag = ` [drifted v${c.base_version?.version ?? '?'} -> v${c.compare_version?.version ?? '?'}]`
  } else if (c.bucket === 'unmatched') {
    if (c.base_version && !c.compare_version) {
      versionTag = ` [only in base (v${c.base_version.version})]`
    } else if (c.compare_version && !c.base_version) {
      versionTag = ` [only in compare (v${c.compare_version.version})]`
    } else {
      versionTag = ` [unmatched]`
    }
  } else if (c.base_version) {
    versionTag = ` [both runs used v${c.base_version.version}]`
  }

  const header = `### \`${c.name}\` — base: ${baseStatus} → compare: ${compareStatus} (${c.delta})${versionTag}`

  // Case-definition block: rules
  //   matched  -> single block (the one version both runs used)
  //   drifted  -> both base-version and compare-version blocks
  //   unmatched-> single block for whichever side had it
  const defParts: string[] = ['#### Case definition']
  if (c.bucket === 'matched' && c.base_version) {
    defParts.push(
      `*Both runs used case version v${c.base_version.version}.*`,
      renderCaseVersion(c.base_version),
    )
  } else if (c.bucket === 'drifted') {
    if (c.base_version) {
      defParts.push(
        `##### Base used v${c.base_version.version}`,
        renderCaseVersion(c.base_version),
      )
    } else {
      defParts.push('##### Base', '*historical case data could not be resolved*')
    }
    if (c.compare_version) {
      defParts.push(
        `##### Compare used v${c.compare_version.version}`,
        renderCaseVersion(c.compare_version),
      )
    } else {
      defParts.push('##### Compare', '*historical case data could not be resolved*')
    }
  } else {
    // unmatched
    const present = c.base_version ?? c.compare_version
    const side = c.base_version ? 'Base' : 'Compare'
    if (present) {
      defParts.push(
        `*Case present only in ${side} at v${present.version}.*`,
        renderCaseVersion(present),
      )
    } else {
      defParts.push('*historical case data could not be resolved for either run*')
    }
  }

  // Results block
  const resultParts = [
    '#### Results',
    renderCaseRunResult('Base', baseRunId, c.base_result),
    renderCaseRunResult('Compare', compareRunId, c.compare_result),
  ]

  return [header, defParts.join('\n\n'), resultParts.join('\n\n')].join('\n\n') + '\n'
}

// ---------------------------------------------------------------------------
// Failing-case summary banner + aggregate comparison table
// ---------------------------------------------------------------------------

/** Top-of-section banner summarizing per-case deltas and drift counts. */
function caseSummaryBanner(cases: ExportCase[]): string {
  if (cases.length === 0) return ''
  const regressed: string[] = []
  const improved: string[] = []
  const erroredInCompare: string[] = []
  const drifted: string[] = []
  const unmatched: string[] = []
  for (const c of cases) {
    if (c.delta === 'regressed') regressed.push(c.name)
    else if (c.delta === 'improved') improved.push(c.name)
    if (c.compare_result?.error_message) erroredInCompare.push(c.name)
    if (c.bucket === 'drifted') drifted.push(c.name)
    else if (c.bucket === 'unmatched') unmatched.push(c.name)
  }
  const formatList = (names: string[]): string => {
    const shown = names.slice(0, 5).map((n) => `\`${n}\``).join(', ')
    const more = names.length > 5 ? `, +${names.length - 5} more` : ''
    return `${shown}${more}`
  }
  const parts: string[] = []
  if (regressed.length > 0) {
    parts.push(`${regressed.length} regressed (${formatList(regressed)})`)
  }
  if (erroredInCompare.length > 0) {
    parts.push(
      `${erroredInCompare.length} errored in compare (${formatList(erroredInCompare)})`,
    )
  }
  if (improved.length > 0) {
    parts.push(`${improved.length} improved (${formatList(improved)})`)
  }
  if (drifted.length > 0) {
    parts.push(
      `${drifted.length} case(s) drifted — the test definition changed between the two runs (${formatList(drifted)})`,
    )
  }
  if (unmatched.length > 0) {
    parts.push(
      `${unmatched.length} case(s) unmatched — present in only one run (${formatList(unmatched)})`,
    )
  }
  if (parts.length === 0) {
    return '**No changes:** all cases passed with the same outcome in both runs; no case definitions drifted.'
  }
  return `**Summary:** ${parts.join('; ')}`
}

function signedInt(n: number): string {
  if (n === 0) return '0'
  return n > 0 ? `+${n}` : `${n}`
}

function signedPct(base: number | null, compare: number | null): string {
  if (base == null || compare == null) return '—'
  const delta = (compare - base) * 100
  if (delta === 0) return '0.0%'
  const sign = delta > 0 ? '+' : ''
  return `${sign}${delta.toFixed(1)}%`
}

function padCell(s: string, w: number): string {
  if (s.length >= w) return s
  return s + ' '.repeat(w - s.length)
}

function aggregateComparisonTable(
  baseRunId: number,
  compareRunId: number,
  baseStats: ExportStats,
  compareStats: ExportStats,
): string {
  const passRateDelta = signedPct(baseStats.pass_rate, compareStats.pass_rate)
  const rows: Array<[string, string, string, string]> = [
    [
      'Pass rate',
      formatPct(baseStats.pass_rate),
      formatPct(compareStats.pass_rate),
      passRateDelta,
    ],
    [
      'Passed',
      `${baseStats.passed}/${baseStats.total}`,
      `${compareStats.passed}/${compareStats.total}`,
      signedInt(compareStats.passed - baseStats.passed),
    ],
    [
      'Failed',
      String(baseStats.failed),
      String(compareStats.failed),
      signedInt(compareStats.failed - baseStats.failed),
    ],
    [
      'Errored',
      String(baseStats.errored),
      String(compareStats.errored),
      signedInt(compareStats.errored - baseStats.errored),
    ],
  ]
  const headers: [string, string, string, string] = [
    'Metric',
    `Base (#${baseRunId})`,
    `Compare (#${compareRunId})`,
    'Δ',
  ]
  // Compute column widths for light padding
  const widths: [number, number, number, number] = [
    headers[0].length,
    headers[1].length,
    headers[2].length,
    headers[3].length,
  ]
  for (const r of rows) {
    for (let i = 0; i < 4; i++) {
      if (r[i].length > widths[i]) widths[i] = r[i].length
    }
  }
  const header =
    `| ${padCell(headers[0], widths[0])} | ${padCell(headers[1], widths[1])} | ${padCell(headers[2], widths[2])} | ${padCell(headers[3], widths[3])} |`
  const sep =
    `|${'-'.repeat(widths[0] + 2)}|${'-'.repeat(widths[1] + 2)}|${'-'.repeat(widths[2] + 2)}|${'-'.repeat(widths[3] + 2)}|`
  const body = rows
    .map(
      (r) =>
        `| ${padCell(r[0], widths[0])} | ${padCell(r[1], widths[1])} | ${padCell(r[2], widths[2])} | ${padCell(r[3], widths[3])} |`,
    )
    .join('\n')
  return [header, sep, body].join('\n')
}

/** Render a resolved prompt (with full text) as a markdown section. */
function renderPrompt(p: ExportRunPrompt): string {
  const parts: string[] = []
  const stepPrefix = p.step_name ? `${p.step_name} · ` : ''
  parts.push(
    `**${stepPrefix}${p.prompt_key} (${p.prompt_type}) — v${p.version}**`,
  )
  parts.push(fenced('', p.content || '(empty)'))
  if (p.variable_definitions && Object.keys(p.variable_definitions).length > 0) {
    parts.push('*Variable definitions:*')
    parts.push(jsonFence(p.variable_definitions))
  }
  return parts.join('\n\n')
}

function renderRunContextSection(
  label: string,
  runId: number,
  ctx: ExportRunContext,
): string {
  const modelLine = ctx.model ? `\`${ctx.model}\`` : '*not recorded*'
  const variantLine = ctx.variant_id
    ? `**Variant:** \`#${ctx.variant_id}\` — overrides applied to the production config for this run.`
    : '**Variant:** *none (run used production configuration directly)*'
  const deltaBlock =
    ctx.variant_delta && Object.keys(ctx.variant_delta).length > 0
      ? `\n\n*Variant delta:*\n${jsonFence(ctx.variant_delta)}`
      : ''
  const promptsSection =
    ctx.prompts.length > 0
      ? ctx.prompts.map(renderPrompt).join('\n\n')
      : '*No prompts recorded.*'
  const instrBlock = ctx.instructions_schema
    ? jsonFence(ctx.instructions_schema)
    : '*not recorded*'
  return [
    `## ${label} (run #${runId})`,
    '',
    `**Model:** ${modelLine}`,
    '',
    variantLine + deltaBlock,
    '',
    '### Prompts used',
    '',
    promptsSection,
    '',
    '### Instructions schema',
    '',
    instrBlock,
  ].join('\n')
}

function buildPayloadMarkdown(args: BuildPayloadArgs): string {
  const payload = buildPayloadJSON(args)
  const { step, dataset, comparison, runs, cases } = payload

  const aggregateTable = aggregateComparisonTable(
    runs.base.id,
    runs.compare.id,
    runs.base.stats,
    runs.compare.stats,
  )

  const banner = caseSummaryBanner(cases)
  const perCase = cases
    .map((c) => renderCase(c, runs.base.id, runs.compare.id))
    .join('\n')
  const perCaseSection = banner
    ? `## Per-case results (all cases, shown in full)\n\n${banner}\n\n${perCase}`
    : `## Per-case results (all cases, shown in full)\n\n${perCase}`

  const datasetDescription =
    dataset.description && dataset.description.trim().length > 0
      ? dataset.description.trim()
      : '*No description provided.*'

  return [
    META_PROMPT,
    '---',
    '',
    '## What is being tested',
    '',
    `**Step under test:** \`${step.name}\` (target type: ${step.target_type})`,
    '',
    `**Dataset:** \`${dataset.name}\` (id ${dataset.id})`,
    '',
    datasetDescription,
    '',
    '## Comparison summary',
    '',
    `Base run \`#${comparison.base_run_id}\` vs Compare run \`#${comparison.compare_run_id}\`.`,
    '',
    renderRunContextSection('Base configuration', runs.base.id, runs.base.context),
    '',
    renderRunContextSection('Compare configuration', runs.compare.id, runs.compare.context),
    '',
    '## Aggregate results',
    '',
    aggregateTable,
    '',
    perCaseSection,
  ].join('\n')
}

// ---------------------------------------------------------------------------
// Export UI helpers
// ---------------------------------------------------------------------------

const CLIPBOARD_WARNING_BYTES = 100 * 1024 // 100 KB

function byteLength(s: string): number {
  // TextEncoder gives UTF-8 byte count; clipboard limits are byte-based.
  return new TextEncoder().encode(s).length
}

function formatKB(bytes: number): string {
  return `${(bytes / 1024).toFixed(1)} KB`
}

function downloadBlob(content: string, mime: string, filename: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

type ExportFormat = 'markdown' | 'json'

interface PendingWarning {
  format: ExportFormat
  content: string
  bytes: number
  filename: string
  mime: string
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

function ComparisonStatCard({
  label,
  baseValue,
  compareValue,
  color,
  invertColor = false,
  format = (v) => (v == null ? '-' : String(v)),
}: {
  label: string
  baseValue: number | null
  compareValue: number | null
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
            <p className="text-[10px] text-muted-foreground uppercase">Compare</p>
            <p className={`text-xl font-bold ${color ?? ''}`}>{format(compareValue)}</p>
          </div>
        </div>
        <div>
          <DeltaBadge
            baseValue={baseValue}
            compareValue={compareValue}
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

function BaseOutputPanel({ result }: { result: CaseResultItem | undefined }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide">
          Base output
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

function CompareOutputPanel({
  baseResult,
  compareResult,
}: {
  baseResult: CaseResultItem | undefined
  compareResult: CaseResultItem | undefined
}) {
  const baseOut = baseResult?.output_data ?? null
  const cmpOut = compareResult?.output_data ?? null

  let body: React.ReactNode
  if (compareResult?.error_message) {
    body = <ErrorBlock message={compareResult.error_message} />
  } else if (cmpOut && baseOut && !isErrored(baseResult)) {
    // Both sides have outputs and base didn't error -- show diff
    body = (
      <JsonScroll>
        <JsonViewer before={baseOut} after={cmpOut} maxDepth={3} />
      </JsonScroll>
    )
  } else if (cmpOut) {
    // Compare produced output but base did not (or errored) -- fall back to plain view
    body = (
      <JsonScroll>
        <JsonViewer data={cmpOut} maxDepth={3} />
      </JsonScroll>
    )
  } else {
    body = <p className="text-xs text-muted-foreground italic">No output recorded</p>
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide">
          Compare output
        </p>
        <PassFailBadge result={compareResult} />
      </div>
      {body}
    </div>
  )
}

/**
 * Configuration comparison panel — renders each run's actual model, prompts,
 * instructions schema, and variant delta side-by-side. Prompts are shown in
 * full (Base as plain text, Compare as a diff against Base when both are
 * present) so the reader can see what each run used without project jargon.
 */
function ConfigurationComparison({
  baseRunId,
  compareRunId,
  baseModel,
  compareModel,
  baseInstructionsSchema,
  compareInstructionsSchema,
  baseVariantDelta,
  compareVariantDelta,
  promptPairs,
}: {
  baseRunId: number
  compareRunId: number
  baseModel: string | null
  compareModel: string | null
  baseInstructionsSchema: Record<string, unknown> | null
  compareInstructionsSchema: Record<string, unknown> | null
  baseVariantDelta: Record<string, unknown> | null
  compareVariantDelta: Record<string, unknown> | null
  promptPairs: PromptPair[]
}) {
  const schemaSame =
    JSON.stringify(baseInstructionsSchema ?? null) ===
    JSON.stringify(compareInstructionsSchema ?? null)
  return (
    <div className="space-y-5">
      {/* Model */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide mb-1">
            Model (Base #{baseRunId})
          </p>
          <p className="text-sm font-mono">
            {baseModel ?? <span className="text-muted-foreground italic">not recorded</span>}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide mb-1">
            Model (Compare #{compareRunId})
            {baseModel != null && compareModel != null && baseModel === compareModel && (
              <span className="ml-2 text-muted-foreground normal-case"> (same as base)</span>
            )}
          </p>
          <p className="text-sm font-mono">
            {compareModel ?? <span className="text-muted-foreground italic">not recorded</span>}
          </p>
        </div>
      </div>

      {/* Prompts: pair each (step, key, type) and show Base + Compare */}
      {promptPairs.map((pair) => (
        <PromptPairPanel key={pair.key} pair={pair} />
      ))}

      {/* Variant deltas (only shown when present) */}
      {(baseVariantDelta || compareVariantDelta) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide mb-1">
              Variant delta (Base)
            </p>
            {baseVariantDelta ? (
              <JsonScroll>
                <JsonViewer data={baseVariantDelta} maxDepth={3} />
              </JsonScroll>
            ) : (
              <p className="text-xs text-muted-foreground italic">
                No variant applied.
              </p>
            )}
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide mb-1">
              Variant delta (Compare)
            </p>
            {compareVariantDelta ? (
              <JsonScroll>
                <JsonViewer data={compareVariantDelta} maxDepth={3} />
              </JsonScroll>
            ) : (
              <p className="text-xs text-muted-foreground italic">
                No variant applied.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Instructions schema */}
      <div>
        <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide mb-1">
          Instructions schema
          {schemaSame && (
            <span className="ml-2 text-muted-foreground normal-case"> (identical in both runs)</span>
          )}
        </p>
        {schemaSame ? (
          baseInstructionsSchema ? (
            <JsonScroll>
              <JsonViewer data={baseInstructionsSchema} maxDepth={3} />
            </JsonScroll>
          ) : (
            <p className="text-xs text-muted-foreground italic">
              No schema recorded.
            </p>
          )
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div>
              <p className="text-[9px] uppercase text-muted-foreground mb-0.5">
                Base #{baseRunId}
              </p>
              {baseInstructionsSchema ? (
                <JsonScroll>
                  <JsonViewer data={baseInstructionsSchema} maxDepth={3} />
                </JsonScroll>
              ) : (
                <p className="text-xs text-muted-foreground italic">
                  not recorded
                </p>
              )}
            </div>
            <div>
              <p className="text-[9px] uppercase text-muted-foreground mb-0.5">
                Compare #{compareRunId}
              </p>
              {compareInstructionsSchema && baseInstructionsSchema ? (
                <JsonScroll>
                  <JsonViewer
                    before={baseInstructionsSchema}
                    after={compareInstructionsSchema}
                    maxDepth={3}
                  />
                </JsonScroll>
              ) : compareInstructionsSchema ? (
                <JsonScroll>
                  <JsonViewer data={compareInstructionsSchema} maxDepth={3} />
                </JsonScroll>
              ) : (
                <p className="text-xs text-muted-foreground italic">
                  not recorded
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Render a single base/compare prompt pair. Base is plain text; Compare is
 * plain text when identical to Base (with a "same" marker) or a highlighted
 * diff when different.
 */
function PromptPairPanel({ pair }: { pair: PromptPair }) {
  const stepPrefix = pair.step_name ? `${pair.step_name} · ` : ''
  const label = `${stepPrefix}${pair.prompt_key} (${pair.prompt_type})`
  const baseContent = pair.base?.content ?? ''
  const compareContent = pair.compare?.content ?? ''
  const contentSame =
    pair.base != null &&
    pair.compare != null &&
    baseContent === compareContent
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide">
        {label}
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div>
          <p className="text-[9px] uppercase text-muted-foreground mb-0.5">
            Base{pair.base ? ` (v${pair.base.version})` : ''}
          </p>
          {pair.base ? (
            <pre className="whitespace-pre-wrap text-xs bg-background border rounded p-2 max-h-[300px] overflow-auto">
              {baseContent || <span className="italic text-muted-foreground">(empty)</span>}
            </pre>
          ) : (
            <p className="text-xs text-muted-foreground italic">
              not used by base
            </p>
          )}
        </div>
        <div>
          <p className="text-[9px] uppercase text-muted-foreground mb-0.5">
            Compare{pair.compare ? ` (v${pair.compare.version})` : ''}
            {contentSame && (
              <span className="ml-2 text-muted-foreground"> (same as base)</span>
            )}
          </p>
          {pair.compare ? (
            <pre className="whitespace-pre-wrap text-xs bg-background border rounded p-2 max-h-[300px] overflow-auto">
              {compareContent || <span className="italic text-muted-foreground">(empty)</span>}
            </pre>
          ) : (
            <p className="text-xs text-muted-foreground italic">
              not used by compare
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function CaseDetailCard({
  datasetId,
  caseDef,
  baseResult,
  compareResult,
  bucket,
}: {
  datasetId: number
  caseDef: CaseItem | undefined
  baseResult: CaseResultItem | undefined
  compareResult: CaseResultItem | undefined
  bucket: VersionBucket | undefined
}) {
  return (
    <Card className="bg-muted/20 border-0 rounded-none">
      <CardContent className="p-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {bucket === 'drifted' || bucket === 'unmatched' ? (
            <DriftedInputExpectedPanel
              datasetId={datasetId}
              baseCaseId={baseResult?.case_id ?? null}
              compareCaseId={compareResult?.case_id ?? null}
              bucket={bucket}
            />
          ) : (
            <InputExpectedPanel caseDef={caseDef} />
          )}
          <BaseOutputPanel result={baseResult} />
          <CompareOutputPanel
            baseResult={baseResult}
            compareResult={compareResult}
          />
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * For drifted/unmatched cases, fetch the exact case row(s) used by each run
 * and render Base (plain) + Compare (diff vs base) stacked per field.
 *
 * Case rows are append-only, so the historical endpoint resolves the exact
 * content used by the past run even if the case has since been edited or
 * soft-deleted.
 */
function DriftedInputExpectedPanel({
  datasetId,
  baseCaseId,
  compareCaseId,
  bucket,
}: {
  datasetId: number
  baseCaseId: number | null
  compareCaseId: number | null
  bucket: 'drifted' | 'unmatched'
}) {
  const baseQ = useHistoricalCase(datasetId, baseCaseId)
  const compareQ = useHistoricalCase(datasetId, compareCaseId)

  const baseCase = baseQ.data
  const compareCase = compareQ.data

  const loading =
    (baseCaseId !== null && baseQ.isLoading) ||
    (compareCaseId !== null && compareQ.isLoading)

  if (loading) {
    return (
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground italic">
          Loading case versions…
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <CaseFieldDiff
        field="inputs"
        label="Input"
        baseCase={baseCase}
        compareCase={compareCase}
        bucket={bucket}
      />
      <CaseFieldDiff
        field="expected_output"
        label="Expected output"
        baseCase={baseCase}
        compareCase={compareCase}
        bucket={bucket}
      />
      <CaseFieldDiff
        field="metadata_"
        label="Metadata"
        baseCase={baseCase}
        compareCase={compareCase}
        bucket={bucket}
      />
    </div>
  )
}

function CaseFieldDiff({
  field,
  label,
  baseCase,
  compareCase,
  bucket,
}: {
  field: 'inputs' | 'expected_output' | 'metadata_'
  label: string
  baseCase: HistoricalCaseItem | undefined
  compareCase: HistoricalCaseItem | undefined
  bucket: 'drifted' | 'unmatched'
}) {
  const baseValue = baseCase?.[field] ?? null
  const compareValue = compareCase?.[field] ?? null

  const emptyMessage =
    field === 'expected_output'
      ? 'No expected output defined'
      : field === 'metadata_'
        ? 'No metadata'
        : 'Not available'

  // Unmatched: only one side has the case. Show the present side with a label.
  if (bucket === 'unmatched') {
    const present = baseCase ? baseValue : compareValue
    const sideLabel = baseCase ? 'Base only' : 'Compare only'
    const versionLabel = baseCase
      ? `v${baseCase.version}`
      : compareCase
        ? `v${compareCase.version}`
        : ''
    return (
      <div>
        <div className="flex items-center gap-2 mb-1">
          <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide">
            {label}
          </p>
          <Badge variant="outline" className="text-[10px] px-1.5 py-0">
            {sideLabel} {versionLabel}
          </Badge>
        </div>
        {present ? (
          <JsonScroll>
            <JsonViewer data={present} maxDepth={3} />
          </JsonScroll>
        ) : (
          <p className="text-xs text-muted-foreground italic">{emptyMessage}</p>
        )}
      </div>
    )
  }

  // Drifted: Base as plain view, Compare as diff (vs base).
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wide">
        {label}
      </p>
      <div>
        <p className="text-[9px] uppercase text-muted-foreground mb-0.5">
          Base{baseCase ? ` (v${baseCase.version})` : ''}
        </p>
        {baseValue ? (
          <JsonScroll>
            <JsonViewer data={baseValue} maxDepth={3} />
          </JsonScroll>
        ) : (
          <p className="text-xs text-muted-foreground italic">{emptyMessage}</p>
        )}
      </div>
      <div>
        <p className="text-[9px] uppercase text-muted-foreground mb-0.5">
          Compare{compareCase ? ` (v${compareCase.version})` : ''}
        </p>
        {baseValue && compareValue ? (
          <JsonScroll>
            <JsonViewer before={baseValue} after={compareValue} maxDepth={3} />
          </JsonScroll>
        ) : compareValue ? (
          <JsonScroll>
            <JsonViewer data={compareValue} maxDepth={3} />
          </JsonScroll>
        ) : (
          <p className="text-xs text-muted-foreground italic">{emptyMessage}</p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Case row
// ---------------------------------------------------------------------------

function CaseRow({
  name,
  datasetId,
  caseDef,
  baseResult,
  compareResult,
  bucket,
  baseVersion,
  compareVersion,
  isExpanded,
  onToggle,
}: {
  name: string
  datasetId: number
  caseDef: CaseItem | undefined
  baseResult: CaseResultItem | undefined
  compareResult: CaseResultItem | undefined
  bucket: VersionBucket | undefined
  baseVersion: string | undefined
  compareVersion: string | undefined
  isExpanded: boolean
  onToggle: () => void
}) {
  const delta = caseDelta(baseResult, compareResult)
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
        <TableCell className="font-medium text-sm">
          <span className="inline-flex items-center gap-1.5">
            {name}
            {bucket && (
              <VersionBucketBadge
                bucket={bucket}
                baseVersion={baseVersion}
                compareVersion={compareVersion}
              />
            )}
          </span>
        </TableCell>
        <TableCell>
          <PassFailBadge result={baseResult} />
        </TableCell>
        <TableCell>
          <ScoresCell result={baseResult} />
        </TableCell>
        <TableCell>
          <PassFailBadge result={compareResult} />
        </TableCell>
        <TableCell>
          <ScoresCell result={compareResult} />
        </TableCell>
        <TableCell>
          <DeltaIndicator kind={delta} />
        </TableCell>
      </TableRow>
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={7} className="p-0 border-b">
            <CaseDetailCard
              datasetId={datasetId}
              caseDef={caseDef}
              baseResult={baseResult}
              compareResult={compareResult}
              bucket={bucket}
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
  const { baseRunId, compareRunId } = Route.useSearch()
  const datasetId = Number(rawDatasetId)

  const baseRunQ = useEvalRun(datasetId, baseRunId)
  const compareRunQ = useEvalRun(datasetId, compareRunId)
  const datasetQ = useDataset(datasetId)

  const isLoading = baseRunQ.isLoading || compareRunQ.isLoading || datasetQ.isLoading
  // Dataset-fetch errors degrade gracefully (no inputs/expected); don't block.
  const error = baseRunQ.error || compareRunQ.error

  const baseRun = baseRunQ.data
  const compareRun = compareRunQ.data

  // Look up variant name if compare run has variant_id
  const variantIdForLookup = compareRun?.variant_id ?? 0
  const variantQ = useVariant(datasetId, variantIdForLookup)

  // Resolve historical prompt content for each run. Runs capture only version
  // ids in `prompt_versions`; these hooks fetch the full prompt rows so the
  // configuration diff and export can show what each run actually used.
  const basePromptsQ = useRunPrompts(baseRun?.prompt_versions)
  const comparePromptsQ = useRunPrompts(compareRun?.prompt_versions)

  // Resolve the exact case rows referenced by each run's case_results. Each
  // result's case_id points at the specific (append-only) row used by that
  // run, which may no longer be the latest version if the case has drifted.
  const historicalCaseIds = useMemo(() => {
    const ids: number[] = []
    for (const r of baseRun?.case_results ?? []) {
      if (r.case_id != null) ids.push(r.case_id)
    }
    for (const r of compareRun?.case_results ?? []) {
      if (r.case_id != null) ids.push(r.case_id)
    }
    return ids
  }, [baseRun?.case_results, compareRun?.case_results])
  const historicalCasesQ = useHistoricalCases(datasetId, historicalCaseIds)

  // Build dataset case map (by case name -> CaseItem). Empty when dataset
  // errored or hasn't loaded yet.
  const caseByName = useMemo(() => {
    const m = new Map<string, CaseItem>()
    for (const c of datasetQ.data?.cases ?? []) m.set(c.name, c)
    return m
  }, [datasetQ.data])

  // Build per-case run-result maps + union of all case names. Memoed so the
  // auto-expand initializer downstream is stable.
  const {
    baseByName,
    compareByName,
    allCaseNames,
    bucketByName,
    matchedCount,
    driftedCount,
    unmatchedCount,
  } = useMemo(() => {
    const baseMap = new Map<string, CaseResultItem>()
    const cmpMap = new Map<string, CaseResultItem>()
    for (const r of baseRun?.case_results ?? []) baseMap.set(r.case_name, r)
    for (const r of compareRun?.case_results ?? []) cmpMap.set(r.case_name, r)
    const names = Array.from(
      new Set([...baseMap.keys(), ...cmpMap.keys()]),
    ).sort()

    const buckets = new Map<string, VersionBucket>()
    let matched = 0
    let drifted = 0
    let unmatched = 0
    if (baseRun && compareRun) {
      for (const name of names) {
        const bucket = computeCaseBucket(
          baseMap.get(name),
          cmpMap.get(name),
          baseRun,
          compareRun,
        )
        buckets.set(name, bucket)
        if (bucket === 'matched') matched++
        else if (bucket === 'drifted') drifted++
        else unmatched++
      }
    }

    return {
      baseByName: baseMap,
      compareByName: cmpMap,
      allCaseNames: names,
      bucketByName: buckets,
      matchedCount: matched,
      driftedCount: drifted,
      unmatchedCount: unmatched,
    }
  }, [baseRun, compareRun])

  // Seed expanded set with regressed + errored cases. useState initializer
  // runs once; when runs load async, we re-seed via useMemo + state merge in
  // the effect below. Simpler: derive initial set lazily once `allCaseNames`
  // is populated.
  const initialExpanded = useMemo(() => {
    const s = new Set<string>()
    for (const name of allCaseNames) {
      const b = baseByName.get(name)
      const v = compareByName.get(name)
      if (caseDelta(b, v) === 'regressed' || isErrored(b) || isErrored(v)) {
        s.add(name)
      }
    }
    return s
  }, [allCaseNames, baseByName, compareByName])

  // Track which cases are expanded. Initialized from initialExpanded via a
  // useState initializer that references the memo; once user interacts we
  // keep their state (no resets on re-render).
  // Seed expanded set with regressed+errored cases once per (baseRun,compareRun)
  // pair. Store as [seededKey, expandedSet] so both update atomically without
  // needing a useEffect setState (avoids react-hooks/set-state-in-effect).
  const seedKey = `${baseRun?.id ?? 0}-${compareRun?.id ?? 0}`
  const [expandedState, setExpandedState] = useState<{ key: string; set: Set<string> }>({
    key: '',
    set: new Set(),
  })
  const expanded =
    baseRun && compareRun && expandedState.key !== seedKey
      ? new Set(initialExpanded)
      : expandedState.set
  // Sync the stored key+set when runs first load for this seedKey
  if (baseRun && compareRun && expandedState.key !== seedKey) {
    setExpandedState({ key: seedKey, set: new Set(initialExpanded) })
  }
  const setExpanded = (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => {
    setExpandedState((prev) => {
      const next = typeof updater === 'function' ? updater(prev.set) : updater
      return { key: prev.key, set: next }
    })
  }
  const [matchedOnly, setMatchedOnly] = useState(false)

  // When matchedOnly is active, filter to only matched-bucket cases for stats
  const filteredCaseNames = useMemo(() => {
    if (!matchedOnly) return allCaseNames
    return allCaseNames.filter((n) => bucketByName.get(n) === 'matched')
  }, [allCaseNames, bucketByName, matchedOnly])

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

  // ---- Export state + handlers --------------------------------------------
  const [exportOpen, setExportOpen] = useState(false)
  const [warning, setWarning] = useState<PendingWarning | null>(null)

  function exportFilename(ext: string): string {
    return `eval-context-run${baseRunId}-vs-${compareRunId}.${ext}`
  }

  /** Gather args for payload builders. */
  function buildArgs(): BuildPayloadArgs | null {
    if (!datasetQ.data || !baseRun || !compareRun) return null
    return {
      dataset: {
        id: datasetQ.data.id,
        name: datasetQ.data.name,
        description: datasetQ.data.description,
        target_name: datasetQ.data.target_name,
        target_type: datasetQ.data.target_type,
      },
      baseRun,
      compareRun,
      basePrompts: toExportRunPrompts(
        basePromptsQ.flat,
        basePromptsQ.items,
      ),
      comparePrompts: toExportRunPrompts(
        comparePromptsQ.flat,
        comparePromptsQ.items,
      ),
      historicalCases: historicalCasesQ.byId,
    }
  }

  async function copyWithWarning(
    format: ExportFormat,
    content: string,
    filename: string,
    mime: string,
  ) {
    const bytes = byteLength(content)
    if (bytes > CLIPBOARD_WARNING_BYTES) {
      setWarning({ format, content, bytes, filename, mime })
      return
    }
    const ok = await writeClipboard(content)
    if (ok) toast.success(`Copied ${format} to clipboard (${formatKB(bytes)})`)
    else toast.error('Clipboard write failed — try downloading instead')
  }

  function handleCopyMarkdown() {
    setExportOpen(false)
    const args = buildArgs()
    if (!args) return
    const md = buildPayloadMarkdown(args)
    void copyWithWarning('markdown', md, exportFilename('md'), 'text/markdown')
  }

  function handleCopyJSON() {
    setExportOpen(false)
    const args = buildArgs()
    if (!args) return
    const json = JSON.stringify(buildPayloadJSON(args), null, 2)
    void copyWithWarning(
      'json',
      json,
      exportFilename('json'),
      'application/json',
    )
  }

  function handleDownloadMarkdown() {
    setExportOpen(false)
    const args = buildArgs()
    if (!args) return
    const md = buildPayloadMarkdown(args)
    downloadBlob(md, 'text/markdown', exportFilename('md'))
    toast.success(`Downloaded ${exportFilename('md')}`)
  }

  function handleDownloadJSON() {
    setExportOpen(false)
    const args = buildArgs()
    if (!args) return
    const json = JSON.stringify(buildPayloadJSON(args), null, 2)
    downloadBlob(json, 'application/json', exportFilename('json'))
    toast.success(`Downloaded ${exportFilename('json')}`)
  }

  async function handleWarningCopyAnyway() {
    if (!warning) return
    const ok = await writeClipboard(warning.content)
    if (ok)
      toast.success(
        `Copied ${warning.format} to clipboard (${formatKB(warning.bytes)})`,
      )
    else toast.error('Clipboard write failed — try downloading instead')
    setWarning(null)
  }

  function handleWarningDownloadInstead() {
    if (!warning) return
    downloadBlob(warning.content, warning.mime, warning.filename)
    toast.success(`Downloaded ${warning.filename}`)
    setWarning(null)
  }

  // Compute filtered aggregate stats when matchedOnly is active.
  // Must be before early returns to satisfy rules-of-hooks.
  const { basePassRate, comparePassRate, filteredBaseStats, filteredCompareStats } =
    useMemo(() => {
      if (!matchedOnly) {
        return {
          basePassRate: passRate(baseRun),
          comparePassRate: passRate(compareRun),
          filteredBaseStats: null,
          filteredCompareStats: null,
        }
      }
      let bPassed = 0, bFailed = 0, bErrored = 0
      let cPassed = 0, cFailed = 0, cErrored = 0
      for (const name of filteredCaseNames) {
        const br = baseByName.get(name)
        const cr = compareByName.get(name)
        if (br) {
          if (br.error_message) bErrored++
          else if (br.passed) bPassed++
          else bFailed++
        }
        if (cr) {
          if (cr.error_message) cErrored++
          else if (cr.passed) cPassed++
          else cFailed++
        }
      }
      const bTotal = bPassed + bFailed + bErrored
      const cTotal = cPassed + cFailed + cErrored
      return {
        basePassRate: bTotal > 0 ? bPassed / bTotal : null,
        comparePassRate: cTotal > 0 ? cPassed / cTotal : null,
        filteredBaseStats: { passed: bPassed, failed: bFailed, errored: bErrored, total: bTotal },
        filteredCompareStats: { passed: cPassed, failed: cFailed, errored: cErrored, total: cTotal },
      }
    }, [matchedOnly, filteredCaseNames, baseByName, compareByName, baseRun, compareRun])

  // Derive the resolved model string from each run's snapshot, and pair
  // the base/compare prompts by (step_name, prompt_key, prompt_type) for
  // the configuration diff card below.
  const baseModel = useMemo(
    () => resolveModelFromSnapshot(baseRun?.model_snapshot ?? null),
    [baseRun?.model_snapshot],
  )
  const compareModel = useMemo(
    () => resolveModelFromSnapshot(compareRun?.model_snapshot ?? null),
    [compareRun?.model_snapshot],
  )
  const basePromptsResolved = useMemo(
    () => toExportRunPrompts(basePromptsQ.flat, basePromptsQ.items),
    [basePromptsQ.flat, basePromptsQ.items],
  )
  const comparePromptsResolved = useMemo(
    () => toExportRunPrompts(comparePromptsQ.flat, comparePromptsQ.items),
    [comparePromptsQ.flat, comparePromptsQ.items],
  )
  const pairedPrompts = useMemo(
    () => pairRunPrompts(basePromptsResolved, comparePromptsResolved),
    [basePromptsResolved, comparePromptsResolved],
  )

  // Early param validation
  if (baseRunId === 0 || compareRunId === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="text-center space-y-2">
          <p className="text-destructive">
            Invalid compare URL. Both baseRunId and compareRunId search params are required.
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

  if (error || !baseRun || !compareRun) {
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

  const showScopeToggle = driftedCount + unmatchedCount > 0

  const statBasePassed = filteredBaseStats?.passed ?? baseRun.passed
  const statBaseFailed = filteredBaseStats?.failed ?? baseRun.failed
  const statBaseErrored = filteredBaseStats?.errored ?? baseRun.errored
  const statComparePassed = filteredCompareStats?.passed ?? compareRun.passed
  const statCompareFailed = filteredCompareStats?.failed ?? compareRun.failed
  const statCompareErrored = filteredCompareStats?.errored ?? compareRun.errored

  const allExpanded =
    allCaseNames.length > 0 && expanded.size === allCaseNames.length

  // The configuration card renders when either run recorded a model or
  // has any resolved prompts — even a partial context is useful.
  const hasConfigData =
    baseModel != null ||
    compareModel != null ||
    pairedPrompts.length > 0 ||
    baseRun?.instructions_schema_snapshot != null ||
    compareRun?.instructions_schema_snapshot != null
  const configLoading = basePromptsQ.isLoading || comparePromptsQ.isLoading

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-6xl space-y-6 p-6">
        {/* Back + breadcrumb + export */}
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
          <div className="ml-auto">
            <Popover open={exportOpen} onOpenChange={setExportOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="h-8 text-xs gap-1">
                  <Download className="h-3.5 w-3.5" />
                  Export
                  <ChevronDown className="h-3 w-3 opacity-60" />
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-56 p-1">
                <div className="flex flex-col">
                  <button
                    type="button"
                    onClick={handleCopyMarkdown}
                    className="text-left text-xs px-2 py-1.5 rounded hover:bg-accent"
                  >
                    Copy as Markdown
                  </button>
                  <button
                    type="button"
                    onClick={handleCopyJSON}
                    className="text-left text-xs px-2 py-1.5 rounded hover:bg-accent"
                  >
                    Copy as JSON
                  </button>
                  <div className="my-1 h-px bg-border" />
                  <button
                    type="button"
                    onClick={handleDownloadMarkdown}
                    className="text-left text-xs px-2 py-1.5 rounded hover:bg-accent"
                  >
                    Download as Markdown (.md)
                  </button>
                  <button
                    type="button"
                    onClick={handleDownloadJSON}
                    className="text-left text-xs px-2 py-1.5 rounded hover:bg-accent"
                  >
                    Download as JSON (.json)
                  </button>
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </div>

        {/* Header */}
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">Comparing runs</h1>
          <p className="text-xs text-muted-foreground">
            Base run #{baseRun.id}{' '}
            {baseRun.started_at && `(${new Date(baseRun.started_at).toLocaleString()})`}
            {' vs '}Compare run #{compareRun.id}{' '}
            {compareRun.started_at && `(${new Date(compareRun.started_at).toLocaleString()})`}
          </p>
          {compareRun.variant_id != null && (
            <p className="text-xs text-muted-foreground">
              Variant:{' '}
              <span className="font-medium text-foreground">
                {variantQ.data?.name ?? `#${compareRun.variant_id}`}
              </span>
            </p>
          )}
        </div>

        {/* Run headers (side by side) */}
        <div className="grid grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Base{' '}
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
                Compare{' '}
                <Link
                  to="/evals/$datasetId/runs/$runId"
                  params={{ datasetId: String(datasetId), runId: String(compareRun.id) }}
                  className="font-mono text-muted-foreground hover:underline ml-1"
                >
                  #{compareRun.id}
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 space-y-1">
              <Badge variant="outline" className="text-xs">{compareRun.status}</Badge>
              <p className="text-xs text-muted-foreground">
                {compareRun.started_at
                  ? new Date(compareRun.started_at).toLocaleString()
                  : 'N/A'}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Configuration comparison — shows each run's actual model + prompts */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Configuration</CardTitle>
          </CardHeader>
          <CardContent>
            {configLoading ? (
              <p className="text-xs text-muted-foreground italic">
                Loading configuration…
              </p>
            ) : hasConfigData ? (
              <ConfigurationComparison
                baseRunId={baseRun.id}
                compareRunId={compareRun.id}
                baseModel={baseModel}
                compareModel={compareModel}
                baseInstructionsSchema={baseRun.instructions_schema_snapshot}
                compareInstructionsSchema={
                  compareRun.instructions_schema_snapshot
                }
                baseVariantDelta={baseRun.delta_snapshot}
                compareVariantDelta={compareRun.delta_snapshot}
                promptPairs={pairedPrompts}
              />
            ) : (
              <p className="text-xs text-muted-foreground">
                No configuration recorded for either run.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Stats comparison */}
        {showScopeToggle && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Aggregate scope:</span>
            <div className="inline-flex rounded-md border">
              <Button
                variant={matchedOnly ? 'ghost' : 'secondary'}
                size="sm"
                className="h-7 text-xs rounded-r-none border-0"
                onClick={() => setMatchedOnly(false)}
              >
                All cases
              </Button>
              <Button
                variant={matchedOnly ? 'secondary' : 'ghost'}
                size="sm"
                className="h-7 text-xs rounded-l-none border-0"
                onClick={() => setMatchedOnly(true)}
              >
                Matched only
              </Button>
            </div>
            <span className="text-[10px] text-muted-foreground">
              {matchedCount} matched, {driftedCount} drifted, {unmatchedCount} unmatched
            </span>
          </div>
        )}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <ComparisonStatCard
            label="Passed"
            baseValue={statBasePassed}
            compareValue={statComparePassed}
            color="text-green-600"
          />
          <ComparisonStatCard
            label="Failed"
            baseValue={statBaseFailed}
            compareValue={statCompareFailed}
            color="text-red-600"
            invertColor
          />
          <ComparisonStatCard
            label="Errored"
            baseValue={statBaseErrored}
            compareValue={statCompareErrored}
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
                  <p className="text-[10px] text-muted-foreground uppercase">Compare</p>
                  <p className="text-xl font-bold">{formatPct(comparePassRate)}</p>
                </div>
              </div>
              <div>
                <DeltaPctBadge
                  baseValue={basePassRate}
                  compareValue={comparePassRate}
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
                    <TableHead>Base</TableHead>
                    <TableHead>Base scores</TableHead>
                    <TableHead>Compare</TableHead>
                    <TableHead>Compare scores</TableHead>
                    <TableHead>Delta</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allCaseNames.map((name) => {
                    const baseRes = baseByName.get(name)
                    const compareRes = compareByName.get(name)
                    const baseVersion =
                      baseRes?.case_id != null && baseRun?.case_versions
                        ? baseRun.case_versions[String(baseRes.case_id)]
                        : undefined
                    const compareVersion =
                      compareRes?.case_id != null && compareRun?.case_versions
                        ? compareRun.case_versions[String(compareRes.case_id)]
                        : undefined
                    return (
                      <CaseRow
                        key={name}
                        name={name}
                        datasetId={datasetId}
                        caseDef={caseByName.get(name)}
                        baseResult={baseRes}
                        compareResult={compareRes}
                        bucket={bucketByName.get(name)}
                        baseVersion={baseVersion}
                        compareVersion={compareVersion}
                        isExpanded={expanded.has(name)}
                        onToggle={() => toggleCase(name)}
                      />
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Clipboard size-warning dialog */}
      <Dialog
        open={warning != null}
        onOpenChange={(open) => {
          if (!open) setWarning(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Large payload</DialogTitle>
            <DialogDescription>
              Payload is {warning ? formatKB(warning.bytes) : ''}. Large content
              may not copy cleanly on all systems (some browsers/OSes truncate
              clipboard writes). Copy anyway, or download as a file?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWarning(null)}>
              Cancel
            </Button>
            <Button variant="outline" onClick={handleWarningDownloadInstead}>
              Download instead
            </Button>
            <Button onClick={handleWarningCopyAnyway}>Copy anyway</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ScrollArea>
  )
}
