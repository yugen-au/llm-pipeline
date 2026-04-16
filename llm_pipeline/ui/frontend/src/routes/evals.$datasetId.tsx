import { useState, useMemo, useCallback } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Plus, Trash2, Play, ArrowLeft } from 'lucide-react'
import {
  useDataset,
  useCreateCase,
  useUpdateCase,
  useDeleteCase,
  useDeleteDataset,
  useEvalRuns,
  useTriggerEvalRun,
  useInputSchema,
} from '@/api/evals'
import type { CaseItem, RunListItem, SchemaResponse } from '@/api/evals'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

export const Route = createFileRoute('/evals/$datasetId')({
  component: DatasetDetailPage,
})

// ---------------------------------------------------------------------------
// Schema helpers
// ---------------------------------------------------------------------------

interface FieldDef {
  name: string
  type: string
  title?: string
}

function extractFields(schema: SchemaResponse | undefined): FieldDef[] | null {
  if (!schema) return null
  const jsonSchema = schema.json_schema as Record<string, unknown> | undefined
  if (!jsonSchema) return null
  const props = jsonSchema.properties as
    | Record<string, { type?: string; title?: string }>
    | undefined
  if (!props || Object.keys(props).length === 0) return null
  return Object.entries(props).map(([name, p]) => ({
    name,
    type: typeof p.type === 'string' ? p.type : 'string',
    title: p.title,
  }))
}

// ---------------------------------------------------------------------------
// Per-field input renderer
// ---------------------------------------------------------------------------

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: FieldDef
  value: unknown
  onChange: (v: unknown) => void
}) {
  if (field.type === 'boolean') {
    return (
      <Checkbox
        checked={Boolean(value)}
        onCheckedChange={(checked) => onChange(Boolean(checked))}
      />
    )
  }

  if (field.type === 'number' || field.type === 'integer') {
    return (
      <Input
        type="number"
        className="h-8 text-xs font-mono"
        value={value != null ? String(value) : ''}
        onChange={(e) => {
          const v = e.target.value
          onChange(
            v === ''
              ? null
              : field.type === 'integer'
                ? parseInt(v, 10)
                : parseFloat(v),
          )
        }}
      />
    )
  }

  if (field.type === 'object' || field.type === 'array') {
    const str =
      value != null
        ? typeof value === 'string'
          ? value
          : JSON.stringify(value, null, 2)
        : ''
    return (
      <Textarea
        className="min-h-[60px] text-xs font-mono"
        value={str}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value))
          } catch {
            // keep raw until valid JSON
          }
        }}
      />
    )
  }

  // default: string
  return (
    <Input
      className="h-8 text-xs"
      value={value != null ? String(value) : ''}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

// ---------------------------------------------------------------------------
// JSON fallback input
// ---------------------------------------------------------------------------

function JsonInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: Record<string, unknown> | null
  onChange: (v: Record<string, unknown>) => void
}) {
  const [raw, setRaw] = useState(() =>
    value ? JSON.stringify(value, null, 2) : '{}',
  )
  const [valid, setValid] = useState(true)

  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Textarea
        className={`min-h-[60px] text-xs font-mono ${!valid ? 'border-red-500' : ''}`}
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value)
          try {
            const parsed = JSON.parse(e.target.value)
            setValid(true)
            onChange(parsed)
          } catch {
            setValid(false)
          }
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Case editor hook
// ---------------------------------------------------------------------------

interface CaseRowState {
  name: string
  inputs: Record<string, unknown>
  expected_output: Record<string, unknown> | null
  dirty: boolean
  isNew: boolean
}

function useCaseEditor(cases: CaseItem[]) {
  const [rows, setRows] = useState<Map<number | string, CaseRowState>>(
    new Map(),
  )
  const [nextTempId, setNextTempId] = useState(-1)

  // sync from server
  useMemo(() => {
    const map = new Map<number | string, CaseRowState>()
    for (const c of cases) {
      map.set(c.id, {
        name: c.name,
        inputs: c.inputs ?? {},
        expected_output: c.expected_output,
        dirty: false,
        isNew: false,
      })
    }
    // preserve unsaved rows
    for (const [key, val] of rows) {
      if (val.isNew) map.set(key, val)
    }
    setRows(map)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cases])

  const addRow = useCallback(() => {
    const tempId = nextTempId
    setNextTempId((prev) => prev - 1)
    setRows((prev) => {
      const next = new Map(prev)
      next.set(tempId, {
        name: `case_${prev.size + 1}`,
        inputs: {},
        expected_output: null,
        dirty: true,
        isNew: true,
      })
      return next
    })
    return tempId
  }, [nextTempId])

  const updateRow = useCallback(
    (id: number | string, patch: Partial<CaseRowState>) => {
      setRows((prev) => {
        const next = new Map(prev)
        const existing = next.get(id)
        if (existing) next.set(id, { ...existing, ...patch, dirty: true })
        return next
      })
    },
    [],
  )

  const removeRow = useCallback((id: number | string) => {
    setRows((prev) => {
      const next = new Map(prev)
      next.delete(id)
      return next
    })
  }, [])

  return { rows, addRow, updateRow, removeRow }
}

