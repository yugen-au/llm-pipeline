import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, beforeEach } from 'vitest'
import { PipelineSelector } from './PipelineSelector'
import type { PipelineListItem } from '@/api/types'

// ---------------------------------------------------------------------------
// Mock usePipelines hook at module level (established pattern)
// ---------------------------------------------------------------------------

const mockUsePipelines = vi.fn()
vi.mock('@/api/pipelines', () => ({
  usePipelines: () => mockUsePipelines(),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const twoPipelines: PipelineListItem[] = [
  {
    name: 'etl-daily',
    strategy_count: 2,
    step_count: 4,
    has_input_schema: true,
    registry_model_count: 1,
    error: null,
  },
  {
    name: 'classify-docs',
    strategy_count: 1,
    step_count: 3,
    has_input_schema: false,
    registry_model_count: 2,
    error: null,
  },
]

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PipelineSelector', () => {
  const defaultProps = {
    selectedPipeline: null,
    onSelect: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockUsePipelines.mockReturnValue({
      data: { pipelines: twoPipelines },
      isLoading: false,
      isError: false,
    })
  })

  it('shows loading skeleton when isLoading=true', () => {
    mockUsePipelines.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })
    const { container } = render(<PipelineSelector {...defaultProps} />)
    const pulsingDivs = container.querySelectorAll('.animate-pulse')
    expect(pulsingDivs.length).toBeGreaterThanOrEqual(1)
  })

  it('shows error state when isError=true', () => {
    mockUsePipelines.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    })
    render(<PipelineSelector {...defaultProps} />)
    expect(screen.getByText('Failed to load pipelines.')).toBeInTheDocument()
  })

  it('shows "No pipelines registered" when pipelines=[]', () => {
    mockUsePipelines.mockReturnValue({
      data: { pipelines: [] },
      isLoading: false,
      isError: false,
    })
    render(<PipelineSelector {...defaultProps} />)
    expect(screen.getByText('No pipelines registered')).toBeInTheDocument()
  })

  it('renders Select with pipeline options when data present', async () => {
    const user = userEvent.setup()
    render(<PipelineSelector {...defaultProps} />)

    const combobox = screen.getByRole('combobox')
    expect(combobox).toBeInTheDocument()

    await user.click(combobox)

    expect(screen.getByRole('option', { name: 'etl-daily' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'classify-docs' })).toBeInTheDocument()
  })

  it('calls onSelect with pipeline name on selection', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<PipelineSelector {...defaultProps} onSelect={onSelect} />)

    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: 'classify-docs' }))

    expect(onSelect).toHaveBeenCalledWith('classify-docs')
  })

  it('disables Select when disabled=true', () => {
    render(<PipelineSelector {...defaultProps} disabled={true} />)
    const combobox = screen.getByRole('combobox')
    expect(combobox).toBeDisabled()
  })
})
