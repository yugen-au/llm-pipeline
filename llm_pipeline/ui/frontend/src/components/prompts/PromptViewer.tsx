import { useEffect, useMemo, useState } from 'react'
import Editor from '@monaco-editor/react'
import { Save, Undo2, Trash2 } from 'lucide-react'
import { usePromptDetail, useCreatePrompt, useUpdatePrompt, useDeletePrompt, usePromptVariableSchema } from '@/api/prompts'
import type { PromptCreateRequest, PromptUpdateRequest } from '@/api/prompts'
import type { PromptVariant } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PromptViewerProps {
  promptKey: string | null
  isCreating?: boolean
  onCreated?: (promptKey: string) => void
}

interface VariantFormState {
  prompt_name: string
  description: string
  category: string
  step_name: string
  content: string
  is_active: boolean
}

function emptyForm(): VariantFormState {
  return { prompt_name: '', description: '', category: '', step_name: '', content: '', is_active: true }
}

function formFromVariant(v: PromptVariant): VariantFormState {
  return {
    prompt_name: v.prompt_name,
    description: v.description ?? '',
    category: v.category ?? '',
    step_name: v.step_name ?? '',
    content: v.content,
    is_active: v.is_active,
  }
}

function formDirty(form: VariantFormState, original: VariantFormState): boolean {
  return (
    form.prompt_name !== original.prompt_name ||
    form.description !== original.description ||
    form.category !== original.category ||
    form.step_name !== original.step_name ||
    form.content !== original.content ||
    form.is_active !== original.is_active
  )
}

// ---------------------------------------------------------------------------
// Variable extraction
// ---------------------------------------------------------------------------

const VAR_RE = /\{[a-zA-Z_][a-zA-Z0-9_]*\}/g

function extractVariables(content: string): string[] {
  const matches = content.match(VAR_RE)
  return matches ? [...new Set(matches)] : []
}

// ---------------------------------------------------------------------------
// Dark mode helper
// ---------------------------------------------------------------------------

function useIsDark(): boolean {
  const [dark, setDark] = useState(() =>
    typeof document !== 'undefined' && document.documentElement.classList.contains('dark'),
  )
  useEffect(() => {
    const obs = new MutationObserver(() => {
      setDark(document.documentElement.classList.contains('dark'))
    })
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])
  return dark
}

// ---------------------------------------------------------------------------
// Metadata grid
// ---------------------------------------------------------------------------

function MetadataGrid({
  form,
  onChange,
  version,
}: {
  form: VariantFormState
  onChange: (patch: Partial<VariantFormState>) => void
  version?: string
}) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
      <div className="space-y-1">
        <Label className="text-xs">Prompt Name</Label>
        <Input
          value={form.prompt_name}
          onChange={(e) => onChange({ prompt_name: e.target.value })}
          placeholder="prompt_name"
          className="h-8 text-xs"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Description</Label>
        <Input
          value={form.description}
          onChange={(e) => onChange({ description: e.target.value })}
          placeholder="description"
          className="h-8 text-xs"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Category</Label>
        <Input
          value={form.category}
          onChange={(e) => onChange({ category: e.target.value })}
          placeholder="category"
          className="h-8 text-xs"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Step Name</Label>
        <Input
          value={form.step_name}
          onChange={(e) => onChange({ step_name: e.target.value })}
          placeholder="step_name"
          className="h-8 text-xs"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Version</Label>
        <Badge variant="secondary" className="mt-1">
          v{version ?? '1'}
        </Badge>
      </div>
      <div className="flex items-end gap-2 pb-0.5">
        <Checkbox
          id="is_active"
          checked={form.is_active}
          onCheckedChange={(v) => onChange({ is_active: v === true })}
        />
        <Label htmlFor="is_active" className="text-xs">
          Active
        </Label>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Variable definitions type
// ---------------------------------------------------------------------------

type VarDefs = Record<string, { type: string; description: string }>

const VAR_TYPES = ['str', 'int', 'float', 'bool', 'list'] as const

