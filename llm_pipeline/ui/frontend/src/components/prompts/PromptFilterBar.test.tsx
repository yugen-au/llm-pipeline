import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PromptFilterBar } from './PromptFilterBar'

describe('PromptFilterBar', () => {
  const defaultProps = {
    promptTypes: [] as string[],
    pipelineNames: [] as string[],
    selectedType: '',
    selectedPipeline: '',
    onTypeChange: vi.fn(),
    onPipelineChange: vi.fn(),
    searchText: '',
    onSearchChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders search input', () => {
    render(<PromptFilterBar {...defaultProps} />)
    expect(
      screen.getByRole('textbox', { name: /search prompts/i }),
    ).toBeInTheDocument()
  })

  it('calls onSearchChange on input', async () => {
    const onSearchChange = vi.fn()
    const user = userEvent.setup()
    render(<PromptFilterBar {...defaultProps} onSearchChange={onSearchChange} />)

    await user.type(
      screen.getByRole('textbox', { name: /search prompts/i }),
      'hi',
    )

    expect(onSearchChange).toHaveBeenCalledTimes(2)
    expect(onSearchChange).toHaveBeenNthCalledWith(1, 'h')
    expect(onSearchChange).toHaveBeenNthCalledWith(2, 'i')
  })

  it('shows "All types" option in type select', async () => {
    const user = userEvent.setup()
    render(<PromptFilterBar {...defaultProps} />)

    await user.click(
      screen.getByRole('combobox', { name: /filter by prompt type/i }),
    )

    expect(screen.getByRole('option', { name: 'All types' })).toBeInTheDocument()
  })

  it('calls onTypeChange with value on selection', async () => {
    const onTypeChange = vi.fn()
    const user = userEvent.setup()
    render(
      <PromptFilterBar
        {...defaultProps}
        promptTypes={['chat', 'embed']}
        onTypeChange={onTypeChange}
      />,
    )

    await user.click(
      screen.getByRole('combobox', { name: /filter by prompt type/i }),
    )
    await user.click(screen.getByRole('option', { name: 'chat' }))

    expect(onTypeChange).toHaveBeenCalledWith('chat')
  })

  it('shows "All pipelines" option in pipeline select', async () => {
    const user = userEvent.setup()
    render(<PromptFilterBar {...defaultProps} />)

    await user.click(
      screen.getByRole('combobox', { name: /filter by pipeline/i }),
    )

    expect(
      screen.getByRole('option', { name: 'All pipelines' }),
    ).toBeInTheDocument()
  })

  it('calls onPipelineChange with value on selection', async () => {
    const onPipelineChange = vi.fn()
    const user = userEvent.setup()
    render(
      <PromptFilterBar
        {...defaultProps}
        pipelineNames={['ingest', 'transform']}
        onPipelineChange={onPipelineChange}
      />,
    )

    await user.click(
      screen.getByRole('combobox', { name: /filter by pipeline/i }),
    )
    await user.click(screen.getByRole('option', { name: 'ingest' }))

    expect(onPipelineChange).toHaveBeenCalledWith('ingest')
  })

  it('populates type options from promptTypes prop', async () => {
    const user = userEvent.setup()
    render(
      <PromptFilterBar
        {...defaultProps}
        promptTypes={['chat', 'embed']}
      />,
    )

    await user.click(
      screen.getByRole('combobox', { name: /filter by prompt type/i }),
    )

    expect(screen.getByRole('option', { name: 'chat' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'embed' })).toBeInTheDocument()
  })
})
