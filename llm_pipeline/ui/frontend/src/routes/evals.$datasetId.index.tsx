import { useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Plus, Play, Trash2, FlaskConical, BeakerIcon } from 'lucide-react'
import {
  flattenExamples,
  flattenExperiments,
  useAddExamples,
  useDataset,
  useDeleteDataset,
  useDeleteExample,
  useExperiments,
} from '@/api/evals'
import type {
  PhoenixDataset,
  PhoenixExample,
  PhoenixExperiment,
  Variant,
} from '@/api/evals'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'

export const Route = createFileRoute('/evals/$datasetId/')({
  component: DatasetDetailPage,
})

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function DatasetDetailPage() {
  const { datasetId } = Route.useParams()
  const navigate = useNavigate()
  const { data, isLoading } = useDataset(datasetId)
  const deleteMutation = useDeleteDataset(datasetId)

  if (isLoading || !data) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    )
  }

  const dataset = data.dataset
  const examples = flattenExamples(data.examples)
  const targetType = dataset.metadata?.target_type ?? '—'
  const targetName = dataset.metadata?.target_name ?? '—'

  function handleDelete() {
    if (!confirm(`Delete dataset "${dataset.name}"? This drops all examples and experiment history.`)) return
    deleteMutation.mutate(undefined, {
      onSuccess: () => navigate({ to: '/evals' }),
    })
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-card-foreground">{dataset.name}</h1>
            <Badge variant="secondary" className="text-xs">
              {targetType}: {targetName}
            </Badge>
          </div>
          {dataset.description && (
            <p className="text-sm text-muted-foreground mt-1">{dataset.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="default"
            size="sm"
            className="gap-1"
            onClick={() =>
              navigate({
                to: '/evals/$datasetId/runs/new',
                params: { datasetId },
              })
            }
          >
            <Play className="size-4" />
            New variant run
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1 text-destructive hover:bg-destructive/10"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="size-4" />
            Delete
          </Button>
        </div>
      </div>

      <Tabs defaultValue="examples" className="flex min-h-0 flex-1 flex-col gap-2">
        <TabsList className="self-start">
          <TabsTrigger value="examples">
            Examples ({examples.length})
          </TabsTrigger>
          <TabsTrigger value="experiments">Experiments</TabsTrigger>
        </TabsList>
        <TabsContent value="examples" className="min-h-0 flex-1">
          <ExamplesTab datasetId={datasetId} examples={examples} dataset={dataset} />
        </TabsContent>
        <TabsContent value="experiments" className="min-h-0 flex-1">
          <ExperimentsTab datasetId={datasetId} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Examples tab
// ---------------------------------------------------------------------------

function ExamplesTab({
  datasetId, examples, dataset,
}: {
  datasetId: string
  examples: PhoenixExample[]
  dataset: PhoenixDataset
}) {
  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex-row items-center justify-between py-3">
        <CardTitle className="text-base">Examples</CardTitle>
        <AddExampleDialog datasetId={datasetId} dataset={dataset} />
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
        {examples.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-12">
            <FlaskConical className="size-10 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">No examples yet</p>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">ID</TableHead>
                  <TableHead className="text-xs">Input</TableHead>
                  <TableHead className="text-xs">Expected output</TableHead>
                  <TableHead className="text-xs w-12"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {examples.map((ex) => (
                  <ExampleRow key={ex.id} datasetId={datasetId} example={ex} />
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}

function ExampleRow({
  datasetId, example,
}: { datasetId: string; example: PhoenixExample }) {
  const deleteMutation = useDeleteExample(datasetId)
  return (
    <TableRow>
      <TableCell className="font-mono text-xs">{example.id}</TableCell>
      <TableCell className="font-mono text-xs">
        <pre className="max-w-[20rem] truncate">
          {JSON.stringify(example.input)}
        </pre>
      </TableCell>
      <TableCell className="font-mono text-xs">
        <pre className="max-w-[20rem] truncate">
          {example.output ? JSON.stringify(example.output) : '—'}
        </pre>
      </TableCell>
      <TableCell>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 text-destructive hover:bg-destructive/10"
          onClick={() => {
            if (!confirm('Delete this example?')) return
            deleteMutation.mutate(example.id)
          }}
          disabled={deleteMutation.isPending}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </TableCell>
    </TableRow>
  )
}

function AddExampleDialog({
  datasetId, dataset: _dataset,
}: { datasetId: string; dataset: PhoenixDataset }) {
  const [open, setOpen] = useState(false)
  const [inputJson, setInputJson] = useState('{}')
  const [outputJson, setOutputJson] = useState('')
  const [metadataJson, setMetadataJson] = useState('')
  const [error, setError] = useState<string | null>(null)
  const addMutation = useAddExamples(datasetId)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const input = JSON.parse(inputJson)
      const output = outputJson.trim() ? JSON.parse(outputJson) : undefined
      const metadata = metadataJson.trim() ? JSON.parse(metadataJson) : undefined
      addMutation.mutate(
        { examples: [{ input, output, metadata }] },
        {
          onSuccess: () => {
            setOpen(false)
            setInputJson('{}')
            setOutputJson('')
            setMetadataJson('')
          },
        },
      )
    } catch (err) {
      setError(`Invalid JSON: ${(err as Error).message}`)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="gap-1">
          <Plus className="size-4" />
          Add example
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add example</DialogTitle>
            <DialogDescription>
              Examples are JSON-shaped. <code>input</code> is the case payload,{' '}
              <code>output</code> the expected output (optional),{' '}
              <code>metadata.evaluators</code> a list of registered evaluator
              names to attach.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-3">
            <div className="space-y-1">
              <Label htmlFor="ex-input">Input (JSON)</Label>
              <textarea
                id="ex-input"
                className="font-mono text-xs w-full h-24 rounded border border-input bg-background p-2"
                value={inputJson}
                onChange={(e) => setInputJson(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ex-output">Expected output (JSON, optional)</Label>
              <textarea
                id="ex-output"
                className="font-mono text-xs w-full h-24 rounded border border-input bg-background p-2"
                value={outputJson}
                onChange={(e) => setOutputJson(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ex-meta">Metadata (JSON, optional)</Label>
              <Input
                id="ex-meta"
                className="font-mono text-xs"
                value={metadataJson}
                onChange={(e) => setMetadataJson(e.target.value)}
                placeholder='{"evaluators": []}'
              />
            </div>
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
          <DialogFooter className="mt-6">
            <Button type="submit" disabled={addMutation.isPending}>
              {addMutation.isPending ? 'Adding...' : 'Add'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Experiments tab
// ---------------------------------------------------------------------------

function ExperimentsTab({ datasetId }: { datasetId: string }) {
  const navigate = useNavigate()
  const { data, isLoading } = useExperiments(datasetId)
  const experiments = flattenExperiments(data)

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="py-3">
        <CardTitle className="text-base">Experiments</CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
        {isLoading ? (
          <div className="flex h-full items-center justify-center py-12">
            <p className="text-sm text-muted-foreground">Loading...</p>
          </div>
        ) : experiments.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-12">
            <BeakerIcon className="size-10 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">No experiments yet</p>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Name</TableHead>
                  <TableHead className="text-xs">Variant</TableHead>
                  <TableHead className="text-xs">Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {experiments.map((exp) => (
                  <ExperimentRow
                    key={exp.id}
                    experiment={exp}
                    onOpen={() =>
                      navigate({
                        to: '/evals/$datasetId/runs/$runId',
                        params: { datasetId, runId: exp.id },
                      })
                    }
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

function ExperimentRow({
  experiment, onOpen,
}: { experiment: PhoenixExperiment; onOpen: () => void }) {
  const variant = experiment.metadata?.variant ?? null
  const created = experiment.created_at
    ? new Date(experiment.created_at).toLocaleString()
    : '—'
  return (
    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onOpen}>
      <TableCell className="text-sm font-medium">{experiment.name}</TableCell>
      <TableCell>
        <VariantBadges variant={variant} />
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">{created}</TableCell>
    </TableRow>
  )
}

function VariantBadges({ variant }: { variant: Variant | null | undefined }) {
  if (!variant) {
    return <Badge variant="outline" className="text-xs">baseline</Badge>
  }
  const tags: string[] = []
  if (variant.model) tags.push(`model: ${variant.model}`)
  const promptCount = Object.keys(variant.prompt_overrides ?? {}).length
  if (promptCount > 0) tags.push(`prompts: ${promptCount}`)
  const deltaCount = (variant.instructions_delta ?? []).length
  if (deltaCount > 0) tags.push(`delta: ${deltaCount}`)
  if (tags.length === 0) {
    return <Badge variant="outline" className="text-xs">baseline</Badge>
  }
  return (
    <div className="flex gap-1 flex-wrap">
      {tags.map((tag) => (
        <Badge key={tag} variant="secondary" className="text-xs">{tag}</Badge>
      ))}
    </div>
  )
}
