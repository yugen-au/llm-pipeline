import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { StepTimeline, deriveStepStatus } from './StepTimeline'
import type { StepTimelineItem } from './StepTimeline'
import type { StepListItem, EventItem } from '@/api/types'

const NOW = '2025-06-15T12:00:00.000Z'

const mockItems: StepTimelineItem[] = [
  {
    step_name: 'extract',
    step_number: 1,
    status: 'completed',
    execution_time_ms: 1500,
    model: 'gemini-2.0-flash',
  },
  {
    step_name: 'transform',
    step_number: 2,
    status: 'running',
    execution_time_ms: null,
    model: null,
  },
]

const noop = vi.fn()

describe('StepTimeline', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(NOW))
    noop.mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders step rows with name, number, status, and duration', () => {
    render(
      <StepTimeline
        items={mockItems}
        isLoading={false}
        isError={false}
        selectedStepId={null}
        onSelectStep={noop}
      />,
    )
    expect(screen.getByText('extract')).toBeInTheDocument()
    expect(screen.getByText('transform')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(screen.getByText('running')).toBeInTheDocument()
    expect(screen.getByText('1.5s')).toBeInTheDocument()
  })

  it('renders model text when present', () => {
    render(
      <StepTimeline
        items={mockItems}
        isLoading={false}
        isError={false}
        selectedStepId={null}
        onSelectStep={noop}
      />,
    )
    expect(screen.getByText('gemini-2.0-flash')).toBeInTheDocument()
  })

  it('shows loading skeleton with animate-pulse elements', () => {
    const { container } = render(
      <StepTimeline
        items={[]}
        isLoading={true}
        isError={false}
        selectedStepId={null}
        onSelectStep={noop}
      />,
    )
    const pulsingDivs = container.querySelectorAll('.animate-pulse')
    // 4 skeleton rows x 4 elements each = 16
    expect(pulsingDivs.length).toBe(16)
  })

  it('shows error text when isError', () => {
    render(
      <StepTimeline
        items={[]}
        isLoading={false}
        isError={true}
        selectedStepId={null}
        onSelectStep={noop}
      />,
    )
    const error = screen.getByText('Failed to load steps')
    expect(error).toBeInTheDocument()
    expect(error).toHaveClass('text-destructive')
  })

  it('shows empty state message', () => {
    render(
      <StepTimeline
        items={[]}
        isLoading={false}
        isError={false}
        selectedStepId={null}
        onSelectStep={noop}
      />,
    )
    const empty = screen.getByText('No steps recorded')
    expect(empty).toBeInTheDocument()
    expect(empty).toHaveClass('text-muted-foreground')
  })

  it('highlights selected step with bg-muted/50 class', () => {
    render(
      <StepTimeline
        items={mockItems}
        isLoading={false}
        isError={false}
        selectedStepId={1}
        onSelectStep={noop}
      />,
    )
    const selectedButton = screen.getByText('extract').closest('button')!
    expect(selectedButton.className).toContain('bg-muted/50')
  })

  it('calls onSelectStep with step_number on row click', async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <StepTimeline
        items={mockItems}
        isLoading={false}
        isError={false}
        selectedStepId={null}
        onSelectStep={onSelect}
      />,
    )

    const row = screen.getByText('extract').closest('button')!
    await user.click(row)

    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith(1)
  })
})

// ---------------------------------------------------------------------------
// deriveStepStatus unit tests
// ---------------------------------------------------------------------------

describe('deriveStepStatus', () => {
  it('marks DB steps as completed by default', () => {
    const dbSteps: StepListItem[] = [
      {
        step_name: 'extract',
        step_number: 1,
        execution_time_ms: 500,
        model: 'gemini',
        created_at: NOW,
      },
    ]
    const result = deriveStepStatus(dbSteps, [])
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('completed')
    expect(result[0].step_name).toBe('extract')
  })

  it('returns empty array for empty inputs', () => {
    const result = deriveStepStatus([], [])
    expect(result).toEqual([])
  })

  it('marks step as running when step_started event has no matching completion', () => {
    const events: EventItem[] = [
      {
        event_type: 'step_started',
        pipeline_name: 'test',
        run_id: 'r1',
        timestamp: NOW,
        event_data: { step_name: 'transform', step_number: 2 },
      },
    ]
    const result = deriveStepStatus([], events)
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('running')
    expect(result[0].step_name).toBe('transform')
    expect(result[0].step_number).toBe(2)
  })

  it('does not mark step as running if step_completed event exists', () => {
    const events: EventItem[] = [
      {
        event_type: 'step_started',
        pipeline_name: 'test',
        run_id: 'r1',
        timestamp: NOW,
        event_data: { step_name: 'extract', step_number: 1 },
      },
      {
        event_type: 'step_completed',
        pipeline_name: 'test',
        run_id: 'r1',
        timestamp: NOW,
        event_data: { step_name: 'extract', step_number: 1 },
      },
    ]
    const result = deriveStepStatus([], events)
    // started + completed -> not added as running, and not in DB -> empty
    expect(result).toHaveLength(0)
  })

  it('marks step as skipped from step_skipped event', () => {
    const dbSteps: StepListItem[] = [
      {
        step_name: 'optional-step',
        step_number: 3,
        execution_time_ms: null,
        model: null,
        created_at: NOW,
      },
    ]
    const events: EventItem[] = [
      {
        event_type: 'step_skipped',
        pipeline_name: 'test',
        run_id: 'r1',
        timestamp: NOW,
        event_data: { step_name: 'optional-step', step_number: 3 },
      },
    ]
    const result = deriveStepStatus(dbSteps, events)
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('skipped')
  })

  it('marks step as failed from step_failed event', () => {
    const dbSteps: StepListItem[] = [
      {
        step_name: 'fragile-step',
        step_number: 2,
        execution_time_ms: 100,
        model: 'gemini',
        created_at: NOW,
      },
    ]
    const events: EventItem[] = [
      {
        event_type: 'step_failed',
        pipeline_name: 'test',
        run_id: 'r1',
        timestamp: NOW,
        event_data: { step_name: 'fragile-step', step_number: 2 },
      },
    ]
    const result = deriveStepStatus(dbSteps, events)
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('failed')
  })

  it('sorts result by step_number ascending', () => {
    const dbSteps: StepListItem[] = [
      {
        step_name: 'second',
        step_number: 2,
        execution_time_ms: 200,
        model: null,
        created_at: NOW,
      },
      {
        step_name: 'first',
        step_number: 1,
        execution_time_ms: 100,
        model: null,
        created_at: NOW,
      },
    ]
    const result = deriveStepStatus(dbSteps, [])
    expect(result[0].step_number).toBe(1)
    expect(result[1].step_number).toBe(2)
  })
})
