import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { PromptViewer } from './PromptViewer'
import type { PromptVariant } from '@/api/types'

// Mock usePromptDetail hook
const mockUsePromptDetail = vi.fn()
vi.mock('@/api/prompts', () => ({
  usePromptDetail: (...args: unknown[]) => mockUsePromptDetail(...args),
}))

function makeVariant(overrides: Partial<PromptVariant> = {}): PromptVariant {
  return {
    id: 1,
    prompt_key: 'test_prompt',
    prompt_name: 'Test Prompt',
    prompt_type: 'system',
    category: null,
    step_name: null,
    content: 'Hello world',
    required_variables: null,
    description: null,
    version: '1',
    is_active: true,
    created_at: '2025-06-01T00:00:00Z',
    updated_at: '2025-06-01T00:00:00Z',
    created_by: null,
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

  it('renders prompt content for single variant (no tabs)', () => {
    const variant = makeVariant({ content: 'Single variant content', prompt_type: 'system' })
    mockUsePromptDetail.mockReturnValue({
      data: { prompt_key: 'my_prompt', variants: [variant] },
      isLoading: false,
      error: null,
    })
    render(<PromptViewer promptKey="my_prompt" />)

    // Prompt key heading visible
    expect(screen.getByText('my_prompt')).toBeInTheDocument()
    // Content visible
    expect(screen.getByText('Single variant content')).toBeInTheDocument()
    // No tab triggers (single variant = no tabs)
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('renders Tabs for multiple variants', () => {
    const v1 = makeVariant({ prompt_type: 'system', content: 'system content' })
    const v2 = makeVariant({ id: 2, prompt_type: 'user', content: 'user content' })
    mockUsePromptDetail.mockReturnValue({
      data: { prompt_key: 'multi_prompt', variants: [v1, v2] },
      isLoading: false,
      error: null,
    })
    render(<PromptViewer promptKey="multi_prompt" />)

    // Heading visible
    expect(screen.getByText('multi_prompt')).toBeInTheDocument()
    // Tab triggers present
    expect(screen.getByRole('tablist')).toBeInTheDocument()
    const tabs = screen.getAllByRole('tab')
    expect(tabs.length).toBe(2)
    // Tab labels match prompt_type values
    expect(tabs.some((t) => t.textContent === 'system')).toBe(true)
    expect(tabs.some((t) => t.textContent === 'user')).toBe(true)
  })

  it('highlights {variable} placeholders in content', () => {
    const variant = makeVariant({ content: 'Hello {name}, your order is {order_id}' })
    mockUsePromptDetail.mockReturnValue({
      data: { prompt_key: 'var_prompt', variants: [variant] },
      isLoading: false,
      error: null,
    })
    const { container } = render(<PromptViewer promptKey="var_prompt" />)

    // Highlighted spans have bg-primary/20 class
    const highlighted = container.querySelectorAll('span.text-primary')
    expect(highlighted.length).toBe(2)
    expect(highlighted[0].textContent).toBe('{name}')
    expect(highlighted[1].textContent).toBe('{order_id}')
  })
})
