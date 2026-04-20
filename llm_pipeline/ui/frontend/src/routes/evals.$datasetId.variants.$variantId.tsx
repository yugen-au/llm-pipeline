import { useMemo, useState, useCallback, useEffect } from 'react'
import { createFileRoute, useNavigate, Link } from '@tanstack/react-router'
import {
  ArrowLeft,
  Plus,
  Trash2,
  Play,
  Info,
  AlertCircle,
  RotateCcw,
} from 'lucide-react'
import {
  useDataset,
  useInputSchema,
  useVariant,
  useUpdateVariant,
  useTriggerEvalRun,
  useDeltaTypeWhitelist,
  useDatasetProdPrompts,
  useDatasetProdModel,
} from '@/api/evals'
import type {
  InstructionDeltaItem,
  ProdModelResponse,
  ProdPromptContent,
  ProdPromptsResponse,
  SchemaResponse,
  VariableDefinitions,
  VariantDelta,
  VariantItem,
} from '@/api/evals'
import { ApiError } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  PromptContentEditor,
  useIsDark,
  type VarDefs,
} from '@/components/prompts/PromptContentEditor'
import { VariableDefinitionsEditor } from '@/components/prompts/VariableDefinitionsEditor'
import {
  ModelCombobox,
  formatModel,
} from '@/components/pipelines/ModelCombobox'

export const Route = createFileRoute('/evals/$datasetId/variants/$variantId')({
  component: VariantEditorPage,
})

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Offline fallback whitelist used only when the backend whitelist fetch fails
 * or is still loading. Runtime source of truth is
 * `GET /evals/delta-type-whitelist` via `useDeltaTypeWhitelist()`.
 * Kept in sync with backend `_TYPE_WHITELIST` in `llm_pipeline/evals/delta.py`.
 */
const FALLBACK_TYPE_WHITELIST: ReadonlyArray<string> = [
  'str',
  'int',
  'float',
  'bool',
  'list',
  'dict',
  'Optional[str]',
  'Optional[int]',
  'Optional[float]',
  'Optional[bool]',
]

const MAX_DELTA_ENTRIES = 50

/** Fields inherited from LLMResultMixin — cannot be removed in v2. */
const INHERITED_FIELDS: ReadonlyArray<string> = ['confidence_score', 'notes']

// ---------------------------------------------------------------------------
// Merged-row state (unified prod + variant instructions schema)
// ---------------------------------------------------------------------------

/**
 * One row in the unified "Instructions schema" table on the variant editor's
 * right pane. Rows are either production fields (from `output_schema`) with an
 * editable default, or variant-added fields with a user-specified type and
 * default.
 *
 * On save, `prod` rows whose `current_default` deviates from `prod_default`
 * emit `{op: 'modify'}` entries (with no `type_str` — the backend preserves
 * the original pydantic annotation, which is essential for complex types like
 * `list[TopicItem]` that would have no stable whitelist representation). All
 * `variant` rows emit `{op: 'add'}` entries.
 */
export type MergedFieldRow =
  | {
      kind: 'prod'
      /** Field name from the production schema; fixed (not user-editable). */
      field: string
      /** Display-only type label (e.g. "str", "Optional[str]", "list"). */
      type_label: string
      /** Production default value; `undefined` means the field is required. */
      prod_default: unknown | undefined
      /**
       * Default currently shown in the editor. Starts equal to `prod_default`
       * and updates on user edit. Deviation from `prod_default` signals a
       * pending modify-op at save time.
       */
      current_default: unknown | undefined
      /** True for confidence_score/notes (from LLMResultMixin). */
      is_inherited: boolean
      /** True if prod had no default (required prod field). */
      is_required: boolean
      description?: string
    }
  | {
      kind: 'variant'
      /** Field name, user-editable. */
      field: string
      /** type_str from the whitelist; always defined. */
      type_str: string
      /**
       * Raw JSON string the user types for the default. Parsed on save;
       * parse-on-save (not parse-on-change) lets the user type mid-edits
       * like `[1,` without losing focus. Parse failure disables save.
       */
      default_json: string
    }

interface EditorState {
  name: string
  description: string
  model: string
  systemPrompt: string
  userPrompt: string
  mergedFields: MergedFieldRow[]
  /**
   * Variable definition overrides keyed by variable name. Stored as a Record
   * matching the shared `VarDefs` shape used by the reusable prompts
   * `VariableDefinitionsEditor`. Serialised to `VariableDefinitions` (same
   * shape) on save — backend accepts this directly.
   */
  variableDefinitions: VarDefs
}

// ---------------------------------------------------------------------------
// JSON-schema helpers
// ---------------------------------------------------------------------------

/**
 * Render a pydantic-generated JSON-schema subtree to a short Python-ish type
 * label for the read-only "type" column of the merged schema table. Matches
 * the style of the left pane's production fields list (e.g. "str", "int",
 * "Optional[str]", "list", "TopicItem").
 *
 * This is display-only. It has NO effect on what gets sent to the backend —
 * modify ops omit `type_str` entirely, so we don't need a round-trippable
 * inverse. Unknown shapes fall back to "unknown".
 */
function jsonSchemaTypeLabel(schema: unknown): string {
  if (!schema || typeof schema !== 'object') return 'unknown'
  const s = schema as Record<string, unknown>

  // $ref -> strip "#/$defs/<Name>" to just <Name>.
  const ref = s.$ref
  if (typeof ref === 'string') {
    const m = ref.match(/\/([^/]+)$/)
    return m ? m[1] : 'unknown'
  }

  // Optional[X] shapes: anyOf with one null branch.
  const anyOf = s.anyOf
  if (Array.isArray(anyOf) && anyOf.length === 2) {
    const a = anyOf[0] as Record<string, unknown> | undefined
    const b = anyOf[1] as Record<string, unknown> | undefined
    const aNull = a?.type === 'null'
    const bNull = b?.type === 'null'
    if (aNull && !bNull) return `Optional[${jsonSchemaTypeLabel(b)}]`
    if (bNull && !aNull) return `Optional[${jsonSchemaTypeLabel(a)}]`
  }

  // Primitive `type` field.
  const t = s.type
  if (typeof t === 'string') {
    switch (t) {
      case 'string':
        return 'str'
      case 'integer':
        return 'int'
      case 'number':
        return 'float'
      case 'boolean':
        return 'bool'
      case 'array':
        return 'list'
      case 'object':
        return 'dict'
      case 'null':
        return 'None'
      default:
        return t
    }
  }

  return 'unknown'
}

function deepEqualJSON(a: unknown, b: unknown): boolean {
  try {
    return JSON.stringify(a) === JSON.stringify(b)
  } catch {
    return false
  }
}

