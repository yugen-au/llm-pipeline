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
} from '@/api/evals'
import type {
  InstructionDeltaItem,
  InstructionDeltaOp,
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
import { Textarea } from '@/components/ui/textarea'

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

/** Cap on variable_definitions rows — prompt-scoped so not huge. */
const MAX_VAR_DEF_ENTRIES = 20

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
  variableDefinitions: VariableDefinitionRow[]
}

/**
 * UI row shape for the variable_definitions editor. Stored as an array of rows
 * (easy to render / dirty-track) and serialised to `VariableDefinitions`
 * (backend map shape keyed by name) on save.
 */
interface VariableDefinitionRow {
  name: string
  type: string
  auto_generate: string
}

/**
 * Convert a stored `VariableDefinitions` map (or null/undefined) into the
 * UI row list. Each `[name, spec]` entry becomes one row; extra keys on the
 * spec are dropped from the UI view but preserved via round-trip only if the
 * user does not re-save (we overwrite on save — documented trade-off). The
 * backend also accepts list-of-dicts with a `name` key, so tolerate that shape
 * here for resilience against hand-edited deltas.
 */
function varDefsToRows(
  defs: VariableDefinitions | null | undefined,
): VariableDefinitionRow[] {
  if (!defs) return []
  if (Array.isArray(defs)) {
    return (defs as Array<Record<string, unknown>>)
      .filter((d) => d && typeof d === 'object')
      .map((d) => ({
        name: typeof d.name === 'string' ? d.name : '',
        type: typeof d.type === 'string' ? d.type : '',
        auto_generate:
          typeof d.auto_generate === 'string' ? d.auto_generate : '',
      }))
  }
  return Object.entries(defs).map(([name, spec]) => ({
    name,
    type: typeof spec?.type === 'string' ? spec.type : '',
    auto_generate:
      typeof spec?.auto_generate === 'string' ? spec.auto_generate : '',
  }))
}

/**
 * Serialise UI rows to the backend map shape. Rows with empty `name` are
 * dropped. `auto_generate` is omitted when blank so we don't spuriously
 * overwrite prod defs with an empty expression string.
 */
function rowsToVarDefs(
  rows: VariableDefinitionRow[],
): VariableDefinitions | null {
  const filtered = rows.filter((r) => r.name.trim() !== '')
  if (filtered.length === 0) return null
  const out: VariableDefinitions = {}
  for (const r of filtered) {
    const entry: VariableDefinitions[string] = { type: r.type }
    if (r.auto_generate.trim() !== '') entry.auto_generate = r.auto_generate
    out[r.name.trim()] = entry
  }
  return out
}

function variantToEditorState(v: VariantItem): EditorState {
  const d: VariantDelta = (v.delta ?? {
    model: null,
    system_prompt: null,
    user_prompt: null,
    instructions_delta: null,
  }) as VariantDelta
  return {
    name: v.name ?? '',
    description: v.description ?? '',
    model: d.model ?? '',
    systemPrompt: d.system_prompt ?? '',
    userPrompt: d.user_prompt ?? '',
    instructionsDelta: Array.isArray(d.instructions_delta)
      ? d.instructions_delta.map((i) => ({ ...i }))
      : [],
    variableDefinitions: varDefsToRows(d.variable_definitions),
  }
}