// ---------------------------------------------------------------------------
// Cases tab
// ---------------------------------------------------------------------------

function CasesTab({
  datasetId,
  cases,
  targetType,
  targetName,
}: {
  datasetId: number
  cases: CaseItem[]
  targetType: string
  targetName: string
}) {
  const { data: schema, isLoading: schemaLoading } = useInputSchema(
    targetType,
    targetName,
  )
  const fields = extractFields(schema)
  const createCaseMut = useCreateCase(datasetId)
  const updateCaseMut = useUpdateCase(datasetId)
  const deleteCaseMut = useDeleteCase(datasetId)
  const { rows, addRow, updateRow, removeRow } = useCaseEditor(cases)

  function handleSave(id: number | string) {
    const row = rows.get(id)
    if (!row) return
    if (row.isNew) {
      createCaseMut.mutate(
        {
          name: row.name,
          inputs: row.inputs,
          expected_output: row.expected_output ?? undefined,
        },
        { onSuccess: () => removeRow(id) },
      )
    } else {
      updateCaseMut.mutate({
        caseId: id as number,
        name: row.name,
        inputs: row.inputs,
        expected_output: row.expected_output,
      })
    }
  }

  function handleDelete(id: number | string, isNew: boolean) {
    if (isNew) {
      removeRow(id)
    } else {
      deleteCaseMut.mutate(id as number)
    }
  }

  if (schemaLoading) {
    return (
      <p className="p-4 text-sm text-muted-foreground">Loading schema...</p>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {fields
            ? `${fields.length} input fields from schema`
            : 'Raw JSON mode (schema unavailable)'}
        </p>
        <Button
          size="sm"
          variant="outline"
          className="gap-1 h-7 text-xs"
          onClick={addRow}
        >
          <Plus className="size-3" /> Add Case
        </Button>
      </div>

      <ScrollArea className="max-h-[60vh]">
        {fields ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs w-32">Name</TableHead>
                {fields.map((f) => (
                  <TableHead key={f.name} className="text-xs">
                    {f.title ?? f.name}
                  </TableHead>
                ))}
                <TableHead className="text-xs">Expected Output</TableHead>
                <TableHead className="text-xs w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {Array.from(rows.entries()).map(([id, row]) => (
                <TableRow key={id}>
                  <TableCell>
                    <Input
                      className="h-8 text-xs"
                      value={row.name}
                      onChange={(e) =>
                        updateRow(id, { name: e.target.value })
                      }
                    />
                  </TableCell>
                  {fields.map((f) => (
                    <TableCell key={f.name}>
                      <FieldInput
                        field={f}
                        value={row.inputs[f.name]}
                        onChange={(v) =>
                          updateRow(id, {
                            inputs: { ...row.inputs, [f.name]: v },
                          })
                        }
                      />
                    </TableCell>
                  ))}
                  <TableCell>
                    <Textarea
                      className="min-h-[40px] text-xs font-mono"
                      value={
                        row.expected_output
                          ? JSON.stringify(row.expected_output, null, 2)
                          : ''
                      }
                      onChange={(e) => {
                        try {
                          updateRow(id, {
                            expected_output: JSON.parse(e.target.value),
                          })
                        } catch {
                          /* ignore invalid JSON while typing */
                        }
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {row.dirty && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs"
                          disabled={
                            createCaseMut.isPending ||
                            updateCaseMut.isPending
                          }
                          onClick={() => handleSave(id)}
                        >
                          Save
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-destructive"
                        onClick={() => handleDelete(id, row.isNew)}
                      >
                        <Trash2 className="size-3" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="space-y-4">
            {Array.from(rows.entries()).map(([id, row]) => (
              <Card key={id} className="p-4">
                <div className="flex items-start gap-4">
                  <div className="flex-1 space-y-3">
                    <div className="space-y-1">
                      <Label className="text-xs">Name</Label>
                      <Input
                        className="h-8 text-xs"
                        value={row.name}
                        onChange={(e) =>
                          updateRow(id, { name: e.target.value })
                        }
                      />
                    </div>
                    <JsonInput
                      label="Inputs"
                      value={row.inputs}
                      onChange={(v) => updateRow(id, { inputs: v })}
                    />
                    <JsonInput
                      label="Expected Output"
                      value={row.expected_output}
                      onChange={(v) =>
                        updateRow(id, { expected_output: v })
                      }
                    />
                  </div>
                  <div className="flex flex-col gap-1 pt-5">
                    {row.dirty && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        disabled={
                          createCaseMut.isPending ||
                          updateCaseMut.isPending
                        }
                        onClick={() => handleSave(id)}
                      >
                        Save
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs text-destructive"
                      onClick={() => handleDelete(id, row.isNew)}
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Run History tab
// ---------------------------------------------------------------------------

function runStatusBadge(status: string) {
  const colors: Record<string, string> = {
    pending: 'border-amber-500 text-amber-500',
    running: 'border-blue-500 text-blue-500',
    completed: 'border-green-500 text-green-500',
    failed: 'border-red-500 text-red-500',
  }
  return (
    <Badge variant="outline" className={`text-xs ${colors[status] ?? ''}`}>
      {status}
    </Badge>
  )
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function RunHistoryTab({ datasetId }: { datasetId: number }) {
  const navigate = useNavigate()
  const { data: runs, isLoading } = useEvalRuns(datasetId)
  const triggerRun = useTriggerEvalRun(datasetId)

  const items: RunListItem[] = Array.isArray(runs)
    ? runs
    : ((runs as unknown) as { items?: RunListItem[] })?.items ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {items.length} run{items.length !== 1 ? 's' : ''}
        </p>
        <Button
          size="sm"
          className="gap-1 h-7 text-xs"
          disabled={triggerRun.isPending}
          onClick={() => triggerRun.mutate({})}
        >
          <Play className="size-3" />
          {triggerRun.isPending ? 'Starting...' : 'Run Evals'}
        </Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No runs yet. Click "Run Evals" to start.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs">ID</TableHead>
              <TableHead className="text-xs">Status</TableHead>
              <TableHead className="text-xs text-center">Passed</TableHead>
              <TableHead className="text-xs text-center">Failed</TableHead>
              <TableHead className="text-xs text-center">Errors</TableHead>
              <TableHead className="text-xs">Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((run) => (
              <TableRow
                key={run.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() =>
                  navigate({
                    to: `/evals/${datasetId}/runs/${run.id}` as string,
                  })
                }
              >
                <TableCell className="text-xs font-mono">#{run.id}</TableCell>
                <TableCell>{runStatusBadge(run.status)}</TableCell>
                <TableCell className="text-center text-xs text-green-600">
                  {run.passed}
                </TableCell>
                <TableCell className="text-center text-xs text-red-600">
                  {run.failed}
                </TableCell>
                <TableCell className="text-center text-xs text-amber-600">
                  {run.errored}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatDate(run.started_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

function DatasetDetailPage() {
  const { datasetId: rawId } = Route.useParams()
  const datasetId = Number(rawId)
  const navigate = useNavigate()
  const { data: dataset, isLoading, error } = useDataset(datasetId)
  const deleteMutation = useDeleteDataset(datasetId)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading dataset...</p>
      </div>
    )
  }

  if (error || !dataset) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-destructive">Dataset not found</p>
      </div>
    )
  }

  function handleDelete() {
    if (!confirm('Delete this dataset and all its cases?')) return
    deleteMutation.mutate(undefined, {
      onSuccess: () => navigate({ to: '/evals' }),
    })
  }

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-5xl space-y-6 p-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={() => navigate({ to: '/evals' })}
              >
                <ArrowLeft className="size-4" />
              </Button>
              <h1 className="text-2xl font-semibold">{dataset.name}</h1>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-xs">
                {dataset.target_type}: {dataset.target_name}
              </Badge>
              {dataset.description && (
                <span className="text-xs text-muted-foreground">
                  {dataset.description}
                </span>
              )}
            </div>
          </div>
          <Button
            variant="destructive"
            size="sm"
            className="h-7 text-xs"
            disabled={deleteMutation.isPending}
            onClick={handleDelete}
          >
            Delete
          </Button>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="cases">
          <TabsList>
            <TabsTrigger value="cases">
              Cases ({dataset.cases?.length ?? 0})
            </TabsTrigger>
            <TabsTrigger value="runs">Run History</TabsTrigger>
          </TabsList>

          <TabsContent value="cases" className="mt-4">
            <CasesTab
              datasetId={datasetId}
              cases={dataset.cases ?? []}
              targetType={dataset.target_type}
              targetName={dataset.target_name}
            />
          </TabsContent>

          <TabsContent value="runs" className="mt-4">
            <RunHistoryTab datasetId={datasetId} />
          </TabsContent>
        </Tabs>
      </div>
    </ScrollArea>
  )
}
