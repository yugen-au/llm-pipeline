# Step 2 Research: Vitest & Testing Library Patterns

## 1. Current Test Infrastructure

### Vitest Configuration (`vitest.config.ts`)
```typescript
import path from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules'],
  },
})
```

**Key points:**
- `globals: true` -- `describe`, `it`, `expect`, `vi` available without import (backed by `vitest/globals` in tsconfig types)
- `environment: 'jsdom'` -- simulates DOM for all tests
- `setupFiles` runs `src/test/setup.ts` before each test file
- Path alias `@/` resolves to `./src/`

### Setup File (`src/test/setup.ts`)
```typescript
import '@testing-library/jest-dom/vitest'

// Polyfill pointer capture APIs missing in jsdom (required by Radix UI)
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {}
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {}
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
```

**Key points:**
- Imports `@testing-library/jest-dom/vitest` for custom matchers (`toBeInTheDocument`, `toHaveClass`, etc.)
- Polyfills jsdom gaps required by Radix UI components (pointer capture, scrollIntoView)
- No additional setup for React or TanStack Query (all handled per-test via mocking)

### TypeScript Configuration (`tsconfig.app.json`)
```json
{
  "compilerOptions": {
    "types": ["vite/client", "vitest/globals", "@testing-library/jest-dom/vitest"]
  }
}
```

- Type declarations for vitest globals and jest-dom matchers are already included.

### Package.json Scripts
```json
{
  "test": "vitest",
  "test:coverage": "vitest run --coverage"
}
```

## 2. Installed Dependencies

### All Required Test Dependencies Present

| Package | Version | Purpose |
|---------|---------|---------|
| `vitest` | `^3.2.1` | Test runner |
| `jsdom` | `^26.1.0` | DOM environment |
| `@testing-library/react` | `^16.3.0` | React render/query utilities |
| `@testing-library/dom` | `^10.4.1` | DOM query utilities |
| `@testing-library/jest-dom` | `^6.6.3` | Custom DOM matchers |
| `@testing-library/user-event` | `^14.6.1` | User interaction simulation |
| `@vitest/coverage-v8` | `^3.2.1` | Coverage reporting |

**No additional packages need to be installed.** The test infrastructure is complete.

## 3. Existing Test Files

| File | Type | Tests | Status |
|------|------|-------|--------|
| `src/test/smoke.test.ts` | Infra smoke | 2 | Passing |
| `src/lib/time.test.ts` | Pure utility | 16 | Passing |
| `src/components/runs/RunsTable.test.tsx` | Component | 12 | Passing |
| `src/components/runs/StepTimeline.test.tsx` | Component + unit | 16 | Passing |
| `src/components/runs/StatusBadge.test.tsx` | Component | 5 | **3 FAILING** |
| `src/components/runs/FilterBar.test.tsx` | Component | 6 | Passing |
| `src/components/runs/Pagination.test.tsx` | Component | 11 | Passing |
| `src/components/runs/StepDetailPanel.test.tsx` | Component | 11 | Passing |
| `src/components/runs/ContextEvolution.test.tsx` | Component | 6 | Passing |

**Total: 9 files, 88 passing, 3 failing**

### StatusBadge Test Failures (Known Issue)

The component was refactored from hardcoded Tailwind colors to semantic CSS custom properties:
- **Before:** `border-green-500`, `text-green-600`, `variant="destructive"`
- **After:** `border-status-completed`, `text-status-completed`, `variant="outline"`

Tests still assert old classes. 3 assertions fail:
1. `'completed'` -- expects `border-green-500` / `text-green-600`, actual has `border-status-completed` / `text-status-completed`
2. `'failed'` -- expects `dataset.variant === 'destructive'`, actual has `variant="outline"` with `border-status-failed` / `text-status-failed`
3. `'unknown'` -- expects `dataset.variant === 'secondary'`, actual has `variant="secondary"` (this assertion may work, but cascades from prior failures)

**Fix:** Update assertions to match current semantic class names and variant values.

## 4. Established Testing Patterns

### Pattern 1: Hook Mocking (not QueryClientProvider wrapping)

The project does **not** wrap components in `QueryClientProvider` for tests. Instead, TanStack Query hooks are mocked at the module level with `vi.mock()`:

```typescript
const mockUseStep = vi.fn()
vi.mock('@/api/steps', () => ({
  useStep: (...args: unknown[]) => mockUseStep(...args),
}))

// In test:
mockUseStep.mockReturnValue({ data: mockStepData, isLoading: false, isError: false })
```

**Rationale:** Components receive `{ data, isLoading, isError }` from hooks. Mocking the hook return value isolates component rendering from network/cache behavior. This avoids QueryClient setup complexity and makes tests synchronous.

### Pattern 2: Router Mocking

```typescript
const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))
```

### Pattern 3: Time Utility Mocking

Time-dependent output is mocked to avoid flaky tests:

```typescript
vi.mock('@/lib/time', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/time')>()
  return {
    ...actual,
    formatRelative: (iso: string) => `relative(${iso})`,
    formatAbsolute: (iso: string) => `absolute(${iso})`,
  }
})
```

### Pattern 4: Fake Timers with Radix Workaround

```typescript
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(NOW))
})

afterEach(() => {
  vi.useRealTimers()
})

it('interaction test', async () => {
  // IMPORTANT: Radix Tooltip deadlocks with fake timers during pointer events
  vi.useRealTimers()
  const user = userEvent.setup()
  // ...
})
```

