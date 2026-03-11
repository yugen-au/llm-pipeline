import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormField } from './FormField'
import type { FormFieldProps } from './FormField'
import type { JsonSchema } from '@/api/types'

function makeProps(overrides: Partial<FormFieldProps> = {}): FormFieldProps {
  return {
    name: 'testField',
    fieldSchema: { type: 'string' } as JsonSchema,
    value: '',
    onChange: vi.fn(),
    error: undefined,
    required: false,
    ...overrides,
  }
}

describe('FormField', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Input for string type', () => {
    render(<FormField {...makeProps({ fieldSchema: { type: 'string' } })} />)
    const input = screen.getByRole('textbox')
    expect(input).toBeInTheDocument()
    expect(input.tagName).toBe('INPUT')
  })

  it('renders number Input for integer type', () => {
    render(<FormField {...makeProps({ fieldSchema: { type: 'integer' } })} />)
    const input = screen.getByRole('spinbutton')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'number')
  })

  it('renders Checkbox for boolean type', () => {
    render(<FormField {...makeProps({ fieldSchema: { type: 'boolean' }, value: false })} />)
    // Radix Checkbox renders as button with role="checkbox"
    const checkbox = screen.getByRole('checkbox')
    expect(checkbox).toBeInTheDocument()
  })

  it('renders Textarea as fallback for object type', () => {
    render(<FormField {...makeProps({ fieldSchema: { type: 'object' } })} />)
    const textarea = screen.getByRole('textbox')
    expect(textarea).toBeInTheDocument()
    expect(textarea.tagName).toBe('TEXTAREA')
  })

  it('shows required indicator when required=true', () => {
    render(<FormField {...makeProps({ required: true })} />)
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('shows error message and aria-invalid when error prop set', () => {
    const error = 'Field is required'
    render(<FormField {...makeProps({ error })} />)
    expect(screen.getByText(error)).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows description when fieldSchema.description present', () => {
    const description = 'Enter your name here'
    render(<FormField {...makeProps({ fieldSchema: { type: 'string', description } })} />)
    expect(screen.getByText(description)).toBeInTheDocument()
  })

  it('calls onChange on input change', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<FormField {...makeProps({ onChange })} />)

    await user.type(screen.getByRole('textbox'), 'a')
    expect(onChange).toHaveBeenCalledWith('a')
  })
})
