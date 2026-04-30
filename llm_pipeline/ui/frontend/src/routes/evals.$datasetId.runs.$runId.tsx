import { useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import {
  ArrowLeft, Check, GitCompare, ShieldCheck, X,
} from 'lucide-react'
import {
  extractReportCases,
  flattenRuns,
  useAcceptExperiment,
  useDataset,
  useExperiment,
} from '@/api/evals'
import type {
  EvaluationResultShape,
  Example,
  PhoenixExperiment,
  PhoenixRun,
  ReportCase,
  Variant,
} from '@/api/evals'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { JsonViewer } from '@/components/JsonViewer'

export const Route = createFileRoute('/evals/$datasetId/runs/$runId')({
  component: ExperimentDetailPage,
})

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function ExperimentDetailPage() {
  const { datasetId, runId } = Route.useParams()
  const navigate = useNavigate()

  const datasetQuery = useDataset(datasetId)
  const examples = datasetQuery.data?.examples ?? []
  const expectedCaseCount = examples.length || undefined

  const experimentQuery = useExperiment(datasetId, runId, {
    pollWhileIncomplete: true,
    expectedCaseCount,
  })

  if (datasetQuery.isLoading || experimentQuery.isLoading || !experimentQuery.data) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    )
  }

  const experiment = experimentQuery.data.experiment
  const runs = flattenRuns(experimentQuery.data.runs)
  const variant = experiment.metadata?.variant ?? null
  const inProgress =
    expectedCaseCount != null && runs.length < expectedCaseCount

  const examplesById = new Map<string, Example>()
  for (const ex of examples) {
    if (ex.id) examplesById.set(ex.id, ex)
  }

  // Map dataset_example_id -> ReportCase. Empty map for old
  // experiments lacking metadata.full_report — rendering degrades.
  const reportCasesByExampleId = extractReportCases(experiment)

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1"
            onClick={() =>
              navigate({ to: '/evals/$datasetId', params: { datasetId } })
            }
          >
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <div>
            <h1 className="text-xl font-semibold text-card-foreground">
              {experiment.name}
            </h1>
            <p className="text-xs text-muted-foreground">
              experiment {experiment.id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1"
            onClick={() =>
              navigate({
                to: '/evals/$datasetId/runs/new',
                params: { datasetId },
                search: { from: experiment.id },
              })
            }
          >
            <GitCompare className="size-4" />
            Re-run / edit variant
          </Button>
          <AcceptExperimentDialog
            experimentId={experiment.id}
            variant={variant}
          />
        </div>
      </div>

      {inProgress && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Run in progress — {runs.length} / {expectedCaseCount} cases recorded.
          The page polls until done.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr] min-h-0 flex-1">
        <VariantPanel variant={variant} experiment={experiment} />
        <CasesPanel
          runs={runs}
          examplesById={examplesById}
          reportCasesByExampleId={reportCasesByExampleId}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Variant panel (read-only)
// ---------------------------------------------------------------------------

function VariantPanel({
  variant, experiment,
}: { variant: Variant | null | undefined; experiment: PhoenixExperiment }) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="py-3">
        <CardTitle className="text-base">Variant</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs overflow-auto">
        <div>
          <Label className="text-xs text-muted-foreground">Model</Label>
          <p className="font-mono">{variant?.model ?? '— production —'}</p>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground">Prompt overrides</Label>
          {variant?.prompt_overrides && Object.keys(variant.prompt_overrides).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(variant.prompt_overrides).map(([step, content]) => (
                <div key={step} className="rounded border border-border p-2">
                  <p className="font-mono text-[10px] text-muted-foreground">{step}</p>
                  <pre className="mt-1 whitespace-pre-wrap font-mono text-[11px]">{content}</pre>
                </div>
              ))}
            </div>
          ) : (
            <p className="font-mono text-muted-foreground">— production —</p>
          )}
        </div>
        <div>
          <Label className="text-xs text-muted-foreground">Instructions delta</Label>
          {variant?.instructions_delta && variant.instructions_delta.length > 0 ? (
            <div className="space-y-1">
              {variant.instructions_delta.map((d, i) => (
                <Badge key={i} variant="secondary" className="text-[10px] mr-1">
                  {d.op} {d.field}
                  {d.type_str ? `: ${d.type_str}` : ''}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="font-mono text-muted-foreground">— production —</p>
          )}
        </div>
        <div>
          <Label className="text-xs text-muted-foreground">Target</Label>
          <p className="font-mono text-[11px]">
            {experiment.metadata?.target_type ?? '?'}: {experiment.metadata?.target_name ?? '?'}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Cases panel (per-run results)
// ---------------------------------------------------------------------------

function CasesPanel({
  runs, examplesById, reportCasesByExampleId,
}: {
  runs: PhoenixRun[]
  examplesById: Map<string, Example>
  reportCasesByExampleId: Map<string, ReportCase>
}) {
  return (
    <Card className="flex min-h-0 flex-col">
      <CardHeader className="py-3">
        <CardTitle className="text-base">
          Cases ({runs.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
        {runs.length === 0 ? (
          <div className="flex h-full items-center justify-center py-12">
            <p className="text-sm text-muted-foreground">No runs recorded yet.</p>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Example</TableHead>
                  <TableHead className="text-xs">Output</TableHead>
                  <TableHead className="text-xs">Assertions</TableHead>
                  <TableHead className="text-xs">Scores</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <CaseRow
                    key={run.id}
                    run={run}
                    example={examplesById.get(run.dataset_example_id)}
                    reportCase={reportCasesByExampleId.get(run.dataset_example_id)}
                  />
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}

function CaseRow({
  run, example, reportCase,
}: {
  run: PhoenixRun
  example: Example | undefined
  reportCase: ReportCase | undefined
}) {
  return (
    <TableRow className="align-top">
      <TableCell className="max-w-xs">
        {example ? (
          <JsonViewer data={example.input} />
        ) : (
          <span className="text-xs text-muted-foreground font-mono">{run.dataset_example_id}</span>
        )}
      </TableCell>
      <TableCell className="max-w-xs">
        {run.error ? (
          <span className="text-xs text-destructive">{run.error}</span>
        ) : (
          <JsonViewer data={run.output as Record<string, unknown>} />
        )}
      </TableCell>
      <TableCell className="max-w-xs">
        <AssertionsCell assertions={reportCase?.assertions} />
      </TableCell>
      <TableCell className="max-w-xs">
        <ScoresCell scores={reportCase?.scores} />
      </TableCell>
      <TableCell>
        {run.error ? (
          <Badge variant="destructive" className="text-xs gap-1">
            <X className="size-3" /> error
          </Badge>
        ) : (
          <Badge variant="default" className="text-xs gap-1">
            <Check className="size-3" /> ok
          </Badge>
        )}
      </TableCell>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Per-evaluator cells (sourced from experiment.metadata.full_report)
// ---------------------------------------------------------------------------

function AssertionsCell({
  assertions,
}: { assertions: Record<string, EvaluationResultShape> | undefined }) {
  if (!assertions) return <span className="text-xs text-muted-foreground">—</span>
  const entries = Object.entries(assertions)
  if (entries.length === 0) return <span className="text-xs text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([name, result]) => {
        const passed = result?.value === true
        const reason = typeof result?.reason === 'string' ? result.reason : ''
        const tooltip = reason ? `${name}: ${reason}` : name
        return (
          <Badge
            key={name}
            variant={passed ? 'default' : 'destructive'}
            className="text-[10px] gap-1"
            title={tooltip}
          >
            {passed
              ? <Check className="size-3" />
              : <X className="size-3" />}
            {name}
          </Badge>
        )
      })}
    </div>
  )
}

function ScoresCell({
  scores,
}: { scores: Record<string, EvaluationResultShape> | undefined }) {
  if (!scores) return <span className="text-xs text-muted-foreground">—</span>
  const entries = Object.entries(scores)
  if (entries.length === 0) return <span className="text-xs text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([name, result]) => {
        const raw = result?.value
        const num = typeof raw === 'number' ? raw : Number(raw)
        const display = Number.isFinite(num) ? num.toFixed(2) : String(raw)
        const reason = typeof result?.reason === 'string' ? result.reason : ''
        const tooltip = reason ? `${name}: ${reason}` : name
        return (
          <Badge
            key={name}
            variant="secondary"
            className="text-[10px]"
            title={tooltip}
          >
            {name}: {display}
          </Badge>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Accept dialog
// ---------------------------------------------------------------------------

function AcceptExperimentDialog({
  experimentId, variant,
}: { experimentId: string; variant: Variant | null | undefined }) {
  const [open, setOpen] = useState(false)
  const [acceptedBy, setAcceptedBy] = useState('')
  const [notes, setNotes] = useState('')
  const acceptMutation = useAcceptExperiment()

  // Don't surface accept on baseline experiments — there's nothing to apply.
  const isBaseline =
    !variant
    || (variant.model == null
      && Object.keys(variant.prompt_overrides ?? {}).length === 0
      && (variant.instructions_delta ?? []).length === 0)

  const paths: string[] = []
  if (variant?.model) paths.push(`Set model to ${variant.model} via StepModelConfig`)
  const promptCount = Object.keys(variant?.prompt_overrides ?? {}).length
  if (promptCount) paths.push(`Post ${promptCount} new Phoenix prompt version(s) tagged production`)
  const deltaCount = (variant?.instructions_delta ?? []).length
  if (deltaCount) paths.push(`Apply ${deltaCount} instructions delta op(s) via AST rewrite (.bak written)`)

  function handleAccept(e: React.FormEvent) {
    e.preventDefault()
    acceptMutation.mutate(
      {
        experimentId,
        accepted_by: acceptedBy.trim() || undefined,
        notes: notes.trim() || undefined,
      },
      { onSuccess: () => setOpen(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          size="sm"
          className="gap-1"
          disabled={isBaseline}
          title={isBaseline ? 'Nothing to accept on a baseline run' : ''}
        >
          <ShieldCheck className="size-4" />
          Accept to production
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleAccept}>
          <DialogHeader>
            <DialogTitle>Accept variant to production</DialogTitle>
            <DialogDescription>
              The accept walk will fire the following. This is destructive on the
              source-file delta path — back up uncommitted work first.
            </DialogDescription>
          </DialogHeader>
          <ul className="mt-3 space-y-1 text-sm list-disc pl-5">
            {paths.map((p) => <li key={p}>{p}</li>)}
          </ul>
          <div className="mt-4 space-y-3">
            <div className="space-y-1">
              <Label htmlFor="acc-by">Accepted by (optional)</Label>
              <Input
                id="acc-by"
                value={acceptedBy}
                onChange={(e) => setAcceptedBy(e.target.value)}
                placeholder="your handle"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="acc-notes">Notes (optional)</Label>
              <Input
                id="acc-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter className="mt-6">
            <Button type="submit" disabled={acceptMutation.isPending}>
              {acceptMutation.isPending ? 'Accepting...' : 'Accept'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
