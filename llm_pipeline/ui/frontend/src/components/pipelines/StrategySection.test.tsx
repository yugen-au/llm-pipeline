import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StrategySection } from './StrategySection'
import type { PipelineStrategyMetadata } from '@/api/types'

// Mock @tanstack/react-router: Link renders a plain <a> stub
vi.mock('@tanstack/react-router', () => ({
  Link: (props: { children: React.ReactNode; to?: string }) => (
    <a href={props.to}>{props.children}</a>
  ),
}))

const makeStrategy = (
  overrides: Partial<PipelineStrategyMetadata> = {},
): PipelineStrategyMetadata => ({
  name: 'default',
  display_name: 'Default Strategy',
  class_name: 'DefaultStrategy',
  steps: [],
  error: null,
  ...overrides,
})

describe('StrategySection', () => {
  it('renders without crashing (smoke)', () => {
    const { container } = render(
      <StrategySection strategy={makeStrategy()} pipelineName="test-pipe" />,
    )
    expect(container).toBeTruthy()
  })

  it('renders strategy display_name', () => {
    render(
      <StrategySection
        strategy={makeStrategy({ display_name: 'My Custom Strategy' })}
        pipelineName="test-pipe"
      />,
    )
    expect(screen.getByText('My Custom Strategy')).toBeInTheDocument()
  })

  it('shows error badge when strategy.error is set', () => {
    render(
      <StrategySection
        strategy={makeStrategy({ error: 'Failed to load strategy config' })}
        pipelineName="test-pipe"
      />,
    )
    expect(screen.getByText('error')).toBeInTheDocument()
    expect(screen.getByText('Failed to load strategy config')).toBeInTheDocument()
  })
})
