import type { JsonSchema } from '@/api/types'
import { FormField } from '@/components/live/FormField'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface InputFormProps {
  schema: JsonSchema | null
  values: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
  fieldErrors: Record<string, string>
  isSubmitting: boolean
}

// ---------------------------------------------------------------------------
// Validation helper
// ---------------------------------------------------------------------------

/**
 * Validate form values against a JSON Schema's required fields.
 * Returns Record<string, string> with error messages for missing required
 * fields, or {} when all required fields are present.
 */
export function validateForm(
  schema: JsonSchema | null,
  values: Record<string, unknown>,
): Record<string, string> {
  if (!schema) return {}

  const required = (schema.required ?? []) as string[]
  const errors: Record<string, string> = {}

  for (const field of required) {
    const val = values[field]
    if (val === undefined || val === null || val === '') {
      const properties = (schema.properties ?? {}) as Record<string, JsonSchema>
      const title = (properties[field]?.title as string) ?? field
      errors[field] = `${title} is required`
    }
  }

  return errors
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function InputForm({
  schema,
  values,
  onChange,
  fieldErrors,
  isSubmitting,
}: InputFormProps) {
  if (!schema) return null

  const properties = (schema.properties ?? {}) as Record<string, JsonSchema>
  const required = (schema.required ?? []) as string[]

  return (
    <form
      onSubmit={(e) => e.preventDefault()}
      className="space-y-4"
      data-testid="input-form"
    >
      <fieldset disabled={isSubmitting} className="space-y-4">
        {Object.entries(properties).map(([name, fieldSchema]) => (
          <FormField
            key={name}
            name={name}
            fieldSchema={fieldSchema}
            value={values[name]}
            onChange={(value) => onChange(name, value)}
            error={fieldErrors[name]}
            required={required.includes(name)}
          />
        ))}
      </fieldset>
    </form>
  )
}
