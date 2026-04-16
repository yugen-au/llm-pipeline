import { useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Plus, FlaskConical } from 'lucide-react'
import { useDatasets, useCreateDataset } from '@/api/evals'
import type { DatasetListItem } from '@/api/evals'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'

export const Route = createFileRoute('/evals')({
  component: EvalDatasetsPage,
})

function passRateBadge(rate: number | null) {
  if (rate == null) return <Badge variant="secondary" className="text-xs">--</Badge>
  const pct = Math.round(rate * 100)
  let color = 'border-red-500 text-red-500'
  if (pct > 80) color = 'border-green-500 text-green-500'
  else if (pct > 50) color = 'border-yellow-500 text-yellow-500'
  return <Badge variant="outline" className={`text-xs ${color}`}>{pct}%</Badge>
}

function EvalDatasetsPage() {
  const navigate = useNavigate()
  const { data, isLoading } = useDatasets()
  const datasets = data?.items ?? []

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-card-foreground">Evals</h1>
          <p className="text-sm text-muted-foreground">Evaluation datasets and test cases</p>
        </div>
        <NewDatasetDialog />
      </div>

      <Card className="min-h-0 flex-1 overflow-hidden">
        {isLoading ? (
          <CardContent className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">Loading...</p>
          </CardContent>
        ) : datasets.length === 0 ? (
          <CardContent className="flex h-full flex-col items-center justify-center gap-3">
            <FlaskConical className="size-10 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">No datasets yet</p>
          </CardContent>
        ) : (
          <ScrollArea className="h-full">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Name</TableHead>
                  <TableHead className="text-xs">Target</TableHead>
                  <TableHead className="text-xs text-center">Cases</TableHead>
                  <TableHead className="text-xs text-center">Last Run</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {datasets.map((ds) => (
                  <DatasetRow
                    key={ds.id}
                    dataset={ds}
                    onOpen={() => navigate({ to: `/evals/${ds.id}` as string })}
                  />
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </Card>
    </div>
  )
}

function DatasetRow({ dataset, onOpen }: { dataset: DatasetListItem; onOpen: () => void }) {
  return (
    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onOpen}>
      <TableCell className="text-sm font-medium">{dataset.name}</TableCell>
      <TableCell>
        <Badge variant="secondary" className="text-xs">
          {dataset.target_type}: {dataset.target_name}
        </Badge>
      </TableCell>
      <TableCell className="text-center text-sm">{dataset.case_count}</TableCell>
      <TableCell className="text-center">{passRateBadge(dataset.last_run_pass_rate)}</TableCell>
    </TableRow>
  )
}

function NewDatasetDialog() {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [targetType, setTargetType] = useState<string>('step')
  const [targetName, setTargetName] = useState('')
  const createMutation = useCreateDataset()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !targetName.trim()) return
    createMutation.mutate(
      { name: name.trim(), target_type: targetType, target_name: targetName.trim() },
      {
        onSuccess: () => {
          setOpen(false)
          setName('')
          setTargetType('step')
          setTargetName('')
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-1">
          <Plus className="size-4" />
          New Dataset
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>New Evaluation Dataset</DialogTitle>
            <DialogDescription>Create a dataset to hold test cases for a step or pipeline.</DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="ds-name">Name</Label>
              <Input id="ds-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. sentiment_analysis" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ds-target-type">Target Type</Label>
              <Select value={targetType} onValueChange={setTargetType}>
                <SelectTrigger id="ds-target-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="step">Step</SelectItem>
                  <SelectItem value="pipeline">Pipeline</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ds-target-name">Target Name</Label>
              <Input id="ds-target-name" value={targetName} onChange={(e) => setTargetName(e.target.value)} placeholder="e.g. sentiment_analysis" />
            </div>
          </div>
          <DialogFooter className="mt-6">
            <Button type="submit" disabled={createMutation.isPending || !name.trim() || !targetName.trim()}>
              {createMutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
