import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EventStream } from './EventStream'
import type { EventItem } from '@/api/types'
import type { WsConnectionStatus } from '@/stores/websocket'

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
})
