import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Pagination } from './Pagination'

describe('Pagination', () => {
  const noop = () => {}

  it('renders correct page label', () => {
    render(<Pagination total={100} page={2} pageSize={25} onPageChange={noop} />)
    expect(screen.getByText('Page 2 of 4')).toBeInTheDocument()
  })

  it('renders correct record range', () => {
    render(<Pagination total={100} page={2} pageSize={25} onPageChange={noop} />)
    expect(screen.getByText('Showing 26-50 of 100')).toBeInTheDocument()
  })

  it('clamps range end to total on last page', () => {
    render(<Pagination total={30} page={2} pageSize={25} onPageChange={noop} />)
    expect(screen.getByText('Showing 26-30 of 30')).toBeInTheDocument()
  })

  it('shows 0-0 range when total is 0', () => {
    render(<Pagination total={0} page={1} pageSize={25} onPageChange={noop} />)
    expect(screen.getByText('Showing 0-0 of 0')).toBeInTheDocument()
  })

  it('disables Previous button on page 1', () => {
    render(<Pagination total={100} page={1} pageSize={25} onPageChange={noop} />)
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  })

  it('enables Previous button when page > 1', () => {
    render(<Pagination total={100} page={2} pageSize={25} onPageChange={noop} />)
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled()
  })

  it('disables Next button on last page', () => {
    render(<Pagination total={100} page={4} pageSize={25} onPageChange={noop} />)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('disables Next button when total is 0', () => {
    render(<Pagination total={0} page={1} pageSize={25} onPageChange={noop} />)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('enables Next button when not on last page', () => {
    render(<Pagination total={100} page={1} pageSize={25} onPageChange={noop} />)
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })

  it('calls onPageChange with decremented page on Previous click', async () => {
    const onPageChange = vi.fn()
    const user = userEvent.setup()
    render(<Pagination total={100} page={3} pageSize={25} onPageChange={onPageChange} />)

    await user.click(screen.getByRole('button', { name: 'Previous' }))

    expect(onPageChange).toHaveBeenCalledTimes(1)
    expect(onPageChange).toHaveBeenCalledWith(2)
  })

  it('calls onPageChange with incremented page on Next click', async () => {
    const onPageChange = vi.fn()
    const user = userEvent.setup()
    render(<Pagination total={100} page={2} pageSize={25} onPageChange={onPageChange} />)

    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(onPageChange).toHaveBeenCalledTimes(1)
    expect(onPageChange).toHaveBeenCalledWith(3)
  })

  it('shows "Page 1 of 1" when total equals pageSize', () => {
    render(<Pagination total={25} page={1} pageSize={25} onPageChange={noop} />)
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })
})
