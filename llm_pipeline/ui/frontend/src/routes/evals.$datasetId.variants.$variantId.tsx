import { useMemo, useState, useCallback, useEffect } from 'react'
import { createFileRoute, useNavigate, Link } from '@tanstack/react-router'
import { ArrowLeft, Plus, Trash2, Play, Info, AlertCircle } from 'lucide-react'
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
  InstructionDeltaOp,
  ProdModelResponse,
  ProdPromptContent,
  ProdPromptsResponse,
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

const OP_CHOICES: ReadonlyArray<InstructionDeltaOp> = ['add', 'modify']

const MAX_DELTA_ENTRIES = 50

/** Fields inherited from LLMResultMixin — cannot be removed in v2. */
const INHERITED_FIELDS: ReadonlyArray<string> = ['confidence_score', 'notes']

// ---------------------------------------------------------------------------
// Dirty-tracking editor state
// ---------------------------------------------------------------------------

interface EditorState {
  name: string
  description: string
  model: string
  systemPrompt: string
  userPrompt: string
  instructionsDelta: InstructionDeltaItem[]
  /**
   * Variable definition overrides keyed by variable name. Stored as a Record
   * matching the shared `VarDefs` shape used by the reusable prompts
   * `VariableDefinitionsEditor`. Serialised to `VariableDefinitions` (same
   * shape) on save — backend accepts this directly.
   */
  variableDefinitions: VarDefs
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
 * Build the editor baseline from a variant + (optional) prod prompts/model.
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
 *
 * The baseline MUST capture the prefilled content — `statesEqual(state,
 * baseline)` is how dirty-tracking works, so returning a baseline without the
 * prefill would make the editor open in a perpetually-dirty state.
 */
function variantToEditorState(
  v: VariantItem,
  prod: ProdPromptsResponse | null | undefined,
  prodModel: ProdModelResponse | null | undefined,
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

  return {
    name: v.name ?? '',
    description: v.description ?? '',
    model,
    systemPrompt,
    userPrompt,
    instructionsDelta: Array.isArray(d.instructions_delta)
      ? d.instructions_delta.map((i) => ({ ...i }))
      : [],
    variableDefinitions,
  }
}

function editorStateToDelta(s: EditorState): VariantDelta {
  return {
    model: s.model.trim() === '' ? null : s.model.trim(),
    system_prompt: s.systemPrompt === '' ? null : s.systemPrompt,
    user_prompt: s.userPrompt === '' ? null : s.userPrompt,
    instructions_delta:
      s.instructionsDelta.length === 0 ? null : s.instructionsDelta,
    variable_definitions: writeVarDefs(s.variableDefinitions),
  }
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
  if (a.instructionsDelta.length !== b.instructionsDelta.length) return false
  for (let i = 0; i < a.instructionsDelta.length; i++) {
    const x = a.instructionsDelta[i]
    const y = b.instructionsDelta[i]
    if (
      x.op !== y.op ||
      x.field !== y.field ||
      x.type_str !== y.type_str ||
      JSON.stringify(x.default ?? null) !== JSON.stringify(y.default ?? null)
    )
      return false
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
  prodReady: boolean,
) {
  const [state, setState] = useState<EditorState | null>(null)
  const [baseline, setBaseline] = useState<EditorState | null>(null)

  // sync from server when variant OR prod data change (only once prod has
  // resolved — otherwise we'd build a baseline without prefill and flip the
  // editor to dirty as soon as prod arrives). `prodReady` gates both
  // prod-prompts and prod-model so the baseline captures all prefills.
  useEffect(() => {
    if (!variant) return
    if (!prodReady) return
    const snap = variantToEditorState(variant, prod ?? null, prodModel ?? null)
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

  const addDeltaRow = useCallback(() => {
    setState((prev) => {
      if (!prev) return prev
      if (prev.instructionsDelta.length >= MAX_DELTA_ENTRIES) return prev
      return {
        ...prev,
        instructionsDelta: [
          ...prev.instructionsDelta,
          { op: 'add', field: '', type_str: 'str', default: null },
        ],
      }
    })
  }, [])

  const updateDeltaRow = useCallback(
    (idx: number, patch: Partial<InstructionDeltaItem>) => {
      setState((prev) => {
        if (!prev) return prev
        const next = prev.instructionsDelta.slice()
        next[idx] = { ...next[idx], ...patch }
        return { ...prev, instructionsDelta: next }
      })
    },
    [],
  )

  const removeDeltaRow = useCallback((idx: number) => {
    setState((prev) => {
      if (!prev) return prev
      const next = prev.instructionsDelta.slice()
      next.splice(idx, 1)
      return { ...prev, instructionsDelta: next }
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
    addDeltaRow,
    updateDeltaRow,
    removeDeltaRow,
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
  isDark,
}: {
  datasetId: number
  prodSystem: ProdPromptContent | null
  prodUser: ProdPromptContent | null
  prodModel: ProdModelResponse | null
  isDark: boolean
}) {
  const { data: dataset } = useDataset(datasetId)
  const { data: schema, isLoading: schemaLoading } = useInputSchema(
    dataset?.target_type ?? '',
    dataset?.target_name ?? '',
  )

  const outputProps = useMemo(() => {
    const props = (schema?.output_schema?.properties ?? null) as
      | Record<string, { type?: string; title?: string; description?: string }>
      | null
    if (!props) return []
    return Object.entries(props).map(([name, p]) => ({
      name,
      type: p.type ?? 'unknown',
      title: p.title,
      description: p.description,
    }))
  }, [schema])

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
                    className="text-[10px] h-4 px-1 py-0"
                  >
                    {f.type}
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
// Instruction delta editor row
// ---------------------------------------------------------------------------

function DeltaRowEditor({
  idx,
  row,
  onChange,
  onRemove,
  error,
  typeOptions,
  typesDisabled,
}: {
  idx: number
  row: InstructionDeltaItem
  onChange: (patch: Partial<InstructionDeltaItem>) => void
  onRemove: () => void
  error?: string
  typeOptions: ReadonlyArray<string>
  typesDisabled?: boolean
}) {
  const defaultStr = useMemo(() => {
    if (row.default === undefined || row.default === null) return ''
    if (typeof row.default === 'string') return row.default
    try {
      return JSON.stringify(row.default)
    } catch {
      return ''
    }
  }, [row.default])

  function onDefaultChange(raw: string) {
    if (raw.trim() === '') {
      onChange({ default: null })
      return
    }
    // Parse as JSON; fall back to raw string on parse failure so user can
    // keep typing. Backend validates via json.dumps round-trip anyway.
    try {
      onChange({ default: JSON.parse(raw) })
    } catch {
      onChange({ default: raw })
    }
  }

  const isInherited = INHERITED_FIELDS.includes(row.field.trim())

  return (
    <div
      className={`grid grid-cols-[90px_1fr_120px_1fr_32px] gap-2 items-start ${
        error ? 'rounded border border-destructive/50 p-1' : ''
      }`}
    >
      <div>
        <Select
          value={row.op}
          onValueChange={(v) => onChange({ op: v as InstructionDeltaOp })}
        >
          <SelectTrigger size="sm" className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OP_CHOICES.map((op) => (
              <SelectItem key={op} value={op} className="text-xs">
                {op}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1">
        <Input
          className={`h-8 text-xs font-mono ${
            isInherited ? 'border-amber-500' : ''
          }`}
          placeholder="field_name"
          value={row.field}
          onChange={(e) =>
            onChange({ field: e.target.value.trim().toLowerCase() })
          }
        />
        {isInherited && (
          <p className="text-[10px] text-amber-600">
            Inherited field (LLMResultMixin) — can be modified but not removed.
          </p>
        )}
      </div>
      <div>
        <Select
          value={row.type_str}
          onValueChange={(v) => onChange({ type_str: v as typeof row.type_str })}
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
      </div>
      <div>
        <Input
          className="h-8 text-xs font-mono"
          placeholder='default (JSON — e.g. "text", 1, true, null, [])'
          value={defaultStr}
          onChange={(e) => onDefaultChange(e.target.value)}
        />
        {error && (
          <p className="text-[10px] text-destructive mt-1 flex items-start gap-1">
            <AlertCircle className="size-3 shrink-0 mt-0.5" />
            <span>{error}</span>
          </p>
        )}
      </div>
      <Button
        size="sm"
        variant="ghost"
        className="h-8 w-8 p-0 text-destructive"
        onClick={onRemove}
        title={`Remove row ${idx + 1}`}
      >
        <Trash2 className="size-3" />
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Editable delta panel (right pane)
// ---------------------------------------------------------------------------

function VariantDeltaPanel({
  state,
  patch,
  addDeltaRow,
  updateDeltaRow,
  removeDeltaRow,
  setVarDefs,
  fieldError,
  typeOptions,
  typesLoading,
  isDark,
}: {
  state: EditorState
  patch: (p: Partial<EditorState>) => void
  addDeltaRow: () => void
  updateDeltaRow: (idx: number, p: Partial<InstructionDeltaItem>) => void
  removeDeltaRow: (idx: number) => void
  setVarDefs: (defs: VarDefs) => void
  fieldError: { rowIdx: number | null; message: string } | null
  typeOptions: ReadonlyArray<string>
  typesLoading: boolean
  isDark: boolean
}) {
  const nearCap = state.instructionsDelta.length >= MAX_DELTA_ENTRIES - 5
  const atCap = state.instructionsDelta.length >= MAX_DELTA_ENTRIES

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

        {/* Instructions delta */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-[10px] uppercase text-muted-foreground">
              Instructions delta ({state.instructionsDelta.length}/
              {MAX_DELTA_ENTRIES})
            </Label>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs gap-1"
              onClick={addDeltaRow}
              disabled={atCap}
            >
              <Plus className="size-3" /> Add field
            </Button>
          </div>

          {/* Info banner about inherited fields */}
          <div className="rounded border border-blue-500/30 bg-blue-500/5 p-2 flex items-start gap-2 text-[11px] text-muted-foreground">
            <Info className="size-3 shrink-0 mt-0.5 text-blue-500" />
            <span>
              Inherited fields from <code>LLMResultMixin</code> (
              <code>confidence_score</code>, <code>notes</code>) cannot be
              removed in v2. You can use <code>modify</code> to change their
              defaults, but <code>remove</code> is not supported (research/CEO
              decision).
            </span>
          </div>

          {nearCap && !atCap && (
            <p className="text-[10px] text-amber-600">
              Approaching the {MAX_DELTA_ENTRIES}-entry cap.
            </p>
          )}
          {atCap && (
            <p className="text-[10px] text-destructive">
              At the {MAX_DELTA_ENTRIES}-entry cap — remove entries to add more.
            </p>
          )}

          {state.instructionsDelta.length === 0 ? (
            <p className="text-muted-foreground italic text-[11px]">
              No instruction overrides. Click "Add field" to extend or modify
              the step's output schema.
            </p>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-[90px_1fr_120px_1fr_32px] gap-2 px-1 text-[10px] uppercase text-muted-foreground">
                <span>Op</span>
                <span>Field</span>
                <span>Type</span>
                <span>Default (JSON)</span>
                <span />
              </div>
              {state.instructionsDelta.map((row, idx) => (
                <DeltaRowEditor
                  key={idx}
                  idx={idx}
                  row={row}
                  onChange={(p) => updateDeltaRow(idx, p)}
                  onRemove={() => removeDeltaRow(idx)}
                  error={
                    fieldError &&
                    fieldError.rowIdx === idx
                      ? fieldError.message
                      : undefined
                  }
                  typeOptions={typeOptions}
                  typesDisabled={typesLoading}
                />
              ))}
            </div>
          )}
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

  // "ready" = we're no longer waiting on any pending prod fetch. Either data
  // landed OR the fetch errored (404/network/etc). Both paths build a
  // baseline — the error path just builds one with `prod = null` /
  // `prodModel = null`, matching prior behavior (no prefill).
  const prodReady = !prodPromptsLoading && !prodModelLoading

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
    addDeltaRow,
    updateDeltaRow,
    removeDeltaRow,
    setVarDefs,
    resetToBaseline,
  } = useVariantEditor(variant, prodPrompts, prodModel, prodReady)

  // Backend 422 error surfacing
  const [saveError, setSaveError] = useState<string | null>(null)
  const [fieldError, setFieldError] = useState<
    { rowIdx: number | null; message: string } | null
  >(null)

  function parseBackendFieldError(
    msg: string,
    delta: InstructionDeltaItem[],
  ): { rowIdx: number | null; message: string } {
    // Backend messages commonly include the offending field name verbatim
    // quoted (e.g. "field name '__class__' is invalid"). Map to row index by
    // finding the LONGEST matching field — avoids prefix collisions where
    // e.g. rows have `foo` and `foobar` and the message mentions 'foobar'
    // (naive iteration would mis-match the shorter 'foo' row even with the
    // wrapping quotes, if candidates were sorted insertion-order).
    let bestIdx: number | null = null
    let bestLen = -1
    for (let i = 0; i < delta.length; i++) {
      const f = delta[i].field
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
    setSaveError(null)
    setFieldError(null)
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
        setFieldError(
          parseBackendFieldError(msg, state.instructionsDelta),
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
    setFieldError(null)
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
              disabled={!dirty || updateVariantMut.isPending}
              onClick={handleSave}
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
            isDark={isDark}
          />
          <VariantDeltaPanel
            state={state}
            patch={patch}
            addDeltaRow={addDeltaRow}
            updateDeltaRow={updateDeltaRow}
            removeDeltaRow={removeDeltaRow}
            setVarDefs={setVarDefs}
            fieldError={fieldError}
            typeOptions={typeOptions}
            typesLoading={typesLoading}
            isDark={isDark}
          />
        </div>
      </div>
    </ScrollArea>
  )
}
