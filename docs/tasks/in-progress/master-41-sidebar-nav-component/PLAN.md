# PLANNING

## Summary
Create `src/components/Sidebar.tsx` as a collapsible sidebar nav component with 4 route links, active route highlighting via TanStack Router `activeProps`, collapse/expand toggle via existing Zustand `useUIStore`, responsive tablet/mobile behavior, ARIA accessibility, and dark theme design tokens. Replace the placeholder `<aside>` in `__root.tsx` with `<Sidebar />`.

## Plugin & Agents
**Plugin:** frontend-mobile-development
**Subagents:** frontend-developer
**Skills:** none

## Phases
1. **Implementation**: Create Sidebar component and wire into root layout

## Architecture Decisions

### Active Route Detection Method
**Choice:** Use TanStack Router `Link` `activeProps`/`inactiveProps` props
**Rationale:** Simpler than `useMatchRoute`, fewer lines, built-in `aria-current="page"` support. All 4 nav routes are leaf routes so exact matching (default) is correct.
**Alternatives:** `useMatchRoute()` hook -- gives manual control but adds boilerplate for no benefit here.

### Label Visibility When Collapsed
**Choice:** `sr-only` Tailwind class toggled conditionally: `className={cn(sidebarCollapsed && 'sr-only')}`
**Rationale:** Keeps labels in DOM for screen readers (WCAG compliance). `display:none` or conditional render `{!collapsed && <span>}` would remove them from the accessibility tree.
**Alternatives:** `opacity-0 w-0 overflow-hidden`, conditional render -- both break screen reader access.

### Custom Sidebar vs shadcn Sidebar Component
**Choice:** Custom component using shadcn primitives (Button, Tooltip, Separator, Sheet)
**Rationale:** shadcn SidebarProvider manages its own `open` state which conflicts with Zustand `sidebarCollapsed`. Full shadcn Sidebar pulls excessive sub-components for a 4-item nav.
**Alternatives:** shadcn Sidebar -- conflicts with existing Zustand state, over-engineered for scope.

### Single File Architecture
**Choice:** Single `src/components/Sidebar.tsx` containing all sidebar logic
**Rationale:** Component tree is shallow (header + nav + mobile sheet). Extracting sub-components adds file overhead without modularity benefit unless file exceeds ~200 lines.
**Alternatives:** Split into SidebarHeader, SidebarNav, MobileSidebar files -- unnecessary for this scope.

## Implementation Steps

### Step 1: Create Sidebar Component
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** /tanstack/router, /lucide-icons/lucide, /pmndrs/zustand
**Group:** A

1. Create `llm_pipeline/ui/frontend/src/components/Sidebar.tsx`
2. Import: `cn` from `@/lib/utils`, `useUIStore` from `@/stores/ui`, `Link` from `@tanstack/react-router`, `Button` from `@/components/ui/button`, `Separator` from `@/components/ui/separator`, `Tooltip`/`TooltipContent`/`TooltipTrigger`/`TooltipProvider` from `@/components/ui/tooltip`, `Sheet`/`SheetContent`/`SheetTrigger` from `@/components/ui/sheet`, icons `List`, `FileText`, `Box`, `Play`, `PanelLeftClose`, `PanelLeftOpen`, `Menu` from `lucide-react`
3. Define `navItems` array typed with `to` as route literal union from `routeTree.gen.ts` (`FileRoutesByTo` key):
   ```
   { to: '/', label: 'Runs', icon: List }
   { to: '/live', label: 'Live', icon: Play }
   { to: '/prompts', label: 'Prompts', icon: FileText }
   { to: '/pipelines', label: 'Pipelines', icon: Box }
   ```
