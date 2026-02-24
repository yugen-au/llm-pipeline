import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { StepDetailPanel } from './StepDetailPanel'
import type { StepDetail, EventListResponse } from '@/api/types'

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

const emptyEventsResponse: EventListResponse = {
  items: [],
  total: 0,
  offset: 0,
  limit: 50,
}

// Mock useStep hook
const mockUseStep = vi.fn()
vi.mock('@/api/steps', () => ({
  useStep: (...args: unknown[]) => mockUseStep(...args),
}))

// Mock useStepEvents hook
const mockUseStepEvents = vi.fn()
vi.mock('@/api/events', () => ({
  useStepEvents: (...args: unknown[]) => mockUseStepEvents(...args),
}))

// Mock useStepInstructions hook
const mockUseStepInstructions = vi.fn()
vi.mock('@/api/pipelines', () => ({
  useStepInstructions: (...args: unknown[]) => mockUseStepInstructions(...args),
}))

// Mock useRunContext hook
const mockUseRunContext = vi.fn()
vi.mock('@/api/runs', () => ({
  useRunContext: (...args: unknown[]) => mockUseRunContext(...args),
}))

const NOW = '2025-06-15T12:00:00.000Z'

/** Helper: find the Sheet content element via data-slot attribute. */
function getSheetContent(): HTMLElement | null {
  return document.querySelector('[data-slot="sheet-content"]')
}

describe('StepDetailPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(NOW))
    mockUseStep.mockReset()
    mockUseStepEvents.mockReset()
    mockUseStepInstructions.mockReset()
    mockUseRunContext.mockReset()
    // Default: events, instructions, and context return empty/idle
    mockUseStepEvents.mockReturnValue({
      data: emptyEventsResponse,
      isLoading: false,
      isError: false,
    })
    mockUseStepInstructions.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    })
    mockUseRunContext.mockReturnValue({
      data: { run_id: 'r1', snapshots: [] },
      isLoading: false,
      isError: false,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders with data-state="closed" when open=false', () => {
    mockUseStep.mockReturnValue({ data: undefined, isLoading: false, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={false}
        onClose={vi.fn()}
      />,
    )
    // Sheet is controlled; when open=false the portal should not render content
    const content = getSheetContent()
    // Radix Dialog does not mount content when open=false by default
    expect(content).toBeNull()
  })

  it('renders panel content when open=true and step loaded', () => {
    vi.useRealTimers()
    mockUseStep.mockReturnValue({ data: mockStepData, isLoading: false, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={vi.fn()}
      />,
    )
    const content = getSheetContent()
    expect(content).not.toBeNull()
    expect(content!.getAttribute('data-state')).toBe('open')

    // Step name visible in header (h3) and metadata area
    const headings = screen.getAllByText('extract')
    expect(headings.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Step 1/)).toBeInTheDocument()
  })

  it('renders all 7 tab triggers when step loaded', () => {
    vi.useRealTimers()
    mockUseStep.mockReturnValue({ data: mockStepData, isLoading: false, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={vi.fn()}
      />,
    )
    const tabList = screen.getByRole('tablist')
    expect(tabList).toBeInTheDocument()

    const tabs = screen.getAllByRole('tab')
    expect(tabs.length).toBe(7)

    // Verify tab trigger values exist (case-insensitive text matching)
    const tabLabels = ['input', 'prompts', 'response', 'instructions', 'context', 'extractions', 'meta']
    for (const label of tabLabels) {
      expect(
        tabs.some((t) => t.textContent?.toLowerCase().includes(label)),
      ).toBe(true)
    }
  })

  it('shows loading skeleton when useStep is loading', () => {
    vi.useRealTimers()
    mockUseStep.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={vi.fn()}
      />,
    )
    // Skeleton uses animate-pulse; query full document (Radix portal)
    const pulsingDivs = document.querySelectorAll('.animate-pulse')
    expect(pulsingDivs.length).toBeGreaterThan(0)
  })

  it('shows error message when useStep errors', () => {
    vi.useRealTimers()
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
    // Sheet's built-in close button has sr-only "Close" text
    const closeBtn = screen.getByRole('button', { name: /close/i })
    await user.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not render StepContent when stepNumber is null', () => {
    vi.useRealTimers()
    mockUseStep.mockReturnValue({ data: undefined, isLoading: false, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={null}
        open={true}
        onClose={vi.fn()}
      />,
    )
    // No step content should render (no step name, no tabs)
    expect(screen.queryByText('extract')).not.toBeInTheDocument()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('calls onClose when Escape key is pressed', async () => {
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
    // Radix Sheet handles Escape natively via onOpenChange
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when overlay is clicked', async () => {
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
    // Sheet overlay is the element with data-slot="sheet-overlay"
    const overlay = document.querySelector('[data-slot="sheet-overlay"]') as HTMLElement
    expect(overlay).toBeTruthy()
    await user.click(overlay)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('switches tab content when a different tab trigger is clicked', async () => {
    vi.useRealTimers()
    mockUseStep.mockReturnValue({ data: mockStepData, isLoading: false, isError: false })
    render(
      <StepDetailPanel
        runId="r1"
        stepNumber={1}
        open={true}
        onClose={vi.fn()}
      />,
    )
    const user = userEvent.setup()
    const tabs = screen.getAllByRole('tab')

    // Find and click "prompts" tab trigger
    const promptsTab = tabs.find((t) => t.textContent?.toLowerCase().includes('prompts'))
    expect(promptsTab).toBeTruthy()
    await user.click(promptsTab!)

    // After click, the prompts tab should be the active one (data-state=active)
    expect(promptsTab!.getAttribute('data-state')).toBe('active')

    // The prompts tab content panel should now be visible
    const tabPanels = screen.getAllByRole('tabpanel')
    expect(tabPanels.length).toBeGreaterThan(0)

    // Click "meta" tab
    const metaTab = tabs.find((t) => t.textContent?.toLowerCase().includes('meta'))
    expect(metaTab).toBeTruthy()
    await user.click(metaTab!)
    expect(metaTab!.getAttribute('data-state')).toBe('active')
    // Previous tab should no longer be active
    expect(promptsTab!.getAttribute('data-state')).not.toBe('active')
  })
})
