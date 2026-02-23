import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterBar } from './FilterBar'

describe('FilterBar', () => {
  const defaultProps = {
    status: '',
    onStatusChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a status label and select trigger', () => {
    render(<FilterBar {...defaultProps} />)
    expect(screen.getByText('Status')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /status/i })).toBeInTheDocument()
  })

  it('shows "All" when status is empty string', () => {
    render(<FilterBar {...defaultProps} status="" />)
    expect(screen.getByRole('combobox', { name: /status/i })).toHaveTextContent('All')
  })

  it('shows current status value when set', () => {
    render(<FilterBar {...defaultProps} status="running" />)
    expect(screen.getByRole('combobox', { name: /status/i })).toHaveTextContent('Running')
  })

  it('renders all 4 options when opened', async () => {
    const user = userEvent.setup()
    render(<FilterBar {...defaultProps} />)

    await user.click(screen.getByRole('combobox', { name: /status/i }))

    expect(screen.getByRole('option', { name: 'All' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Running' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Completed' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Failed' })).toBeInTheDocument()
  })

  it('calls onStatusChange with status value on selection', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<FilterBar status="" onStatusChange={onChange} />)

    await user.click(screen.getByRole('combobox', { name: /status/i }))
    await user.click(screen.getByRole('option', { name: 'Failed' }))

    expect(onChange).toHaveBeenCalledWith('failed')
  })

  it('calls onStatusChange with empty string when "All" selected', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<FilterBar status="running" onStatusChange={onChange} />)

    await user.click(screen.getByRole('combobox', { name: /status/i }))
    await user.click(screen.getByRole('option', { name: 'All' }))

    expect(onChange).toHaveBeenCalledWith('')
  })
})