4. Build `<aside>` with classes: `bg-sidebar border-r border-sidebar-border shrink-0 flex flex-col transition-all duration-200` + width toggle `sidebarCollapsed ? 'w-16' : 'w-60'` + responsive override `max-lg:w-16`
5. Build `SidebarHeader` div: toggle `Button` (variant="ghost", size="icon-sm") with `PanelLeftClose`/`PanelLeftOpen` icon based on state, `aria-expanded={!sidebarCollapsed}`, `aria-label` dynamic, `aria-controls="sidebar-nav"`; app name `<span>` with `className={cn('text-sm font-semibold text-sidebar-foreground', sidebarCollapsed && 'sr-only')}` showing "llm-pipeline"
6. Add `<Separator />`
7. Wrap nav section in `<TooltipProvider delayDuration={0}>`
8. Build `<nav aria-label="Main navigation" id="sidebar-nav">` with `<ul role="list">` containing `<li>` per nav item
9. For each nav item: when `sidebarCollapsed`, wrap `Link` in `<Tooltip>` with `<TooltipContent side="right" sideOffset={8}>`; when expanded, render bare `Link`
10. `Link` uses `activeProps={{ 'aria-current': 'page', className: 'bg-sidebar-accent text-sidebar-accent-foreground border-l-2 border-sidebar-primary font-medium' }}` and `inactiveProps={{ className: 'text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground border-l-2 border-transparent' }}`; common `Link` classes: `flex items-center gap-3 px-3 py-2 rounded-md text-sm w-full`
11. Inside each `Link`: icon with `aria-hidden="true"` at `size={20}` (Tailwind `size-5`), label `<span>` with `className={cn(sidebarCollapsed && 'sr-only')}`
12. Build mobile section: `<div className="md:hidden">` containing `Sheet` with `side="left"` trigger `<Button variant="ghost" size="icon"><Menu size={20} /></Button>` and `SheetContent` wrapping the same nav items (no tooltip needed in sheet; full labels visible); mobile sheet nav uses identical `Link` activeProps/inactiveProps
13. Export named function: `export function Sidebar()`

### Step 2: Wire Sidebar into Root Layout
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** B

1. Open `llm_pipeline/ui/frontend/src/routes/__root.tsx`
2. Add import: `import { Sidebar } from '@/components/Sidebar'`
3. Replace the placeholder `<aside>` block (lines 6-8) with `<Sidebar />`
4. Verify outer `<div>` retains `flex h-screen bg-background text-foreground overflow-hidden` (no change needed)
5. Remove now-unused placeholder comment text

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `routeTree.gen.ts` `FileRoutesByTo` type not exported or named differently | Medium | Fall back to `string` type for `to` field if import fails; check generated file for actual export name |
| `TooltipProvider` already exists higher in tree (e.g., `main.tsx`) | Low | Redundant provider is harmless; no action needed. Verify during implementation. |
| `Button` size prop "icon-sm" not valid (shadcn may use "icon" only) | Medium | Verified in VALIDATED_RESEARCH.md that "icon-sm" exists in `button.tsx`; confirm before use |
| Tablet CSS `max-lg:w-16` conflicts with Zustand expanded state visually | Low | Acceptable -- CSS wins below lg breakpoint; Zustand state preserved for desktop return |
| `Sheet` import path differs from expected | Low | Verify actual export shape of `@/components/ui/sheet` before writing imports |
| Mobile hamburger button placement in layout unclear | Low | Place `<div className="md:hidden fixed top-4 left-4 z-50">` as overlay trigger; defer to implementation detail |

## Success Criteria
- [ ] `src/components/Sidebar.tsx` created and TypeScript compiles without errors
- [ ] Sidebar renders with `w-60` when expanded and `w-16` when collapsed
- [ ] `transition-all duration-200` provides smooth width animation on toggle
- [ ] All 4 nav links render with correct icons and labels
- [ ] Active route link has `bg-sidebar-accent`, `border-sidebar-primary` left border, and `aria-current="page"`
- [ ] Inactive links have `border-transparent` (no layout shift on activation)
- [ ] Labels hidden with `sr-only` when collapsed (still in DOM for screen readers)
- [ ] Toggle button has correct `aria-expanded`, `aria-label`, `aria-controls` attributes
- [ ] Collapsed icons show tooltips with label text via Radix `Tooltip` (`side="right"`)
- [ ] Below `lg` breakpoint, `max-lg:w-16` forces collapsed regardless of Zustand state
- [ ] Below `md` breakpoint, Sheet overlay with hamburger button visible
- [ ] `sidebarCollapsed` state persists across page reload (Zustand localStorage)
- [ ] `__root.tsx` imports and renders `<Sidebar />` replacing the placeholder `<aside>`
- [ ] All design tokens used (`bg-sidebar`, `bg-sidebar-accent`, `border-sidebar-border`, `border-sidebar-primary`, `text-sidebar-foreground`, `text-sidebar-accent-foreground`)
- [ ] No heroicons imports; only lucide-react

## Phase Recommendation
**Risk Level:** low
**Reasoning:** All assumptions validated against source files. No new dependencies required. No schema changes. Well-defined component tree with existing primitives. Two-step implementation (create component, wire into layout) with no concurrent file conflicts.
**Suggested Exclusions:** testing, review
