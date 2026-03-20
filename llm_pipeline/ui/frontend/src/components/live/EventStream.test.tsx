import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { EventStream, getEventSummary, getDisplayData } from './EventStream'
import type { EventItem } from '@/api/types'
import type { WsConnectionStatus } from '@/stores/websocket'

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

vi.mock('@/lib/time', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/time')>()
  return {
    ...actual,
    formatRelative: (iso: string) => `relative(${iso})`,
  }
})

function makeEvent(overrides: Partial<EventItem> = {}): EventItem {
  return {
    event_type: 'step_started',
    pipeline_name: 'test-pipeline',
    run_id: 'r1',
    timestamp: '2025-06-15T10:00:00.000Z',
    event_data: {},
    ...overrides,
  }
}

describe('EventStream', () => {
  it('shows "Waiting for run..." when runId is null', () => {
    render(<EventStream events={[]} wsStatus="idle" runId={null} />)
    expect(screen.getByText('Waiting for run...')).toBeInTheDocument()
  })

  it('shows "No events yet" when events array is empty and runId present', () => {
    render(<EventStream events={[]} wsStatus="idle" runId="r1" />)
    expect(screen.getByText('No events yet')).toBeInTheDocument()
  })

  it('renders event rows when events present', () => {
    const events: EventItem[] = [
      makeEvent({
        event_type: 'step_started',
        timestamp: '2025-06-15T10:00:00.000Z',
        event_data: { step_name: 'extract' },
      }),
      makeEvent({
        event_type: 'step_completed',
        timestamp: '2025-06-15T10:01:00.000Z',
        event_data: { step_name: 'transform' },
      }),
    ]

    render(<EventStream events={events} wsStatus="connected" runId="r1" />)

    // event type badges
    expect(screen.getByText('step_started')).toBeInTheDocument()
    expect(screen.getByText('step_completed')).toBeInTheDocument()

    // step names
    expect(screen.getByText('extract')).toBeInTheDocument()
    expect(screen.getByText('transform')).toBeInTheDocument()

    // deterministic relative timestamps from mock
    expect(screen.getByText('relative(2025-06-15T10:00:00.000Z)')).toBeInTheDocument()
    expect(screen.getByText('relative(2025-06-15T10:01:00.000Z)')).toBeInTheDocument()
  })

  describe('ConnectionIndicator', () => {
    const statuses: [WsConnectionStatus, string][] = [
      ['idle', 'Idle'],
      ['connected', 'Connected'],
      ['error', 'Error'],
      ['connecting', 'Connecting...'],
    ]

    it.each(statuses)(
      'shows "%s" status label as "%s"',
      (status, label) => {
        render(<EventStream events={[]} wsStatus={status} runId={null} />)
        expect(screen.getByText(label)).toBeInTheDocument()
      },
    )
  })

  describe('click-to-expand', () => {
    it('expands event row on click to show event_data', async () => {
      const user = userEvent.setup()
      const events: EventItem[] = [
        makeEvent({
          event_type: 'llm_call_completed',
          event_data: {
            step_name: 'parse',
            model_name: 'gemini-2.0-flash',
            total_tokens: 1500,
            cost_usd: 0.003,
          },
        }),
      ]

      render(<EventStream events={events} wsStatus="connected" runId="r1" />)

      // Detail panel should not exist yet
      expect(screen.queryByTestId('event-detail-0')).not.toBeInTheDocument()

      // Click the event row
      await user.click(screen.getByTestId('event-row-0').firstElementChild!)

      // Detail panel should now be visible with event_data content
      expect(screen.getByTestId('event-detail-0')).toBeInTheDocument()
      expect(screen.getByText('"gemini-2.0-flash"')).toBeInTheDocument()
    })

    it('collapses expanded row on second click', async () => {
      const user = userEvent.setup()
      const events: EventItem[] = [
        makeEvent({
          event_type: 'step_completed',
          event_data: { step_name: 'x', execution_time_ms: 500 },
        }),
      ]

      render(<EventStream events={events} wsStatus="connected" runId="r1" />)

      const rowEl = screen.getByTestId('event-row-0').firstElementChild!

      // Expand
      await user.click(rowEl)
      expect(screen.getByTestId('event-detail-0')).toBeInTheDocument()

      // Collapse
      await user.click(rowEl)
      expect(screen.queryByTestId('event-detail-0')).not.toBeInTheDocument()
    })

    it('clicking different event collapses previous', async () => {
      const user = userEvent.setup()
      const events: EventItem[] = [
        makeEvent({
          event_type: 'step_completed',
          timestamp: '2025-06-15T10:00:00.000Z',
          event_data: { step_name: 'a', execution_time_ms: 100 },
        }),
        makeEvent({
          event_type: 'step_completed',
          timestamp: '2025-06-15T10:01:00.000Z',
          event_data: { step_name: 'b', execution_time_ms: 200 },
        }),
      ]

      render(<EventStream events={events} wsStatus="connected" runId="r1" />)

      // Expand first
      await user.click(screen.getByTestId('event-row-0').firstElementChild!)
      expect(screen.getByTestId('event-detail-0')).toBeInTheDocument()

      // Expand second -- first should collapse
      await user.click(screen.getByTestId('event-row-1').firstElementChild!)
      expect(screen.queryByTestId('event-detail-0')).not.toBeInTheDocument()
      expect(screen.getByTestId('event-detail-1')).toBeInTheDocument()
    })

    it('does not show expand affordance for events with no displayable data', () => {
      const events: EventItem[] = [
        makeEvent({ event_data: {} }),
        makeEvent({ event_data: { step_name: 'only-redundant' } }),
      ]

      render(<EventStream events={events} wsStatus="connected" runId="r1" />)

      // Neither row should have role=button (no expandable data)
      const row0 = screen.getByTestId('event-row-0').firstElementChild!
      const row1 = screen.getByTestId('event-row-1').firstElementChild!
      expect(row0).not.toHaveAttribute('role', 'button')
      expect(row1).not.toHaveAttribute('role', 'button')
    })
  })
})

