import { useCallback, useState } from 'react'
import { ChevronRight, ChevronDown, Plus, Trash2, AlertCircle } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

/** Enum member: `{name: 'POSITIVE', value: 'positive'}`. */
export interface EnumMemberSpec {
  name: string
  value: string
}

/** Catalog of registered enums keyed by enum name. Passed down from the
 * parent component that owns the `useAutoGenerateObjects()` hook, so this
 * component remains hook-free and testable. */
export type EnumCatalog = Record<string, ReadonlyArray<EnumMemberSpec>>

// ---------------------------------------------------------------------------
// TypedValueEditor
//
// Renders a typed value using structured widgets (text/number/checkbox for
// scalars; expandable tree for list/dict). Single component; `readOnly` prop
// toggles display vs edit mode so the variant-editor right pane (editable)
// and prod panel left pane (read-only) look structurally identical.
//
// Visual language mirrors JsonViewer: same color palette (green strings, blue
// numbers, orange bools, muted null), same chevrons, same indentation.
// ---------------------------------------------------------------------------

export interface TypedValueEditorProps {
  /**
   * Type annotation label — e.g. `str`, `int`, `float`, `bool`, `list`,
   * `dict`, `Optional[str]`, `enum:<Name>`, `Optional[enum:<Name>]`.
   * Unknown / complex labels (e.g. a $ref like `TopicItem`) fall back to
   * the dict/object tree renderer so nested JSON is still editable.
   */
  type_str: string
  value: unknown
  /** Required unless `readOnly`. */
  onChange?: (value: unknown) => void
  readOnly?: boolean
  /** Inline parse / validation error shown below the widget. */
  error?: string
  /** Placeholder text for empty scalar inputs / null placeholders. */
  placeholder?: string
  className?: string
  /**
   * Registered enum catalog (enum name -> ordered member list). Required
   * for `enum:<Name>` / `Optional[enum:<Name>]` types to render the member
   * picker. When a referenced enum is missing from the catalog the widget
   * falls back to a plain string input with a muted warning — never blocks
   * editing (user might still want to pin a literal member value manually).
   */
  enumCatalog?: EnumCatalog
}

/** Max recursion depth, matching backend nested-default cap (thematic). */
const MAX_DEPTH = 20

/** Child type options for heterogeneous list/dict children. Excludes
 * Optional[X] to keep v1 simple — nested nulls can still be expressed as
 * `null` JSON literals when the user picks a concrete type. Registered
 * enum names are appended at render time as `enum:<Name>` options. */
const BASIC_CHILD_TYPE_OPTIONS: ReadonlyArray<ChildType> = [
  'str',
  'int',
  'float',
  'bool',
  'list',
  'dict',
]

type ChildType = 'str' | 'int' | 'float' | 'bool' | 'list' | 'dict' | string

/** Encode/decode `enum:<Name>` type_str for child selectors. */
function isEnumTypeStr(t: string): boolean {
  return t.startsWith('enum:')
}
function enumNameFromTypeStr(t: string): string {
  return t.slice('enum:'.length)
}

// ---------------------------------------------------------------------------
// Type parsing
// ---------------------------------------------------------------------------

interface ParsedType {
  /** Base type after Optional-unwrap. */
  base: 'str' | 'int' | 'float' | 'bool' | 'list' | 'dict' | 'object' | 'enum'
  optional: boolean
  /** Enum class name when `base === 'enum'`. */
  enumName?: string
}

function parseTypeStr(type_str: string): ParsedType {
  const t = (type_str ?? '').trim()
  // Optional[X] — unwrap.
  const m = /^Optional\[(.+)\]$/.exec(t)
  if (m) {
    const inner = parseTypeStr(m[1])
    return { base: inner.base, optional: true, enumName: inner.enumName }
  }
  // enum:<Name>
  if (t.startsWith('enum:')) {
    return { base: 'enum', optional: false, enumName: t.slice('enum:'.length) }
  }
  switch (t) {
    case 'str':
    case 'string':
      return { base: 'str', optional: false }
    case 'int':
    case 'integer':
      return { base: 'int', optional: false }
    case 'float':
    case 'number':
      return { base: 'float', optional: false }
    case 'bool':
    case 'boolean':
      return { base: 'bool', optional: false }
    case 'list':
    case 'array':
      return { base: 'list', optional: false }
    case 'dict':
    case 'object':
      return { base: 'dict', optional: false }
    default:
      // $ref like "TopicItem" or unknown shape — treat as editable object.
      return { base: 'object', optional: false }
  }
}

