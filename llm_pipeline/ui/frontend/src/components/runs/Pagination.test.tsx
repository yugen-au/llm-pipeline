import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Pagination } from './Pagination'

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))

describe('Pagination', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
  })

  it('renders correct page label', () => {
    render(<Pagination total={100} page={2} pageSize={25} />)
    expect(screen.getByText('Page 2 of 4')).toBeInTheDocument()
  })

  it('renders correct record range', () => {
    render(<Pagination total={100} page={2} pageSize={25} />)
    expect(screen.getByText('Showing 26-50 of 100')).toBeInTheDocument()
  })

  it('clamps range end to total on last page', () => {
    render(<Pagination total={30} page={2} pageSize={25} />)
    expect(screen.getByText('Showing 26-30 of 30')).toBeInTheDocument()
  })

  it('shows 0-0 range when total is 0', () => {
    render(<Pagination total={0} page={1} pageSize={25} />)
    expect(screen.getByText('Showing 0-0 of 0')).toBeInTheDocument()
  })

  it('disables Previous button on page 1', () => {
    render(<Pagination total={100} page={1} pageSize={25} />)
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  })

  it('enables Previous button when page > 1', () => {
    render(<Pagination total={100} page={2} pageSize={25} />)
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled()
  })

  it('disables Next button on last page', () => {
    render(<Pagination total={100} page={4} pageSize={25} />)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('disables Next button when total is 0', () => {
    render(<Pagination total={0} page={1} pageSize={25} />)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('enables Next button when not on last page', () => {
    render(<Pagination total={100} page={1} pageSize={25} />)
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })

  it('calls navigate with decremented page on Previous click', async () => {
    const user = userEvent.setup()
    render(<Pagination total={100} page={3} pageSize={25} />)

    await user.click(screen.getByRole('button', { name: 'Previous' }))

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    const call = mockNavigate.mock.calls[0][0]
    expect(call.to).toBe('/')
    // search is a function; invoke it with prev state to verify
    expect(call.search({ page: 3, status: '' })).toEqual({ page: 2, status: '' })
  })

  it('calls navigate with incremented page on Next click', async () => {
    const user = userEvent.setup()
    render(<Pagination total={100} page={2} pageSize={25} />)

    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    const call = mockNavigate.mock.calls[0][0]
    expect(call.to).toBe('/')
    expect(call.search({ page: 2, status: '' })).toEqual({ page: 3, status: '' })
  })

  it('shows "Page 1 of 1" when total equals pageSize', () => {
    render(<Pagination total={25} page={1} pageSize={25} />)
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })
})
