import { useEffect, useMemo, useState } from 'react'
import { Save, Undo2, Trash2 } from 'lucide-react'
import {
  usePromptDetail,
  useCreatePrompt,
  useUpdatePrompt,
  useDeletePrompt,
} from '@/api/prompts'
import type { Prompt } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  PromptContentEditor,
  useIsDark,
  type VarDefs,
} from './PromptContentEditor'
import { VariableDefinitionsEditor } from './VariableDefinitionsEditor'

// ---------------------------------------------------------------------------
// Form state — one record per prompt, both messages stacked.
// ---------------------------------------------------------------------------

interface FormState {
  name: string
  description: string
  display_name: string
  category: string
  step_name: string
  system: string
  user: string
}

function emptyForm(): FormState {
  return {
    name: '',
    description: '',
    display_name: '',
    category: '',
    step_name: '',
    system: '',
    user: '',
  }
}

function formFromPrompt(p: Prompt): FormState {
  const sysMsg = p.messages.find((m) => m.role === 'system')
  const userMsg = p.messages.find((m) => m.role === 'user')
  return {
    name: p.name,
    description: p.description ?? '',
    display_name: p.metadata.display_name ?? '',
    category: p.metadata.category ?? '',
    step_name: p.metadata.step_name ?? '',
    system: sysMsg?.content ?? '',
    user: userMsg?.content ?? '',
  }
}

function formDirty(form: FormState, original: FormState): boolean {
  return (
    form.name !== original.name ||
    form.description !== original.description ||
    form.display_name !== original.display_name ||
    form.category !== original.category ||
    form.step_name !== original.step_name ||
    form.system !== original.system ||
    form.user !== original.user
  )
}

function buildPromptPayload(form: FormState, varDefs: VarDefs): Prompt {
  const messages: Prompt['messages'] = []
  if (form.system) messages.push({ role: 'system', content: form.system })
  if (form.user) messages.push({ role: 'user', content: form.user })
  return {
    name: form.name.trim(),
    description: form.description || null,
    metadata: {
      display_name: form.display_name || null,
      category: form.category || null,
      step_name: form.step_name || null,
      variable_definitions: Object.keys(varDefs).length > 0 ? varDefs : null,
    },
    messages,
    version_id: null,
  }
}

// ---------------------------------------------------------------------------
// Metadata grid
// ---------------------------------------------------------------------------

