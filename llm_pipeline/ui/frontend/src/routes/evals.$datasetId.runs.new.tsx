import { useEffect, useMemo, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, Play, Plus, Trash2 } from 'lucide-react'
import {
  BASELINE_VARIANT,
  useDatasetProdModel,
  useDatasetProdPrompts,
  useDeltaTypeWhitelist,
  useExperiment,
  useTriggerRun,
} from '@/api/evals'
import type {
  DeltaTypeStr,
  InstructionDeltaItem,
  Variant,
} from '@/api/evals'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

type Search = { from?: string }

export const Route = createFileRoute('/evals/$datasetId/runs/new')({
  component: NewVariantRunPage,
  validateSearch: (input: Record<string, unknown>): Search => ({
    from: typeof input.from === 'string' ? input.from : undefined,
  }),
})

function NewVariantRunPage() {
  const { datasetId } = Route.useParams()
  const { from } = Route.useSearch()
  const navigate = useNavigate()

  const prodPromptsQuery = useDatasetProdPrompts(datasetId)
  const prodModelQuery = useDatasetProdModel(datasetId)
  const prefillQuery = useExperiment(datasetId, from ?? '', {})
  const typeWhitelistQuery = useDeltaTypeWhitelist()
  const triggerMutation = useTriggerRun(datasetId)

  const stepName = prodPromptsQuery.data?.step_name ?? null
  const prodSystemPrompt = prodPromptsQuery.data?.system ?? null
  const prodUserPrompt = prodPromptsQuery.data?.user ?? null
  const prodModel = prodModelQuery.data?.model ?? null

  const prefillVariant = useMemo<Variant | null>(() => {
    if (!from || !prefillQuery.data) return null
    return prefillQuery.data.experiment.metadata?.variant ?? null
  }, [from, prefillQuery.data])

  // Editor state
  const [model, setModel] = useState<string>('')
  const [userPrompt, setUserPrompt] = useState<string>('')
  const [delta, setDelta] = useState<InstructionDeltaItem[]>([])
  const [runName, setRunName] = useState('')

  // Once both prefill source AND prod prompts have loaded, hydrate the editor
  // exactly once. Subsequent edits to those queries don't clobber user state.
  const [hydrated, setHydrated] = useState(false)
  useEffect(() => {
    if (hydrated) return
    if (from && !prefillVariant) return
    if (prodPromptsQuery.isLoading || prodModelQuery.isLoading) return

    const seed = prefillVariant ?? BASELINE_VARIANT
    setModel(seed.model ?? '')
    if (stepName && seed.prompt_overrides[stepName]) {
      setUserPrompt(seed.prompt_overrides[stepName])
    } else {
      setUserPrompt(prodUserPrompt ?? '')
    }
    setDelta(seed.instructions_delta ?? [])
    setHydrated(true)
  }, [
    hydrated, from, prefillVariant, prodPromptsQuery.isLoading,
    prodModelQuery.isLoading, stepName, prodUserPrompt,
  ])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!stepName) return

    const promptOverrides: Record<string, string> = {}
    if (userPrompt.trim() && userPrompt !== (prodUserPrompt ?? '')) {
      promptOverrides[stepName] = userPrompt
    }

    const variant: Variant = {
      model: model.trim() && model.trim() !== (prodModel ?? '') ? model.trim() : null,
      prompt_overrides: promptOverrides,
      instructions_delta: delta,
    }

    triggerMutation.mutate(
      { variant, run_name: runName.trim() || undefined },
      {
        onSuccess: (resp) =>
          navigate({
            to: '/evals/$datasetId/runs/$runId',
            params: { datasetId, runId: resp.experiment_id },
          }),
      },
    )
  }

  if (prodPromptsQuery.isLoading || prodModelQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-sm text-muted-foreground">Loading prefill...</p>
      </div>
    )
  }

  // Pipeline-target datasets cannot edit prompts (no single step to scope to).
  const isPipelineTarget = prodPromptsQuery.data == null

  return (
    <form onSubmit={handleSubmit} className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1"
            onClick={() => navigate({ to: '/evals/$datasetId', params: { datasetId } })}
          >
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <div>
            <h1 className="text-xl font-semibold">New variant run</h1>
            <p className="text-xs text-muted-foreground">
              {from ? `Prefilled from experiment ${from}` : 'Baseline variant — no overrides'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={runName}
            onChange={(e) => setRunName(e.target.value)}
            placeholder="Run name (optional)"
            className="w-56"
          />
          <Button type="submit" className="gap-1" disabled={triggerMutation.isPending}>
            <Play className="size-4" />
            {triggerMutation.isPending ? 'Triggering...' : 'Save & run'}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-h-0 flex-1 overflow-auto">
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-base">Model</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Label htmlFor="vr-model" className="text-xs">
              Model override
            </Label>
            <Input
              id="vr-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={prodModel ? `production: ${prodModel}` : '— production —'}
            />
            <p className="text-xs text-muted-foreground">
              Leave blank to use production. {prodModel ? `Production model is ${prodModel}.` : ''}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-base">User prompt</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {isPipelineTarget ? (
              <p className="text-xs text-muted-foreground">
                Pipeline-target datasets don't support prompt overrides (variants
                are scoped to a single step). Tweak the model or instructions
                delta instead.
              </p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <Label htmlFor="vr-user" className="text-xs">
                    Override for step
                  </Label>
                  <Badge variant="secondary" className="text-xs">{stepName}</Badge>
                </div>
                <textarea
                  id="vr-user"
                  className="font-mono text-xs w-full h-48 rounded border border-input bg-background p-2"
                  value={userPrompt}
                  onChange={(e) => setUserPrompt(e.target.value)}
                />
                {prodSystemPrompt && (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted-foreground">
                      System prompt (read-only — not overridable in variants)
                    </summary>
                    <pre className="mt-2 whitespace-pre-wrap rounded bg-muted/40 p-2">
                      {prodSystemPrompt}
                    </pre>
                  </details>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="py-3 flex-row items-center justify-between">
            <CardTitle className="text-base">Instructions delta</CardTitle>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="gap-1"
              onClick={() =>
                setDelta((d) => [...d, { op: 'add', field: '', type_str: 'str', default: '' }])
              }
            >
              <Plus className="size-4" />
              Add op
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {delta.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No delta — instructions schema matches production.
              </p>
            ) : (
              delta.map((op, idx) => (
                <DeltaRow
                  key={idx}
                  op={op}
                  whitelist={typeWhitelistQuery.data?.types ?? []}
                  onChange={(next) =>
                    setDelta((d) => d.map((x, i) => (i === idx ? next : x)))
                  }
                  onRemove={() => setDelta((d) => d.filter((_, i) => i !== idx))}
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </form>
  )
}

function DeltaRow({
  op, whitelist, onChange, onRemove,
}: {
  op: InstructionDeltaItem
  whitelist: DeltaTypeStr[]
  onChange: (next: InstructionDeltaItem) => void
  onRemove: () => void
}) {
  const [defaultJson, setDefaultJson] = useState<string>(() => {
    if (op.default === undefined) return ''
    try { return JSON.stringify(op.default) } catch { return '' }
  })

  function commitDefault(raw: string) {
    setDefaultJson(raw)
    if (raw.trim() === '') {
      onChange({ ...op, default: undefined })
      return
    }
    try {
      onChange({ ...op, default: JSON.parse(raw) })
    } catch {
      // leave as-is; user can keep editing. UI surfaces the raw text.
    }
  }

  return (
    <div className="flex items-center gap-2 rounded border border-border p-2">
      <Select
        value={op.op}
        onValueChange={(v) => onChange({ ...op, op: v as InstructionDeltaItem['op'] })}
      >
        <SelectTrigger className="w-24 h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="add">add</SelectItem>
          <SelectItem value="modify">modify</SelectItem>
        </SelectContent>
      </Select>
      <Input
        value={op.field}
        onChange={(e) => onChange({ ...op, field: e.target.value })}
        placeholder="field"
        className="h-8 text-xs flex-1"
      />
      <Select
        value={op.type_str ?? 'str'}
        onValueChange={(v) => onChange({ ...op, type_str: v as DeltaTypeStr })}
      >
        <SelectTrigger className="w-36 h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {whitelist.map((t) => (
            <SelectItem key={t} value={t}>{t}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        value={defaultJson}
        onChange={(e) => commitDefault(e.target.value)}
        placeholder="default (JSON)"
        className="h-8 text-xs font-mono flex-1"
      />
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 w-7 p-0 text-destructive hover:bg-destructive/10"
        onClick={onRemove}
      >
        <Trash2 className="size-3.5" />
      </Button>
    </div>
  )
}
