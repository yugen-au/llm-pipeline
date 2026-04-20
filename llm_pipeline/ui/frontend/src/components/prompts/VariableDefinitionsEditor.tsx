import { useEffect, useMemo, useState } from 'react'
import { ChevronsUpDown, X } from 'lucide-react'
import {
  usePromptVariableSchema,
  useAutoGenerateObjects,
} from '@/api/prompts'
import type { AutoGenerateObject } from '@/api/prompts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { extractVariables, type VarDefs } from './PromptContentEditor'

// Re-export VarDefs so consumers can import either module.
export type { VarDefs } from './PromptContentEditor'

export const VAR_TYPES = ['enum', 'str', 'int', 'float', 'bool', 'list'] as const

// ---------------------------------------------------------------------------
// Auto-generate helpers
// ---------------------------------------------------------------------------

export interface AutoGenOption {
  label: string
  expression: string
  /** If true, needs a second pick (enum member) */
  needsMember?: boolean
  enumName?: string
}

export function getAutoGenOptions(
  type: string,
  objects: AutoGenerateObject[],
): AutoGenOption[] {
  if (type === 'enum') {
    return objects
      .filter((o) => o.kind === 'enum')
      .map((o) => ({ label: o.name, expression: `enum_names(${o.name})` }))
  }
  if (type === 'str') {
    const opts: AutoGenOption[] = []
    for (const o of objects) {
      if (o.kind === 'enum') {
        opts.push({ label: `All values of ${o.name}`, expression: `enum_values(${o.name})` })
        for (const m of o.members ?? []) {
          opts.push({ label: `${o.name}.${m.name}`, expression: `enum_value(${o.name}, ${m.name})` })
        }
      }
      if (o.kind === 'constant' && o.value_type === 'str') {
        opts.push({ label: `Constant: ${o.name}`, expression: `constant(${o.name})` })
      }
    }
    return opts
  }
  if (type === 'int') {
    return objects
      .filter((o) => o.kind === 'constant' && o.value_type === 'int')
      .map((o) => ({ label: `Constant: ${o.name}`, expression: `constant(${o.name})` }))
  }
  if (type === 'float') {
    return objects
      .filter((o) => o.kind === 'constant' && o.value_type === 'float')
      .map((o) => ({ label: `Constant: ${o.name}`, expression: `constant(${o.name})` }))
  }
  return []
}

export function expressionToLabel(expr: string): string {
  if (!expr) return ''
  const namesMatch = expr.match(/^enum_names\((\w+)\)$/)
  if (namesMatch) return namesMatch[1]
  const valuesMatch = expr.match(/^enum_values\((\w+)\)$/)
  if (valuesMatch) return `All values of ${valuesMatch[1]}`
  const valueMatch = expr.match(/^enum_value\((\w+),\s*(\w+)\)$/)
  if (valueMatch) return `${valueMatch[1]}.${valueMatch[2]}`
  const constMatch = expr.match(/^constant\((.+)\)$/)
  if (constMatch) return `Constant: ${constMatch[1]}`
  return expr
}

// ---------------------------------------------------------------------------
// Auto-generate selector (per variable row)
// ---------------------------------------------------------------------------

export function AutoGenerateSelector({
  type,
  value,
  objects,
  onChange,
  onClear,
}: {
  type: string
  value: string
  objects: AutoGenerateObject[]
  onChange: (expr: string) => void
  onClear: () => void
}) {
  const [open, setOpen] = useState(false)
  const options = useMemo(() => getAutoGenOptions(type, objects), [type, objects])

  if (options.length === 0) {
    return (
      <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-muted-foreground">
        N/A
      </Badge>
    )
  }

  if (value) {
    // Show current selection with clear button
    const label = expressionToLabel(value)
    return (
      <div className="flex items-center gap-1">
        <Badge
          variant="secondary"
          className="text-[10px] px-1.5 py-0 font-mono truncate max-w-[160px]"
        >
          {label}
        </Badge>
        <Button variant="ghost" size="icon" className="h-5 w-5" onClick={onClear}>
          <X className="h-3 w-3" />
        </Button>
      </div>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs gap-1 font-normal text-muted-foreground"
        >
          Select...
          <ChevronsUpDown className="h-3 w-3" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[260px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Search..." className="h-8 text-xs" />
          <CommandList className="max-h-[200px]">
            <CommandEmpty className="text-xs py-2">No options.</CommandEmpty>
            <CommandGroup>
              {options.map((opt) => (
                <CommandItem
                  key={opt.expression}
                  value={opt.label}
                  className="text-xs"
                  onSelect={() => {
                    onChange(opt.expression)
                    setOpen(false)
                  }}
                >
                  {opt.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

// ---------------------------------------------------------------------------
// Variable definitions editor
// ---------------------------------------------------------------------------

export function VariableDefinitionsEditor({
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
  const { data: autoGenData } = useAutoGenerateObjects()
  const autoGenObjects = autoGenData?.objects ?? []

  // Build merged rows: content-detected vars + schema fields
  const rows = useMemo(() => {
    const names = new Set<string>()
    for (const v of vars) {
      names.add(v.replace(/[{}]/g, ''))
    }
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
        auto_generate: schemaField?.auto_generate ?? '',
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
    for (const name of contentNames) {
      if (!(name in updated)) {
        updated[name] = { type: 'str', description: '' }
        changed = true
      }
    }
    for (const name of Object.keys(updated)) {
      if (!contentNames.has(name) && sourceMap[name] !== 'code' && sourceMap[name] !== 'both') {
        delete updated[name]
        changed = true
      }
    }
    if (changed) onChange(updated)
  }, [vars]) // eslint-disable-line react-hooks/exhaustive-deps

  if (rows.length === 0) return null

  function updateField(
    name: string,
    patch: Partial<{ type: string; description: string; auto_generate: string }>,
  ) {
    const current = value[name] ?? { type: 'str', description: '', auto_generate: '' }
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
            <TableHead className="h-8 text-xs">Auto Generate</TableHead>
            <TableHead className="h-8 text-xs w-16">Source</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((name) => {
            const def = value[name] ?? { type: 'str', description: '' }
            const source = sourceMap[name] ?? 'auto'
            const hasAutoGen = Boolean(def.auto_generate)
            return (
              <TableRow key={name}>
                <TableCell className="py-1 font-mono text-xs">{name}</TableCell>
                <TableCell className="py-1 text-xs">
                  <Select
                    value={def.type}
                    onValueChange={(v) => updateField(name, { type: v, auto_generate: '' })}
                    disabled={hasAutoGen}
                  >
                    <SelectTrigger className="h-7 w-24 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VAR_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
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
                  <AutoGenerateSelector
                    type={def.type}
                    value={def.auto_generate ?? ''}
                    objects={autoGenObjects}
                    onChange={(expr) => updateField(name, { auto_generate: expr })}
                    onClear={() => updateField(name, { auto_generate: '' })}
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
