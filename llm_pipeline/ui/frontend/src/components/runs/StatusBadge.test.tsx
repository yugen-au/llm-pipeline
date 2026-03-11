import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders "running" with semantic outline styling', () => {
    render(<StatusBadge status="running" />)
    const badge = screen.getByText('running')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('border-status-running')
    expect(badge).toHaveClass('text-status-running')
  })

  it('renders "completed" with semantic outline styling', () => {
    render(<StatusBadge status="completed" />)
    const badge = screen.getByText('completed')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('border-status-completed')
    expect(badge).toHaveClass('text-status-completed')
  })

  it('renders "failed" with semantic outline styling', () => {
    render(<StatusBadge status="failed" />)
    const badge = screen.getByText('failed')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('border-status-failed')
    expect(badge).toHaveClass('text-status-failed')
  })

  it('renders "skipped" with semantic outline styling', () => {
    render(<StatusBadge status="skipped" />)
    const badge = screen.getByText('skipped')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('border-status-skipped')
    expect(badge).toHaveClass('text-status-skipped')
  })

  it('renders "pending" with semantic outline styling', () => {
    render(<StatusBadge status="pending" />)
    const badge = screen.getByText('pending')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('border-status-pending')
    expect(badge).toHaveClass('text-status-pending')
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
