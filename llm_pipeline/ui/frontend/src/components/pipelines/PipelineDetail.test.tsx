import { render, screen } from '@testing-library/react'
import type { PipelineMetadata, PipelineStrategyMetadata } from '@/api/types'
import { PipelineDetail } from './PipelineDetail'

// Radix ScrollArea uses ResizeObserver internally (not in jsdom)
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

// Mock usePipeline hook
const mockUsePipeline = vi.fn()
vi.mock('@/api/pipelines', () => ({
  usePipeline: (...args: unknown[]) => mockUsePipeline(...args),
}))

// Mock StrategySection to avoid TanStack Router Link dependency
vi.mock('./StrategySection', () => ({
  StrategySection: ({ strategy }: { strategy: PipelineStrategyMetadata }) => (
    <div data-testid={`strategy-${strategy.name}`}>{strategy.display_name}</div>
  ),
}))

// Mock JsonTree to keep assertions simple
vi.mock('./JsonTree', () => ({
  JsonTree: ({ data }: { data: Record<string, unknown> | null }) => (
    <div data-testid="json-tree">
      {data ? Object.keys(data).join(', ') : 'null'}
    </div>
  ),
}))

function makeStrategy(overrides: Partial<PipelineStrategyMetadata> = {}): PipelineStrategyMetadata {
  return {
    name: 'default',
    display_name: 'Default Strategy',
    class_name: 'DefaultStrategy',
    steps: [],
    error: null,
    ...overrides,
  }
}

function makeMetadata(overrides: Partial<PipelineMetadata> = {}): PipelineMetadata {
  return {
    pipeline_name: 'test-pipeline',
    registry_models: ['gemini-2.0-flash'],
    strategies: [makeStrategy()],
    execution_order: ['step_a', 'step_b'],
    pipeline_input_schema: { shipment_id: { type: 'string' } },
    ...overrides,
  }
}

describe('PipelineDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows "Select a pipeline" when pipelineName=null', () => {
    mockUsePipeline.mockReturnValue({ data: undefined, isLoading: false, error: null })
    render(<PipelineDetail pipelineName={null} />)
    expect(screen.getByText(/Select a pipeline/)).toBeInTheDocument()
  })

  it('shows loading skeleton when isLoading=true', () => {
    mockUsePipeline.mockReturnValue({ data: undefined, isLoading: true, error: null })
    const { container } = render(<PipelineDetail pipelineName="test" />)
    const pulses = container.querySelectorAll('.animate-pulse')
    expect(pulses.length).toBeGreaterThan(0)
  })

  it('shows error state when error is set', () => {
    mockUsePipeline.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('not found'),
    })
    render(<PipelineDetail pipelineName="test" />)
    expect(screen.getByText('Failed to load pipeline')).toBeInTheDocument()
  })

  it('renders pipeline name, execution_order, and registry_models badges', () => {
    const metadata = makeMetadata({
      pipeline_name: 'my-pipeline',
      execution_order: ['extract', 'transform'],
      registry_models: ['gemini-2.0-flash', 'gpt-4o'],
    })
    mockUsePipeline.mockReturnValue({ data: metadata, isLoading: false, error: null })
    render(<PipelineDetail pipelineName="my-pipeline" />)

    // Pipeline name heading
    expect(screen.getByText('my-pipeline')).toBeInTheDocument()

    // Execution order badges (prefixed with index)
    expect(screen.getByText('1. extract')).toBeInTheDocument()
    expect(screen.getByText('2. transform')).toBeInTheDocument()

    // Registry model badges
    expect(screen.getByText('gemini-2.0-flash')).toBeInTheDocument()
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
  })

  it('renders JsonTree for pipeline_input_schema', () => {
    const metadata = makeMetadata({
      pipeline_input_schema: { shipment_id: { type: 'string' }, weight: { type: 'number' } },
    })
    mockUsePipeline.mockReturnValue({ data: metadata, isLoading: false, error: null })
    render(<PipelineDetail pipelineName="test" />)

    // Mocked JsonTree renders keys as text
    expect(screen.getByText('shipment_id, weight')).toBeInTheDocument()
    expect(screen.getByText('Input Schema')).toBeInTheDocument()
  })

  it('renders StrategySection for each strategy', () => {
    const metadata = makeMetadata({
      strategies: [
        makeStrategy({ name: 'alpha', display_name: 'Alpha Strategy' }),
        makeStrategy({ name: 'beta', display_name: 'Beta Strategy' }),
      ],
    })
    mockUsePipeline.mockReturnValue({ data: metadata, isLoading: false, error: null })
    render(<PipelineDetail pipelineName="test" />)

    expect(screen.getByText('Alpha Strategy')).toBeInTheDocument()
    expect(screen.getByText('Beta Strategy')).toBeInTheDocument()
    expect(screen.getByTestId('strategy-alpha')).toBeInTheDocument()
    expect(screen.getByTestId('strategy-beta')).toBeInTheDocument()
  })
})