### Pattern 5: userEvent for Interactions

```typescript
const user = userEvent.setup()
await user.click(screen.getByText('test-pipeline').closest('tr')!)
expect(mockNavigate).toHaveBeenCalledWith({ to: '/runs/$runId', params: { runId: '...' } })
```

### Pattern 6: Loading/Error/Empty State Testing

Every component consistently tests three states:
```typescript
it('shows loading skeleton', () => {
  const { container } = render(<Component isLoading={true} ... />)
  expect(container.querySelectorAll('.animate-pulse').length).toBe(N)
})

it('shows error message', () => {
  render(<Component isError={true} ... />)
  expect(screen.getByText('Failed to load X')).toHaveClass('text-destructive')
})

it('shows empty state', () => {
  render(<Component data={[]} isLoading={false} isError={false} ... />)
  expect(screen.getByText('No X found')).toHaveClass('text-muted-foreground')
})
```

### Pattern 7: Radix Portal Queries

For Sheet/Dialog components rendered via Radix portals, tests query the full `document` instead of the render container:

```typescript
function getSheetContent(): HTMLElement | null {
  return document.querySelector('[data-slot="sheet-content"]')
}
```

## 5. TanStack Query Testing Approach

### Current Approach: Hook-Level Mocking

The project mocks hooks rather than setting up QueryClient with fake network responses. This is a valid pattern documented by TanStack Query:

> "For components that use TanStack Query hooks, you can either test with a real QueryClient+QueryClientProvider (integration-style) or mock the hooks at the module level (unit-style)."

**This project uses the unit-style approach consistently.** All 6 component test files that depend on data hooks mock them via `vi.mock()`.

### When QueryClientProvider Wrapping Would Be Needed

If future tests need to verify:
- Cache invalidation behavior
- Refetch intervals / staleTime
- Optimistic updates
- Error retry logic

Then a `QueryClientProvider` wrapper with test-specific config would be required:

```typescript
const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = createTestQueryClient()
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
```

**Current recommendation:** Continue with hook mocking for component tests. No need to change the pattern.

## 6. MSW (Mock Service Worker) Assessment

**MSW is NOT used in this project and is NOT needed.** The hook-mocking pattern eliminates the need for HTTP-level mocking. MSW would only be valuable if:
- Testing the `apiClient` fetch wrapper itself
- Writing integration tests that exercise real TanStack Query cache behavior
- Testing WebSocket/SSE event streams end-to-end

None of these are in scope for task 55.

## 7. Untested Components (Coverage Gap)

### High-Priority (referenced in task 55 description)
- `JsonDiff.tsx` -- complex tree diff rendering, task explicitly mentions testing diff highlighting
- `InputForm.tsx` + `FormField.tsx` -- form generation from JSON Schema, task mentions "test form generation"

### Medium-Priority (key user flows)
- `PipelineSelector.tsx` -- uses `usePipelines()` hook, renders Select with pipeline list
- `Sidebar.tsx` -- navigation links
- `EventStream.tsx` -- live SSE streaming component

### Lower-Priority (page-level / less critical)
- Route pages: `index.tsx`, `runs/$runId.tsx`, `live.tsx`, `prompts.tsx`, `pipelines.tsx`
- Pipeline components: `PipelineDetail`, `PipelineList`, `StrategySection`, `JsonTree`
- Prompt components: `PromptFilterBar`, `PromptList`, `PromptViewer`

## 8. Recommended Test Structure

Following the established pattern, new test files should be co-located:

```
src/
  components/
    JsonDiff.test.tsx           # new
    live/
      InputForm.test.tsx        # new
      PipelineSelector.test.tsx # new (mock usePipelines)
    runs/
      StatusBadge.test.tsx      # FIX existing failures
```

### Test Template for Hook-Dependent Components

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { ComponentUnderTest } from './ComponentUnderTest'

// Mock hook at module level
const mockUseHook = vi.fn()
vi.mock('@/api/module', () => ({
  useHook: (...args: unknown[]) => mockUseHook(...args),
}))

describe('ComponentUnderTest', () => {
  beforeEach(() => {
    mockUseHook.mockReset()
  })

  it('renders data', () => {
    mockUseHook.mockReturnValue({ data: mockData, isLoading: false, isError: false })
    render(<ComponentUnderTest />)
    expect(screen.getByText('expected text')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    mockUseHook.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    const { container } = render(<ComponentUnderTest />)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows error state', () => {
    mockUseHook.mockReturnValue({ data: undefined, isLoading: false, isError: true })
    render(<ComponentUnderTest />)
    expect(screen.getByText(/failed to load/i)).toHaveClass('text-destructive')
  })
})
```

## 9. Summary

| Aspect | Status |
|--------|--------|
| Vitest configuration | Complete, working |
| jsdom environment | Configured with Radix polyfills |
| Testing Library deps | All installed (react, dom, jest-dom, user-event) |
| TypeScript types | Configured (vitest/globals, jest-dom/vitest) |
| Test scripts | `test` and `test:coverage` ready |
| Coverage tooling | @vitest/coverage-v8 installed |
| Established patterns | Hook mocking, props rendering, loading/error/empty states |
| MSW needed | No |
| New deps needed | No |
| Existing failures | 3 in StatusBadge.test.tsx (stale assertions post-refactor) |
