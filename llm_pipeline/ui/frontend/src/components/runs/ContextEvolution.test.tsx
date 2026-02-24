import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ContextEvolution } from './ContextEvolution'
import type { ContextSnapshot } from '@/api/types'

const mockSnapshots: ContextSnapshot[] = [
  {
    step_name: 'extract',
    step_number: 1,
    context_snapshot: { input: 'raw data', extracted: true },
  },
  {
    step_name: 'transform',
    step_number: 2,
    context_snapshot: { result: 42, tags: ['a', 'b'] },
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

  it('renders JSON snapshots as formatted text', () => {
    render(
      <ContextEvolution snapshots={mockSnapshots} isLoading={false} isError={false} />,
    )
    // Check that the JSON content is rendered
    expect(screen.getByText(/"input": "raw data"/)).toBeInTheDocument()
    expect(screen.getByText(/"result": 42/)).toBeInTheDocument()
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
