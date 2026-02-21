# IMPLEMENTATION - STEP 3: ROOT LAYOUT SHELL
**Status:** completed

## Summary
Updated `__root.tsx` with a dark-themed sidebar layout shell using OKLCH design tokens from `index.css`. Replaced the pass-through arrow function with a named `RootLayout` component that renders a flex layout with sidebar placeholder and main content area.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/routes/__root.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/__root.tsx`
Replaced pass-through `() => <Outlet />` with named `RootLayout` function rendering flex layout with `<aside>` sidebar placeholder and `<main>` content area.

```
# Before
export const Route = createRootRoute({
  component: () => <Outlet />,
})

# After
function RootLayout() {
  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <aside className="w-60 shrink-0 bg-sidebar border-r border-sidebar-border">
        <div className="p-4 text-sm text-muted-foreground">Sidebar (task 41)</div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

export const Route = createRootRoute({
  component: RootLayout,
})
```

## Decisions
### Placeholder sidebar content wrapper
**Choice:** Wrapped placeholder text in a `<div>` with `p-4 text-sm text-muted-foreground` classes
**Rationale:** Provides minimal visual structure and uses `muted-foreground` design token to indicate placeholder status. Task 41 replaces this entire `<aside>` content.

## Verification
[x] Uses design tokens (bg-background, text-foreground, bg-sidebar, border-sidebar-border, text-muted-foreground) not raw gray classes
[x] Named function component `RootLayout`
[x] No semicolons, single quotes, 2-space indent
[x] Imports only `createRootRoute` and `Outlet` from `@tanstack/react-router`
[x] Flex layout with h-screen, overflow-hidden on outer div
[x] Aside: w-60 shrink-0, border-r
[x] Main: flex-1 overflow-auto containing `<Outlet />`
