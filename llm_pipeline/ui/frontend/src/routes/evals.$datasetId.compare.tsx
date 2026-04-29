import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, ArrowRight, GitCompare } from 'lucide-react'
import {
  flattenExamples,
  flattenExperiments,
  flattenRuns,
  useDataset,
  useExperiment,
  useExperiments,
} from '@/api/evals'
import type {
  PhoenixExample,
  PhoenixExperiment,
  PhoenixRun,
  Variant,
} from '@/api/evals'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { JsonViewer } from '@/components/JsonViewer'

type Search = { baseRunId?: string; compareRunId?: string }

export const Route = createFileRoute('/evals/$datasetId/compare')({
  component: ComparePage,
  validateSearch: (input: Record<string, unknown>): Search => ({
    baseRunId: typeof input.baseRunId === 'string' ? input.baseRunId : undefined,
    compareRunId:
      typeof input.compareRunId === 'string' ? input.compareRunId : undefined,
  }),
})

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function ComparePage() {
  const { datasetId } = Route.useParams()
  const { baseRunId, compareRunId } = Route.useSearch()
  const navigate = useNavigate()

  const datasetQuery = useDataset(datasetId)
  const experimentsQuery = useExperiments(datasetId)
  const baseExperimentQuery = useExperiment(datasetId, baseRunId ?? '', {})
  const compareExperimentQuery = useExperiment(
    datasetId, compareRunId ?? '', {},
  )

  const examples = flattenExamples(datasetQuery.data?.examples)
  const examplesById = new Map<string, PhoenixExample>()
  for (const ex of examples) examplesById.set(ex.id, ex)

  const allExperiments = flattenExperiments(experimentsQuery.data)

  function setRun(side: 'base' | 'compare', id: string | undefined) {
    navigate({
      to: '/evals/$datasetId/compare',
      params: { datasetId },
      search: {
        baseRunId: side === 'base' ? id : baseRunId,
        compareRunId: side === 'compare' ? id : compareRunId,
      },
    })
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1"
            onClick={() => navigate({ to: '/evals/$datasetId', params: { datasetId } })}
          >
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <div>
            <h1 className="text-xl font-semibold">Compare experiments</h1>
            <p className="text-xs text-muted-foreground">
              Side-by-side variant + per-case diff
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <ExperimentPicker
          label="Base"
          value={baseRunId}
          experiments={allExperiments}
          onChange={(id) => setRun('base', id)}
        />
        <ExperimentPicker
          label="Compare"
          value={compareRunId}
          experiments={allExperiments}
          onChange={(id) => setRun('compare', id)}
        />
      </div>

      {!baseRunId || !compareRunId ? (
        <Card className="flex flex-1 items-center justify-center py-16">
          <CardContent className="flex flex-col items-center gap-3">
            <GitCompare className="size-10 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">
              Pick a base + compare experiment to see the diff.
            </p>
          </CardContent>
        </Card>
      ) : baseExperimentQuery.isLoading || compareExperimentQuery.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading experiments...</p>
      ) : !baseExperimentQuery.data || !compareExperimentQuery.data ? (
        <p className="text-sm text-destructive">
          One of the experiments could not be loaded.
        </p>
      ) : (
        <CompareBody
          base={baseExperimentQuery.data.experiment}
          baseRuns={flattenRuns(baseExperimentQuery.data.runs)}
          compare={compareExperimentQuery.data.experiment}
          compareRuns={flattenRuns(compareExperimentQuery.data.runs)}
          examplesById={examplesById}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Experiment picker
// ---------------------------------------------------------------------------

function ExperimentPicker({
  label, value, experiments, onChange,
}: {
  label: string
  value: string | undefined
  experiments: PhoenixExperiment[]
  onChange: (id: string | undefined) => void
}) {
  return (
    <Card>
      <CardHeader className="py-3">
        <CardTitle className="text-sm">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <Select
          value={value ?? ''}
          onValueChange={(v) => onChange(v || undefined)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Pick experiment" />
          </SelectTrigger>
          <SelectContent>
            {experiments.map((exp) => (
              <SelectItem key={exp.id} value={exp.id}>
                {exp.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Compare body
// ---------------------------------------------------------------------------

function CompareBody({
  base, baseRuns, compare, compareRuns, examplesById,
}: {
  base: PhoenixExperiment
  baseRuns: PhoenixRun[]
  compare: PhoenixExperiment
  compareRuns: PhoenixRun[]
  examplesById: Map<string, PhoenixExample>
}) {
  const baseVariant = base.metadata?.variant ?? null
  const compareVariant = compare.metadata?.variant ?? null

  const baseRunsById = new Map<string, PhoenixRun>()
  for (const r of baseRuns) baseRunsById.set(r.dataset_example_id, r)
  const compareRunsById = new Map<string, PhoenixRun>()
  for (const r of compareRuns) compareRunsById.set(r.dataset_example_id, r)

  const allExampleIds = Array.from(new Set<string>([
    ...baseRunsById.keys(),
    ...compareRunsById.keys(),
  ]))

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto">
      <VariantDiffPanel base={baseVariant} compare={compareVariant} />
      <CaseDiffTable
        baseRunsById={baseRunsById}
        compareRunsById={compareRunsById}
        examplesById={examplesById}
        allExampleIds={allExampleIds}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Variant diff
// ---------------------------------------------------------------------------

function VariantDiffPanel({
  base, compare,
}: { base: Variant | null | undefined; compare: Variant | null | undefined }) {
  const baseModel = base?.model ?? null
  const compareModel = compare?.model ?? null
  const modelChanged = baseModel !== compareModel

  const basePrompts = base?.prompt_overrides ?? {}
  const comparePrompts = compare?.prompt_overrides ?? {}
  const promptKeys = Array.from(
    new Set([...Object.keys(basePrompts), ...Object.keys(comparePrompts)]),
  )

  const baseDelta = base?.instructions_delta ?? []
  const compareDelta = compare?.instructions_delta ?? []
  const deltaChanged = JSON.stringify(baseDelta) !== JSON.stringify(compareDelta)

  return (
    <Card>
      <CardHeader className="py-3">
        <CardTitle className="text-base">Variant diff</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <DiffField label="Model" changed={modelChanged}>
            <span className="font-mono text-xs">
              {baseModel ?? '— production —'}
            </span>
          </DiffField>
          <DiffField label="Model" changed={modelChanged}>
            <span className="font-mono text-xs">
              {compareModel ?? '— production —'}
            </span>
          </DiffField>
        </div>

        {promptKeys.length > 0 && (
          <div className="space-y-2">
            <Label className="text-xs">Prompt overrides</Label>
            {promptKeys.map((step) => {
              const a = basePrompts[step] ?? null
              const b = comparePrompts[step] ?? null
              const changed = a !== b
              return (
                <div key={step} className="grid grid-cols-2 gap-2">
                  <DiffField label={step} changed={changed}>
                    <pre className="font-mono text-[11px] whitespace-pre-wrap">
                      {a ?? '— production —'}
                    </pre>
                  </DiffField>
                  <DiffField label={step} changed={changed}>
                    <pre className="font-mono text-[11px] whitespace-pre-wrap">
                      {b ?? '— production —'}
                    </pre>
                  </DiffField>
                </div>
              )
            })}
          </div>
        )}

        {(baseDelta.length > 0 || compareDelta.length > 0) && (
          <div className="grid grid-cols-2 gap-4">
            <DiffField label="Instructions delta" changed={deltaChanged}>
              {baseDelta.length === 0 ? (
                <span className="text-xs text-muted-foreground">— production —</span>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {baseDelta.map((d, i) => (
                    <Badge key={i} variant="secondary" className="text-[10px]">
                      {d.op} {d.field}{d.type_str ? `: ${d.type_str}` : ''}
                    </Badge>
                  ))}
                </div>
              )}
            </DiffField>
            <DiffField label="Instructions delta" changed={deltaChanged}>
              {compareDelta.length === 0 ? (
                <span className="text-xs text-muted-foreground">— production —</span>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {compareDelta.map((d, i) => (
                    <Badge key={i} variant="secondary" className="text-[10px]">
                      {d.op} {d.field}{d.type_str ? `: ${d.type_str}` : ''}
                    </Badge>
                  ))}
                </div>
              )}
            </DiffField>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function DiffField({
  label, changed, children,
}: {
  label: string
  changed: boolean
  children: React.ReactNode
}) {
  return (
    <div
      className={`rounded border p-2 ${
        changed ? 'border-amber-500 bg-amber-50/40' : 'border-border'
      }`}
    >
      <Label className="text-[10px] text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Per-case diff
// ---------------------------------------------------------------------------

function CaseDiffTable({
  baseRunsById, compareRunsById, examplesById, allExampleIds,
}: {
  baseRunsById: Map<string, PhoenixRun>
  compareRunsById: Map<string, PhoenixRun>
  examplesById: Map<string, PhoenixExample>
  allExampleIds: string[]
}) {
  return (
    <Card className="flex min-h-0 flex-col">
      <CardHeader className="py-3">
        <CardTitle className="text-base">Cases ({allExampleIds.length})</CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Example</TableHead>
                <TableHead className="text-xs">Base output</TableHead>
                <TableHead className="text-xs w-6 text-center"></TableHead>
                <TableHead className="text-xs">Compare output</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {allExampleIds.map((id) => {
                const a = baseRunsById.get(id)
                const b = compareRunsById.get(id)
                const example = examplesById.get(id)
                return <CaseDiffRow key={id} example={example} a={a} b={b} />
              })}
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

function CaseDiffRow({
  example, a, b,
}: { example: PhoenixExample | undefined; a: PhoenixRun | undefined; b: PhoenixRun | undefined }) {
  const changed = JSON.stringify(a?.output ?? null) !== JSON.stringify(b?.output ?? null)
  return (
    <TableRow className="align-top">
      <TableCell className="max-w-xs">
        {example ? (
          <JsonViewer data={example.input} />
        ) : (
          <span className="text-xs font-mono text-muted-foreground">
            (no example metadata)
          </span>
        )}
      </TableCell>
      <TableCell className="max-w-xs">
        <RunCell run={a} />
      </TableCell>
      <TableCell className="text-center">
        {changed ? (
          <Badge variant="default" className="text-[10px]">diff</Badge>
        ) : (
          <ArrowRight className="size-3 text-muted-foreground inline" />
        )}
      </TableCell>
      <TableCell className="max-w-xs">
        <RunCell run={b} />
      </TableCell>
    </TableRow>
  )
}

function RunCell({ run }: { run: PhoenixRun | undefined }) {
  if (!run) {
    return <span className="text-xs text-muted-foreground">— missing —</span>
  }
  if (run.error) {
    return <span className="text-xs text-destructive">{run.error}</span>
  }
  return <JsonViewer data={run.output} />
}