/** Default value for a freshly-picked child type. For `enum:<Name>` child
 * types, seeds to the first registered member value or empty string when
 * the catalog is missing / empty. */
function defaultForChildType(t: ChildType, enumCatalog?: EnumCatalog): unknown {
  if (isEnumTypeStr(t)) {
    const name = enumNameFromTypeStr(t)
    const members = enumCatalog?.[name]
    return members && members.length > 0 ? members[0].value : ''
  }
  switch (t) {
    case 'str':
      return ''
    case 'int':
      return 0
    case 'float':
      return 0
    case 'bool':
      return false
    case 'list':
      return []
    case 'dict':
      return {}
  }
  return null
}

/** Best-effort runtime type inference — used to pick the right widget when
 * rendering list items / dict values whose declared type is heterogeneous.
 * Note: enum-typed children in heterogeneous containers can't be detected
 * from value alone (string) — users must pick `enum:<Name>` explicitly. */
function inferChildType(v: unknown): ChildType {
  if (typeof v === 'string') return 'str'
  if (typeof v === 'boolean') return 'bool'
  if (typeof v === 'number') return Number.isInteger(v) ? 'int' : 'float'
  if (Array.isArray(v)) return 'list'
  if (v !== null && typeof v === 'object') return 'dict'
  // null falls back to str (caller handles the null case separately).
  return 'str'
}

/** Build the full child-type dropdown option list: base scalars/containers
 * plus each registered enum as `enum:<Name>`. */
function buildChildTypeOptions(
  enumCatalog: EnumCatalog | undefined,
): ReadonlyArray<{ value: ChildType; label: string }> {
  const out: Array<{ value: ChildType; label: string }> = BASIC_CHILD_TYPE_OPTIONS.map(
    (t) => ({ value: t, label: t }),
  )
  if (enumCatalog) {
    for (const name of Object.keys(enumCatalog).sort()) {
      out.push({ value: `enum:${name}`, label: name })
    }
  }
  return out
}

// ---------------------------------------------------------------------------
// Scalar widgets
// ---------------------------------------------------------------------------

function ReadOnlyScalar({
  base,
  value,
}: {
  base: ParsedType['base']
  value: unknown
}) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">null</span>
  }
  if (base === 'str') {
    // Empty string: render "" (quoted empty) to disambiguate from null.
    return (
      <span className="text-green-600 dark:text-green-400">
        "{String(value)}"
      </span>
    )
  }
  if (base === 'int' || base === 'float') {
    return (
      <span className="text-blue-600 dark:text-blue-400">{String(value)}</span>
    )
  }
  if (base === 'bool') {
    // Per spec: read-only bool uses a disabled Checkbox, not text.
    return <Checkbox checked={Boolean(value)} disabled />
  }
  return <span className="text-muted-foreground">{String(value)}</span>
}

/** Read-only enum display: value + enum-name badge to the right. When the
 * enum isn't in the catalog, still show the raw value with an "unregistered"
 * warning badge so the user can spot drift. */
function ReadOnlyEnum({
  enumName,
  value,
  members,
}: {
  enumName: string
  value: unknown
  members: ReadonlyArray<EnumMemberSpec> | undefined
}) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">null</span>
  }
  const raw = String(value)
  const member = members?.find((m) => m.value === raw)
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-green-600 dark:text-green-400 font-mono text-xs">
        {member ? member.name : raw}
        {member && member.name !== member.value && (
          <span className="text-muted-foreground"> ({member.value})</span>
        )}
      </span>
      <Badge
        variant="secondary"
        className="text-[9px] h-4 px-1 py-0 font-mono"
        title={members ? `enum ${enumName}` : `enum '${enumName}' not in registry`}
      >
        {enumName}
        {!members && ' ?'}
      </Badge>
    </span>
  )
}

/** Edit-mode enum picker. When the enum is missing from the catalog, falls
 * back to a plain string input with a muted warning so the user can still
 * type a literal member value (not blocked). */
