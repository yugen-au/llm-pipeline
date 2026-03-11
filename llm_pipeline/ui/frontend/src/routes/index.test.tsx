import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, beforeEach, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks (vi.hoisted so they're available inside vi.mock factories)
// ---------------------------------------------------------------------------

const { mockNavigate, mockUseSearch, mockUseRuns } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockUseSearch: vi.fn(() => ({ page: 1, status: '' })),
  mockUseRuns: vi.fn(),
}))

vi.mock('@tanstack/react-router', () => ({
  createFileRoute: () => (opts: Record<string, unknown>) => ({
    ...opts,
    useSearch: mockUseSearch,
  }),
  useNavigate: () => mockNavigate,
}))

vi.mock('@tanstack/zod-adapter', () => ({
  fallback: (_schema: unknown, defaultVal: unknown) => ({
    default: () => defaultVal,
  }),
  zodValidator: () => undefined,
}))

vi.mock('@/api/runs', () => ({
  useRuns: (...args: unknown[]) => mockUseRuns(...args),
}))

vi.mock('@/stores/filters', () => ({
  useFiltersStore: () => ({
    pipelineName: null,
    startedAfter: null,
    startedBefore: null,
  }),
}))

// Mock time utils so RunsTable doesn't produce flaky output
vi.mock('@/lib/time', () => ({
  formatRelative: (iso: string) => `relative(${iso})`,
  formatAbsolute: (iso: string) => `absolute(${iso})`,
  formatDuration: (ms: number | null) => (ms != null ? `${ms / 1000}s` : '\u2014'),
}))

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import { Route } from './index'
import type { RunListItem } from '@/api/types'

// Extract the page component from the mocked Route object
const RunListPage = (Route as unknown as { component: React.ComponentType }).component

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TWO_RUNS: RunListItem[] = [
  {
    run_id: 'aaaaaaaa-1111-2222-3333-444444444444',
    pipeline_name: 'pipeline-alpha',
    status: 'completed',
    started_at: '2025-06-15T10:00:00.000Z',
    completed_at: '2025-06-15T11:00:00.000Z',
    step_count: 3,
    total_time_ms: 1500,
  },
  {
    run_id: 'bbbbbbbb-5555-6666-7777-888888888888',
    pipeline_name: 'pipeline-beta',
    status: 'running',
    started_at: '2025-06-15T11:00:00.000Z',
    completed_at: null,
    step_count: null,
    total_time_ms: null,
  },
]

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RunListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseSearch.mockReturnValue({ page: 1, status: '' })
    mockUseRuns.mockReturnValue({ data: undefined, isLoading: false, isError: false })
  })

  it('renders "Pipeline Runs" heading', () => {
    render(<RunListPage />)
    expect(screen.getByRole('heading', { name: /pipeline runs/i })).toBeInTheDocument()
  })

  it('shows loading skeleton when useRuns isLoading=true', () => {
    mockUseRuns.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    const { container } = render(<RunListPage />)
    const pulsingEls = container.querySelectorAll('.animate-pulse')
    expect(pulsingEls.length).toBeGreaterThan(0)
  })

  it('shows error state when useRuns isError=true', () => {
    mockUseRuns.mockReturnValue({ data: undefined, isLoading: false, isError: true })
    render(<RunListPage />)
    expect(screen.getByText('Failed to load runs')).toBeInTheDocument()
  })

  it('renders runs table when data present', () => {
    mockUseRuns.mockReturnValue({
      data: { items: TWO_RUNS, total: 2, offset: 0, limit: 25 },
      isLoading: false,
      isError: false,
    })
    render(<RunListPage />)
    expect(screen.getByText('pipeline-alpha')).toBeInTheDocument()
    expect(screen.getByText('pipeline-beta')).toBeInTheDocument()
    // Truncated run IDs (first 8 chars)
    expect(screen.getByText('aaaaaaaa')).toBeInTheDocument()
    expect(screen.getByText('bbbbbbbb')).toBeInTheDocument()
  })

  it('calls navigate on status filter change', async () => {
    const user = userEvent.setup()
    render(<RunListPage />)

    // Open the status select and pick "Failed"
    await user.click(screen.getByRole('combobox', { name: /status/i }))
    await user.click(screen.getByRole('option', { name: 'Failed' }))

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({
        to: '/',
        search: expect.any(Function),
      }),
    )
    // Verify the search function produces correct params
    const searchFn = mockNavigate.mock.calls[0][0].search
    expect(searchFn({ page: 3, status: '' })).toEqual({ page: 1, status: 'failed' })
  })

  it('calls navigate on pagination change', async () => {
    mockUseRuns.mockReturnValue({
      data: { items: TWO_RUNS, total: 100, offset: 0, limit: 25 },
      isLoading: false,
      isError: false,
    })
    const user = userEvent.setup()
    render(<RunListPage />)

    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({
        to: '/',
        search: expect.any(Function),
      }),
    )
    // Verify the search function increments page
    const searchFn = mockNavigate.mock.calls[0][0].search
    expect(searchFn({ page: 1, status: 'running' })).toEqual({ page: 2, status: 'running' })
  })
})
