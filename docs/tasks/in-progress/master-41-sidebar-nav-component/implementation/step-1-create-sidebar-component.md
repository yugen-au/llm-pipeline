# IMPLEMENTATION - STEP 1: CREATE SIDEBAR COMPONENT
**Status:** completed

## Summary
Created `src/components/Sidebar.tsx` -- a collapsible sidebar navigation component with 4 route links, active route highlighting via TanStack Router `Link` `activeProps`/`inactiveProps`, collapse/expand toggle via Zustand `useUIStore`, responsive behavior (tablet forced-collapse via `max-lg:w-16`, mobile Sheet overlay), ARIA accessibility, and dark theme design tokens.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/Sidebar.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/Sidebar.tsx`
New file. Single-file sidebar component containing:
- `NavLinks` internal component (renders `<ul>` with `<li>` per nav item)
- `Sidebar` named export (renders mobile Sheet trigger + desktop/tablet aside)
- 4 nav items typed against `FileRoutesByTo` from `routeTree.gen.ts`
- `activeProps` with `aria-current="page"` + active classes, `inactiveProps` with transparent border (no layout shift)
- Collapsed state tooltips via `<Tooltip>` wrapping `<Link>` when `sidebarCollapsed`
- `responsiveCollapse` prop on NavLinks adds `max-lg:sr-only` to labels for tablet forced-narrow
- Mobile: `md:hidden` fixed hamburger button with `Sheet side="left"` containing full nav
- Desktop: `hidden md:flex` aside with `max-lg:w-16` responsive override
- Header: toggle Button with `aria-expanded`, `aria-controls`, `aria-label`; app name span with conditional `sr-only`

## Decisions
### Responsive label hiding for tablet
**Choice:** Added `responsiveCollapse` prop to NavLinks that applies `max-lg:sr-only` to label spans
**Rationale:** When `max-lg:w-16` CSS forces sidebar narrow on tablet but Zustand `sidebarCollapsed` is `false`, labels would overflow. `max-lg:sr-only` hides them visually while keeping them in DOM for screen readers.

### SheetTitle for accessibility
**Choice:** Used `SheetTitle` inside `SheetContent` for mobile nav
**Rationale:** Radix Dialog (underlying Sheet) requires a Title for accessibility. Without it, console warnings appear. Using SheetTitle with the app name satisfies the requirement.

### Type-safe route `to` prop
**Choice:** Typed `NavItem.to` as `keyof FileRoutesByTo` from `routeTree.gen.ts`
**Rationale:** Ensures compile-time validation that nav links match actual defined routes. If a route is renamed/removed, TypeScript will catch the mismatch.

## Verification
[x] TypeScript compiles without errors (`npx tsc --noEmit` passes clean)
[x] Named export `export function Sidebar()` present
[x] 4 nav items with correct icons (List, Play, FileText, Box) and routes (/, /live, /prompts, /pipelines)
[x] `activeProps` includes `aria-current: 'page'` and active styling classes
[x] `inactiveProps` includes `border-transparent` (no layout shift)
[x] Labels use `sr-only` when collapsed (still in DOM for screen readers)
[x] Toggle button has `aria-expanded`, `aria-controls="sidebar-nav"`, dynamic `aria-label`
[x] Tooltips on collapsed icons via `Tooltip` with `side="right"` and `sideOffset={8}`
[x] `max-lg:w-16` forces collapsed width on tablet
[x] Mobile Sheet with hamburger Menu button below md breakpoint
[x] All design tokens used: bg-sidebar, bg-sidebar-accent, border-sidebar-border, border-sidebar-primary, text-sidebar-foreground, text-sidebar-accent-foreground
[x] `transition-all duration-200` on aside for smooth width animation
[x] Single file architecture, under 200 lines
[x] Only lucide-react icons, no heroicons
