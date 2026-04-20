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
  useDatasetProdModel,
  useDatasetProdPrompts,
  useEvalRun,
  useInputSchema,
  useVariant,
} from '@/api/evals'
import type {
  CaseItem,
  CaseResultItem,
  ProdPromptsResponse,
  RunDetail,
  VariableDefinitions,
  VariantDelta,
  VariantItem,
} from '@/api/evals'
import { useAutoGenerateObjects } from '@/api/prompts'
import type { AutoGenerateObject } from '@/api/prompts'
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

interface ExportRun {
  id: number
  stats: ExportStats
  case_results: ExportCaseResult[]
}

interface ExportPayload {
  step: {
    name: string
    target_type: string
  }
  prod_config: {
    model: string | null
    system_prompt: string | null
    user_prompt: string | null
    variable_definitions: Record<string, unknown> | null
    instructions_schema: Record<string, unknown> | null
    enum_catalog: Record<string, Array<{ name: string; value: string }>>
  }
  variant: {
    id: number
    name: string | null
    description: string | null
    delta: Record<string, unknown> | null
  } | null
  runs: {
    baseline: ExportRun
    variant: ExportRun
  }
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

function toExportRun(run: RunDetail): ExportRun {
  return {
    id: run.id,
    stats: toExportStats(run),
    case_results: run.case_results.map(toExportCaseResult),
  }
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
  dataset: { target_name: string; target_type: string; cases: CaseItem[] }
  prodModel: string | null
  prodPrompts: ProdPromptsResponse | undefined
  instructionsSchema: Record<string, unknown> | null
  enumObjects: AutoGenerateObject[] | undefined
  variant: VariantItem | undefined
  variantId: number | null
  baseRun: RunDetail
  variantRun: RunDetail
}

function buildPayloadJSON(args: BuildPayloadArgs): ExportPayload {
  const {
    dataset,
    prodModel,
    prodPrompts,
    instructionsSchema,
    enumObjects,
    variant,
    variantId,
    baseRun,
    variantRun,
  } = args

  return {
    step: {
      name: dataset.target_name,
      target_type: dataset.target_type,
    },
    prod_config: {
      model: prodModel,
      system_prompt: prodPrompts?.system?.content ?? null,
      user_prompt: prodPrompts?.user?.content ?? null,
      variable_definitions: mergeProdVarDefs(prodPrompts) as
        | Record<string, unknown>
        | null,
      instructions_schema: instructionsSchema,
      enum_catalog: buildEnumCatalog(enumObjects),
    },
    variant:
      variantId != null
        ? {
            id: variantId,
            name: variant?.name ?? null,
            description: variant?.description ?? null,
            delta: (variant?.delta ?? null) as Record<string, unknown> | null,
          }
        : null,
    runs: {
      baseline: toExportRun(baseRun),
      variant: toExportRun(variantRun),
    },
    dataset_cases: dataset.cases.map((c) => ({
      name: c.name,
      inputs: c.inputs,
      expected_output: c.expected_output,
    })),
  }
}

// Meta-prompt prepended to markdown exports. JSON omits this.
const META_PROMPT = `# Eval Variant Iteration Context

You are helping iterate on a production LLM step. Given the context below,
propose a variant delta that addresses the failing cases.

## Response format
Respond with a single JSON code block matching the VariantDelta shape:

\`\`\`json
{
  "model": "<model_name>" or null,
  "system_prompt": "<content>" or null,
  "user_prompt": "<content>" or null,
  "variable_definitions": {...} or null,
  "instructions_delta": [{"op": "add|modify", "field": "...", "type_str": "...", "default": <any>}] or null
}
\`\`\`

## Validation rules
- \`type_str\` must be one of: \`str\`, \`int\`, \`float\`, \`bool\`, \`list\`, \`dict\`, \`Optional[<base>]\`, \`enum:<RegisteredName>\`
- \`"modify"\` ops can omit \`type_str\` (backend preserves the original annotation — safest for complex types)
- \`"add"\` ops require both \`type_str\` and \`default\`
- \`default\` must be JSON-serialisable
- Registered enums available below under "Registered enums"

## Goal
Minimal changes that are likely to improve the pass rate. Explain reasoning briefly, then provide the JSON.
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
  if (/[:#\[\]{},&*!|>'"%@`\n\r\t]/.test(s) || /^\s|\s$/.test(s) || s === '') {
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
  variantRes: CaseResultItem | undefined,
): string {
  const baseStatus = formatCaseStatus(baseRes)
  const varStatus = formatCaseStatus(variantRes)
  const kind = caseDelta(baseRes, variantRes)

  // Collapse both-passed identical-output cases to a one-liner.
  if (
    baseStatus === 'pass' &&
    varStatus === 'pass' &&
    baseRes?.output_data &&
    variantRes?.output_data &&
    JSON.stringify(baseRes.output_data) === JSON.stringify(variantRes.output_data)
  ) {
    return `### \`${caseName}\` — both passed, outputs identical\n`
  }

  const header = `### \`${caseName}\` [baseline: ${baseStatus}] -> [variant: ${varStatus}] (${formatDeltaTag(kind)})`
  const input = caseDef
    ? `**Input:**\n${jsonFence(caseDef.inputs)}`
    : `**Input:** *not available*`
  const expected = caseDef?.expected_output
    ? `**Expected:**\n${jsonFence(caseDef.expected_output)}`
    : `**Expected:** *none defined*`
  const baseScores = evaluatorScoresBlock('Baseline', baseRes)
  const varScores = evaluatorScoresBlock('Variant', variantRes)
  const baseOut = `**Baseline output:**\n${outputOrError(baseRes)}`
  const varOut = `**Variant output:**\n${outputOrError(variantRes)}`

  const parts = [header, input, expected]
  if (baseScores) parts.push(baseScores)
  parts.push(baseOut)
  if (varScores) parts.push(varScores)
  parts.push(varOut)
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

function failingSummaryBanner(
  allNames: string[],
  baseByName: Map<string, CaseResultLike>,
  variantByName: Map<string, CaseResultLike>,
): string {
  // caseDelta/isErrored only touch `passed` + `error_message`; cast-through is
  // safe here and avoids threading a generic through both helpers.
  const asFull = (r: CaseResultLike | undefined) =>
    r as unknown as CaseResultItem | undefined
  if (allNames.length === 0) return ''
  const regressed: string[] = []
  const erroredInVariant: string[] = []
  for (const name of allNames) {
    const b = asFull(baseByName.get(name))
    const v = asFull(variantByName.get(name))
    if (caseDelta(b, v) === 'regressed') regressed.push(name)
    if (isErrored(v)) erroredInVariant.push(name)
  }
  const parts: string[] = []
  if (regressed.length > 0) {
    const shown = regressed.slice(0, 5).map((n) => `\`${n}\``).join(', ')
    const more = regressed.length > 5 ? `, +${regressed.length - 5} more` : ''
    parts.push(`${regressed.length} regressed (${shown}${more})`)
  }
  if (erroredInVariant.length > 0) {
    const shown = erroredInVariant.slice(0, 5).map((n) => `\`${n}\``).join(', ')
    const more =
      erroredInVariant.length > 5 ? `, +${erroredInVariant.length - 5} more` : ''
    parts.push(`${erroredInVariant.length} errored (${shown}${more})`)
  }
  if (parts.length === 0) return '**All cases passed.**'
  return `**Failing cases:** ${parts.join(', ')}`
}

function signedInt(n: number): string {
  if (n === 0) return '0'
  return n > 0 ? `+${n}` : `${n}`
}

function signedPct(base: number | null, variant: number | null): string {
  if (base == null || variant == null) return '—'
  const delta = (variant - base) * 100
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
  variantRunId: number,
  baseStats: ExportStats,
  varStats: ExportStats,
): string {
  const passRateDelta = signedPct(baseStats.pass_rate, varStats.pass_rate)
  const rows: Array<[string, string, string, string]> = [
    [
      'Pass rate',
      formatPct(baseStats.pass_rate),
      formatPct(varStats.pass_rate),
      passRateDelta,
    ],
    [
      'Passed',
      `${baseStats.passed}/${baseStats.total}`,
      `${varStats.passed}/${varStats.total}`,
      signedInt(varStats.passed - baseStats.passed),
    ],
    [
      'Failed',
      String(baseStats.failed),
      String(varStats.failed),
      signedInt(varStats.failed - baseStats.failed),
    ],
    [
      'Errored',
      String(baseStats.errored),
      String(varStats.errored),
      signedInt(varStats.errored - baseStats.errored),
    ],
  ]
  const headers: [string, string, string, string] = [
    'Metric',
    `Baseline (#${baseRunId})`,
    `Variant (#${variantRunId})`,
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

function buildPayloadMarkdown(args: BuildPayloadArgs): string {
  const payload = buildPayloadJSON(args)
  const { step, prod_config, variant, runs, dataset_cases } = payload

  // Order cases: regressed/errored first, then failing-on-variant, then others.
  const caseByName = new Map(dataset_cases.map((c) => [c.name, c]))
  const baseByName = new Map(
    runs.baseline.case_results.map((r) => [r.case_name, r]),
  )
  const variantByName = new Map(
    runs.variant.case_results.map((r) => [r.case_name, r]),
  )
  const allNames = Array.from(
    new Set([...baseByName.keys(), ...variantByName.keys()]),
  )

  function priority(name: string): number {
    const b = baseByName.get(name) as CaseResultItem | undefined
    const v = variantByName.get(name) as CaseResultItem | undefined
    const kind = caseDelta(b, v)
    if (kind === 'regressed' || isErrored(b) || isErrored(v)) return 0
    const varFailing = v ? v.error_message || !v.passed : false
    if (varFailing) return 1
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
        variantByName.get(name) as CaseResultItem | undefined,
      ),
    )
    .join('\n')

  const varDefs = prod_config.variable_definitions
  const varDefsBlock =
    varDefs && Object.keys(varDefs).length > 0
      ? jsonFence(varDefs)
      : '(none defined)'
  const instrBlock = prod_config.instructions_schema
    ? jsonFence(prod_config.instructions_schema)
    : '*not available*'
  const modelLine = prod_config.model ? `\`${prod_config.model}\`` : '*not set*'
  const sysBlock = prod_config.system_prompt
    ? fenced('', prod_config.system_prompt)
    : '*none*'
  const userBlock = prod_config.user_prompt
    ? fenced('', prod_config.user_prompt)
    : '*none*'

  const variantSection = variant
    ? [
        `## Current variant: ${variant.name ?? `#${variant.id}`}`,
        variant.description ? variant.description : '(no description)',
        '',
        '### Delta',
        variant.delta ? jsonFence(variant.delta) : '*empty delta*',
      ].join('\n')
    : '## Current variant\n*none — comparing two raw runs*'

  const baseStats = runs.baseline.stats
  const varStats = runs.variant.stats
  const aggregateTable = aggregateComparisonTable(
    runs.baseline.id,
    runs.variant.id,
    baseStats,
    varStats,
  )

  const banner = failingSummaryBanner(sortedNames, baseByName, variantByName)
  const perCaseSection = banner
    ? `## Per-case details\n\n${banner}\n\n${perCase}`
    : `## Per-case details\n\n${perCase}`

  return [
    META_PROMPT,
    '---',
    '',
    `## Step: ${step.name} (${step.target_type})`,
    '',
    '## Production configuration',
    '',
    '### Model',
    modelLine,
    '',
    '### System prompt',
    sysBlock,
    '',
    '### User prompt',
    userBlock,
    '',
    '### Variable definitions',
    varDefsBlock,
    '',
    '### Instructions schema',
    instrBlock,
    '',
    '### Registered enums',
    enumCatalogMarkdown(prod_config.enum_catalog),
    '',
    variantSection,
    '',
    '## Run results',
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

  // Export-context fetches. Non-blocking: export proceeds with nulls if
  // these error/are still loading.
  const inputSchemaQ = useInputSchema(
    datasetQ.data?.target_type ?? '',
    datasetQ.data?.target_name ?? '',
  )
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

  // ---- Export state + handlers --------------------------------------------
  const [exportOpen, setExportOpen] = useState(false)
  const [warning, setWarning] = useState<PendingWarning | null>(null)

  function exportFilename(ext: string): string {
    return `eval-context-run${baseRunId}-vs-${variantRunId}.${ext}`
  }

  /** Gather args for payload builders; tolerates missing prod data. */
  function buildArgs(): BuildPayloadArgs | null {
    if (!datasetQ.data || !baseRun || !variantRun) return null
    const outputSchema =
      (inputSchemaQ.data?.output_schema as Record<string, unknown> | null) ??
      null
    return {
      dataset: {
        target_name: datasetQ.data.target_name,
        target_type: datasetQ.data.target_type,
        cases: datasetQ.data.cases,
      },
      prodModel: prodModelQ.data?.model ?? null,
      prodPrompts: prodPromptsQ.data,
      instructionsSchema: outputSchema,
      enumObjects: autoGenQ.data?.objects,
      variant: variantQ.data,
      variantId: variantRun.variant_id ?? null,
      baseRun,
      variantRun,
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
