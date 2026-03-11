# IMPLEMENTATION - STEP 12: SIDEBAR SMOKE TEST
**Status:** completed

## Summary
Smoke tests for Sidebar component. Mocks router Link, useMediaQuery, and Zustand useUIStore (selector pattern). Two tests: render smoke and nav item verification.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/Sidebar.test.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/Sidebar.test.tsx`
New test file with 3 module-level mocks and 2 smoke tests.

```tsx
# Mocks
- @tanstack/react-router: Link -> <a href={to}>
- @/hooks/use-media-query: useMediaQuery -> false (desktop)
- @/stores/ui: useUIStore -> selector-based mock returning { sidebarCollapsed: false, toggleSidebar: vi.fn() }

# Tests
- 'renders without crashing (smoke)' - render + assert container truthy
- 'shows 4 navigation items' - assert >= 4 links, verify Runs/Live/Prompts/Pipelines text
```

## Decisions
### Zustand selector mock approach
**Choice:** Mock useUIStore as a function that receives and calls the selector against a fake state object
**Rationale:** Sidebar calls `useUIStore((s) => s.sidebarCollapsed)` and `useUIStore((s) => s.toggleSidebar)` separately. The selector-invocation mock handles both calls correctly without needing to know which selector is passed.

### Navigation count assertion
**Choice:** Use `toBeGreaterThanOrEqual(4)` for link count instead of exact match
**Rationale:** The mobile Sheet header also contains navigation links. Radix Sheet may or may not render portal content in jsdom. Using >= 4 avoids brittle coupling to Radix portal behavior while still verifying the desktop nav renders all items.

## Verification
[x] Tests pass: 2/2 green (npx vitest run Sidebar)
[x] No interaction tests per CEO directive
[x] Co-located test file next to source
[x] Follows established vi.mock() pattern
