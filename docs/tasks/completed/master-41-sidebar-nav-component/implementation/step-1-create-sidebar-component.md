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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] MEDIUM - Tablet tooltip gap: `max-lg:w-16` forced sidebar narrow via CSS but Zustand `sidebarCollapsed` stayed false, so tooltips didn't render on tablet viewports
[x] LOW - Mobile hamburger overlay: floating `div.fixed.top-4.left-4` obscured page content
[x] LOW - border-l-2 + rounded-md cosmetic: left border on rounded element created corner artifact

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/hooks/use-media-query.ts`
New reusable hook. SSR-safe `useMediaQuery` that tracks a CSS media query string via `window.matchMedia`, returns boolean.

#### File: `llm_pipeline/ui/frontend/src/components/Sidebar.tsx`
Three fixes applied:

**1. Tablet tooltip gap** -- Added `useMediaQuery('(max-width: 1023px)')` to detect below-lg viewport. Derived `isEffectivelyCollapsed = sidebarCollapsed || belowLg`. This single boolean now drives NavLinks `collapsed` prop, aside width class, and header label visibility. Removed `max-lg:w-16` CSS override (no longer needed since JS drives the width). Removed `responsiveCollapse` prop from NavLinks (no longer needed since collapsed state is accurate at React level).
```
# Before
const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
// ...
<aside className={cn('...', sidebarCollapsed ? 'w-16' : 'w-60', 'max-lg:w-16')}>
<NavLinks collapsed={sidebarCollapsed} responsiveCollapse />

# After
const belowLg = useMediaQuery('(max-width: 1023px)')
const isEffectivelyCollapsed = sidebarCollapsed || belowLg
// ...
<aside className={cn('...', isEffectivelyCollapsed ? 'w-16' : 'w-60')}>
<NavLinks collapsed={isEffectivelyCollapsed} />
```

**2. Mobile hamburger overlay** -- Replaced floating `div.fixed.top-4.left-4` with a full-width `header.fixed.top-0.inset-x-0` mobile top bar. Contains hamburger + "llm-pipeline" label. Uses `bg-sidebar border-b border-sidebar-border` to match sidebar theme. `h-12` gives consistent height. Main content below md should use `pt-12` to avoid overlap (handled by layout integration in Step 2).
```
# Before
<div className="md:hidden fixed top-4 left-4 z-50">
  <Sheet>
    <SheetTrigger asChild>
      <Button ...><Menu /></Button>
    </SheetTrigger>
    ...
  </Sheet>
</div>

# After
<header className="md:hidden fixed top-0 inset-x-0 z-50 flex items-center h-12 px-3 bg-sidebar border-b border-sidebar-border">
  <Sheet>
    <SheetTrigger asChild>
      <Button ...><Menu /></Button>
    </SheetTrigger>
    ...
  </Sheet>
  <span className="ml-2 text-sm font-semibold text-sidebar-foreground">llm-pipeline</span>
</header>
```

**3. Border radius cosmetic** -- Changed `rounded-md` to `rounded-r-md rounded-l-none` on `baseLinkClasses` so left border edge is straight.
```
# Before
const baseLinkClasses = '... rounded-md ...'

# After
const baseLinkClasses = '... rounded-r-md rounded-l-none ...'
```

### Verification
[x] TypeScript compiles without errors (`npx tsc --noEmit` clean)
[x] `useMediaQuery` hook created at `src/hooks/use-media-query.ts`
[x] `isEffectivelyCollapsed` derived from `sidebarCollapsed || belowLg`
[x] Tooltips render when `isEffectivelyCollapsed` is true (covers both explicit collapse and tablet viewport)
[x] `max-lg:w-16` CSS removed, width driven by `isEffectivelyCollapsed` ternary
[x] `responsiveCollapse` prop removed from NavLinks (simplified)
[x] Mobile hamburger in full-width top bar, no longer floating over content
[x] `rounded-r-md rounded-l-none` on link base classes, straight left edge for border-l-2
