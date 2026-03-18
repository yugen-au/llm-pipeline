import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import type { JsonSchema } from '@/api/types'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface FormFieldProps {
  name: string
  fieldSchema: JsonSchema
  value: unknown
  onChange: (value: unknown) => void
  error: string | undefined
  required: boolean
  /** Top-level schema for resolving $ref */
  rootSchema?: JsonSchema
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Resolve a $ref like "#/$defs/RateCardQuery" against the root schema. */
function resolveRef(schema: JsonSchema, rootSchema?: JsonSchema): JsonSchema {
  const ref = schema.$ref as string | undefined
  if (!ref || !rootSchema) return schema
  // Handle "#/$defs/Name" or "#/definitions/Name"
  const parts = ref.replace(/^#\//, '').split('/')
  let resolved: unknown = rootSchema
  for (const part of parts) {
    if (resolved && typeof resolved === 'object') {
      resolved = (resolved as Record<string, unknown>)[part]
    } else {
      return schema
    }
  }
  return (resolved as JsonSchema) ?? schema
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FormField({
  name,
  fieldSchema: rawSchema,
  value,
  onChange,
  error,
  required,
  rootSchema,
}: FormFieldProps) {
  const fieldSchema = resolveRef(rawSchema, rootSchema)
  const label = (fieldSchema.title as string) ?? name
  const description = fieldSchema.description as string | undefined
  const fieldType = fieldSchema.type as string | undefined
  const fieldId = `field-${name}`
  const properties = fieldSchema.properties as Record<string, JsonSchema> | undefined
  const fieldRequired = (fieldSchema.required ?? []) as string[]

  // Object with known properties -> render sub-fields
  if ((fieldType === 'object' || properties) && properties && Object.keys(properties).length > 0) {
    const objValue = (value ?? {}) as Record<string, unknown>
    return (
      <div className="space-y-2">
        <Label className={cn('text-sm font-semibold', error && 'text-destructive')}>
          {label}
          {required && <span className="text-destructive ml-0.5">*</span>}
        </Label>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
        <div className="pl-4 border-l-2 border-muted space-y-3">
          {Object.entries(properties).map(([subName, subSchema]) => (
            <FormField
              key={subName}
              name={subName}
              fieldSchema={subSchema}
              value={objValue[subName]}
              onChange={(subValue) => {
                onChange({ ...objValue, [subName]: subValue })
              }}
              error={undefined}
              required={fieldRequired.includes(subName)}
              rootSchema={rootSchema}
            />
          ))}
        </div>
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {fieldType === 'boolean' ? (
        <div className="flex items-center gap-2">
          <Checkbox
            id={fieldId}
            checked={Boolean(value)}
            onCheckedChange={(checked) => onChange(Boolean(checked))}
            aria-invalid={error ? true : undefined}
          />
          <Label htmlFor={fieldId} className={cn(error && 'text-destructive')}>
            {label}
            {required && <span className="text-destructive ml-0.5">*</span>}
          </Label>
        </div>
      ) : (
        <Label htmlFor={fieldId} className={cn(error && 'text-destructive')}>
          {label}
          {required && <span className="text-destructive ml-0.5">*</span>}
        </Label>
      )}

      {fieldType === 'string' && (
        <Input
          id={fieldId}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={error ? true : undefined}
        />
      )}

      {(fieldType === 'integer' || fieldType === 'number') && (
        <Input
          id={fieldId}
          type="number"
          value={value != null ? String(value) : ''}
          onChange={(e) => {
            const raw = e.target.value
            if (raw === '') {
              onChange(undefined)
              return
            }
            onChange(fieldType === 'integer' ? parseInt(raw, 10) : parseFloat(raw))
          }}
          aria-invalid={error ? true : undefined}
        />
      )}

      {/* boolean rendered inline with checkbox above */}

      {fieldType !== 'string' &&
        fieldType !== 'integer' &&
        fieldType !== 'number' &&
        fieldType !== 'boolean' &&
        !properties && (
          <Textarea
            id={fieldId}
            value={value != null ? (typeof value === 'string' ? value : JSON.stringify(value, null, 2)) : ''}
            onChange={(e) => {
              const raw = e.target.value
              try {
                onChange(JSON.parse(raw))
              } catch {
                onChange(raw)
              }
            }}
            placeholder="Enter JSON value"
            aria-invalid={error ? true : undefined}
          />
        )}

      {description && (
        <p className="text-xs text-muted-foreground">{description}</p>
      )}

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}
    </div>
  )
}