/**
 * Read stored `VariableDefinitions` (or a legacy list-of-dicts variant) into
 * the shared `VarDefs` Record shape. Backend historically accepted both; we
 * now standardise on Record going forward but keep list-shape tolerance for
 * backward compat on read.
 */
function readVarDefs(
  defs: VariableDefinitions | null | undefined,
): VarDefs {
  if (!defs) return {}
  if (Array.isArray(defs)) {
    const out: VarDefs = {}
    for (const d of defs as Array<Record<string, unknown>>) {
      if (!d || typeof d !== 'object') continue
      const name = typeof d.name === 'string' ? d.name : ''
      if (!name) continue
      out[name] = {
        type: typeof d.type === 'string' ? d.type : 'str',
        description: typeof d.description === 'string' ? d.description : '',
        auto_generate:
          typeof d.auto_generate === 'string' ? d.auto_generate : '',
      }
    }
    return out
  }
  // Record shape: normalise to VarDefs, coercing missing fields.
  const out: VarDefs = {}
  for (const [name, spec] of Object.entries(defs)) {
    out[name] = {
      type: typeof spec?.type === 'string' ? spec.type : 'str',
      description:
        typeof spec?.description === 'string' ? spec.description : '',
      auto_generate:
        typeof spec?.auto_generate === 'string' ? spec.auto_generate : '',
    }
  }
  return out
}

/**
 * Serialise `VarDefs` back to `VariableDefinitions` for the backend.
 * Drops rows with empty names; omits `auto_generate` when blank so we don't
 * spuriously overwrite prod defs with an empty expression string.
 */
function writeVarDefs(defs: VarDefs): VariableDefinitions | null {
  const entries = Object.entries(defs).filter(([name]) => name.trim() !== '')
  if (entries.length === 0) return null
  const out: VariableDefinitions = {}
  for (const [name, spec] of entries) {
    const entry: VariableDefinitions[string] = { type: spec.type }
    if (spec.description && spec.description.trim() !== '') {
      entry.description = spec.description
    }
    if (spec.auto_generate && spec.auto_generate.trim() !== '') {
      entry.auto_generate = spec.auto_generate
    }
    out[name.trim()] = entry
  }
  return out
}

/**
 * Merge two `VarDefs` records. Variant wins on key collision — matches
 * backend runner behavior where variant `variable_definitions` override prod
 * at sandbox-merge time.
 */
function mergeVarDefs(a: VarDefs, b: VarDefs): VarDefs {
  return { ...a, ...b }
}

/**
 * Build the editor baseline from a variant + (optional) prod prompts/model/schema.
 *
 * Prefill rules:
 * - `systemPrompt` / `userPrompt`: if the variant delta has no override AND
 *   prod content is available, use prod content as the baseline.
 * - `model`: if the variant delta has no model override AND prod model
 *   resolved, use prod model as the baseline. Degrades silently when
 *   `prodModel` is null (fetch errored or pipeline-target dataset).
 * - `variableDefinitions`: if the variant has none AND prod has any, use the
 *   MERGED prod system + user defs (runner merges both prod prompts anyway,
 *   so one combined set on the variant matches runtime behavior).
 * - `mergedFields`: seeded from `prodSchema.output_schema.properties` as `prod`
 *   rows. The variant's persisted `instructions_delta` then patches those rows
 *   (modify -> overwrite `current_default`) or appends `variant` rows (add).
 *
 * The baseline MUST capture the prefilled content — `statesEqual(state,
 * baseline)` is how dirty-tracking works, so returning a baseline without the
 * prefill would make the editor open in a perpetually-dirty state.
 */
function variantToEditorState(
  v: VariantItem,
  prod: ProdPromptsResponse | null | undefined,
  prodModel: ProdModelResponse | null | undefined,
  prodSchema: SchemaResponse | null | undefined,
): EditorState {
  const d: VariantDelta = (v.delta ?? {
    model: null,
    system_prompt: null,
    user_prompt: null,
    instructions_delta: null,
  }) as VariantDelta

  const variantSystem = d.system_prompt ?? ''
  const variantUser = d.user_prompt ?? ''
  const prodSystem = prod?.system?.content ?? ''
  const prodUser = prod?.user?.content ?? ''

  // Prefill prompt content only when variant is empty AND prod exists.
  const systemPrompt = variantSystem === '' && prodSystem !== ''
    ? prodSystem
    : variantSystem
  const userPrompt = variantUser === '' && prodUser !== ''
    ? prodUser
    : variantUser

  // Prefill model only when variant has no override AND prod model resolved.
  const variantModel = d.model ?? ''
  const prodModelStr = prodModel?.model ?? ''
  const model = variantModel === '' && prodModelStr !== ''
    ? prodModelStr
    : variantModel

  // Variable definitions: variant override wins wholesale when present.
  const variantDefs = readVarDefs(d.variable_definitions)
  const hasVariantDefs = Object.keys(variantDefs).length > 0
  let variableDefinitions: VarDefs = variantDefs
  if (!hasVariantDefs) {
    const prodSysDefs = readVarDefs(
      (prod?.system?.variable_definitions ?? null) as
        | VariableDefinitions
        | null,
    )
    const prodUserDefs = readVarDefs(
      (prod?.user?.variable_definitions ?? null) as
        | VariableDefinitions
        | null,
    )
    const merged = mergeVarDefs(prodSysDefs, prodUserDefs)
    if (Object.keys(merged).length > 0) {
      variableDefinitions = merged
    }
  }

  // Build merged-rows: prod fields first (insertion order from JSON object),
  // then variant-added rows from any `add` ops in the persisted delta.
  const outSchema =
    (prodSchema?.output_schema as Record<string, unknown> | null) ?? null
  const props =
    (outSchema?.properties as Record<string, Record<string, unknown>>) ?? {}
  const required = Array.isArray(outSchema?.required)
    ? (outSchema!.required as string[])
    : []

  const mergedFields: MergedFieldRow[] = []
  const prodIndex = new Map<string, number>()

  for (const [name, prop] of Object.entries(props)) {
    const hasDefault = Object.prototype.hasOwnProperty.call(prop, 'default')
    const prodDefault = hasDefault ? prop.default : undefined
    const description =
      typeof prop.description === 'string' ? prop.description : undefined
    const row: MergedFieldRow = {
      kind: 'prod',
      field: name,
      type_label: jsonSchemaTypeLabel(prop),
      prod_default: prodDefault,
      current_default: prodDefault,
      is_inherited: INHERITED_FIELDS.includes(name),
      // Spec: required iff prod has no default. pydantic's json_schema puts
      // the field in the top-level `required` array when it has no default;
      // we cross-check both so schemas from non-pydantic sources still work.
      is_required: !hasDefault || required.includes(name),
      description,
    }
    prodIndex.set(name, mergedFields.length)
    mergedFields.push(row)
  }

  // Apply persisted delta on top of prod baseline.
  const persisted = Array.isArray(d.instructions_delta)
    ? d.instructions_delta
    : []
  for (const item of persisted) {
    if (item.op === 'modify') {
      const idx = prodIndex.get(item.field)
      if (idx === undefined) {
        // Modify on a non-prod field — shouldn't happen, but tolerate by
        // promoting to a variant row so the user still sees the entry.
        console.warn(
          `[variants] modify op references unknown field '${item.field}'; rendering as variant row.`,
        )
        mergedFields.push({
          kind: 'variant',
          field: item.field,
          type_str: item.type_str ?? 'str',
          default_json: JSON.stringify(item.default ?? null),
        })
        continue
      }
      const existing = mergedFields[idx]
      if (existing.kind === 'prod') {
        mergedFields[idx] = {
          ...existing,
          current_default: item.default,
        }
      }
    } else if (item.op === 'add') {
      mergedFields.push({
        kind: 'variant',
        field: item.field,
        type_str: item.type_str ?? 'str',
        default_json: JSON.stringify(item.default ?? null),
      })
    }
  }

  return {
    name: v.name ?? '',
    description: v.description ?? '',
    model,
    systemPrompt,
    userPrompt,
    mergedFields,
    variableDefinitions,
  }
}

