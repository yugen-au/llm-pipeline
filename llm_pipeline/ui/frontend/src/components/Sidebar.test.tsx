import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { Sidebar } from './Sidebar'

// ---------------------------------------------------------------------------
// Mock @tanstack/react-router: Link renders a plain <a>
// ---------------------------------------------------------------------------
vi.mock('@tanstack/react-router', () => ({
  Link: ({
    to,
    children,
    className,
  }: {
    to: string
    children: React.ReactNode
    className?: string
    activeProps?: Record<string, unknown>
    inactiveProps?: Record<string, unknown>
  }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}))

// ---------------------------------------------------------------------------
// Mock useMediaQuery: default desktop (false = not below lg)
// ---------------------------------------------------------------------------
vi.mock('@/hooks/use-media-query', () => ({
  useMediaQuery: () => false,
}))

// ---------------------------------------------------------------------------
// Mock useUIStore (Zustand selector pattern)
// ---------------------------------------------------------------------------
const mockToggleSidebar = vi.fn()
vi.mock('@/stores/ui', () => ({
  useUIStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      sidebarCollapsed: false,
      toggleSidebar: mockToggleSidebar,
    }),
}))

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without crashing (smoke)', () => {
    const { container } = render(<Sidebar />)
    expect(container).toBeTruthy()
  })

  it('shows 4 navigation items', () => {
    render(<Sidebar />)
    // The desktop sidebar nav has role="list" containing the 4 items
    const links = screen.getAllByRole('link')
    // Desktop aside renders 4 links; mobile Sheet may add 4 more if open,
    // but Sheet content is hidden by default. Expect at least 4.
    expect(links.length).toBeGreaterThanOrEqual(4)

    // Verify the expected labels exist in the document
    expect(screen.getAllByText('Runs').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Live').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Prompts').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Pipelines').length).toBeGreaterThanOrEqual(1)
  })
})