function editorStateToDelta(s: EditorState): VariantDelta {
  return {
    model: s.model.trim() === '' ? null : s.model.trim(),
    system_prompt: s.systemPrompt === '' ? null : s.systemPrompt,
    user_prompt: s.userPrompt === '' ? null : s.userPrompt,
    instructions_delta:
      s.instructionsDelta.length === 0 ? null : s.instructionsDelta,
    variable_definitions: rowsToVarDefs(s.variableDefinitions),
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
  if (a.variableDefinitions.length !== b.variableDefinitions.length)
    return false
  for (let i = 0; i < a.variableDefinitions.length; i++) {
    const x = a.variableDefinitions[i]
    const y = b.variableDefinitions[i]
    if (
      x.name !== y.name ||
      x.type !== y.type ||
      x.auto_generate !== y.auto_generate
    )
      return false
  }
  return true
}

function useVariantEditor(variant: VariantItem | undefined) {
  const [state, setState] = useState<EditorState | null>(null)
  const [baseline, setBaseline] = useState<EditorState | null>(null)

  // sync from server when variant changes
  useEffect(() => {
    if (!variant) return
    const snap = variantToEditorState(variant)
    setState((prev) => (prev === null ? snap : prev))
    setBaseline(snap)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant?.id, variant?.updated_at])

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

  const addVarDefRow = useCallback(() => {
    setState((prev) => {
      if (!prev) return prev
      if (prev.variableDefinitions.length >= MAX_VAR_DEF_ENTRIES) return prev
      return {
        ...prev,
        variableDefinitions: [
          ...prev.variableDefinitions,
          { name: '', type: '', auto_generate: '' },
        ],
      }
    })
  }, [])

  const updateVarDefRow = useCallback(
    (idx: number, patch: Partial<VariableDefinitionRow>) => {
      setState((prev) => {
        if (!prev) return prev
        const next = prev.variableDefinitions.slice()
        next[idx] = { ...next[idx], ...patch }
        return { ...prev, variableDefinitions: next }
      })
    },
    [],
  )

  const removeVarDefRow = useCallback((idx: number) => {
    setState((prev) => {
      if (!prev) return prev
      const next = prev.variableDefinitions.slice()
      next.splice(idx, 1)
      return { ...prev, variableDefinitions: next }
    })
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
    addVarDefRow,
    updateVarDefRow,
    removeVarDefRow,
    resetToBaseline,
  }
}

// ---------------------------------------------------------------------------
// Prod step definition panel (read-only left pane)
// ---------------------------------------------------------------------------

function ProdStepDefPanel({
  datasetId,
}: {
  datasetId: number
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
            Model / prompts
          </Label>
          <p className="text-muted-foreground">
            Production model and prompt content are inherited at run time.
            Override them in the delta panel on the right. Leave blank to use
            the production value unchanged.
          </p>
        </div>
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
  addVarDefRow,
  updateVarDefRow,
  removeVarDefRow,
  fieldError,
  typeOptions,
  typesLoading,
}: {
  state: EditorState
  patch: (p: Partial<EditorState>) => void
  addDeltaRow: () => void
  updateDeltaRow: (idx: number, p: Partial<InstructionDeltaItem>) => void
  removeDeltaRow: (idx: number) => void
  addVarDefRow: () => void
  updateVarDefRow: (idx: number, p: Partial<VariableDefinitionRow>) => void
  removeVarDefRow: (idx: number) => void
  fieldError: { rowIdx: number | null; message: string } | null
  typeOptions: ReadonlyArray<string>
  typesLoading: boolean
}) {
  const nearCap = state.instructionsDelta.length >= MAX_DELTA_ENTRIES - 5
  const atCap = state.instructionsDelta.length >= MAX_DELTA_ENTRIES
  const varDefsAtCap = state.variableDefinitions.length >= MAX_VAR_DEF_ENTRIES

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
          <Input
            className="h-8 text-xs font-mono"
            placeholder="Leave blank to use production model"
            value={state.model}
            onChange={(e) => patch({ model: e.target.value })}
          />
        </div>

        {/* System prompt */}
        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            System prompt override
          </Label>
          <Textarea
            className="min-h-[80px] text-xs font-mono"
            placeholder="Leave blank to use production system prompt"
            value={state.systemPrompt}
            onChange={(e) => patch({ systemPrompt: e.target.value })}
          />
        </div>

        {/* User prompt */}
        <div className="space-y-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            User prompt override
          </Label>
          <Textarea
            className="min-h-[80px] text-xs font-mono"
            placeholder="Leave blank to use production user prompt"
            value={state.userPrompt}
            onChange={(e) => patch({ userPrompt: e.target.value })}
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
          <div className="flex items-center justify-between">
            <Label className="text-[10px] uppercase text-muted-foreground">
              Variable definitions ({state.variableDefinitions.length}/
              {MAX_VAR_DEF_ENTRIES})
            </Label>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs gap-1"
              onClick={addVarDefRow}
              disabled={varDefsAtCap}
            >
              <Plus className="size-3" /> Add variable
            </Button>
          </div>

          <div className="rounded border border-blue-500/30 bg-blue-500/5 p-2 flex items-start gap-2 text-[11px] text-muted-foreground">
            <Info className="size-3 shrink-0 mt-0.5 text-blue-500" />
            <span>
              Variables defined here override or add to the production prompt's
              variable_definitions. Variant wins on name collision.{' '}
              <code>auto_generate</code> expressions are resolved at prompt
              render time by the backend registry — not evaluated client-side.
            </span>
          </div>

          {varDefsAtCap && (
            <p className="text-[10px] text-destructive">
              At the {MAX_VAR_DEF_ENTRIES}-entry cap — remove entries to add
              more.
            </p>
          )}

          {state.variableDefinitions.length === 0 ? (
            <p className="text-muted-foreground italic text-[11px]">
              No variable overrides. Click "Add variable" to override or extend
              the prompt's variable_definitions.
            </p>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-[1fr_120px_1fr_32px] gap-2 px-1 text-[10px] uppercase text-muted-foreground">
                <span>Name</span>
                <span>Type</span>
                <span>auto_generate</span>
                <span />
              </div>
              {state.variableDefinitions.map((row, idx) => (
                <div
                  key={idx}
                  className="grid grid-cols-[1fr_120px_1fr_32px] gap-2 items-start"
                >
                  <Input
                    className="h-8 text-xs font-mono"
                    placeholder="variable_name"
                    value={row.name}
                    onChange={(e) =>
                      updateVarDefRow(idx, { name: e.target.value })
                    }
                  />
                  <Input
                    className="h-8 text-xs font-mono"
                    placeholder="str / int / EnumName"
                    value={row.type}
                    onChange={(e) =>
                      updateVarDefRow(idx, { type: e.target.value })
                    }
                  />
                  <Input
                    className="h-8 text-xs font-mono"
                    placeholder="optional, e.g. enum_values(Foo)"
                    value={row.auto_generate}
                    onChange={(e) =>
                      updateVarDefRow(idx, { auto_generate: e.target.value })
                    }
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0 text-destructive"
                    onClick={() => removeVarDefRow(idx)}
                    title={`Remove variable row ${idx + 1}`}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              ))}
            </div>
          )}
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

  const {
    data: variant,
    isLoading: variantLoading,
    error: variantError,
  } = useVariant(datasetId, variantId)
  const { data: dataset } = useDataset(datasetId)

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
    addVarDefRow,
    updateVarDefRow,
    removeVarDefRow,
    resetToBaseline,
  } = useVariantEditor(variant)

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

  if (variantLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading variant...</p>
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
          <ProdStepDefPanel datasetId={datasetId} />
          <VariantDeltaPanel
            state={state}
            patch={patch}
            addDeltaRow={addDeltaRow}
            updateDeltaRow={updateDeltaRow}
            removeDeltaRow={removeDeltaRow}
            addVarDefRow={addVarDefRow}
            updateVarDefRow={updateVarDefRow}
            removeVarDefRow={removeVarDefRow}
            fieldError={fieldError}
            typeOptions={typeOptions}
            typesLoading={typesLoading}
          />
        </div>
      </div>
    </ScrollArea>
  )
}
