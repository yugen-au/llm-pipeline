import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ContextEvolution } from './ContextEvolution'
import type { ContextSnapshot } from '@/api/types'

// Accumulated context shape: each step includes all prior keys plus new ones
const mockSnapshots: ContextSnapshot[] = [
  {
    step_name: 'extract',
    step_number: 1,
    context_snapshot: { input: 'raw data', extracted: true },
  },
  {
    step_name: 'transform',
    step_number: 2,
    context_snapshot: { input: 'raw data', extracted: true, result: 42, tags: ['a', 'b'] },
  },
]

describe('ContextEvolution', () => {
  it('renders step names as headers', () => {
    render(
      <ContextEvolution snapshots={mockSnapshots} isLoading={false} isError={false} />,
    )
    // Headers contain "Step N -- step_name"; use heading role to target h4 only
    const headings = screen.getAllByRole('heading', { level: 4 })
    expect(headings).toHaveLength(2)
    expect(headings[0].textContent).toContain('extract')
    expect(headings[0].textContent).toContain('1')
    expect(headings[1].textContent).toContain('transform')
    expect(headings[1].textContent).toContain('2')
  })

  it('renders addition for first step keys', () => {
    render(
      <ContextEvolution snapshots={mockSnapshots} isLoading={false} isError={false} />,
    )
    // Step 1 gets before={} so all keys render as green CREATE additions
    // JsonDiff renders key names as text nodes; input and extracted appear as additions
    const additionMarkers = screen.getAllByText('+')
    // At minimum step 1's 2 keys (input, extracted) render as additions
    expect(additionMarkers.length).toBeGreaterThanOrEqual(2)
    // Key names are present in the document
    expect(screen.getAllByText((_, el) => el?.tagName === 'SPAN' && el.textContent?.includes('input') === true).length).toBeGreaterThan(0)
    expect(screen.getAllByText((_, el) => el?.tagName === 'SPAN' && el.textContent?.includes('extracted') === true).length).toBeGreaterThan(0)
  })

  it('renders changes between steps', () => {
    render(
      <ContextEvolution snapshots={mockSnapshots} isLoading={false} isError={false} />,
    )
    // Step 2 adds result and tags; those appear as green additions (CREATE)
    // Step 2's context has input/extracted as unchanged (muted) and result/tags as new (green +)
    // getAllByText('+') covers additions across both steps; step 2 adds result and tags
    const additionMarkers = screen.getAllByText('+')
    // step 1: 2 additions (input, extracted); step 2: 2 new keys (result, tags) = at least 4 total
    expect(additionMarkers.length).toBeGreaterThanOrEqual(4)
    // New key names from step 2 are present
    expect(screen.getAllByText((_, el) => el?.tagName === 'SPAN' && el.textContent?.includes('result') === true).length).toBeGreaterThan(0)
    expect(screen.getAllByText((_, el) => el?.tagName === 'SPAN' && el.textContent?.includes('tags') === true).length).toBeGreaterThan(0)
  })

  it('shows loading skeleton with animate-pulse elements', () => {
    const { container } = render(
      <ContextEvolution snapshots={[]} isLoading={true} isError={false} />,
    )
    const pulsingDivs = container.querySelectorAll('.animate-pulse')
    // 3 skeleton blocks x 2 elements each = 6
    expect(pulsingDivs.length).toBe(6)
  })

  it('shows error text when isError', () => {
    render(
      <ContextEvolution snapshots={[]} isLoading={false} isError={true} />,
    )
    const error = screen.getByText('Failed to load context')
    expect(error).toBeInTheDocument()
    expect(error).toHaveClass('text-destructive')
  })

  it('shows empty state message', () => {
    render(
      <ContextEvolution snapshots={[]} isLoading={false} isError={false} />,
    )
    const empty = screen.getByText('No context snapshots')
    expect(empty).toBeInTheDocument()
    expect(empty).toHaveClass('text-muted-foreground')
  })
})