/**
 * Serialise the merged-rows state back into an `instructions_delta` payload
 * by diffing against the prod baseline.
 *
 * - `prod` rows: emit `{op: 'modify', field, default}` ONLY if `current_default`
 *   differs from `prod_default`. No `type_str` — backend re-uses the original
 *   pydantic annotation (see delta.py:235-246).
 * - Required prod rows with no current default: emit nothing (no modification,
 *   state is identical to prod's "required" contract).
 * - `variant` rows: emit `{op: 'add', field, type_str, default}` with the
 *   parsed JSON default. Parse failures surface as row-level errors (caller
 *   must gate Save on `mergedFieldsHaveErrors`).
 */
function editorStateToDelta(s: EditorState): VariantDelta {
  const items: InstructionDeltaItem[] = []

  for (const row of s.mergedFields) {
    if (row.kind === 'prod') {
      const prodDefined = row.prod_default !== undefined
      const currDefined = row.current_default !== undefined
      // Required prod field with no current default -> no modification.
      if (!prodDefined && !currDefined) continue
      // Unchanged -> no modification.
      if (
        prodDefined &&
        currDefined &&
        deepEqualJSON(row.prod_default, row.current_default)
      ) {
        continue
      }
      // Transition either way (required -> now has default, or default changed).
      items.push({
        op: 'modify',
        field: row.field,
        // type_str is omitted on the wire; required by the InstructionDeltaItem
        // TS shape, so we cast. Backend handles the missing key as "preserve
        // original pydantic annotation" (delta.py:236-246).
        type_str: undefined as unknown as InstructionDeltaItem['type_str'],
        default: row.current_default ?? null,
      })
    } else {
      // variant-added: parse default_json. On failure we emit a placeholder
      // entry of null so the caller's error-check logic fires before Save.
      let parsed: unknown = null
      try {
        parsed = row.default_json.trim() === ''
          ? null
          : JSON.parse(row.default_json)
      } catch {
        parsed = null
      }
      items.push({
        op: 'add',
        field: row.field,
        type_str: row.type_str as InstructionDeltaItem['type_str'],
        default: parsed,
      })
    }
  }

  // Strip undefined type_str on modify ops before sending — JSON.stringify
  // drops undefined keys in object values anyway, but be explicit so the
  // wire payload never carries a key with an undefined value.
  const wireItems = items.map((it) => {
    if (it.op === 'modify' && it.type_str === undefined) {
      const copy: Partial<InstructionDeltaItem> = { ...it }
      delete copy.type_str
      return copy as InstructionDeltaItem
    }
    return it
  })

  return {
    model: s.model.trim() === '' ? null : s.model.trim(),
    system_prompt: s.systemPrompt === '' ? null : s.systemPrompt,
    user_prompt: s.userPrompt === '' ? null : s.userPrompt,
    instructions_delta: wireItems.length === 0 ? null : wireItems,
    variable_definitions: writeVarDefs(s.variableDefinitions),
  }
}

/**
 * Row-level validation: true when any variant row has an unparseable default.
 * Empty string is treated as null (valid). Prod rows never fail validation
 * here — their default is a native value, not a raw JSON string.
 */
function mergedFieldsHaveErrors(rows: MergedFieldRow[]): boolean {
  for (const r of rows) {
    if (r.kind !== 'variant') continue
    if (r.default_json.trim() === '') continue
    try {
      JSON.parse(r.default_json)
    } catch {
      return true
    }
  }
  return false
}

function statesEqual(a: EditorState, b: EditorState): boolean {
  if (
    a.name !== b.name ||
    a.description !== b.description ||
    a.model !== b.model ||
    a.systemPrompt !== b.systemPrompt ||
    a.userPrompt !== b.userPrompt
  )
    return false
  if (a.mergedFields.length !== b.mergedFields.length) return false
  for (let i = 0; i < a.mergedFields.length; i++) {
    const x = a.mergedFields[i]
    const y = b.mergedFields[i]
    if (x.kind !== y.kind) return false
    if (x.kind === 'prod' && y.kind === 'prod') {
      if (x.field !== y.field) return false
      if (!deepEqualJSON(x.current_default, y.current_default)) return false
    } else if (x.kind === 'variant' && y.kind === 'variant') {
      if (x.field !== y.field) return false
      if (x.type_str !== y.type_str) return false
      if (x.default_json !== y.default_json) return false
    }
  }
  // Record shape: order-independent JSON comparison is sufficient — both sides
  // are produced by `readVarDefs`/component updates which always emit stable
  // key ordering (component key set is deterministic).
  if (
    JSON.stringify(a.variableDefinitions) !==
    JSON.stringify(b.variableDefinitions)
  ) {
    return false
  }
  return true
}