describe('getEventSummary', () => {
  it('returns type-specific fields for step_completed', () => {
    const event = makeEvent({
      event_type: 'step_completed',
      event_data: { step_number: 2, execution_time_ms: 450, total_tokens: 800, cost_usd: 0.01 },
    })
    const lines = getEventSummary(event)
    expect(lines).toEqual([
      'step_number: 2',
      'execution_time_ms: 450',
      'total_tokens: 800',
      'cost_usd: 0.01',
    ])
  })

  it('includes validation_errors count for llm_call_completed', () => {
    const event = makeEvent({
      event_type: 'llm_call_completed',
      event_data: {
        call_index: 0,
        model_name: 'gemini-2.0-flash',
        total_tokens: 1000,
        cost_usd: 0.002,
        attempt_count: 1,
        validation_errors: ['field X missing', 'wrong type'],
      },
    })
    const lines = getEventSummary(event)
    expect(lines).toContain('validation_errors: 2')
  })

  it('falls back to first 4 non-redundant keys for unknown event type', () => {
    const event = makeEvent({
      event_type: 'custom_event',
      event_data: { event_type: 'skip', foo: 1, bar: 'hi', baz: true, qux: null, extra: 5 },
    })
    const lines = getEventSummary(event)
    expect(lines).toHaveLength(4)
    expect(lines[0]).toBe('foo: 1')
  })

  it('returns empty array for empty event_data', () => {
    expect(getEventSummary(makeEvent({ event_data: {} }))).toEqual([])
  })
})

describe('getDisplayData', () => {
  it('filters redundant keys from event_data', () => {
    const event = makeEvent({
      event_data: {
        event_type: 'step_started',
        run_id: 'r1',
        pipeline_name: 'test',
        timestamp: '...',
        step_name: 'x',
        model_name: 'gemini',
        total_tokens: 500,
      },
    })
    const data = getDisplayData(event)
    expect(data).toEqual({ model_name: 'gemini', total_tokens: 500 })
  })
})
