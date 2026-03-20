import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import type { RunDetail, StepListResponse, EventListResponse, ContextEvolutionResponse } from '@/api/types'

// ---------------------------------------------------------------------------
// Mock @tanstack/react-router: createFileRoute returns a Route with
// useParams/useSearch stubs; Link renders a plain <a>
// ---------------------------------------------------------------------------
vi.mock('@tanstack/react-router', () => ({
  createFileRoute: () => (opts: { component: React.FC; validateSearch?: unknown }) => ({
    ...opts,
    useParams: () => ({ runId: 'r1' }),
    useSearch: () => ({ tab: 'steps' }),
  }),
  Link: ({
    to,
    children,
    className,
  }: {
    to: string
    children: React.ReactNode
    className?: string
  }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}))

// ---------------------------------------------------------------------------
// Mock @tanstack/zod-adapter (used at module level by route definition)
// ---------------------------------------------------------------------------
vi.mock('@tanstack/zod-adapter', () => ({
  fallback: (_schema: unknown, defaultVal: unknown) => ({
    default: () => defaultVal,
  }),
  zodValidator: () => undefined,
}))

// ---------------------------------------------------------------------------
// Mock @/lib/time with deterministic stubs
// ---------------------------------------------------------------------------
vi.mock('@/lib/time', () => ({
  formatRelative: (iso: string) => `relative(${iso})`,
  formatAbsolute: (iso: string) => `absolute(${iso})`,
  formatDuration: (ms: number | null) => (ms == null ? '\u2014' : `${(ms / 1000).toFixed(1)}s`),
}))

// ---------------------------------------------------------------------------
// Mock data hooks
// ---------------------------------------------------------------------------
const mockUseRun = vi.fn()
const mockUseRunContext = vi.fn()
vi.mock('@/api/runs', () => ({
  useRun: (...args: unknown[]) => mockUseRun(...args),
  useRunContext: (...args: unknown[]) => mockUseRunContext(...args),
}))

const mockUseSteps = vi.fn()
vi.mock('@/api/steps', () => ({
  useSteps: (...args: unknown[]) => mockUseSteps(...args),
}))

const mockUseEvents = vi.fn()
vi.mock('@/api/events', () => ({
  useEvents: (...args: unknown[]) => mockUseEvents(...args),
}))

// ---------------------------------------------------------------------------
// Mock useSubscribeRun (no-op)
// ---------------------------------------------------------------------------
vi.mock('@/api/websocket', () => ({
  useSubscribeRun: () => {},
}))

// ---------------------------------------------------------------------------
// Mock useUIStore (direct destructure, no selector)
// ---------------------------------------------------------------------------
const mockSelectStep = vi.fn()
const mockCloseStepDetail = vi.fn()
vi.mock('@/stores/ui', () => ({
  useUIStore: () => ({
    selectedStepId: null,
    stepDetailOpen: false,
    selectStep: mockSelectStep,
    closeStepDetail: mockCloseStepDetail,
  }),
}))

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------
const NOW = '2025-06-15T12:00:00.000Z'

const mockRunDetail: RunDetail = {
  run_id: 'r1-full-uuid-value',
  pipeline_name: 'test-pipeline',
  status: 'completed',
  started_at: '2025-06-15T10:00:00.000Z',
  completed_at: NOW,
  step_count: 2,
  total_time_ms: 3500,
  steps: [
    { step_name: 'extract', step_number: 1, execution_time_ms: 1500, created_at: '2025-06-15T10:00:00.000Z' },
    { step_name: 'transform', step_number: 2, execution_time_ms: 2000, created_at: '2025-06-15T10:01:00.000Z' },
  ],
}

const mockStepsResponse: StepListResponse = {
  items: [
    { step_name: 'extract', step_number: 1, execution_time_ms: 1500, model: 'gemini-2.0-flash', created_at: '2025-06-15T10:00:00.000Z' },
    { step_name: 'transform', step_number: 2, execution_time_ms: 2000, model: 'gemini-2.0-flash', created_at: '2025-06-15T10:01:00.000Z' },
  ],
}

const emptyEventsResponse: EventListResponse = {
  items: [],
  total: 0,
  offset: 0,
  limit: 50,
}

const emptyContextResponse: ContextEvolutionResponse = {
  run_id: 'r1',
  snapshots: [],
}

// ---------------------------------------------------------------------------
// Import component AFTER mocks are set up
// ---------------------------------------------------------------------------
// The Route export is the result of createFileRoute(...)(opts), so Route.component
// is the RunDetailPage function. We render it directly.
// eslint-disable-next-line import/first
import { Route } from './$runId'

const RunDetailPage = Route.component

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('RunDetailPage', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(NOW))
    mockUseRun.mockReset()
    mockUseRunContext.mockReset()
    mockUseSteps.mockReset()
    mockUseEvents.mockReset()
    mockSelectStep.mockClear()
    mockCloseStepDetail.mockClear()

    // Defaults: steps, events, context return empty/idle
    mockUseSteps.mockReturnValue({ data: mockStepsResponse, isLoading: false, isError: false })
    mockUseEvents.mockReturnValue({ data: emptyEventsResponse, isLoading: false, isError: false })
    mockUseRunContext.mockReturnValue({ data: emptyContextResponse, isLoading: false, isError: false })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows loading skeleton when useRun isLoading=true', () => {
    mockUseRun.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    const { container } = render(<RunDetailPage />)
    const pulsingDivs = container.querySelectorAll('.animate-pulse')
    expect(pulsingDivs.length).toBeGreaterThan(0)
  })

  it('shows run ID and status badge when data loaded', () => {
    mockUseRun.mockReturnValue({ data: mockRunDetail, isLoading: false, isError: false })
    render(<RunDetailPage />)
    // Run ID is sliced to 8 chars
    expect(screen.getByText('r1-full-')).toBeInTheDocument()
    // Pipeline name visible
    expect(screen.getByText('test-pipeline')).toBeInTheDocument()
    // Status badge shows "completed" (run header + 2 step rows = 3 badges)
    const completedBadges = screen.getAllByText('completed')
    expect(completedBadges.length).toBeGreaterThanOrEqual(1)
  })

  it('shows error state when useRun isError=true', () => {
    mockUseRun.mockReturnValue({ data: undefined, isLoading: false, isError: true })
    render(<RunDetailPage />)
    expect(screen.getByText('Run not found')).toBeInTheDocument()
  })

  it('renders StepTimeline with steps', () => {
    mockUseRun.mockReturnValue({ data: mockRunDetail, isLoading: false, isError: false })
    render(<RunDetailPage />)
    // StepTimeline renders step names from deriveStepStatus result
    expect(screen.getByText('extract')).toBeInTheDocument()
    expect(screen.getByText('transform')).toBeInTheDocument()
  })

  it('renders back navigation link', () => {
    mockUseRun.mockReturnValue({ data: mockRunDetail, isLoading: false, isError: false })
    render(<RunDetailPage />)
    // Link component is mocked as <a href={to}>; the back link points to "/"
    const backLink = screen.getAllByRole('link').find((el) => el.getAttribute('href') === '/')
    expect(backLink).toBeTruthy()
  })
})