function useVariantEditor(
  variant: VariantItem | undefined,
  prod: ProdPromptsResponse | null | undefined,
  prodModel: ProdModelResponse | null | undefined,
  prodSchema: SchemaResponse | null | undefined,
  prodReady: boolean,
) {
  const [state, setState] = useState<EditorState | null>(null)
  const [baseline, setBaseline] = useState<EditorState | null>(null)

  // sync from server when variant OR prod data change (only once prod has
  // resolved — otherwise we'd build a baseline without prefill and flip the
  // editor to dirty as soon as prod arrives). `prodReady` gates prod-prompts,
  // prod-model, AND prod-schema so the baseline captures all prefills.
  useEffect(() => {
    if (!variant) return
    if (!prodReady) return
    const snap = variantToEditorState(
      variant,
      prod ?? null,
      prodModel ?? null,
      prodSchema ?? null,
    )
    setState((prev) => (prev === null ? snap : prev))
    setBaseline(snap)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant?.id, variant?.updated_at, prodReady])

  const dirty = useMemo(() => {
    if (!state || !baseline) return false
    return !statesEqual(state, baseline)
  }, [state, baseline])

  const patch = useCallback((p: Partial<EditorState>) => {
    setState((prev) => (prev ? { ...prev, ...p } : prev))
  }, [])

  const updateMergedRow = useCallback(
    (idx: number, p: Partial<MergedFieldRow>) => {
      setState((prev) => {
        if (!prev) return prev
        const next = prev.mergedFields.slice()
        const existing = next[idx]
        if (!existing) return prev
        // Narrow partial apply per kind — TS won't let us spread a cross-kind
        // partial without a cast, and behavior is identical since we always
        // pass same-kind patches.
        if (existing.kind === 'prod') {
          next[idx] = { ...existing, ...(p as Partial<typeof existing>) }
        } else {
          next[idx] = { ...existing, ...(p as Partial<typeof existing>) }
        }
        return { ...prev, mergedFields: next }
      })
    },
    [],
  )

  const addVariantRow = useCallback(() => {
    setState((prev) => {
      if (!prev) return prev
      const current = prev.mergedFields
      const variantCount = current.filter((r) => r.kind === 'variant').length
      const modifiedCount = current.filter(
        (r) =>
          r.kind === 'prod' &&
          !deepEqualJSON(r.current_default, r.prod_default),
      ).length
      if (variantCount + modifiedCount >= MAX_DELTA_ENTRIES) return prev
      return {
        ...prev,
        mergedFields: [
          ...current,
          { kind: 'variant', field: '', type_str: 'str', default_json: '' },
        ],
      }
    })
  }, [])

  const removeVariantRow = useCallback((idx: number) => {
    setState((prev) => {
      if (!prev) return prev
      const next = prev.mergedFields.slice()
      const row = next[idx]
      // Only variant rows are removable — guard against stray calls.
      if (!row || row.kind !== 'variant') return prev
      next.splice(idx, 1)
      return { ...prev, mergedFields: next }
    })
  }, [])

  const resetProdRow = useCallback((idx: number) => {
    setState((prev) => {
      if (!prev) return prev
      const next = prev.mergedFields.slice()
      const row = next[idx]
      if (!row || row.kind !== 'prod') return prev
      next[idx] = { ...row, current_default: row.prod_default }
      return { ...prev, mergedFields: next }
    })
  }, [])

  const setVarDefs = useCallback((defs: VarDefs) => {
    setState((prev) => (prev ? { ...prev, variableDefinitions: defs } : prev))
  }, [])

  const resetToBaseline = useCallback(() => {
    if (baseline) setState(baseline)
  }, [baseline])

  return {
    state,
    baseline,
    dirty,
    patch,
    updateMergedRow,
    addVariantRow,
    removeVariantRow,
    resetProdRow,
    setVarDefs,
    resetToBaseline,
  }
}

// ---------------------------------------------------------------------------
// Prod step definition panel (read-only left pane)
// ---------------------------------------------------------------------------

/** Human-readable label for a ProdModelSource. "none" collapses to no label. */
function prodModelSourceLabel(source: ProdModelResponse['source']): string | null {
  switch (source) {
    case 'db':
      return 'user override'
    case 'step_definition':
      return 'step definition'
    case 'pipeline_default':
      return 'pipeline default'
    case 'none':
      return null
  }
}

