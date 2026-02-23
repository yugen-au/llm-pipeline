import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders "running" with amber outline styling', () => {
    render(<StatusBadge status="running" />)
    const badge = screen.getByText('running')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('border-amber-500')
    expect(badge).toHaveClass('text-amber-600')
  })

  it('renders "completed" with green outline styling', () => {
    render(<StatusBadge status="completed" />)
    const badge = screen.getByText('completed')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('border-green-500')
    expect(badge).toHaveClass('text-green-600')
  })

  it('renders "failed" with destructive variant', () => {
    render(<StatusBadge status="failed" />)
    const badge = screen.getByText('failed')
    expect(badge).toBeInTheDocument()
    expect(badge.dataset.variant).toBe('destructive')
  })

  it('renders unknown status as fallback with secondary variant', () => {
    render(<StatusBadge status="unknown-state" />)
    const badge = screen.getByText('unknown-state')
    expect(badge).toBeInTheDocument()
    expect(badge.dataset.variant).toBe('secondary')
  })

  it('displays the raw status string as label for all known statuses', () => {
    const { unmount: u1 } = render(<StatusBadge status="running" />)
    expect(screen.getByText('running')).toBeInTheDocument()
    u1()

    const { unmount: u2 } = render(<StatusBadge status="completed" />)
    expect(screen.getByText('completed')).toBeInTheDocument()
    u2()

    const { unmount: u3 } = render(<StatusBadge status="failed" />)
    expect(screen.getByText('failed')).toBeInTheDocument()
    u3()
  })
})
