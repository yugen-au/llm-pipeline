import { useMemo, useState, useCallback, useEffect } from 'react'
import { createFileRoute, useNavigate, Link } from '@tanstack/react-router'
import { ArrowLeft, Plus, Trash2, Play, Info, AlertCircle } from 'lucide-react'
import {
  useDataset,
  useInputSchema,
  useVariant,
  useUpdateVariant,
  useTriggerEvalRun,
} from '@/api/evals'
import type {
  InstructionDeltaItem,
  InstructionDeltaOp,
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

/** Must match backend whitelist in llm_pipeline/evals/delta.py. */
const TYPE_WHITELIST: ReadonlyArray<string> = [
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
  }
}

function editorStateToDelta(s: EditorState): VariantDelta {
  return {
    model: s.model.trim() === '' ? null : s.model.trim(),
    system_prompt: s.systemPrompt === '' ? null : s.systemPrompt,
    user_prompt: s.userPrompt === '' ? null : s.userPrompt,
    instructions_delta:
      s.instructionsDelta.length === 0 ? null : s.instructionsDelta,
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
}: {
  idx: number
  row: InstructionDeltaItem
  onChange: (patch: Partial<InstructionDeltaItem>) => void
  onRemove: () => void
  error?: string
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
          onValueChange={(v) => onChange({ type_str: v })}
        >
          <SelectTrigger size="sm" className="h-8 text-xs font-mono">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TYPE_WHITELIST.map((t) => (
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
  fieldError,
}: {
  state: EditorState
  patch: (p: Partial<EditorState>) => void
  addDeltaRow: () => void
  updateDeltaRow: (idx: number, p: Partial<InstructionDeltaItem>) => void
  removeDeltaRow: (idx: number) => void
  fieldError: { rowIdx: number | null; message: string } | null
}) {
  const nearCap = state.instructionsDelta.length >= MAX_DELTA_ENTRIES - 5
  const atCap = state.instructionsDelta.length >= MAX_DELTA_ENTRIES

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
                />
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

  const {
    state,
    dirty,
    patch,
    addDeltaRow,
    updateDeltaRow,
    removeDeltaRow,
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
    // (e.g. "field name '__class__' is invalid"). Map to row index when we
    // can; otherwise leave as a banner-only error.
    for (let i = 0; i < delta.length; i++) {
      const f = delta[i].field
      if (f && msg.includes(`'${f}'`)) return { rowIdx: i, message: msg }
    }
    return { rowIdx: null, message: msg }
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
            fieldError={fieldError}
          />
        </div>
      </div>
    </ScrollArea>
  )
}