function ProdStepDefPanel({
  datasetId,
  prodSystem,
  prodUser,
  prodModel,
  prodSchema,
  schemaLoading,
  isDark,
}: {
  datasetId: number
  prodSystem: ProdPromptContent | null
  prodUser: ProdPromptContent | null
  prodModel: ProdModelResponse | null
  prodSchema: SchemaResponse | null | undefined
  schemaLoading: boolean
  isDark: boolean
}) {
  const { data: dataset } = useDataset(datasetId)

  const outputProps = useMemo(() => {
    const props = (prodSchema?.output_schema?.properties ?? null) as
      | Record<string, Record<string, unknown>>
      | null
    if (!props) return []
    return Object.entries(props).map(([name, p]) => ({
      name,
      type_label: jsonSchemaTypeLabel(p),
      title: typeof p.title === 'string' ? p.title : undefined,
      description:
        typeof p.description === 'string' ? p.description : undefined,
    }))
  }, [prodSchema])

  // Read prod variable_definitions once per prompt side so the read-only
  // editor can still show hover info for {variable} tokens. readVarDefs
  // tolerates both map and list shapes from the backend.
  const prodSystemVarDefs = useMemo<VarDefs>(
    () =>
      readVarDefs(
        (prodSystem?.variable_definitions ?? null) as
          | VariableDefinitions
          | null,
      ),
    [prodSystem],
  )
  const prodUserVarDefs = useMemo<VarDefs>(
    () =>
      readVarDefs(
        (prodUser?.variable_definitions ?? null) as
          | VariableDefinitions
          | null,
      ),
    [prodUser],
  )

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          Production Step Definition
          <Badge variant="secondary" className="text-[10px]">
            read-only
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-xs">
        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Target
          </Label>
          <p className="font-mono">
            {dataset
              ? `${dataset.target_type}: ${dataset.target_name}`
              : 'Loading...'}
          </p>
        </div>

        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Base eval model
          </Label>
          {prodModel?.model ? (
            <div className="flex items-center gap-1.5 flex-wrap">
              <Badge variant="secondary" className="text-xs py-0 shrink-0">
                {formatModel(prodModel.model).provider}
              </Badge>
              <code className="text-xs font-mono">
                {formatModel(prodModel.model).name}
              </code>
              {prodModelSourceLabel(prodModel.source) && (
                <span className="text-muted-foreground text-xs">
                  ({prodModelSourceLabel(prodModel.source)})
                </span>
              )}
            </div>
          ) : (
            <p className="text-muted-foreground italic">
              No production model configured.
            </p>
          )}
        </div>

        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Instructions fields
          </Label>
          {schemaLoading ? (
            <p className="text-muted-foreground">Loading schema...</p>
          ) : outputProps.length === 0 ? (
            <p className="text-muted-foreground italic">
              No typed output schema available for this step.
            </p>
          ) : (
            <div className="rounded border bg-muted/30 divide-y">
              {outputProps.map((f) => (
                <div
                  key={f.name}
                  className="px-2 py-1.5 flex items-start gap-2"
                >
                  <span className="font-mono font-medium">{f.name}</span>
                  <Badge
                    variant="outline"
                    className="text-[10px] h-4 px-1 py-0 font-mono"
                  >
                    {f.type_label}
                  </Badge>
                  {f.description && (
                    <span className="text-muted-foreground ml-auto truncate max-w-[160px]">
                      {f.description}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Production system prompt
            {prodSystem?.version && (
              <span className="ml-2 font-mono normal-case text-muted-foreground">
                v{prodSystem.version}
              </span>
            )}
          </Label>
          {prodSystem ? (
            <>
              <PromptContentEditor
                value={prodSystem.content}
                onChange={() => {}}
                varDefs={prodSystemVarDefs}
                isDark={isDark}
                height="180px"
                readOnly
              />
              <VariableDefinitionsEditor
                readOnly
                content={prodSystem.content}
                value={prodSystemVarDefs}
                onChange={() => {}}
              />
            </>
          ) : (
            <p className="text-muted-foreground italic">
              No production system prompt.
            </p>
          )}
        </div>

        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Production user prompt
            {prodUser?.version && (
              <span className="ml-2 font-mono normal-case text-muted-foreground">
                v{prodUser.version}
              </span>
            )}
          </Label>
          {prodUser ? (
            <>
              <PromptContentEditor
                value={prodUser.content}
                onChange={() => {}}
                varDefs={prodUserVarDefs}
                isDark={isDark}
                height="180px"
                readOnly
              />
              <VariableDefinitionsEditor
                readOnly
                content={prodUser.content}
                value={prodUserVarDefs}
                onChange={() => {}}
              />
            </>
          ) : (
            <p className="text-muted-foreground italic">
              No production user prompt.
            </p>
          )}
        </div>

        <p className="text-muted-foreground text-[11px]">
          Inherit by leaving variant fields blank.
        </p>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Merged schema rows (prod + variant-added) for the right pane table
// ---------------------------------------------------------------------------

/**
 * JSON-stringify a value for the prod-row default Input. `undefined` collapses
 * to empty string so the placeholder ("required — no default") is visible.
 */
function prodDefaultToInput(v: unknown): string {
  if (v === undefined) return ''
  try {
    return JSON.stringify(v)
  } catch {
    return ''
  }
}

/**
 * Inner controlled component for the prod row. We lift `current_default` into
 * a local raw-string buffer so the user can type mid-parse values like `[1,`.
 * The outer `ProdFieldRow` keys this component on `current_default` via a
 * `JSON.stringify` key so external state mutations (Reset, Discard) remount
 * the inner component with a fresh buffer — avoiding setState-in-effect.
 */
function ProdFieldRowInner({
  row,
  onChangeDefault,
  backendErrorMsg,
}: {
  row: Extract<MergedFieldRow, { kind: 'prod' }>
  onChangeDefault: (next: unknown | undefined) => void
  backendErrorMsg?: string
}) {
  const [raw, setRaw] = useState(() => prodDefaultToInput(row.current_default))
  const [parseError, setParseError] = useState<string | null>(null)

  function handleChange(next: string) {
    setRaw(next)
    if (next.trim() === '') {
      setParseError(null)
      onChangeDefault(undefined)
      return
    }
    try {
      const parsed = JSON.parse(next)
      setParseError(null)
      onChangeDefault(parsed)
    } catch (e) {
      setParseError(e instanceof Error ? e.message : 'Invalid JSON')
      // Hold the parse-failed value in local `raw` only — don't push to state
      // until the user types something valid. This keeps the diff clean.
    }
  }

  const modified = !deepEqualJSON(row.current_default, row.prod_default)

  return (
    <>
      <Input
        className="h-8 text-xs font-mono"
        placeholder={
          row.is_required && !modified
            ? 'required — no default'
            : 'JSON (e.g. "text", 1, true, null, [])'
        }
        value={raw}
        onChange={(e) => handleChange(e.target.value)}
      />
      {parseError && (
        <p className="text-[10px] text-destructive mt-1 flex items-start gap-1">
          <AlertCircle className="size-3 shrink-0 mt-0.5" />
          <span>{parseError}</span>
        </p>
      )}
      {backendErrorMsg && (
        <p className="text-[10px] text-destructive mt-1 flex items-start gap-1">
          <AlertCircle className="size-3 shrink-0 mt-0.5" />
          <span>{backendErrorMsg}</span>
        </p>
      )}
      {row.description && (
        <p className="text-[10px] text-muted-foreground mt-1 truncate">
          {row.description}
        </p>
      )}
    </>
  )
}

function ProdFieldRow({
  row,
  idx,
  onChangeDefault,
  onReset,
  backendErrorMsg,
}: {
  row: Extract<MergedFieldRow, { kind: 'prod' }>
  idx: number
  onChangeDefault: (next: unknown | undefined) => void
  onReset: () => void
  backendErrorMsg?: string
}) {
  const modified = !deepEqualJSON(row.current_default, row.prod_default)
  // Key on the JSON-stringified current_default so external mutations
  // (Reset, Discard) remount the inner buffer component.
  const innerKey = JSON.stringify(row.current_default ?? null)

  return (
    <tr data-row-idx={idx} className="border-t align-top">
      <td className="px-2 py-1.5 font-mono font-medium whitespace-nowrap">
        {row.field}
      </td>
      <td className="px-2 py-1.5 whitespace-nowrap">
        <Badge
          variant="outline"
          className="text-[10px] h-4 px-1 py-0 font-mono"
        >
          {row.type_label}
        </Badge>
      </td>
      <td className="px-2 py-1.5">
        <ProdFieldRowInner
          key={innerKey}
          row={row}
          onChangeDefault={onChangeDefault}
          backendErrorMsg={backendErrorMsg}
        />
      </td>
      <td className="px-2 py-1.5 whitespace-nowrap">
        <div className="flex items-center gap-1">
          {row.is_required && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge
                    variant="outline"
                    className="text-[9px] h-4 px-1 py-0 border-amber-500 text-amber-600"
                  >
                    required
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  Setting a default makes this field optional in the variant.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          {row.is_inherited && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge
                    variant="outline"
                    className="text-[9px] h-4 px-1 py-0 border-blue-500 text-blue-600"
                  >
                    inherited
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  Inherited from LLMResultMixin — cannot be removed.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          {modified && (
            <>
              <Badge
                variant="outline"
                className="text-[9px] h-4 px-1 py-0 border-amber-500 text-amber-600"
              >
                modified
              </Badge>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 w-6 p-0"
                onClick={onReset}
                title="Reset to production default"
              >
                <RotateCcw className="size-3" />
              </Button>
            </>
          )}
        </div>
      </td>
    </tr>
  )
}

function VariantFieldRow({
  row,
  idx,
  onChangeField,
  onChangeType,
  onChangeDefault,
  onRemove,
  typeOptions,
  typesDisabled,
  backendErrorMsg,
}: {
  row: Extract<MergedFieldRow, { kind: 'variant' }>
  idx: number
  onChangeField: (v: string) => void
  onChangeType: (v: string) => void
  onChangeDefault: (v: string) => void
  onRemove: () => void
  typeOptions: ReadonlyArray<string>
  typesDisabled: boolean
  backendErrorMsg?: string
}) {
  const isInherited = INHERITED_FIELDS.includes(row.field.trim())

  // Parse check — display error without blocking typing. Save button is gated
  // separately via `mergedFieldsHaveErrors`.
  let parseError: string | null = null
  if (row.default_json.trim() !== '') {
    try {
      JSON.parse(row.default_json)
    } catch (e) {
      parseError = e instanceof Error ? e.message : 'Invalid JSON'
    }
  }

  return (
    <tr data-row-idx={idx} className="border-t align-top bg-muted/20">
      <td className="px-2 py-1.5">
        <Input
          className={`h-8 text-xs font-mono ${
            isInherited ? 'border-amber-500' : ''
          }`}
          placeholder="field_name"
          value={row.field}
          onChange={(e) =>
            onChangeField(e.target.value.trim().toLowerCase())
          }
        />
        {isInherited && (
          <p className="text-[10px] text-amber-600 mt-1">
            Inherited field — use the prod row above to modify it.
          </p>
        )}
      </td>
      <td className="px-2 py-1.5">
        <Select
          value={row.type_str}
          onValueChange={onChangeType}
          disabled={typesDisabled}
        >
          <SelectTrigger size="sm" className="h-8 text-xs font-mono">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {typeOptions.map((t) => (
              <SelectItem key={t} value={t} className="text-xs font-mono">
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </td>
      <td className="px-2 py-1.5">
        <Input
          className="h-8 text-xs font-mono"
          placeholder='JSON (e.g. "text", 1, true, null, [])'
          value={row.default_json}
          onChange={(e) => onChangeDefault(e.target.value)}
        />
        {parseError && (
          <p className="text-[10px] text-destructive mt-1 flex items-start gap-1">
            <AlertCircle className="size-3 shrink-0 mt-0.5" />
            <span>{parseError}</span>
          </p>
        )}
        {backendErrorMsg && (
          <p className="text-[10px] text-destructive mt-1 flex items-start gap-1">
            <AlertCircle className="size-3 shrink-0 mt-0.5" />
            <span>{backendErrorMsg}</span>
          </p>
        )}
      </td>
      <td className="px-2 py-1.5 whitespace-nowrap">
        <div className="flex items-center gap-1">
          <Badge
            variant="outline"
            className="text-[9px] h-4 px-1 py-0 border-emerald-500 text-emerald-600"
          >
            added
          </Badge>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 w-6 p-0 text-destructive"
            onClick={onRemove}
            title="Remove variant-added field"
          >
            <Trash2 className="size-3" />
          </Button>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Editable delta panel (right pane)
// ---------------------------------------------------------------------------

function VariantDeltaPanel({
  state,
  patch,
  updateMergedRow,
  addVariantRow,
  removeVariantRow,
  resetProdRow,
  setVarDefs,
  backendFieldError,
  typeOptions,
  typesLoading,
  isDark,
}: {
  state: EditorState
  patch: (p: Partial<EditorState>) => void
  updateMergedRow: (idx: number, p: Partial<MergedFieldRow>) => void
  addVariantRow: () => void
  removeVariantRow: (idx: number) => void
  resetProdRow: (idx: number) => void
  setVarDefs: (defs: VarDefs) => void
  backendFieldError: { rowIdx: number | null; message: string } | null
  typeOptions: ReadonlyArray<string>
  typesLoading: boolean
  isDark: boolean
}) {
  // Count only entries that contribute to instructions_delta payload:
  // modified prod rows + all variant rows. Matches backend cap semantics.
  const emittedCount = useMemo(() => {
    let n = 0
    for (const r of state.mergedFields) {
      if (r.kind === 'variant') {
        n++
      } else if (!deepEqualJSON(r.current_default, r.prod_default)) {
        n++
      }
    }
    return n
  }, [state.mergedFields])

  const nearCap = emittedCount >= MAX_DELTA_ENTRIES - 5
  const atCap = emittedCount >= MAX_DELTA_ENTRIES

  // Concatenate both prompts so the shared VariableDefinitionsEditor can
  // extract variables from either.
  const combinedPromptContent = useMemo(
    () => state.systemPrompt + '\n' + state.userPrompt,
    [state.systemPrompt, state.userPrompt],
  )

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Variant Delta</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 text-xs">
        {/* Metadata */}
        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Variant name
          </Label>
          <Input
            className="h-8 text-xs"
            value={state.name}
            onChange={(e) => patch({ name: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Description
          </Label>
          <Input
            className="h-8 text-xs"
            placeholder="Optional description"
            value={state.description}
            onChange={(e) => patch({ description: e.target.value })}
          />
        </div>

        {/* Model override */}
        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Model override
          </Label>
          <ModelCombobox
            value={state.model || null}
            onChange={(m) => patch({ model: m })}
            onClear={() => patch({ model: '' })}
            placeholder="Inherit production model"
          />
        </div>

        {/* System prompt */}
        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            System prompt override
          </Label>
          <PromptContentEditor
            value={state.systemPrompt}
            onChange={(v) => patch({ systemPrompt: v })}
            varDefs={state.variableDefinitions}
            isDark={isDark}
            height="240px"
          />
        </div>

        {/* User prompt */}
        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            User prompt override
          </Label>
          <PromptContentEditor
            value={state.userPrompt}
            onChange={(v) => patch({ userPrompt: v })}
            varDefs={state.variableDefinitions}
            isDark={isDark}
            height="240px"
          />
        </div>

        {/* Instructions schema (merged: prod fields + variant-added) */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-[10px] uppercase text-muted-foreground">
              Instructions schema ({emittedCount}/{MAX_DELTA_ENTRIES} delta
              entries)
            </Label>
          </div>

          {/* Info banner about inherited fields */}
          <div className="rounded border border-blue-500/30 bg-blue-500/5 p-2 flex items-start gap-2 text-[11px] text-muted-foreground">
            <Info className="size-3 shrink-0 mt-0.5 text-blue-500" />
            <span>
              Inherited fields from <code>LLMResultMixin</code> (
              <code>confidence_score</code>, <code>notes</code>) cannot be
              removed. Edit defaults inline; variant-added fields go at the
              bottom.
            </span>
          </div>

          {state.mergedFields.length === 0 ? (
            <p className="text-muted-foreground italic text-[11px]">
              No typed output schema available for this step. Variant-added
              fields can still be appended below.
            </p>
          ) : (
            <div className="rounded border overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-muted/40">
                  <tr className="text-left text-[10px] uppercase text-muted-foreground">
                    <th className="px-2 py-1.5 font-normal">Field</th>
                    <th className="px-2 py-1.5 font-normal">Type</th>
                    <th className="px-2 py-1.5 font-normal">Default (JSON)</th>
                    <th className="px-2 py-1.5 font-normal" />
                  </tr>
                </thead>
                <tbody>
                  {state.mergedFields.map((row, idx) => {
                    const backendMsg =
                      backendFieldError && backendFieldError.rowIdx === idx
                        ? backendFieldError.message
                        : undefined
                    if (row.kind === 'prod') {
                      return (
                        <ProdFieldRow
                          key={`prod-${row.field}`}
                          row={row}
                          idx={idx}
                          onChangeDefault={(next) =>
                            updateMergedRow(idx, { current_default: next })
                          }
                          onReset={() => resetProdRow(idx)}
                          backendErrorMsg={backendMsg}
                        />
                      )
                    }
                    return (
                      <VariantFieldRow
                        key={`variant-${idx}`}
                        row={row}
                        idx={idx}
                        onChangeField={(v) =>
                          updateMergedRow(idx, { field: v })
                        }
                        onChangeType={(v) =>
                          updateMergedRow(idx, { type_str: v })
                        }
                        onChangeDefault={(v) =>
                          updateMergedRow(idx, { default_json: v })
                        }
                        onRemove={() => removeVariantRow(idx)}
                        typeOptions={typeOptions}
                        typesDisabled={typesLoading}
                        backendErrorMsg={backendMsg}
                      />
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex items-center justify-between">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs gap-1"
              onClick={addVariantRow}
              disabled={atCap}
            >
              <Plus className="size-3" /> Add field
            </Button>
            {nearCap && !atCap && (
              <p className="text-[10px] text-amber-600">
                Approaching the {MAX_DELTA_ENTRIES}-entry cap.
              </p>
            )}
            {atCap && (
              <p className="text-[10px] text-destructive">
                At the {MAX_DELTA_ENTRIES}-entry cap — remove or reset entries
                to add more.
              </p>
            )}
          </div>
        </div>

        {/* Variable definitions */}
        <div className="space-y-2">
          <Label className="text-[10px] uppercase text-muted-foreground">
            Variable definitions
          </Label>

          <div className="rounded border border-blue-500/30 bg-blue-500/5 p-2 flex items-start gap-2 text-[11px] text-muted-foreground">
            <Info className="size-3 shrink-0 mt-0.5 text-blue-500" />
            <span>
              Variables are auto-detected from the system and user prompt
              overrides above. Edits here override or add to the production
              prompt's variable_definitions — variant wins on name collision.{' '}
              <code>auto_generate</code> expressions are resolved at prompt
              render time by the backend registry (not evaluated client-side).
            </span>
          </div>

          <VariableDefinitionsEditor
            content={combinedPromptContent}
            value={state.variableDefinitions}
            onChange={setVarDefs}
          />
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function VariantEditorPage() {
  const { datasetId: rawDatasetId, variantId: rawVariantId } =
    Route.useParams()
  const datasetId = Number(rawDatasetId)
  const variantId = Number(rawVariantId)
  const navigate = useNavigate()
  const isDark = useIsDark()

  const {
    data: variant,
    isLoading: variantLoading,
    error: variantError,
  } = useVariant(datasetId, variantId)
  const { data: dataset } = useDataset(datasetId)

  // Prod prompts power two things:
  //   1. Prefill empty variant overrides so the editor opens with a copy of
  //      the prod prompt the user can edit (instead of blank text).
  //   2. Populate the read-only left pane so the user can compare.
  // Failures degrade gracefully — we still let the editor open, just with no
  // prefill (matching prior behavior).
  const {
    data: prodPrompts,
    isLoading: prodPromptsLoading,
    isError: prodPromptsErrored,
    error: prodPromptsError,
  } = useDatasetProdPrompts(datasetId)
  useEffect(() => {
    if (prodPromptsErrored) {
      // eslint-disable-next-line no-console
      console.warn(
        '[variants] Failed to fetch prod prompts; editor will open without prefill.',
        prodPromptsError,
      )
    }
  }, [prodPromptsErrored, prodPromptsError])

  // Prod model mirrors prod prompts: prefill source + left-pane display.
  // Fetch failure degrades silently (empty model override field, left pane
  // shows "No production model configured").
  const {
    data: prodModel,
    isLoading: prodModelLoading,
    isError: prodModelErrored,
    error: prodModelError,
  } = useDatasetProdModel(datasetId)
  useEffect(() => {
    if (prodModelErrored) {
      // eslint-disable-next-line no-console
      console.warn(
        '[variants] Failed to fetch prod model; editor will open without prefill.',
        prodModelError,
      )
    }
  }, [prodModelErrored, prodModelError])

  // Prod schema (output_schema.properties) drives the merged-schema table on
  // the right pane AND the Instructions fields list on the left pane. Fetch
  // gated on dataset having loaded its target_type/target_name.
  const {
    data: prodSchema,
    isLoading: prodSchemaLoading,
    isError: prodSchemaErrored,
    error: prodSchemaError,
  } = useInputSchema(
    dataset?.target_type ?? '',
    dataset?.target_name ?? '',
  )
  useEffect(() => {
    if (prodSchemaErrored) {
      // eslint-disable-next-line no-console
      console.warn(
        '[variants] Failed to fetch prod schema; editor will open with no prod fields.',
        prodSchemaError,
      )
    }
  }, [prodSchemaErrored, prodSchemaError])

  // "ready" = we're no longer waiting on any pending prod fetch. Either data
  // landed OR the fetch errored (404/network/etc). Both paths build a
  // baseline — the error path just builds one with the missing bit as null,
  // matching prior behavior (no prefill for that piece).
  //
  // Note: we also wait for `dataset` to have loaded since the schema fetch is
  // gated on it — without the dataset, schema fetch is disabled and
  // `prodSchemaLoading` is false-but-never-started.
  const prodReady =
    !prodPromptsLoading &&
    !prodModelLoading &&
    Boolean(dataset) &&
    !prodSchemaLoading

  const updateVariantMut = useUpdateVariant(datasetId)
  const triggerRun = useTriggerEvalRun(datasetId)

  // Backend whitelist — single source of truth for the type_str dropdown.
  // Fall back to the static list on fetch failure so the editor remains usable.
  const {
    data: typeWhitelist,
    isLoading: typesLoading,
    error: typesError,
  } = useDeltaTypeWhitelist()
  useEffect(() => {
    if (typesError) {
      // eslint-disable-next-line no-console
      console.error(
        '[variants] Failed to fetch delta type whitelist; using fallback.',
        typesError,
      )
    }
  }, [typesError])
  const typeOptions: ReadonlyArray<string> = useMemo(() => {
    if (typeWhitelist?.types && typeWhitelist.types.length > 0) {
      return typeWhitelist.types
    }
    return FALLBACK_TYPE_WHITELIST
  }, [typeWhitelist])

  const {
    state,
    dirty,
    patch,
    updateMergedRow,
    addVariantRow,
    removeVariantRow,
    resetProdRow,
    setVarDefs,
    resetToBaseline,
  } = useVariantEditor(variant, prodPrompts, prodModel, prodSchema, prodReady)

  // Save is blocked on unparseable variant-row defaults.
  const hasRowErrors = useMemo(
    () => (state ? mergedFieldsHaveErrors(state.mergedFields) : false),
    [state],
  )

  // Backend 422 error surfacing
  const [saveError, setSaveError] = useState<string | null>(null)
  const [backendFieldError, setBackendFieldError] = useState<
    { rowIdx: number | null; message: string } | null
  >(null)

  function parseBackendFieldError(
    msg: string,
    rows: MergedFieldRow[],
  ): { rowIdx: number | null; message: string } {
    // Backend messages commonly include the offending field name verbatim
    // quoted (e.g. "field name '__class__' is invalid"). Map to row index by
    // finding the LONGEST matching field — avoids prefix collisions where
    // e.g. rows have `foo` and `foobar` and the message mentions 'foobar'
    // (naive iteration would mis-match the shorter 'foo' row even with the
    // wrapping quotes, if candidates were sorted insertion-order).
    let bestIdx: number | null = null
    let bestLen = -1
    for (let i = 0; i < rows.length; i++) {
      const f = rows[i].field
      if (!f) continue
      if (msg.includes(`'${f}'`) && f.length > bestLen) {
        bestIdx = i
        bestLen = f.length
      }
    }
    return { rowIdx: bestIdx, message: msg }
  }

  async function handleSave() {
    if (!state || !variant) return
    if (hasRowErrors) return
    setSaveError(null)
    setBackendFieldError(null)
    const delta = editorStateToDelta(state)
    try {
      await updateVariantMut.mutateAsync({
        variantId: variant.id,
        name: state.name.trim() || variant.name,
        description: state.description.trim() === '' ? null : state.description,
        delta,
      })
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const msg = err.detail || 'Validation failed'
        setSaveError(msg)
        setBackendFieldError(
          parseBackendFieldError(msg, state.mergedFields),
        )
      } else {
        setSaveError(
          err instanceof Error ? err.message : 'Failed to save variant',
        )
      }
    }
  }

  function handleDiscard() {
    setSaveError(null)
    setBackendFieldError(null)
    resetToBaseline()
  }

  async function handleRunWithVariant() {
    if (!variant) return
    if (dirty) {
      if (
        !confirm(
          'You have unsaved changes. Run will use the saved variant. Continue?',
        )
      )
        return
    }
    try {
      await triggerRun.mutateAsync({ variant_id: variant.id })
      // Navigate back to dataset detail (Run History tab is default-openable
      // via the user clicking it; no search-param handling for tabs yet).
      navigate({ to: `/evals/${datasetId}` as string })
    } catch {
      // apiClient already surfaces via toast
    }
  }

  if (variantLoading || !prodReady) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">
          {variantLoading
            ? 'Loading variant...'
            : 'Loading production config...'}
        </p>
      </div>
    )
  }

  if (variantError || !variant || !state) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-destructive">
          {(variantError as { detail?: string } | null)?.detail ??
            'Variant not found'}
        </p>
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-7xl space-y-6 p-6">
        {/* Breadcrumb + header */}
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" className="h-7 px-2" asChild>
            <Link
              to="/evals/$datasetId"
              params={{ datasetId: String(datasetId) }}
            >
              <ArrowLeft className="size-4" />
            </Link>
          </Button>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link
              to="/evals/$datasetId"
              params={{ datasetId: String(datasetId) }}
              className="hover:underline"
            >
              {dataset?.name ?? `Dataset #${datasetId}`}
            </Link>
            <span>/</span>
            <span>Variants</span>
            <span>/</span>
            <span className="font-medium text-foreground">{variant.name}</span>
          </div>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold">{state.name || '(unnamed)'}</h1>
            <p className="text-xs text-muted-foreground">
              Variant #{variant.id} · updated{' '}
              {new Date(variant.updated_at).toLocaleString()}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <Badge
                variant="outline"
                className="text-[10px] border-amber-500 text-amber-500"
              >
                unsaved changes
              </Badge>
            )}
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-xs"
              disabled={!dirty || updateVariantMut.isPending}
              onClick={handleDiscard}
            >
              Discard
            </Button>
            <Button
              size="sm"
              className="h-8 text-xs"
              disabled={
                !dirty || updateVariantMut.isPending || hasRowErrors
              }
              onClick={handleSave}
              title={
                hasRowErrors
                  ? 'Fix JSON parse errors in variant-added fields before saving'
                  : undefined
              }
            >
              {updateVariantMut.isPending ? 'Saving...' : 'Save'}
            </Button>
            <Button
              size="sm"
              variant="default"
              className="h-8 text-xs gap-1"
              disabled={triggerRun.isPending}
              onClick={handleRunWithVariant}
            >
              <Play className="size-3" />
              {triggerRun.isPending ? 'Starting...' : 'Run with Variant'}
            </Button>
          </div>
        </div>

        {/* Save error banner */}
        {saveError && (
          <div className="rounded border border-destructive/50 bg-destructive/5 p-3 flex items-start gap-2 text-xs text-destructive">
            <AlertCircle className="size-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Validation failed</p>
              <p className="font-mono mt-1 whitespace-pre-wrap">{saveError}</p>
            </div>
          </div>
        )}

        {/* Split-pane layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ProdStepDefPanel
            datasetId={datasetId}
            prodSystem={prodPrompts?.system ?? null}
            prodUser={prodPrompts?.user ?? null}
            prodModel={prodModel ?? null}
            prodSchema={prodSchema ?? null}
            schemaLoading={prodSchemaLoading}
            isDark={isDark}
          />
          <VariantDeltaPanel
            state={state}
            patch={patch}
            updateMergedRow={updateMergedRow}
            addVariantRow={addVariantRow}
            removeVariantRow={removeVariantRow}
            resetProdRow={resetProdRow}
            setVarDefs={setVarDefs}
            backendFieldError={backendFieldError}
            typeOptions={typeOptions}
            typesLoading={typesLoading}
            isDark={isDark}
          />
        </div>
      </div>
    </ScrollArea>
  )
}