function EnumInput({
  enumName,
  value,
  onChange,
  members,
  placeholder,
}: {
  enumName: string
  value: unknown
  onChange: (v: unknown) => void
  members: ReadonlyArray<EnumMemberSpec> | undefined
  placeholder?: string
}) {
  if (!members) {
    return (
      <div className="w-full space-y-0.5">
        <Input
          className="h-8 text-xs font-mono"
          value={typeof value === 'string' ? value : ''}
          placeholder={placeholder ?? `enum:${enumName}`}
          onChange={(e) => onChange(e.target.value)}
        />
        <p className="text-[10px] text-muted-foreground italic">
          enum '{enumName}' not in registry — free-text entry
        </p>
      </div>
    )
  }
  const current = typeof value === 'string' ? value : ''
  return (
    <Select value={current} onValueChange={(v) => onChange(v)}>
      <SelectTrigger size="sm" className="h-8 text-xs font-mono">
        <SelectValue placeholder={placeholder ?? 'Select member'} />
      </SelectTrigger>
      <SelectContent>
        {members.map((m) => (
          <SelectItem key={m.value} value={m.value} className="text-xs font-mono">
            {m.name}
            {m.name !== m.value && (
              <span className="text-muted-foreground"> ({m.value})</span>
            )}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function ScalarInput({
  base,
  value,
  onChange,
  placeholder,
}: {
  base: ParsedType['base']
  value: unknown
  onChange: (v: unknown) => void
  placeholder?: string
}) {
  if (base === 'str') {
    return (
      <Input
        className="h-8 text-xs font-mono"
        value={typeof value === 'string' ? value : ''}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    )
  }
  if (base === 'int') {
    return (
      <Input
        type="number"
        step="1"
        className="h-8 text-xs font-mono"
        value={typeof value === 'number' ? value : ''}
        placeholder={placeholder}
        onChange={(e) => {
          const raw = e.target.value
          if (raw === '') {
            onChange(0)
            return
          }
          const n = parseInt(raw, 10)
          if (!Number.isNaN(n)) onChange(n)
        }}
      />
    )
  }
  if (base === 'float') {
    return (
      <Input
        type="number"
        step="any"
        className="h-8 text-xs font-mono"
        value={typeof value === 'number' ? value : ''}
        placeholder={placeholder}
        onChange={(e) => {
          const raw = e.target.value
          if (raw === '') {
            onChange(0)
            return
          }
          const n = parseFloat(raw)
          if (!Number.isNaN(n)) onChange(n)
        }}
      />
    )
  }
  if (base === 'bool') {
    return (
      <div className="flex items-center gap-2 h-8">
        <Checkbox
          checked={Boolean(value)}
          onCheckedChange={(c) => onChange(c === true)}
        />
        <span className="text-orange-600 font-mono text-xs">
          {Boolean(value) ? 'true' : 'false'}
        </span>
      </div>
    )
  }
  return null
}

// ---------------------------------------------------------------------------
// Container widgets (list / dict)
// ---------------------------------------------------------------------------

function ListEditor({
  value,
  onChange,
  readOnly,
  depth,
  enumCatalog,
}: {
  value: unknown[]
  onChange?: (v: unknown) => void
  readOnly: boolean
  depth: number
  enumCatalog?: EnumCatalog
}) {
  // Auto-expand only the top two levels (root + immediate children). Deeper
  // containers open collapsed so prod schemas like list[TopicItem] with 10
  // items x 5 fields don't flood the viewport.
  const [expanded, setExpanded] = useState(depth < 2)
  const [newItemType, setNewItemType] = useState<ChildType>('str')
  const childTypeOptions = buildChildTypeOptions(enumCatalog)

  const addItem = useCallback(() => {
    if (!onChange) return
    onChange([...value, defaultForChildType(newItemType, enumCatalog)])
  }, [value, onChange, newItemType, enumCatalog])

  const removeItem = useCallback(
    (idx: number) => {
      if (!onChange) return
      const next = value.slice()
      next.splice(idx, 1)
      onChange(next)
    },
    [value, onChange],
  )

  const updateItem = useCallback(
    (idx: number, v: unknown) => {
      if (!onChange) return
      const next = value.slice()
      next[idx] = v
      onChange(next)
    },
    [value, onChange],
  )

  const changeItemType = useCallback(
    (idx: number, t: ChildType) => {
      if (!onChange) return
      const next = value.slice()
      next[idx] = defaultForChildType(t, enumCatalog)
      onChange(next)
    },
    [value, onChange, enumCatalog],
  )

  return (
    <div className="w-full">
      <button
        type="button"
        className="flex w-full items-center gap-1 py-0.5 font-mono text-xs hover:bg-muted/30 rounded"
        style={{ paddingLeft: `${depth * 8}px` }}
        onClick={() => setExpanded((p) => !p)}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <span className="text-muted-foreground">
          [{value.length} {value.length === 1 ? 'item' : 'items'}]
        </span>
      </button>
      {expanded && (
        <div
          className="border-l border-border/60 pl-1"
          style={{ marginLeft: `${depth * 8 + 4}px` }}
        >
          {value.map((item, i) => {
            // Heterogeneous lists: we can't know at runtime which items are
            // enum-typed from value alone. Default to inferred scalar type;
            // users can switch an item to `enum:<Name>` via the dropdown.
            const childType = inferChildType(item)
            return (
              <div key={i} className="flex items-start gap-1 py-0.5">
                <span className="text-muted-foreground font-mono text-xs shrink-0 w-4 pt-1.5">
                  {i}:
                </span>
                {!readOnly && (
                  <Select
                    value={childType}
                    onValueChange={(t) => changeItemType(i, t as ChildType)}
                  >
                    <SelectTrigger
                      size="sm"
                      className="h-7 w-[100px] text-[10px] font-mono shrink-0"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {childTypeOptions.map((opt) => (
                        <SelectItem
                          key={opt.value}
                          value={opt.value}
                          className="text-xs font-mono"
                        >
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <div className="flex-1 min-w-0">
                  <TypedValueEditor
                    type_str={childType}
                    value={item}
                    onChange={readOnly ? undefined : (v) => updateItem(i, v)}
                    readOnly={readOnly}
                    depth={depth + 1}
                    nested
                    enumCatalog={enumCatalog}
                  />
                </div>
                {!readOnly && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0 shrink-0 text-destructive"
                    onClick={() => removeItem(i)}
                    title="Remove item"
                  >
                    <Trash2 className="size-3" />
                  </Button>
                )}
              </div>
            )
          })}
          {!readOnly && (
            <div className="flex items-center gap-1 py-1">
              <Select
                value={newItemType}
                onValueChange={(t) => setNewItemType(t as ChildType)}
              >
                <SelectTrigger
                  size="sm"
                  className="h-7 w-[100px] text-[10px] font-mono shrink-0"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {childTypeOptions.map((opt) => (
                    <SelectItem
                      key={opt.value}
                      value={opt.value}
                      className="text-xs font-mono"
                    >
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-[11px] gap-1"
                onClick={addItem}
              >
                <Plus className="size-3" /> Add item
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DictEditor({
  value,
  onChange,
  readOnly,
  depth,
  enumCatalog,
}: {
  value: Record<string, unknown>
  onChange?: (v: unknown) => void
  readOnly: boolean
  depth: number
  enumCatalog?: EnumCatalog
}) {
  // Auto-expand only the top two levels (root + immediate children). Deeper
  // containers open collapsed so nested dicts with many entries don't flood
  // the viewport.
  const [expanded, setExpanded] = useState(depth < 2)
  const [newEntryKey, setNewEntryKey] = useState('')
  const [newEntryType, setNewEntryType] = useState<ChildType>('str')

  // Preserve insertion order by working against entries arrays.
  const entries = Object.entries(value)
  const childTypeOptions = buildChildTypeOptions(enumCatalog)

  const addEntry = useCallback(() => {
    if (!onChange) return
    const k = newEntryKey.trim()
    if (k === '') return
    if (Object.prototype.hasOwnProperty.call(value, k)) return
    onChange({ ...value, [k]: defaultForChildType(newEntryType, enumCatalog) })
    setNewEntryKey('')
  }, [value, onChange, newEntryKey, newEntryType, enumCatalog])

  const removeEntry = useCallback(
    (key: string) => {
      if (!onChange) return
      const next = { ...value }
      delete next[key]
      onChange(next)
    },
    [value, onChange],
  )

  const renameEntry = useCallback(
    (oldKey: string, newKey: string) => {
      if (!onChange) return
      const trimmed = newKey
      if (trimmed === oldKey) return
      // Rebuild preserving order.
      const next: Record<string, unknown> = {}
      for (const [k, v] of entries) {
        if (k === oldKey) {
          next[trimmed] = v
        } else {
          next[k] = v
        }
      }
      onChange(next)
    },
    [entries, onChange],
  )

  const updateEntry = useCallback(
    (key: string, v: unknown) => {
      if (!onChange) return
      onChange({ ...value, [key]: v })
    },
    [value, onChange],
  )

  const changeEntryType = useCallback(
    (key: string, t: ChildType) => {
      if (!onChange) return
      onChange({ ...value, [key]: defaultForChildType(t, enumCatalog) })
    },
    [value, onChange, enumCatalog],
  )

  return (
    <div className="w-full">
      <button
        type="button"
        className="flex w-full items-center gap-1 py-0.5 font-mono text-xs hover:bg-muted/30 rounded"
        style={{ paddingLeft: `${depth * 8}px` }}
        onClick={() => setExpanded((p) => !p)}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <span className="text-muted-foreground">
          {'{'}
          {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
          {'}'}
        </span>
      </button>
      {expanded && (
        <div
          className="border-l border-border/60 pl-1"
          style={{ marginLeft: `${depth * 8 + 4}px` }}
        >
          {entries.map(([k, v]) => {
            const childType = inferChildType(v)
            return (
              <div key={k} className="flex items-start gap-1 py-0.5">
                {readOnly ? (
                  <span className="text-muted-foreground font-mono text-xs shrink-0 pt-1.5">
                    {k}:
                  </span>
                ) : (
                  <Input
                    className="h-7 w-[120px] text-[11px] font-mono shrink-0"
                    value={k}
                    onChange={(e) => renameEntry(k, e.target.value)}
                  />
                )}
                {!readOnly && (
                  <Select
                    value={childType}
                    onValueChange={(t) => changeEntryType(k, t as ChildType)}
                  >
                    <SelectTrigger
                      size="sm"
                      className="h-7 w-[100px] text-[10px] font-mono shrink-0"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {childTypeOptions.map((opt) => (
                        <SelectItem
                          key={opt.value}
                          value={opt.value}
                          className="text-xs font-mono"
                        >
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <div className="flex-1 min-w-0">
                  <TypedValueEditor
                    type_str={childType}
                    value={v}
                    onChange={readOnly ? undefined : (nv) => updateEntry(k, nv)}
                    readOnly={readOnly}
                    depth={depth + 1}
                    nested
                    enumCatalog={enumCatalog}
                  />
                </div>
                {!readOnly && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0 shrink-0 text-destructive"
                    onClick={() => removeEntry(k)}
                    title="Remove entry"
                  >
                    <Trash2 className="size-3" />
                  </Button>
                )}
              </div>
            )
          })}
          {!readOnly && (
            <div className="flex items-center gap-1 py-1">
              <Input
                className="h-7 w-[120px] text-[11px] font-mono shrink-0"
                placeholder="key"
                value={newEntryKey}
                onChange={(e) => setNewEntryKey(e.target.value)}
              />
              <Select
                value={newEntryType}
                onValueChange={(t) => setNewEntryType(t as ChildType)}
              >
                <SelectTrigger
                  size="sm"
                  className="h-7 w-[100px] text-[10px] font-mono shrink-0"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {childTypeOptions.map((opt) => (
                    <SelectItem
                      key={opt.value}
                      value={opt.value}
                      className="text-xs font-mono"
                    >
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-[11px] gap-1"
                onClick={addEntry}
                disabled={
                  newEntryKey.trim() === '' ||
                  Object.prototype.hasOwnProperty.call(
                    value,
                    newEntryKey.trim(),
                  )
                }
              >
                <Plus className="size-3" /> Add entry
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Top-level component (recursive)
// ---------------------------------------------------------------------------

interface InternalProps extends TypedValueEditorProps {
  depth?: number
  /** True when rendered as a child of a list/dict — suppresses the null-
   * toggle control since the parent container manages item identity. */
  nested?: boolean
}

export function TypedValueEditor({
  type_str,
  value,
  onChange,
  readOnly = false,
  error,
  placeholder,
  className,
  depth = 0,
  nested = false,
  enumCatalog,
}: InternalProps) {
  const parsed = parseTypeStr(type_str)

  if (depth > MAX_DEPTH) {
    return (
      <span className="text-muted-foreground italic text-xs font-mono">
        (max depth reached)
      </span>
    )
  }

  const isNull = value === null || value === undefined

  // Null-toggle shown at top-level when:
  //  - Optional[X]: always surface the toggle so user can flip between null
  //    and inner value.
  //  - required field currently null (no default yet): show a "set value"
  //    button so the user can enter the scalar/container widget.
  const showNullToggle = !nested && !readOnly && (parsed.optional || isNull)

  const widget = (() => {
    if (isNull) {
      // In edit mode with a non-Optional null we still want to render a "set
      // value" affordance — handled by the null-toggle wrapper below. Here we
      // just show the muted null placeholder/label.
      return (
        <span className="text-muted-foreground italic font-mono text-xs">
          null{placeholder && !readOnly ? ` — ${placeholder}` : ''}
        </span>
      )
    }

    if (parsed.base === 'enum') {
      const enumName = parsed.enumName ?? ''
      const members = enumCatalog?.[enumName]
      if (readOnly) {
        return <ReadOnlyEnum enumName={enumName} value={value} members={members} />
      }
      return (
        <EnumInput
          enumName={enumName}
          value={value}
          onChange={(v) => onChange?.(v)}
          members={members}
          placeholder={placeholder}
        />
      )
    }

    if (parsed.base === 'list') {
      const arr = Array.isArray(value) ? value : []
      return (
        <ListEditor
          value={arr}
          onChange={readOnly ? undefined : onChange}
          readOnly={readOnly}
          depth={depth}
          enumCatalog={enumCatalog}
        />
      )
    }
    if (parsed.base === 'dict' || parsed.base === 'object') {
      const obj =
        value !== null && typeof value === 'object' && !Array.isArray(value)
          ? (value as Record<string, unknown>)
          : {}
      return (
        <DictEditor
          value={obj}
          onChange={readOnly ? undefined : onChange}
          readOnly={readOnly}
          depth={depth}
          enumCatalog={enumCatalog}
        />
      )
    }

    // Scalar.
    if (readOnly) {
      return <ReadOnlyScalar base={parsed.base} value={value} />
    }
    return (
      <ScalarInput
        base={parsed.base}
        value={value}
        onChange={(v) => onChange?.(v)}
        placeholder={placeholder}
      />
    )
  })()

  return (
    <div className={cn('w-full', className)}>
      {showNullToggle ? (
        <div className="flex items-start gap-2">
          <div className="flex items-center h-8 gap-1 shrink-0">
            <Checkbox
              checked={isNull}
              onCheckedChange={(c) => {
                if (c === true) {
                  onChange?.(null)
                } else {
                  onChange?.(defaultForBase(parsed.base, parsed.enumName, enumCatalog))
                }
              }}
              aria-label="null"
            />
            <span className="text-[10px] uppercase text-muted-foreground">
              null
            </span>
          </div>
          <div className="flex-1 min-w-0">{widget}</div>
        </div>
      ) : (
        widget
      )}
      {/* Read-only null at top level with placeholder: show placeholder text. */}
      {readOnly && isNull && placeholder && !nested && (
        <span className="text-muted-foreground italic text-xs">
          {' '}
          — {placeholder}
        </span>
      )}
      {error && (
        <p className="text-[10px] text-destructive mt-1 flex items-start gap-1">
          <AlertCircle className="size-3 shrink-0 mt-0.5" />
          <span>{error}</span>
        </p>
      )}
    </div>
  )
}

function defaultForBase(
  base: ParsedType['base'],
  enumName?: string,
  enumCatalog?: EnumCatalog,
): unknown {
  switch (base) {
    case 'str':
      return ''
    case 'int':
      return 0
    case 'float':
      return 0
    case 'bool':
      return false
    case 'list':
      return []
    case 'dict':
    case 'object':
      return {}
    case 'enum': {
      const members = enumName ? enumCatalog?.[enumName] : undefined
      return members && members.length > 0 ? members[0].value : ''
    }
  }
}
