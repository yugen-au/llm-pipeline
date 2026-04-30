import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach, beforeAll, afterAll } from 'vitest'
import { PromptViewer } from './PromptViewer'
import type { Prompt } from '@/api/types'

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

// Mock TanStack hooks (Monaco-based editor + mutation hooks need plumbing).
const mockUsePromptDetail = vi.fn()
vi.mock('@/api/prompts', () => {
  const noopMutation = () => ({ mutate: vi.fn(), isPending: false })
  return {
    usePromptDetail: (...args: unknown[]) => mockUsePromptDetail(...args),
    useCreatePrompt: noopMutation,
    useUpdatePrompt: noopMutation,
    useDeletePrompt: noopMutation,
    usePromptVariableSchema: () => ({ data: undefined }),
    useAutoGenerateObjects: () => ({ data: { objects: [] } }),
  }
})

// Stub Monaco editor: it doesn't render in jsdom and isn't load-bearing here.
vi.mock('@monaco-editor/react', () => ({
  __esModule: true,
  default: ({ value }: { value: string }) => (
    <textarea data-testid="monaco-stub" value={value} readOnly />
  ),
}))

function makePrompt(overrides: Partial<Prompt> = {}): Prompt {
  return {
    name: 'test_prompt',
    description: null,
    metadata: { display_name: 'Test Prompt' },
    messages: [
      { role: 'system', content: 'system content' },
      { role: 'user', content: 'user content' },
    ],
    version_id: 'v_001',
    ...overrides,
  }
}

describe('PromptViewer', () => {
  beforeEach(() => {
    mockUsePromptDetail.mockReset()
  })

  it('shows "Select a prompt" when promptKey=null', () => {
    mockUsePromptDetail.mockReturnValue({ data: undefined, isLoading: false, error: null })
    render(<PromptViewer promptKey={null} />)
    expect(screen.getByText(/select a prompt/i)).toBeInTheDocument()
  })

  it('shows loading skeleton when isLoading=true', () => {
    mockUsePromptDetail.mockReturnValue({ data: undefined, isLoading: true, error: null })
    const { container } = render(<PromptViewer promptKey="test" />)
    const pulsingDivs = container.querySelectorAll('.animate-pulse')
    expect(pulsingDivs.length).toBeGreaterThan(0)
  })

  it('shows error state when error is set', () => {
    mockUsePromptDetail.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('network error'),
    })
    render(<PromptViewer promptKey="test" />)
    expect(screen.getByText('Failed to load prompt')).toBeInTheDocument()
  })

  it('renders both system and user editors stacked (no tabs)', () => {
    const prompt = makePrompt()
    mockUsePromptDetail.mockReturnValue({
      data: prompt,
      isLoading: false,
      error: null,
    })
    render(<PromptViewer promptKey="test_prompt" />)

    // Heading shows the prompt name
    expect(screen.getByText('test_prompt')).toBeInTheDocument()
    // Both message editors are visible — labels rendered for each
    expect(screen.getByText('System message')).toBeInTheDocument()
    expect(screen.getByText('User message')).toBeInTheDocument()
    // No tablist (collapsed editor renders both inline)
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    // Two Monaco stubs (one per message)
    expect(screen.getAllByTestId('monaco-stub')).toHaveLength(2)
  })

  it('renders editors even when only one message exists', () => {
    const prompt = makePrompt({
      messages: [{ role: 'system', content: 'just system' }],
    })
    mockUsePromptDetail.mockReturnValue({
      data: prompt,
      isLoading: false,
      error: null,
    })
    render(<PromptViewer promptKey="test_prompt" />)
    // Both editors still mount (user message editor stays visible to allow add).
    expect(screen.getAllByTestId('monaco-stub')).toHaveLength(2)
  })
})
