import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { JsonDiff } from './JsonDiff'

describe('JsonDiff', () => {
  it('shows "No changes" for identical objects', () => {
    const obj = { a: 1, b: 'hello' }
    render(<JsonDiff before={obj} after={obj} />)
    expect(screen.getByText('No changes')).toBeInTheDocument()
  })

  it('shows CREATE entry with + prefix for added key', () => {
    render(<JsonDiff before={{}} after={{ b: 2 }} />)
    expect(screen.getByText('+')).toBeInTheDocument()
    expect(screen.getByText(/b:/)).toBeInTheDocument()
  })

  it('shows REMOVE entry with - prefix for deleted key', () => {
    render(<JsonDiff before={{ a: 1 }} after={{}} />)
    expect(screen.getByText('-')).toBeInTheDocument()
    expect(screen.getByText(/a:/)).toBeInTheDocument()
  })

  it('shows CHANGE entry for modified value', () => {
    render(<JsonDiff before={{ a: 1 }} after={{ a: 2 }} />)
    // Both old and new values should be visible in the change row
    expect(screen.getByText(/a:/)).toBeInTheDocument()
    // The arrow entity renders as the unicode right arrow character
    const changeRow = screen.getByText(/a:/)
    expect(changeRow.textContent).toContain('1')
    expect(changeRow.textContent).toContain('2')
  })

  it('renders nested object diffs', () => {
    const before = { nested: { x: 1 } }
    const after = { nested: { x: 2 } }
    // Should render without crashing and show the branch node
    const { container } = render(<JsonDiff before={before} after={after} />)
    expect(container.querySelector('button')).toBeInTheDocument()
    expect(screen.getByText('nested')).toBeInTheDocument()
  })

  it('expands nested diffs and shows child changes', async () => {
    const user = userEvent.setup()
    const before = { nested: { x: 1 } }
    const after = { nested: { x: 2 } }
    render(<JsonDiff before={before} after={after} />)

    // Branch node auto-expands within maxDepth (default 3), so child should be visible
    expect(screen.getByText(/x:/)).toBeInTheDocument()
  })

  it('respects maxDepth prop', () => {
    const before = { a: { b: { c: 1 } } }
    const after = { a: { b: { c: 2 } } }
    // With maxDepth=1, only first level branch auto-expands
    const { container } = render(
      <JsonDiff before={before} after={after} maxDepth={1} />,
    )
    // Component should render without error
    expect(container).toBeInTheDocument()
    // Top-level branch "a" should be visible
    expect(screen.getByText('a')).toBeInTheDocument()
  })

  it('collapses branch node on click', async () => {
    const user = userEvent.setup()
    const before = { nested: { x: 1 } }
    const after = { nested: { x: 2 } }
    render(<JsonDiff before={before} after={after} />)

    // Initially expanded (within maxDepth), child visible
    expect(screen.getByText(/x:/)).toBeInTheDocument()

    // Click the branch button to collapse
    await user.click(screen.getByRole('button', { name: /nested/i }))

    // Child should no longer be visible
    expect(screen.queryByText(/x:/)).not.toBeInTheDocument()
    // Should show change count instead
    expect(screen.getByText(/1 change/)).toBeInTheDocument()
  })
})