function MetadataGrid({
  form,
  onChange,
  versionId,
  nameEditable,
}: {
  form: FormState
  onChange: (patch: Partial<FormState>) => void
  versionId?: string | null
  nameEditable: boolean
}) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
      <div className="space-y-1">
        <Label className="text-xs">
          Name {nameEditable && <span className="text-destructive">*</span>}
        </Label>
        <Input
          value={form.name}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder="prompt_name"
          className="h-8 text-xs"
          disabled={!nameEditable}
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Display Name</Label>
        <Input
          value={form.display_name}
          onChange={(e) => onChange({ display_name: e.target.value })}
          placeholder="display name"
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
      {versionId && (
        <div className="space-y-1">
          <Label className="text-xs">Version</Label>
          <Badge variant="secondary" className="mt-1 font-mono text-[10px]">
            {versionId.slice(0, 12)}
          </Badge>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stacked message editors (system + user)
// ---------------------------------------------------------------------------

function MessageEditors({
  form,
  varDefs,
  setVarDefs,
  onChange,
  promptName,
  isDark,
}: {
  form: FormState
  varDefs: VarDefs
  setVarDefs: (d: VarDefs) => void
  onChange: (patch: Partial<FormState>) => void
  promptName: string
  isDark: boolean
}) {
  const combinedContent = useMemo(
    () => `${form.system}\n${form.user}`,
    [form.system, form.user],
  )
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label className="text-xs font-medium">System message</Label>
        <PromptContentEditor
          value={form.system}
          onChange={(v) => onChange({ system: v })}
          varDefs={varDefs}
          isDark={isDark}
        />
      </div>
      <div className="space-y-2">
        <Label className="text-xs font-medium">User message</Label>
        <PromptContentEditor
          value={form.user}
          onChange={(v) => onChange({ user: v })}
          varDefs={varDefs}
          isDark={isDark}
        />
      </div>
      <VariableDefinitionsEditor
        content={combinedContent}
        promptKey={promptName}
        value={varDefs}
        onChange={setVarDefs}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Edit existing prompt
// ---------------------------------------------------------------------------

function EditForm({
  prompt,
  onDeleted,
}: {
  prompt: Prompt
  onDeleted?: () => void
}) {
  const isDark = useIsDark()
  const original = useMemo(() => formFromPrompt(prompt), [prompt])
  const [form, setForm] = useState<FormState>(original)
  const initialVarDefs = (prompt.metadata.variable_definitions ?? {}) as VarDefs
  const [varDefs, setVarDefs] = useState<VarDefs>(initialVarDefs)

  useEffect(() => {
    setForm(formFromPrompt(prompt))
    setVarDefs((prompt.metadata.variable_definitions ?? {}) as VarDefs)
  }, [prompt])

  const dirty =
    formDirty(form, original) ||
    JSON.stringify(varDefs) !== JSON.stringify(initialVarDefs)

  const updateMutation = useUpdatePrompt(prompt.name)
  const deleteMutation = useDeletePrompt(prompt.name)

  function patch(p: Partial<FormState>) {
    setForm((prev) => ({ ...prev, ...p }))
  }

  function handleSave() {
    updateMutation.mutate(buildPromptPayload(form, varDefs))
  }

  function handleDiscard() {
    setForm(original)
    setVarDefs(initialVarDefs)
  }

  function handleDelete() {
    if (!window.confirm(`Delete prompt "${prompt.name}"? This removes all versions.`))
      return
    deleteMutation.mutate(undefined, { onSuccess: () => onDeleted?.() })
  }

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">
        <h2 className="text-lg font-semibold">{prompt.name}</h2>
        <MetadataGrid
          form={form}
          onChange={patch}
          versionId={prompt.version_id}
          nameEditable={false}
        />
        <MessageEditors
          form={form}
          varDefs={varDefs}
          setVarDefs={setVarDefs}
          onChange={patch}
          promptName={prompt.name}
          isDark={isDark}
        />
        <div className="flex items-center gap-2 border-t pt-3">
          <Button
            size="sm"
            disabled={!dirty || updateMutation.isPending}
            onClick={handleSave}
          >
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
    </ScrollArea>
  )
}

// ---------------------------------------------------------------------------
// Create new prompt
// ---------------------------------------------------------------------------

function CreateForm({ onCreated }: { onCreated?: (name: string) => void }) {
  const isDark = useIsDark()
  const [form, setForm] = useState<FormState>(emptyForm())
  const [varDefs, setVarDefs] = useState<VarDefs>({})
  const createMutation = useCreatePrompt()

  function patch(p: Partial<FormState>) {
    setForm((prev) => ({ ...prev, ...p }))
  }

  function handleSave() {
    const name = form.name.trim()
    if (!name) return
    if (!form.system && !form.user) return
    createMutation.mutate(buildPromptPayload(form, varDefs), {
      onSuccess: () => onCreated?.(name),
    })
  }

  const canSave =
    form.name.trim().length > 0 && (form.system.length > 0 || form.user.length > 0)

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">
        <h2 className="text-lg font-semibold">New Prompt</h2>
        <MetadataGrid form={form} onChange={patch} nameEditable={true} />
        <MessageEditors
          form={form}
          varDefs={varDefs}
          setVarDefs={setVarDefs}
          onChange={patch}
          promptName={form.name.trim()}
          isDark={isDark}
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

interface PromptViewerProps {
  promptKey: string | null
  isCreating?: boolean
  onCreated?: (promptName: string) => void
}

export function PromptViewer({ promptKey, isCreating, onCreated }: PromptViewerProps) {
  const { data, isLoading, error } = usePromptDetail(promptKey ?? '')

  if (isCreating) {
    return <CreateForm onCreated={onCreated} />
  }

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

  return <EditForm prompt={data} />
}
