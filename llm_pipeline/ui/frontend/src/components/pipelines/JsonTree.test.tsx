import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { JsonTree } from './JsonTree'

describe('JsonTree', () => {
  it('renders italic "null" when data=null', () => {
    render(<JsonTree data={null} />)
    const nullEl = screen.getByText('null')
    expect(nullEl.tagName).toBe('SPAN')
    expect(nullEl).toHaveClass('italic')
    expect(nullEl).toHaveClass('text-muted-foreground')
  })

  it('renders empty tree for empty object {}', () => {
    const { container } = render(<JsonTree data={{}} />)
    // renders wrapper div with no child nodes
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper).toBeInTheDocument()
    expect(wrapper.children).toHaveLength(0)
  })

  it('renders empty tree for empty array []', () => {
    const { container } = render(<JsonTree data={[]} />)
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper).toBeInTheDocument()
    expect(wrapper.children).toHaveLength(0)
  })

  it('renders primitive values at single level', () => {
    render(<JsonTree data={{ a: 'str', b: 42, c: true }} />)
    // all 3 keys visible as labels
    expect(screen.getByText('a:')).toBeInTheDocument()
    expect(screen.getByText('b:')).toBeInTheDocument()
    expect(screen.getByText('c:')).toBeInTheDocument()
    // primitive values rendered by PrimitiveValue
    expect(screen.getByText('"str"')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('true')).toBeInTheDocument()
  })
})
