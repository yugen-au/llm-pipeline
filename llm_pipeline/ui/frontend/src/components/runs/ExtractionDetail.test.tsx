import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ExtractionDetail } from './ExtractionDetail'
import type { ExtractionCompletedData } from '@/api/types'

vi.mock('@/lib/time', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/time')>()
  return {
    ...actual,
    formatDuration: (ms: number | null) => (ms == null ? '\u2014' : `${(ms / 1000).toFixed(1)}s`),
  }
})

const baseData: ExtractionCompletedData = {
  extraction_class: 'LaneExtraction',
  model_class: 'Lane',
  instance_count: 2,
  execution_time_ms: 150,
}

describe('ExtractionDetail', () => {
  it('renders header with class and model', () => {
    render(<ExtractionDetail data={baseData} />)
    expect(screen.getByText('LaneExtraction')).toBeInTheDocument()
    expect(screen.getByText(/\u2192 Lane/)).toBeInTheDocument()
  })

  it('shows instance_count fallback when no created/updated', () => {
    render(<ExtractionDetail data={baseData} />)
    expect(screen.getByText('2 instances')).toBeInTheDocument()
  })

  it('renders created records as all-green diffs', async () => {
    const user = userEvent.setup()
    const data: ExtractionCompletedData = {
      ...baseData,
      created: [
        { id: 1, name: 'Sydney-Melbourne', origin_city: 'Sydney' },
        { id: 2, name: 'Perth-Adelaide', origin_city: 'Perth' },
      ],
    }
    render(<ExtractionDetail data={data} />)
    expect(screen.getByText('2 created')).toBeInTheDocument()

    // Expand first record -- should show green additions via JsonDiff
    const recordBtn = screen.getByText('Sydney-Melbourne').closest('button')!
    await user.click(recordBtn)
    // All fields render as CREATE (green +)
    const plusMarkers = screen.getAllByText('+')
    expect(plusMarkers.length).toBeGreaterThanOrEqual(3) // id, name, origin_city
  })

  it('renders updated records with color-coded diffs', async () => {
    const user = userEvent.setup()
    const data: ExtractionCompletedData = {
      ...baseData,
      updated: [
        {
          id: 5,
          before: { amount: '100' },
          after: { amount: '200' },
        },
      ],
    }
    render(<ExtractionDetail data={data} />)
    expect(screen.getByText('1 updated')).toBeInTheDocument()

    // Expand updated record
    const recordBtn = screen.getByText('id=5').closest('button')!
    await user.click(recordBtn)

    // JsonDiff shows the change
    expect(screen.getByText(/100/)).toBeInTheDocument()
    expect(screen.getByText(/200/)).toBeInTheDocument()
  })

  it('shows combined summary for mixed created and updated', () => {
    const data: ExtractionCompletedData = {
      ...baseData,
      created: [{ name: 'A' }],
      updated: [{ id: 1, before: { x: 1 }, after: { x: 2 } }],
    }
    render(<ExtractionDetail data={data} />)
    expect(screen.getByText('1 created')).toBeInTheDocument()
    expect(screen.getByText('1 updated')).toBeInTheDocument()
  })

  it('handles missing created/updated gracefully (old events)', () => {
    const oldData = {
      extraction_class: 'RateExtraction',
      model_class: 'Rate',
      instance_count: 5,
      execution_time_ms: 200,
    } as ExtractionCompletedData

    render(<ExtractionDetail data={oldData} />)
    expect(screen.getByText('5 instances')).toBeInTheDocument()
    // No created/updated in summary
    expect(screen.queryByText(/created/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/updated/i)).not.toBeInTheDocument()
  })
})
