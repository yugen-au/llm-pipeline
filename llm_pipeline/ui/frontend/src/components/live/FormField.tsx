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
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FormField({
  name,
  fieldSchema,
  value,
  onChange,
  error,
  required,
}: FormFieldProps) {
  const label = (fieldSchema.title as string) ?? name
  const description = fieldSchema.description as string | undefined
  const fieldType = fieldSchema.type as string | undefined
  const fieldId = `field-${name}`

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
        fieldType !== 'boolean' && (
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