// ---------------------------------------------------------------------------
// Variable definitions editor
// ---------------------------------------------------------------------------

function VariableDefinitionsEditor({
  content,
  promptKey,
  promptType,
  value,
  onChange,
}: {
  content: string
  promptKey?: string
  promptType?: string
  value: VarDefs
  onChange: (defs: VarDefs) => void
}) {
  const vars = useMemo(() => extractVariables(content), [content])
  const { data: schema } = usePromptVariableSchema(promptKey ?? '', promptType ?? '')

  // Build merged rows: content-detected vars + schema fields
  const rows = useMemo(() => {
    const names = new Set<string>()
    // Content variables (strip braces)
    for (const v of vars) {
      names.add(v.replace(/[{}]/g, ''))
    }
    // Schema fields
    if (schema?.fields) {
      for (const f of schema.fields) {
        names.add(f.name)
      }
    }
    return [...names].sort()
  }, [vars, schema])

  // Determine source per field
  const sourceMap = useMemo(() => {
    const m: Record<string, string> = {}
    if (schema?.fields) {
      for (const f of schema.fields) {
        m[f.name] = f.source
      }
    }
    // Auto-detected vars not in schema are "auto"
    for (const v of vars) {
      const name = v.replace(/[{}]/g, '')
      if (!m[name]) m[name] = 'auto'
    }
    return m
  }, [vars, schema])

  // Initialize value from schema if empty
  useEffect(() => {
    if (rows.length === 0) return
    if (Object.keys(value).length > 0) return
    const init: VarDefs = {}
    for (const name of rows) {
      const schemaField = schema?.fields?.find((f) => f.name === name)
      init[name] = {
        type: schemaField?.type ?? 'str',
        description: schemaField?.description ?? '',
      }
    }
    onChange(init)
  }, [rows, schema]) // eslint-disable-line react-hooks/exhaustive-deps

  // Sync when content variables change: add new, remove gone
  useEffect(() => {
    const contentNames = new Set(vars.map((v) => v.replace(/[{}]/g, '')))
    if (contentNames.size === 0 && Object.keys(value).length === 0) return
    const updated = { ...value }
    let changed = false
    // Add new
    for (const name of contentNames) {
      if (!(name in updated)) {
        updated[name] = { type: 'str', description: '' }
        changed = true
      }
    }
    // Remove gone (only auto/db, not code)
    for (const name of Object.keys(updated)) {
      if (!contentNames.has(name) && sourceMap[name] !== 'code' && sourceMap[name] !== 'both') {
        delete updated[name]
        changed = true
      }
    }
    if (changed) onChange(updated)
  }, [vars]) // eslint-disable-line react-hooks/exhaustive-deps

  if (rows.length === 0) return null

  function updateField(name: string, patch: Partial<{ type: string; description: string }>) {
    const current = value[name] ?? { type: 'str', description: '' }
    onChange({ ...value, [name]: { ...current, ...patch } })
  }

  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">
        Variables{schema?.code_class_name ? ` (${schema.code_class_name})` : ''}
      </span>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="h-8 text-xs">Name</TableHead>
            <TableHead className="h-8 text-xs w-28">Type</TableHead>
            <TableHead className="h-8 text-xs">Description</TableHead>
            <TableHead className="h-8 text-xs w-16">Source</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((name) => {
            const def = value[name] ?? { type: 'str', description: '' }
            const source = sourceMap[name] ?? 'auto'
            return (
              <TableRow key={name}>
                <TableCell className="py-1 font-mono text-xs">{name}</TableCell>
                <TableCell className="py-1 text-xs">
                  <Select value={def.type} onValueChange={(v) => updateField(name, { type: v })}>
                    <SelectTrigger className="h-7 w-24 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VAR_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>{t}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell className="py-1 text-xs">
                  <Input
                    value={def.description}
                    onChange={(e) => updateField(name, { description: e.target.value })}
                    placeholder="description"
                    className="h-7 text-xs"
                  />
                </TableCell>
                <TableCell className="py-1 text-xs">
                  <Badge
                    variant={source === 'code' || source === 'both' ? 'default' : 'secondary'}
                    className="text-[10px] px-1.5 py-0"
                  >
                    {source}
                  </Badge>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// VariantEditor (single tab content)
// ---------------------------------------------------------------------------

function VariantEditor({
  variant,
  promptKey,
  onDeleted,
}: {
  variant: PromptVariant
  promptKey: string
  onDeleted?: () => void
}) {
  const isDark = useIsDark()

  const original = useMemo(() => formFromVariant(variant), [variant])
  const [form, setForm] = useState<VariantFormState>(original)
  const [varDefs, setVarDefs] = useState<VarDefs>(variant.variable_definitions ?? {})

  // Reset when upstream data changes (e.g. after save)
  useEffect(() => {
    setForm(formFromVariant(variant))
    setVarDefs(variant.variable_definitions ?? {})
  }, [variant])

  const dirty = formDirty(form, original) ||
    JSON.stringify(varDefs) !== JSON.stringify(variant.variable_definitions ?? {})

  const updateMutation = useUpdatePrompt(promptKey, variant.prompt_type)
  const deleteMutation = useDeletePrompt(promptKey, variant.prompt_type)

  function patch(p: Partial<VariantFormState>) {
    setForm((prev) => ({ ...prev, ...p }))
  }

  function handleSave() {
    const body: PromptUpdateRequest = {
      prompt_name: form.prompt_name || null,
      content: form.content || null,
      category: form.category || null,
      step_name: form.step_name || null,
      description: form.description || null,
      variable_definitions: Object.keys(varDefs).length > 0 ? varDefs : null,
    }
    updateMutation.mutate(body)
  }

  function handleDiscard() {
    setForm(original)
    setVarDefs(variant.variable_definitions ?? {})
  }

  function handleDelete() {
    if (!window.confirm(`Deactivate "${promptKey}" (${variant.prompt_type})?`)) return
    deleteMutation.mutate(undefined, { onSuccess: () => onDeleted?.() })
  }

  return (
    <div className="flex flex-col gap-3">
      <MetadataGrid form={form} onChange={patch} version={variant.version} />

      <div className="min-h-[300px] overflow-hidden rounded-md border">
        <Editor
          height="300px"
          language="markdown"
          theme={isDark ? 'vs-dark' : 'light'}
          value={form.content}
          onChange={(v) => patch({ content: v ?? '' })}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'on',
            wordWrap: 'on',
            fontSize: 13,
            scrollBeyondLastLine: false,
          }}
        />
      </div>

      <VariableDefinitionsEditor
        content={form.content}
        promptKey={promptKey}
        promptType={variant.prompt_type}
        value={varDefs}
        onChange={setVarDefs}
      />

      <div className="flex items-center gap-2 border-t pt-3">
        <Button size="sm" disabled={!dirty || updateMutation.isPending} onClick={handleSave}>
          <Save className="size-3.5" />
          Save
        </Button>
        <Button size="sm" variant="ghost" disabled={!dirty} onClick={handleDiscard}>
          <Undo2 className="size-3.5" />
          Discard
        </Button>
        <div className="flex-1" />
        <Button
          size="sm"
          variant="destructive"
          disabled={deleteMutation.isPending}
          onClick={handleDelete}
        >
          <Trash2 className="size-3.5" />
          Delete
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CreateForm
// ---------------------------------------------------------------------------

function CreateForm({ onCreated }: { onCreated?: (key: string) => void }) {
  const isDark = useIsDark()
  const [promptKey, setPromptKey] = useState('')
  const [promptType, setPromptType] = useState('system')
  const [form, setForm] = useState<VariantFormState>(emptyForm())
  const [varDefs, setVarDefs] = useState<VarDefs>({})

  const createMutation = useCreatePrompt()

  function patch(p: Partial<VariantFormState>) {
    setForm((prev) => ({ ...prev, ...p }))
  }

  function handleSave() {
    if (!promptKey.trim() || !promptType) return
    const body: PromptCreateRequest = {
      prompt_key: promptKey.trim(),
      prompt_name: form.prompt_name || promptKey.trim(),
      prompt_type: promptType,
      content: form.content,
      category: form.category || undefined,
      step_name: form.step_name || undefined,
      description: form.description || undefined,
      variable_definitions: Object.keys(varDefs).length > 0 ? varDefs : undefined,
    }
    createMutation.mutate(body, {
      onSuccess: () => onCreated?.(promptKey.trim()),
    })
  }

  const canSave = promptKey.trim().length > 0 && form.content.length > 0

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">
        <h2 className="text-lg font-semibold">New Prompt</h2>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">
              Prompt Key <span className="text-destructive">*</span>
            </Label>
            <Input
              value={promptKey}
              onChange={(e) => setPromptKey(e.target.value)}
              placeholder="e.g. rate_card_system"
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">
              Prompt Type <span className="text-destructive">*</span>
            </Label>
            <Select value={promptType} onValueChange={setPromptType}>
              <SelectTrigger className="h-8 w-full text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system">system</SelectItem>
                <SelectItem value="user">user</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <MetadataGrid form={form} onChange={patch} />

        <div className="min-h-[300px] overflow-hidden rounded-md border">
          <Editor
            height="300px"
            language="markdown"
            theme={isDark ? 'vs-dark' : 'light'}
            value={form.content}
            onChange={(v) => patch({ content: v ?? '' })}
            options={{
              minimap: { enabled: false },
              lineNumbers: 'on',
              wordWrap: 'on',
              fontSize: 13,
              scrollBeyondLastLine: false,
            }}
          />
        </div>

        <VariableDefinitionsEditor
          content={form.content}
          value={varDefs}
          onChange={setVarDefs}
        />

        <div className="flex items-center gap-2 border-t pt-3">
          <Button
            size="sm"
            disabled={!canSave || createMutation.isPending}
            onClick={handleSave}
          >
            <Save className="size-3.5" />
            Create
          </Button>
        </div>
      </div>
    </ScrollArea>
  )
}

// ---------------------------------------------------------------------------
// PromptViewer (main export)
// ---------------------------------------------------------------------------

export function PromptViewer({ promptKey, isCreating, onCreated }: PromptViewerProps) {
  const { data, isLoading, error } = usePromptDetail(promptKey ?? '')

  // Create mode
  if (isCreating) {
    return <CreateForm onCreated={onCreated} />
  }

  // Empty state
  if (!promptKey) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Select a prompt to view details</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-4 p-4">
        <div className="h-7 w-48 animate-pulse rounded bg-muted" />
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
        <div className="h-40 animate-pulse rounded bg-muted" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-destructive">Failed to load prompt</p>
      </div>
    )
  }

  if (!data) return null

  const { variants } = data

  // Single variant
  if (variants.length <= 1) {
    return (
      <ScrollArea className="h-full">
        <div className="space-y-4 p-4">
          <h2 className="text-lg font-semibold">{data.prompt_key}</h2>
          {variants[0] && (
            <VariantEditor variant={variants[0]} promptKey={data.prompt_key} />
          )}
        </div>
      </ScrollArea>
    )
  }

  // Multiple variants in tabs
  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">
        <h2 className="text-lg font-semibold">{data.prompt_key}</h2>
        <Tabs defaultValue={variants[0].prompt_type}>
          <TabsList>
            {variants.map((v) => (
              <TabsTrigger key={v.prompt_type} value={v.prompt_type}>
                {v.prompt_type}
              </TabsTrigger>
            ))}
          </TabsList>
          {variants.map((v) => (
            <TabsContent key={v.prompt_type} value={v.prompt_type}>
              <VariantEditor variant={v} promptKey={data.prompt_key} />
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </ScrollArea>
  )
}
