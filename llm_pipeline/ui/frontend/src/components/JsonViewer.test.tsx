import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { JsonViewer } from './JsonViewer'

// ---------------------------------------------------------------------------
// Data mode (replaces JsonTree tests)
// ---------------------------------------------------------------------------

describe('JsonViewer (data mode)', () => {
  it('renders italic "null" when data=null', () => {
    render(<JsonViewer data={null} />)
    const nullEl = screen.getByText('null')
    expect(nullEl.tagName).toBe('SPAN')
    expect(nullEl).toHaveClass('italic')
    expect(nullEl).toHaveClass('text-muted-foreground')
  })

  it('renders empty tree for empty object {}', () => {
    const { container } = render(<JsonViewer data={{}} />)
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper).toBeInTheDocument()
    expect(wrapper.children).toHaveLength(0)
  })

  it('renders empty tree for empty array []', () => {
    const { container } = render(<JsonViewer data={[]} />)
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper).toBeInTheDocument()
    expect(wrapper.children).toHaveLength(0)
  })

  it('renders primitive values at single level', () => {
    render(<JsonViewer data={{ a: 'str', b: 42, c: true }} />)
    expect(screen.getByText('a:')).toBeInTheDocument()
    expect(screen.getByText('b:')).toBeInTheDocument()
    expect(screen.getByText('c:')).toBeInTheDocument()
    expect(screen.getByText('"str"')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('true')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Diff mode (replaces JsonDiff tests)
// ---------------------------------------------------------------------------

describe('JsonViewer (diff mode)', () => {
  it('shows "No changes" for identical objects', () => {
    const obj = { a: 1, b: 'hello' }
    render(<JsonViewer before={obj} after={obj} />)
    expect(screen.getByText('No changes')).toBeInTheDocument()
  })

  it('shows CREATE entry with + prefix for added key', () => {
    render(<JsonViewer before={{}} after={{ b: 2 }} />)
    expect(screen.getByText('+')).toBeInTheDocument()
    expect(screen.getByText(/b:/)).toBeInTheDocument()
  })

  it('shows REMOVE entry with - prefix for deleted key', () => {
    render(<JsonViewer before={{ a: 1 }} after={{}} />)
    expect(screen.getByText('-')).toBeInTheDocument()
    expect(screen.getByText(/a:/)).toBeInTheDocument()
  })

  it('shows CHANGE entry for modified value', () => {
    render(<JsonViewer before={{ a: 1 }} after={{ a: 2 }} />)
    expect(screen.getByText(/a:/)).toBeInTheDocument()
    const changeRow = screen.getByText(/a:/)
    expect(changeRow.textContent).toContain('1')
    expect(changeRow.textContent).toContain('2')
  })

  it('renders nested object diffs', () => {
    const before = { nested: { x: 1 } }
    const after = { nested: { x: 2 } }
    const { container } = render(<JsonViewer before={before} after={after} />)
    expect(container.querySelector('button')).toBeInTheDocument()
    expect(screen.getByText('nested')).toBeInTheDocument()
  })

  it('expands nested diffs and shows child changes', async () => {
    const before = { nested: { x: 1 } }
    const after = { nested: { x: 2 } }
    render(<JsonViewer before={before} after={after} />)
    // Branch node auto-expands within maxDepth (default 3)
    expect(screen.getByText(/x:/)).toBeInTheDocument()
  })

  it('respects maxDepth prop', () => {
    const before = { a: { b: { c: 1 } } }
    const after = { a: { b: { c: 2 } } }
    const { container } = render(
      <JsonViewer before={before} after={after} maxDepth={1} />,
    )
    expect(container).toBeInTheDocument()
    expect(screen.getByText('a')).toBeInTheDocument()
  })

  it('collapses branch node on click', async () => {
    const user = userEvent.setup()
    const before = { nested: { x: 1 } }
    const after = { nested: { x: 2 } }
    render(<JsonViewer before={before} after={after} />)

    expect(screen.getByText(/x:/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /nested/i }))
    expect(screen.queryByText(/x:/)).not.toBeInTheDocument()
    expect(screen.getByText(/1 change/)).toBeInTheDocument()
  })

  it('renders complex CREATE value as expandable subtree', () => {
    render(<JsonViewer before={{}} after={{ obj: { a: 1, b: 2 } }} />)
    const btn = screen.getByRole('button', { name: /obj/ })
    expect(btn).toBeInTheDocument()
    expect(screen.getByText(/a:/)).toBeInTheDocument()
    expect(screen.getByText(/b:/)).toBeInTheDocument()
  })

  it('renders complex REMOVE value as expandable red subtree', () => {
    render(<JsonViewer before={{ obj: { x: 'hello' } }} after={{}} />)
    const btn = screen.getByRole('button', { name: /obj/ })
    expect(btn).toBeInTheDocument()
    expect(btn.className).toContain('text-red')
    expect(screen.getByText(/x:/)).toBeInTheDocument()
  })

  it('renders complex unchanged value as collapsible muted subtree', () => {
    render(<JsonViewer before={{ meta: { foo: 1 }, a: 1 }} after={{ meta: { foo: 1 }, a: 2 }} />)
    const btn = screen.getByRole('button', { name: /meta/ })
    expect(btn).toBeInTheDocument()
    expect(btn.className).toContain('text-muted-foreground')
    expect(screen.getByText(/foo:/)).toBeInTheDocument()
  })
})
