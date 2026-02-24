import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { RunsTable } from './RunsTable'
import type { RunListItem } from '@/api/types'

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))

// Mock formatRelative/formatAbsolute to avoid flaky time-dependent output.
// formatDuration uses real implementation for rendered-value assertions.
vi.mock('@/lib/time', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/time')>()
  return {
    ...actual,
    formatRelative: (iso: string) => `relative(${iso})`,
    formatAbsolute: (iso: string) => `absolute(${iso})`,
  }
})

// Fixed "now" so mock dates are self-documenting regardless of when tests run
const NOW = '2025-06-15T12:00:00.000Z'
const ONE_HOUR_AGO = '2025-06-15T11:00:00.000Z'
const TWO_HOURS_AGO = '2025-06-15T10:00:00.000Z'

const mockRuns: RunListItem[] = [
  {
    run_id: 'abcdef12-3456-7890-abcd-ef1234567890',
    pipeline_name: 'test-pipeline',
    status: 'completed',
    started_at: TWO_HOURS_AGO,
    completed_at: ONE_HOUR_AGO,
    step_count: 3,
    total_time_ms: 1500,
  },
  {
    run_id: '11223344-5566-7788-99aa-bbccddeeff00',
    pipeline_name: 'other-pipeline',
    status: 'running',
    started_at: ONE_HOUR_AGO,
    completed_at: null,
    step_count: null,
    total_time_ms: null,
  },
]

describe('RunsTable', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(NOW))
    mockNavigate.mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders column headers', () => {
    render(<RunsTable runs={[]} isLoading={false} isError={false} />)
    expect(screen.getByText('Run ID')).toBeInTheDocument()
    expect(screen.getByText('Pipeline')).toBeInTheDocument()
    expect(screen.getByText('Started')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
    expect(screen.getByText('Steps')).toBeInTheDocument()
    expect(screen.getByText('Duration')).toBeInTheDocument()
  })

  it('renders run rows with truncated run ID', () => {
    render(<RunsTable runs={mockRuns} isLoading={false} isError={false} />)
    // First 8 chars of run_id
    expect(screen.getByText('abcdef12')).toBeInTheDocument()
    expect(screen.getByText('11223344')).toBeInTheDocument()
  })

  it('renders pipeline names', () => {
    render(<RunsTable runs={mockRuns} isLoading={false} isError={false} />)
    expect(screen.getByText('test-pipeline')).toBeInTheDocument()
    expect(screen.getByText('other-pipeline')).toBeInTheDocument()
  })

  it('renders relative timestamps via formatRelative', () => {
    render(<RunsTable runs={mockRuns} isLoading={false} isError={false} />)
    expect(screen.getByText(`relative(${TWO_HOURS_AGO})`)).toBeInTheDocument()
    expect(screen.getByText(`relative(${ONE_HOUR_AGO})`)).toBeInTheDocument()
  })

  it('shows StatusBadge with correct status text', () => {
    render(<RunsTable runs={mockRuns} isLoading={false} isError={false} />)
    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(screen.getByText('running')).toBeInTheDocument()
  })

  it('renders step count or em dash for null', () => {
    render(<RunsTable runs={mockRuns} isLoading={false} isError={false} />)
    expect(screen.getByText('3')).toBeInTheDocument()
    // Second run has both step_count=null and total_time_ms=null -> 2 em dashes
    const dashes = screen.getAllByText('\u2014')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('renders duration formatted as seconds', () => {
    render(<RunsTable runs={mockRuns} isLoading={false} isError={false} />)
    expect(screen.getByText('1.5s')).toBeInTheDocument()
  })

  it('navigates on row click', async () => {
    // Radix Tooltip uses internal timers that deadlock with fake timers
    // during pointer events, so restore real timers for this interaction test
    vi.useRealTimers()
    const user = userEvent.setup()
    render(<RunsTable runs={mockRuns} isLoading={false} isError={false} />)

    // Click first data row (contains "test-pipeline")
    const row = screen.getByText('test-pipeline').closest('tr')!
    await user.click(row)

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/runs/$runId',
      params: { runId: 'abcdef12-3456-7890-abcd-ef1234567890' },
    })
  })

  it('shows loading skeleton when isLoading', () => {
    const { container } = render(
      <RunsTable runs={[]} isLoading={true} isError={false} />,
    )
    const pulsingDivs = container.querySelectorAll('.animate-pulse')
    // 5 skeleton rows x 6 columns = 30 pulsing cells
    expect(pulsingDivs.length).toBe(30)
  })

  it('shows error message when isError', () => {
    render(<RunsTable runs={[]} isLoading={false} isError={true} />)
    const errorCell = screen.getByText('Failed to load runs')
    expect(errorCell).toBeInTheDocument()
    expect(errorCell).toHaveClass('text-destructive')
  })

  it('shows empty state when runs is empty array', () => {
    render(<RunsTable runs={[]} isLoading={false} isError={false} />)
    const emptyCell = screen.getByText('No runs found')
    expect(emptyCell).toBeInTheDocument()
    expect(emptyCell).toHaveClass('text-muted-foreground')
  })

  it('applies cursor-pointer class on data rows', () => {
    render(<RunsTable runs={mockRuns} isLoading={false} isError={false} />)
    const row = screen.getByText('test-pipeline').closest('tr')!
    expect(row).toHaveClass('cursor-pointer')
  })
})
