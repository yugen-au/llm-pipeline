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
    name: 'prompt_one',
    description: null,
    metadata: { display_name: 'Prompt One' },
    messages: [{ role: 'system', content: 'hi' }],
    version_id: 'v_001',
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

  it('renders a button per prompt with display_name when present', () => {
    const prompts = [
      makePrompt({ name: 'a', metadata: { display_name: 'Alpha' } }),
      makePrompt({ name: 'b', metadata: { display_name: 'Beta' } }),
    ]
    render(<PromptList {...defaultProps} prompts={prompts} />)

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(2)
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  it('falls back to name when metadata.display_name is missing', () => {
    const prompts = [makePrompt({ name: 'lonely_prompt', metadata: {} })]
    render(<PromptList {...defaultProps} prompts={prompts} />)
    expect(screen.getByText('lonely_prompt')).toBeInTheDocument()
  })

  it('highlights selected prompt', () => {
    const prompts = [
      makePrompt({ name: 'a', metadata: { display_name: 'Alpha' } }),
      makePrompt({ name: 'b', metadata: { display_name: 'Beta' } }),
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

  it('calls onSelect with prompt name on click', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    const prompts = [
      makePrompt({ name: 'a', metadata: { display_name: 'Alpha' } }),
      makePrompt({ name: 'b', metadata: { display_name: 'Beta' } }),
    ]
    render(
      <PromptList {...defaultProps} prompts={prompts} onSelect={onSelect} />,
    )

    await user.click(screen.getByText('Beta'))
    expect(onSelect).toHaveBeenCalledWith('b')
    expect(onSelect).toHaveBeenCalledTimes(1)
  })
})
