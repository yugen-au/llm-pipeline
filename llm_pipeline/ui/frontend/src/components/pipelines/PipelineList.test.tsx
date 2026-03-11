import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, beforeEach, beforeAll, afterAll } from 'vitest'
import { PipelineList } from './PipelineList'
import type { PipelineListItem } from '@/api/types'

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

const makePipeline = (overrides: Partial<PipelineListItem> = {}): PipelineListItem => ({
  name: 'default-pipeline',
  strategy_count: 1,
  step_count: 3,
  has_input_schema: false,
  registry_model_count: null,
  error: null,
  ...overrides,
})

const defaultProps = {
  pipelines: [] as PipelineListItem[],
  selectedName: '',
  onSelect: vi.fn(),
  isLoading: false,
  error: null,
}

describe('PipelineList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton when isLoading=true', () => {
    const { container } = render(<PipelineList {...defaultProps} isLoading={true} />)
    const pulsingDivs = container.querySelectorAll('.animate-pulse')
    expect(pulsingDivs.length).toBeGreaterThanOrEqual(1)
  })

  it('shows error message when error is an Error object', () => {
    render(<PipelineList {...defaultProps} error={new Error('network fail')} />)
    const errorEl = screen.getByText('Failed to load pipelines')
    expect(errorEl).toBeInTheDocument()
    expect(errorEl).toHaveClass('text-destructive')
  })

  it('shows empty state when pipelines=[]', () => {
    render(<PipelineList {...defaultProps} pipelines={[]} />)
    const emptyEl = screen.getByText('No pipelines found')
    expect(emptyEl).toBeInTheDocument()
    expect(emptyEl).toHaveClass('text-muted-foreground')
  })

  it('renders a button per pipeline', () => {
    const pipelines = [
      makePipeline({ name: 'alpha' }),
      makePipeline({ name: 'beta' }),
    ]
    render(<PipelineList {...defaultProps} pipelines={pipelines} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(2)
    expect(screen.getByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('beta')).toBeInTheDocument()
  })

  it('shows step count badge when pipeline has no error', () => {
    const pipelines = [makePipeline({ name: 'ok-pipe', step_count: 5, error: null })]
    render(<PipelineList {...defaultProps} pipelines={pipelines} />)
    expect(screen.getByText('5 steps')).toBeInTheDocument()
    // step count badge uses outline variant
    const badge = screen.getByText('5 steps').closest('[data-slot="badge"]')!
    expect(badge).toHaveAttribute('data-variant', 'outline')
    // no destructive badge
    const allBadges = document.querySelectorAll('[data-variant="destructive"]')
    expect(allBadges).toHaveLength(0)
  })

  it('shows destructive error badge instead of step count when pipeline.error != null', () => {
    const pipelines = [makePipeline({ name: 'broken', step_count: 5, error: 'import failed' })]
    render(<PipelineList {...defaultProps} pipelines={pipelines} />)
    // destructive badge with "error" text
    const errorBadge = screen.getByText('error')
    const badge = errorBadge.closest('[data-slot="badge"]')!
    expect(badge).toHaveAttribute('data-variant', 'destructive')
    // no step count badge shown (mutual exclusivity)
    expect(screen.queryByText('5 steps')).not.toBeInTheDocument()
  })

  it('calls onSelect on click', async () => {
    const onSelect = vi.fn()
    const pipelines = [makePipeline({ name: 'click-me' })]
    const user = userEvent.setup()
    render(<PipelineList {...defaultProps} pipelines={pipelines} onSelect={onSelect} />)

    await user.click(screen.getByRole('button'))
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith('click-me')
  })

  it('highlights selected pipeline', () => {
    const pipelines = [
      makePipeline({ name: 'sel' }),
      makePipeline({ name: 'other' }),
    ]
    render(<PipelineList {...defaultProps} pipelines={pipelines} selectedName="sel" />)
    const selectedBtn = screen.getByText('sel').closest('button')!
    expect(selectedBtn).toHaveClass('bg-accent')
    const otherBtn = screen.getByText('other').closest('button')!
    expect(otherBtn).not.toHaveClass('bg-accent')
  })
})
