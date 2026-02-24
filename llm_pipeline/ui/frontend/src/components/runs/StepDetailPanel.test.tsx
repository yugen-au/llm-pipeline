import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { StepDetailPanel } from './StepDetailPanel'
import type { StepDetail } from '@/api/types'

vi.mock('@/lib/time', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/time')>()
  return {
    ...actual,
    formatRelative: (iso: string) => `relative(${iso})`,
    formatAbsolute: (iso: string) => `absolute(${iso})`,
    formatDuration: (ms: number | null) => (ms == null ? '\u2014' : `${(ms / 1000).toFixed(1)}s`),
  }
})

const mockStepData: StepDetail = {
  step_name: 'extract',
  step_number: 1,
  pipeline_name: 'test-pipeline',
  run_id: 'r1',
  input_hash: 'abc123',
  result_data: {},
  context_snapshot: {},
  prompt_system_key: null,
  prompt_user_key: null,
  prompt_version: null,
  model: 'gemini-2.0-flash',
  execution_time_ms: 2500,
  created_at: '2025-06-15T10:00:00.000Z',
}

// Mock useStep hook
const mockUseStep = vi.fn()
vi.mock('@/api/steps', () => ({
  useStep: (...args: unknown[]) => mockUseStep(...args),
}))

const NOW = '2025-06-15T12:00:00.000Z'

describe('StepDetailPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(NOW))
    mockUseStep.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders with translate-x-full when open=false', () => {
    mockUseStep.mockReturnValue({ data: undefined, isLoading: false, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={false}
        onClose={vi.fn()}
      />,
    )
    const panel = screen.getByRole('dialog', { hidden: true })
    expect(panel.className).toContain('translate-x-full')
    expect(panel.className).not.toContain('translate-x-0')
  })

  it('renders panel content when open=true and step loaded', () => {
    mockUseStep.mockReturnValue({ data: mockStepData, isLoading: false, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={vi.fn()}
      />,
    )
    const panel = screen.getByRole('dialog')
    expect(panel.className).toContain('translate-x-0')

    expect(screen.getByText('extract')).toBeInTheDocument()
    expect(screen.getByText('Step 1')).toBeInTheDocument()
    expect(screen.getByText('gemini-2.0-flash')).toBeInTheDocument()
    expect(screen.getByText('2.5s')).toBeInTheDocument()
  })

  it('shows loading skeleton when useStep is loading', () => {
    mockUseStep.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    const { container } = render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={vi.fn()}
      />,
    )
    const pulsingDivs = container.querySelectorAll('.animate-pulse')
    expect(pulsingDivs.length).toBeGreaterThan(0)
  })

  it('shows error message when useStep errors', () => {
    mockUseStep.mockReturnValue({ data: undefined, isLoading: false, isError: true })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={vi.fn()}
      />,
    )
    const error = screen.getByText('Failed to load step')
    expect(error).toBeInTheDocument()
    expect(error).toHaveClass('text-destructive')
  })

  it('calls onClose when close button clicked', async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    mockUseStep.mockReturnValue({ data: mockStepData, isLoading: false, isError: false })
    const onClose = vi.fn()
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={onClose}
      />,
    )
    const closeBtn = screen.getByRole('button', { name: 'Close step detail' })
    await user.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not render StepContent when stepNumber is null', () => {
    mockUseStep.mockReturnValue({ data: undefined, isLoading: false, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={null}
        open={true}
        onClose={vi.fn()}
      />,
    )
    // Panel should be closed (translated out) when stepNumber is null
    expect(screen.queryByText('extract')).not.toBeInTheDocument()
  })

  it('calls onClose when Escape key is pressed', () => {
    mockUseStep.mockReturnValue({ data: mockStepData, isLoading: false, isError: false })
    const onClose = vi.fn()
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={onClose}
      />,
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when backdrop is clicked', async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    mockUseStep.mockReturnValue({ data: mockStepData, isLoading: false, isError: false })
    const onClose = vi.fn()
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={onClose}
      />,
    )
    // Backdrop is the aria-hidden overlay element
    const backdrop = document.querySelector('[aria-hidden="true"]') as HTMLElement
    expect(backdrop).toBeTruthy()
    await user.click(backdrop)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
