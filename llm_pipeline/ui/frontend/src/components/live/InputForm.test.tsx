import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InputForm, validateForm } from './InputForm'
import type { InputFormProps } from './InputForm'
import type { JsonSchema } from '@/api/types'

const twoFieldSchema: JsonSchema = {
  type: 'object',
  properties: {
    name: { type: 'string', title: 'Name' },
    age: { type: 'integer', title: 'Age' },
  },
  required: ['name'],
}

function makeProps(overrides: Partial<InputFormProps> = {}): InputFormProps {
  return {
    schema: twoFieldSchema,
    values: {},
    onChange: vi.fn(),
    fieldErrors: {},
    isSubmitting: false,
    ...overrides,
  }
}

describe('InputForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when schema is null', () => {
    const { container } = render(<InputForm {...makeProps({ schema: null })} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders data-testid="input-form" when schema present', () => {
    render(<InputForm {...makeProps()} />)
    expect(screen.getByTestId('input-form')).toBeInTheDocument()
  })

  it('renders FormField for each property in schema', () => {
    render(<InputForm {...makeProps()} />)
    // string field -> textbox, integer field -> spinbutton
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByRole('spinbutton')).toBeInTheDocument()
  })

  it('disables fieldset when isSubmitting=true', () => {
    render(<InputForm {...makeProps({ isSubmitting: true })} />)
    const fieldset = screen.getByTestId('input-form').querySelector('fieldset')
    expect(fieldset).toBeDisabled()
  })

  it('calls onChange when field changes', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<InputForm {...makeProps({ onChange })} />)

    await user.type(screen.getByRole('textbox'), 'a')
    expect(onChange).toHaveBeenCalledWith('name', 'a')
  })
})

describe('validateForm', () => {
  it('returns error for missing required field', () => {
    const errors = validateForm(twoFieldSchema, {})
    expect(errors).toEqual({ name: 'Name is required' })
  })

  it('returns empty object when all required fields present', () => {
    const errors = validateForm(twoFieldSchema, { name: 'Alice' })
    expect(errors).toEqual({})
  })

  it('returns empty object when schema is null', () => {
    const errors = validateForm(null, {})
    expect(errors).toEqual({})
  })

  it('treats empty string as missing', () => {
    const errors = validateForm(twoFieldSchema, { name: '' })
    expect(errors).toEqual({ name: 'Name is required' })
  })
})
