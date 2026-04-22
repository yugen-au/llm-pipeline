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
  useVariant,
} from '@/api/evals'
import type {
  CaseItem,
  CaseResultItem,
  HistoricalCaseItem,
  RunDetail,
} from '@/api/evals'
import { useAutoGenerateObjects, useRunPrompts } from '@/api/prompts'
import type {
  AutoGenerateObject,
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

interface ExportCaseResult {
  case_name: string
  passed: boolean
  error_message: string | null
  output_data: Record<string, unknown> | null
  evaluator_scores: Record<string, unknown>
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
  case_results: ExportCaseResult[]
  context: ExportRunContext
}

interface ExportCaseDrift {
  case_name: string
  base_version: string | null
  compare_version: string | null
  bucket: 'matched' | 'drifted' | 'unmatched'
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
  /** Distinct evaluator names observed across both runs' case results. Lets
   * the reader see what scoring was applied without mining each case. */
  evaluators: string[]
  /** Runtime-registered enum catalog (referenced by instructions schemas). */
  registered_enums: Record<string, Array<{ name: string; value: string }>>
  comparison: {
    base_run_id: number
    compare_run_id: number
  }
  runs: {
    base: ExportRun
    compare: ExportRun
  }
  /** Per-case version drift between the two runs. Empty when both runs used
   * the same case versions. */
  case_drift: ExportCaseDrift[]
  dataset_cases: Array<{
    name: string
    inputs: Record<string, unknown>
    expected_output: Record<string, unknown> | null
  }>
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

function toExportCaseResult(r: CaseResultItem): ExportCaseResult {
  return {
    case_name: r.case_name,
    passed: r.passed,
    error_message: r.error_message,
    output_data: r.output_data,
    evaluator_scores: r.evaluator_scores,
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
    case_results: run.case_results.map(toExportCaseResult),
    context: toExportRunContext(run, prompts),
  }
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

/** Collect distinct evaluator names across both runs' case results. */
function collectEvaluatorNames(
  baseRun: RunDetail,
  compareRun: RunDetail,
): string[] {
  const names = new Set<string>()
  for (const r of [...baseRun.case_results, ...compareRun.case_results]) {
    for (const k of Object.keys(r.evaluator_scores ?? {})) {
      names.add(k)
    }
  }
  return Array.from(names).sort()
}

/** Build the case-drift list for the export payload. Uses case_versions on
 * each run and the case_id embedded in each case result to key into them. */
function computeCaseDrift(
  baseRun: RunDetail,
  compareRun: RunDetail,
): ExportCaseDrift[] {
  const baseCv = baseRun.case_versions ?? {}
  const compareCv = compareRun.case_versions ?? {}
  const baseByName = new Map(
    baseRun.case_results.map((r) => [r.case_name, r]),
  )
  const compareByName = new Map(
    compareRun.case_results.map((r) => [r.case_name, r]),
  )
  const names = Array.from(
    new Set([...baseByName.keys(), ...compareByName.keys()]),
  ).sort()
  const out: ExportCaseDrift[] = []
  for (const name of names) {
    const b = baseByName.get(name)
    const c = compareByName.get(name)
    const baseVersion =
      b?.case_id != null ? (baseCv[String(b.case_id)] ?? null) : null
    const compareVersion =
      c?.case_id != null ? (compareCv[String(c.case_id)] ?? null) : null
    let bucket: ExportCaseDrift['bucket']
    if (!b || !c) bucket = 'unmatched'
    else if (baseVersion == null && compareVersion == null) bucket = 'matched'
    else if (baseVersion === compareVersion) bucket = 'matched'
    else bucket = 'drifted'
    out.push({
      case_name: name,
      base_version: baseVersion,
      compare_version: compareVersion,
      bucket,
    })
  }
  return out
}

function buildEnumCatalog(
  objects: AutoGenerateObject[] | undefined,
): Record<string, Array<{ name: string; value: string }>> {
  const out: Record<string, Array<{ name: string; value: string }>> = {}
  for (const o of objects ?? []) {
    if (o.kind !== 'enum' || !o.members) continue
    out[o.name] = o.members.map((m) => ({ name: m.name, value: m.value }))
  }
  return out
}

interface BuildPayloadArgs {
  dataset: {
    id: number
    name: string
    description: string | null
    target_name: string
    target_type: string
    cases: CaseItem[]
  }
  enumObjects: AutoGenerateObject[] | undefined
  baseRun: RunDetail
  compareRun: RunDetail
  basePrompts: ExportRunPrompt[]
  comparePrompts: ExportRunPrompt[]
}

function buildPayloadJSON(args: BuildPayloadArgs): ExportPayload {
  const {
    dataset,
    enumObjects,
    baseRun,
    compareRun,
    basePrompts,
    comparePrompts,
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
    evaluators: collectEvaluatorNames(baseRun, compareRun),
    registered_enums: buildEnumCatalog(enumObjects),
    comparison: {
      base_run_id: baseRun.id,
      compare_run_id: compareRun.id,
    },
    runs: {
      base: toExportRun(baseRun, basePrompts),
      compare: toExportRun(compareRun, comparePrompts),
    },
    case_drift: computeCaseDrift(baseRun, compareRun),
    dataset_cases: dataset.cases.map((c) => ({
      name: c.name,
      inputs: c.inputs,
      expected_output: c.expected_output,
    })),
  }
}

// Meta-prompt prepended to markdown exports. JSON omits this.
const META_PROMPT = `# Eval Run Comparison

## Your task

You are reviewing two runs of an automated evaluation suite for a language-model step. Each run executes the same set of test cases through the LLM step and scores the outputs using one or more evaluator functions. Your job is to analyze the differences between the two runs and recommend concrete changes that would improve results on the failing or regressed cases.

## How to approach this

Look at the data as a pattern-matching exercise:

1. **What changed between the two runs?** Compare the model, system prompt, user prompt, instructions schema, and any variant overrides. These are the knobs that were adjusted.
2. **What changed in the cases themselves?** Cases may have been edited between runs (different inputs or different expected outputs). Any such changes are flagged in the "Case version drift" section; treat drifted cases cautiously — an apparent improvement may reflect the test changing, not the model getting better.
3. **Where are the model's outputs wrong?** For failing or regressed cases, compare the actual output to the expected output and identify patterns (e.g. specific edge cases the prompt doesn't cover, schema fields the model misinterprets, formatting issues).
4. **What can be tweaked to fix this?** The levers available are: the system prompt, the user prompt template, the instructions schema (including enum values), per-case expected outputs, and the underlying model. Recommend specific, actionable changes.

## What to produce

A summary of the patterns you see and a prioritized list of recommended changes, each naming the specific lever (system prompt, user prompt, schema, expected output, model) and the rationale.
`

function fenced(lang: string, body: string): string {
  return '```' + lang + '\n' + body + '\n```'
}

function jsonFence(obj: unknown): string {
  return fenced('json', JSON.stringify(obj, null, 2))
}

function formatCaseStatus(r: CaseResultItem | undefined): string {
  if (!r) return 'n/a'
  if (r.error_message) return 'errored'
  return r.passed ? 'pass' : 'fail'
}

function formatDeltaTag(kind: DeltaKind): string {
  switch (kind) {
    case 'improved':
      return 'improved'
    case 'regressed':
      return 'regressed'
    case 'unchanged':
      return 'unchanged'
    default:
      return 'n/a'
  }
}

function outputOrError(r: CaseResultItem | undefined): string {
  if (!r) return '*no result*'
  if (r.error_message) {
    return fenced('', `error: ${r.error_message}`)
  }
  if (r.output_data == null) return '*no output*'
  return jsonFence(r.output_data)
}

// --- YAML rendering for evaluator scores -----------------------------------

/** Escape a string value for YAML flow-scalar use. Quotes if contains special chars. */
function yamlString(s: string): string {
  // Quote if contains control chars, colons, hashes, brackets, or leading/trailing
  // whitespace — keeps things safe without full YAML spec compliance.
  if (/[:#[\]{},&*!|>'"%@`\n\r\t]/.test(s) || /^\s|\s$/.test(s) || s === '') {
    return JSON.stringify(s)
  }
  return s
}

function yamlScalar(v: unknown): string {
  if (v === null || v === undefined) return 'null'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : 'null'
  if (typeof v === 'string') return yamlString(v)
  // Fallback: JSON-encode arrays/objects on one line
  return JSON.stringify(v)
}

function isScalar(v: unknown): boolean {
  return (
    v === null ||
    v === undefined ||
    typeof v === 'boolean' ||
    typeof v === 'number' ||
    typeof v === 'string'
  )
}

/** Render an object as YAML, indented by `indent` spaces per level. */
function yamlObject(obj: Record<string, unknown>, indent = 0): string {
  const pad = ' '.repeat(indent)
  const lines: string[] = []
  for (const [k, v] of Object.entries(obj)) {
    const key = yamlString(k)
    if (isScalar(v)) {
      lines.push(`${pad}${key}: ${yamlScalar(v)}`)
    } else if (Array.isArray(v)) {
      if (v.length === 0) {
        lines.push(`${pad}${key}: []`)
      } else {
        lines.push(`${pad}${key}:`)
        for (const item of v) {
          if (isScalar(item)) {
            lines.push(`${pad}  - ${yamlScalar(item)}`)
          } else if (item && typeof item === 'object') {
            const sub = yamlObject(item as Record<string, unknown>, indent + 4)
            // Push first key onto the "- " line for readability
            const subLines = sub.split('\n')
            if (subLines.length > 0) {
              lines.push(`${pad}  - ${subLines[0].trimStart()}`)
              for (let i = 1; i < subLines.length; i++) lines.push(subLines[i])
            }
          }
        }
      }
    } else if (v && typeof v === 'object') {
      const entries = Object.keys(v as Record<string, unknown>)
      if (entries.length === 0) {
        lines.push(`${pad}${key}: {}`)
      } else {
        lines.push(`${pad}${key}:`)
        lines.push(yamlObject(v as Record<string, unknown>, indent + 2))
      }
    } else {
      lines.push(`${pad}${key}: ${yamlScalar(v)}`)
    }
  }
  return lines.join('\n')
}

/**
 * Render evaluator_scores map as YAML. Handles nested shapes flexibly:
 * - scalar value -> `key: value`
 * - `{value: X}` -> `key: X`
 * - `{value: X, reason: Y}` -> `key: X  # Y`
 * - other object -> nested YAML block
 */
function evaluatorScoresYaml(raw: Record<string, unknown>): string {
  const lines: string[] = []
  for (const [k, v] of Object.entries(raw)) {
    const key = yamlString(k)
    if (isScalar(v)) {
      lines.push(`${key}: ${yamlScalar(v)}`)
      continue
    }
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const obj = v as Record<string, unknown>
      const keys = Object.keys(obj)
      if ('value' in obj && isScalar(obj.value)) {
        const inline = `${key}: ${yamlScalar(obj.value)}`
        const reason = obj.reason
        const onlyValueAndMaybeReason = keys.every((kk) => kk === 'value' || kk === 'reason')
        if (onlyValueAndMaybeReason && typeof reason === 'string' && reason) {
          // Inline comment — strip newlines so comment stays single-line
          const safeReason = reason.replace(/[\r\n]+/g, ' ').trim()
          lines.push(`${inline}  # ${safeReason}`)
        } else if (onlyValueAndMaybeReason) {
          lines.push(inline)
        } else {
          // Has extra keys — fall through to nested render
          lines.push(`${key}:`)
          lines.push(yamlObject(obj, 2))
        }
      } else {
        lines.push(`${key}:`)
        lines.push(yamlObject(obj, 2))
      }
    } else if (Array.isArray(v)) {
      lines.push(`${key}: ${JSON.stringify(v)}`)
    } else {
      lines.push(`${key}: ${yamlScalar(v)}`)
    }
  }
  return lines.join('\n')
}

/** Build evaluator-scores markdown block for a single side, or empty string. */
function evaluatorScoresBlock(
  label: string,
  r: CaseResultItem | undefined,
): string {
  if (!r || !r.evaluator_scores) return ''
  const scores = r.evaluator_scores as Record<string, unknown>
  if (Object.keys(scores).length === 0) return ''
  return `**${label} evaluator scores:**\n${fenced('yaml', evaluatorScoresYaml(scores))}`
}

interface MarkdownCaseInput {
  inputs: Record<string, unknown>
  expected_output: Record<string, unknown> | null
}

function caseMarkdownSection(
  caseName: string,
  caseDef: MarkdownCaseInput | undefined,
  baseRes: CaseResultItem | undefined,
  compareRes: CaseResultItem | undefined,
  drift: ExportCaseDrift | undefined,
): string {
  const baseStatus = formatCaseStatus(baseRes)
  const compareStatus = formatCaseStatus(compareRes)
  const kind = caseDelta(baseRes, compareRes)

  // Build the drift annotation appended to headers (e.g. "drifted v1.0 -> v1.1"
  // or "only in base (v1.0)"). Empty string when matched.
  let driftTag = ''
  if (drift) {
    if (drift.bucket === 'drifted') {
      driftTag = ` [drifted v${drift.base_version ?? '?'} -> v${drift.compare_version ?? '?'}]`
    } else if (drift.bucket === 'unmatched') {
      if (drift.base_version && !drift.compare_version) {
        driftTag = ` [only in base (v${drift.base_version})]`
      } else if (drift.compare_version && !drift.base_version) {
        driftTag = ` [only in compare (v${drift.compare_version})]`
      } else {
        driftTag = ` [unmatched]`
      }
    }
  }

  // Compress unchanged-passing cases to a one-liner regardless of whether the
  // output strings match byte-for-byte — wording variations in explanations
  // are noise when both evaluators agreed the case passed.
  if (
    kind === 'unchanged' &&
    baseStatus === 'pass' &&
    compareStatus === 'pass'
  ) {
    return `### \`${caseName}\` — both passed (unchanged)${driftTag}\n`
  }

  const header = `### \`${caseName}\` [base: ${baseStatus}] -> [compare: ${compareStatus}] (${formatDeltaTag(kind)})${driftTag}`
  const input = caseDef
    ? `**Input:**\n${jsonFence(caseDef.inputs)}`
    : `**Input:** *not available*`
  const expected = caseDef?.expected_output
    ? `**Expected:**\n${jsonFence(caseDef.expected_output)}`
    : `**Expected:** *none defined*`
  const baseScores = evaluatorScoresBlock('Base', baseRes)
  const compareScores = evaluatorScoresBlock('Compare', compareRes)
  const baseOut = `**Base output:**\n${outputOrError(baseRes)}`
  const compareOut = `**Compare output:**\n${outputOrError(compareRes)}`

  const parts = [header, input, expected]
  if (baseScores) parts.push(baseScores)
  parts.push(baseOut)
  if (compareScores) parts.push(compareScores)
  parts.push(compareOut)
  return parts.join('\n\n') + '\n'
}

function enumCatalogMarkdown(
  catalog: Record<string, Array<{ name: string; value: string }>>,
): string {
  const keys = Object.keys(catalog)
  if (keys.length === 0) return '*none registered*'
  return keys
    .map((k) => {
      const members = catalog[k]
        .map((m) => `${m.name} (${m.value})`)
        .join(', ')
      return `- \`${k}\`: [${members}]`
    })
    .join('\n')
}

// ---------------------------------------------------------------------------
// Failing-case summary banner + aggregate comparison table
// ---------------------------------------------------------------------------

// Minimal shape needed by caseDelta/isErrored — accepts both CaseResultItem and
// ExportCaseResult since both expose `passed` + `error_message`.
type CaseResultLike = Pick<CaseResultItem, 'passed' | 'error_message'>

function caseSummaryBanner(
  allNames: string[],
  baseByName: Map<string, CaseResultLike>,
  compareByName: Map<string, CaseResultLike>,
): string {
  // caseDelta/isErrored only touch `passed` + `error_message`; cast-through is
  // safe here and avoids threading a generic through both helpers.
  const asFull = (r: CaseResultLike | undefined) =>
    r as unknown as CaseResultItem | undefined
  if (allNames.length === 0) return ''
  const regressed: string[] = []
  const improved: string[] = []
  const erroredInCompare: string[] = []
  for (const name of allNames) {
    const b = asFull(baseByName.get(name))
    const v = asFull(compareByName.get(name))
    const kind = caseDelta(b, v)
    if (kind === 'regressed') regressed.push(name)
    else if (kind === 'improved') improved.push(name)
    if (isErrored(v)) erroredInCompare.push(name)
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
  if (parts.length === 0) {
    return '**No changes:** all cases passed with the same outcome in both runs.'
  }
  return `**Changes:** ${parts.join('; ')}`
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

function renderCaseDriftSection(drift: ExportCaseDrift[]): string {
  const changed = drift.filter((d) => d.bucket !== 'matched')
  if (changed.length === 0) {
    return '## Case version drift\n\n*All cases used the same version in both runs.*'
  }
  const lines = changed.map((d) => {
    if (d.bucket === 'drifted') {
      return `- \`${d.case_name}\`: v${d.base_version ?? '?'} → v${d.compare_version ?? '?'} (drifted)`
    }
    if (d.base_version && !d.compare_version) {
      return `- \`${d.case_name}\`: only in base (v${d.base_version})`
    }
    if (d.compare_version && !d.base_version) {
      return `- \`${d.case_name}\`: only in compare (v${d.compare_version})`
    }
    return `- \`${d.case_name}\`: unmatched`
  })
  return `## Case version drift\n\n${lines.join('\n')}`
}

function buildPayloadMarkdown(args: BuildPayloadArgs): string {
  const payload = buildPayloadJSON(args)
  const {
    step,
    dataset,
    evaluators,
    registered_enums,
    comparison,
    runs,
    case_drift,
    dataset_cases,
  } = payload

  // Build a drift lookup for per-case annotation.
  const driftByName = new Map(case_drift.map((d) => [d.case_name, d]))

  // Order cases: regressed/errored first, then failing-on-compare, then
  // improved, then unchanged.
  const caseByName = new Map(dataset_cases.map((c) => [c.name, c]))
  const baseByName = new Map(
    runs.base.case_results.map((r) => [r.case_name, r]),
  )
  const compareByName = new Map(
    runs.compare.case_results.map((r) => [r.case_name, r]),
  )
  const allNames = Array.from(
    new Set([...baseByName.keys(), ...compareByName.keys()]),
  )

  function priority(name: string): number {
    const b = baseByName.get(name) as CaseResultItem | undefined
    const v = compareByName.get(name) as CaseResultItem | undefined
    const kind = caseDelta(b, v)
    if (kind === 'regressed' || isErrored(b) || isErrored(v)) return 0
    const compareFailing = v ? v.error_message || !v.passed : false
    if (compareFailing) return 1
    if (kind === 'improved') return 2
    return 3
  }

  const sortedNames = allNames
    .slice()
    .sort((a, b) => priority(a) - priority(b) || a.localeCompare(b))

  const perCase = sortedNames
    .map((name) =>
      caseMarkdownSection(
        name,
        caseByName.get(name),
        baseByName.get(name) as CaseResultItem | undefined,
        compareByName.get(name) as CaseResultItem | undefined,
        driftByName.get(name),
      ),
    )
    .join('\n')

  const baseStats = runs.base.stats
  const compareStats = runs.compare.stats
  const aggregateTable = aggregateComparisonTable(
    runs.base.id,
    runs.compare.id,
    baseStats,
    compareStats,
  )

  const banner = caseSummaryBanner(sortedNames, baseByName, compareByName)
  const perCaseSection = banner
    ? `## Per-case details\n\n${banner}\n\n${perCase}`
    : `## Per-case details\n\n${perCase}`

  const datasetDescription =
    dataset.description && dataset.description.trim().length > 0
      ? dataset.description.trim()
      : '*No description provided.*'

  const evaluatorsLine =
    evaluators.length > 0
      ? evaluators.map((n) => `\`${n}\``).join(', ')
      : '*No evaluators recorded.*'

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
    `**Evaluators applied:** ${evaluatorsLine}`,
    '',
    '## Comparison summary',
    '',
    `Base run \`#${comparison.base_run_id}\` vs Compare run \`#${comparison.compare_run_id}\`.`,
    '',
    renderRunContextSection('Base configuration', runs.base.id, runs.base.context),
    '',
    renderRunContextSection('Compare configuration', runs.compare.id, runs.compare.context),
    '',
    renderCaseDriftSection(case_drift),
    '',
    '## Run results',
    '',
    aggregateTable,
    '',
    perCaseSection,
    '',
    '## Registered enums (referenced by the instructions schema)',
    '',
    enumCatalogMarkdown(registered_enums),
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

  // Registered enums reference (static lookup for the export).
  const autoGenQ = useAutoGenerateObjects()

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

  /** Gather args for payload builders; tolerates missing prod data. */
  function buildArgs(): BuildPayloadArgs | null {
    if (!datasetQ.data || !baseRun || !compareRun) return null
    return {
      dataset: {
        id: datasetQ.data.id,
        name: datasetQ.data.name,
        description: datasetQ.data.description,
        target_name: datasetQ.data.target_name,
        target_type: datasetQ.data.target_type,
        cases: datasetQ.data.cases,
      },
      enumObjects: autoGenQ.data?.objects,
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
