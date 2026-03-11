import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Prompt } from '@/api/types'
import { PromptList } from './PromptList'

// Radix ScrollArea uses ResizeObserver internally; polyfill for jsdom
const originalRO = globalThis.ResizeObserver
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})
afterAll(() => {
  globalThis.ResizeObserver = originalRO
})

function makePrompt(overrides: Partial<Prompt> = {}): Prompt {
  return {
    id: 1,
    prompt_key: 'key-1',
    prompt_name: 'Prompt One',
    prompt_type: 'chat',
    category: null,
    step_name: null,
    content: '',
    required_variables: null,
    description: null,
    version: '1',
    ...overrides,
  }
}

const defaultProps = {
  prompts: [] as Prompt[],
  selectedKey: '',
  onSelect: vi.fn(),
  isLoading: false,
  error: null,
}

describe('PromptList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton when isLoading=true', () => {
    const { container } = render(
      <PromptList {...defaultProps} isLoading={true} />,
    )
    const pulses = container.querySelectorAll('.animate-pulse')
    expect(pulses.length).toBeGreaterThan(0)
  })

  it('shows error message when error is an Error object', () => {
    const { container } = render(
      <PromptList {...defaultProps} error={new Error('load failed')} />,
    )
    const errorEl = container.querySelector('.text-destructive')
    expect(errorEl).toBeInTheDocument()
    expect(errorEl).toHaveTextContent('Failed to load prompts')
  })

  it('shows empty state when prompts=[]', () => {
    const { container } = render(
      <PromptList {...defaultProps} prompts={[]} />,
    )
    const emptyEl = container.querySelector('.text-muted-foreground')
    expect(emptyEl).toBeInTheDocument()
    expect(emptyEl).toHaveTextContent('No prompts match filters')
  })

  it('renders a button per prompt', () => {
    const prompts = [
      makePrompt({ prompt_key: 'a', prompt_name: 'Alpha' }),
      makePrompt({ id: 2, prompt_key: 'b', prompt_name: 'Beta' }),
    ]
    render(<PromptList {...defaultProps} prompts={prompts} />)

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(2)
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  it('highlights selected prompt', () => {
    const prompts = [
      makePrompt({ prompt_key: 'a', prompt_name: 'Alpha' }),
      makePrompt({ id: 2, prompt_key: 'b', prompt_name: 'Beta' }),
    ]
    render(
      <PromptList {...defaultProps} prompts={prompts} selectedKey="b" />,
    )

    const buttons = screen.getAllByRole('button')
    const selectedBtn = buttons.find((b) => b.textContent?.includes('Beta'))
    expect(selectedBtn).toHaveClass('bg-accent')

    const unselectedBtn = buttons.find((b) => b.textContent?.includes('Alpha'))
    expect(unselectedBtn).not.toHaveClass('bg-accent')
  })

  it('calls onSelect with prompt key on click', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    const prompts = [
      makePrompt({ prompt_key: 'a', prompt_name: 'Alpha' }),
      makePrompt({ id: 2, prompt_key: 'b', prompt_name: 'Beta' }),
    ]
    render(
      <PromptList {...defaultProps} prompts={prompts} onSelect={onSelect} />,
    )

    await user.click(screen.getByText('Beta'))
    expect(onSelect).toHaveBeenCalledWith('b')
    expect(onSelect).toHaveBeenCalledTimes(1)
  })
})
