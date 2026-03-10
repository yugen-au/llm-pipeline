# Research Summary

## Executive Summary

Consolidated and validated two research documents (frontend architecture + UI/UX patterns) against actual source files. Research was largely accurate. Three ambiguities escalated to CEO and resolved: collapsed width (w-16), responsive scope (included), sidebar header content (branding + toggle). One internal inconsistency in step-1 research corrected (section 8 said w-12, section 11 said w-16). One cross-document inconsistency in label-hiding approach resolved in favor of `sr-only` for accessibility. Task 41 description is outdated on icon library (heroicons -> lucide-react) and styling (raw gray classes -> design tokens); research correctly identified both.

## Domain Findings

### Root Layout Integration
**Source:** step-1-frontend-architecture-research.md (sections 1, 8)

- `__root.tsx` has placeholder `<aside>` with `w-60 shrink-0 bg-sidebar border-r border-sidebar-border`
- Sidebar component replaces placeholder; root layout imports `<Sidebar />`
- `shrink-0` must be retained on the sidebar `<aside>` to prevent flex compression
- Root layout `<div>` has `flex h-screen bg-background text-foreground overflow-hidden`

### Route Structure
**Source:** step-1-frontend-architecture-research.md (section 2)

4 nav items mapping to file-based routes:

| Path | Route File | Nav Label | Icon (lucide-react) |
|------|-----------|-----------|---------------------|
| `/` | `routes/index.tsx` | Runs | `List` |
| `/live` | `routes/live.tsx` | Live | `Play` |
| `/prompts` | `routes/prompts.tsx` | Prompts | `FileText` |
| `/pipelines` | `routes/pipelines.tsx` | Pipelines | `Box` |

`/runs/$runId` is a detail page, NOT a nav item.

Type-safe `to` field: use `FileRoutesByTo` type from `routeTree.gen.ts` for compile-time route validation in the navItems array.

### Active Route Detection
**Source:** step-1 (section 3), step-2 (section 4)

Two valid approaches. Recommended: `activeProps`/`inactiveProps` on TanStack Router `Link`.

```tsx
<Link
  to={item.to}
  activeProps={{ 'aria-current': 'page', className: activeClasses }}
  inactiveProps={{ className: inactiveClasses }}
>
```

Rationale: simpler than `useMatchRoute`, fewer lines, built-in `aria-current` support. All 4 nav routes are leaf routes -- exact matching (default) is correct for all.

Alternative: `useMatchRoute()` gives manual control if fuzzy matching or custom logic needed later. Either works; `activeProps` preferred for initial implementation.

### Zustand Store (useUIStore)
**Source:** step-1 (section 4), verified against `src/stores/ui.ts`

```typescript
// Usage in Sidebar:
const { sidebarCollapsed, toggleSidebar } = useUIStore()
```

- `sidebarCollapsed: boolean` -- persisted to localStorage under key `llm-pipeline-ui`
- `toggleSidebar()` -- flips `sidebarCollapsed`
- Middleware: `devtools(persist(...))`
- `onRehydrateStorage` applies dark class on load
- Deviation from task 32 spec: `selectedStepId` is `number | null`, not `string | null`

No store changes needed for sidebar. State already exists and is persisted.

### Icon Library
**Source:** step-1 (section 5), verified against `package.json`

- `lucide-react` v0.575.0 -- the ONLY icon library installed
- Task 41 description references `@heroicons/react` -- **outdated, do not use**
- Existing usage: `Play`, `ChevronRight`, `ChevronDown`, `ArrowLeft`, `CheckIcon`, `XIcon`
- New icons needed: `List`, `FileText`, `Box`, `PanelLeftClose`, `PanelLeftOpen`
- Standard size: `size-5` (20px) for nav icons, matching shadcn sidebar conventions

### Styling & Design Tokens
**Source:** step-1 (section 6), step-2 (section 8), verified against `src/index.css`

All sidebar tokens exist in both `:root` and `.dark`:

| Token Class | Dark Value | Usage |
|-------------|-----------|-------|
| `bg-sidebar` | `oklch(0.205 0 0)` | Sidebar background |
| `text-sidebar-foreground` | `oklch(0.985 0 0)` | Default text |
| `bg-sidebar-accent` | `oklch(0.269 0 0)` | Active/hover bg |
| `text-sidebar-accent-foreground` | `oklch(0.985 0 0)` | Active/hover text |
| `border-sidebar-border` | `oklch(1 0 0 / 10%)` | Right border |
| `border-sidebar-primary` | `oklch(0.488 0.243 264.376)` | Active left border (blue) |
| `ring-sidebar-ring` | `oklch(0.556 0 0)` | Focus ring |

**Enforced convention**: use design tokens, NOT raw gray classes (`bg-gray-800` etc.). Task 41 description violates this -- research correctly overrides.

### Collapse/Expand Animation
**Source:** step-2 (sections 1, 2)

| State | Width | Pixels |
|-------|-------|--------|
| Expanded | `w-60` | 240px |
| Collapsed | `w-16` | 64px (CEO confirmed) |

- Transition: `transition-all duration-200` (cubic-bezier ease-in-out, Tailwind default)
- `overflow-hidden` on `<aside>` during transition to prevent label wrap
- Width-based transition (not transform-based) -- appropriate for 4-item sidebar

### Label Visibility (Collapsed State)
**Source:** step-2 (sections 1, 2, 4, 5) -- internal inconsistency resolved

Three approaches appeared across step-2:
1. `opacity-0 w-0` (section 1) -- visual hide, still in DOM
2. `{!sidebarCollapsed && <span>}` (section 2) -- conditional render, removed from DOM
3. `sr-only` (sections 4, 5) -- visually hidden, accessible to screen readers

**Canonical approach: `sr-only`** (option 3). This is the only method that:
- Keeps labels in DOM for screen readers (WCAG compliance)
- Hides them visually when collapsed
- Avoids `display: none` or `aria-hidden` which would break accessibility

```tsx
<span className={cn(sidebarCollapsed && 'sr-only')}>
  {item.label}
</span>
```

Icons get `aria-hidden="true"` since labels carry the accessible name.

### Active Route Indicator
**Source:** step-2 (section 3)

Recommended: background highlight + left border accent (works in both expanded and collapsed states).

```tsx
const activeClasses = 'bg-sidebar-accent text-sidebar-accent-foreground border-l-2 border-sidebar-primary font-medium'
const inactiveClasses = 'text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground border-l-2 border-transparent'
```

`border-transparent` on inactive items prevents layout shift when active border appears.

### Accessibility (ARIA & Keyboard)
**Source:** step-2 (section 4)

Required ARIA attributes:

| Element | Attribute | Value |
|---------|-----------|-------|
| `<nav>` | `aria-label` | `"Main navigation"` |
| `<nav>` | `id` | `"sidebar-nav"` |
| Active Link | `aria-current` | `"page"` (via `activeProps`) |
| Toggle button | `aria-expanded` | `{!sidebarCollapsed}` |
| Toggle button | `aria-label` | Dynamic: "Collapse sidebar" / "Expand sidebar" |
| Toggle button | `aria-controls` | `"sidebar-nav"` |

Keyboard: natural DOM order (toggle -> nav links top to bottom) creates logical tab order. No custom keyboard handling needed.

### Tooltips (Collapsed State)
**Source:** step-2 (section 5), verified against `src/components/ui/tooltip.tsx`

- Show tooltips ONLY when `sidebarCollapsed === true`
- Use existing Radix-based `Tooltip`/`TooltipContent`/`TooltipTrigger` from `@/components/ui/tooltip`
- `side="right"` with `sideOffset={8}` (component defaults to 0, override per-use)
- Wrap nav items section in `<TooltipProvider delayDuration={0}>` (matches existing default)
- No Radix `data-state` conflict risk -- nav links are plain TanStack Router `Link`, not Radix primitives
- Conditionally wrap: only wrap in `Tooltip` when collapsed, render bare `Link` when expanded

### Responsive Behavior (CEO confirmed: in scope)
**Source:** step-2 (section 6)

| Breakpoint | Width | Behavior |
|-----------|-------|----------|
| Desktop | >= 1024px (`lg`) | User-controlled collapse/expand via Zustand |
| Tablet | 768-1023px (`md` to `lg`) | Auto-collapsed to icon-only via CSS `max-lg:w-16` |
| Mobile | < 768px | Hidden entirely; overlay via Sheet component |

Desktop/tablet implementation (CSS-only approach, no JS media query needed):
```tsx
className={cn(
  'transition-all duration-200',
  sidebarCollapsed ? 'w-16' : 'w-60',
  'max-lg:w-16'  // force collapsed below lg
)}
```

Mobile: use existing `Sheet` component (`@/components/ui/sheet`) with `side="left"`. Hamburger menu button (`Menu` icon from lucide-react) visible only below `md` breakpoint (`md:hidden`). Sheet wraps the same nav items for consistency.

### Sidebar Header
**Source:** step-2 (section 7), CEO confirmed branding

Expanded: toggle button (PanelLeftClose) + "llm-pipeline" text
Collapsed: toggle button (PanelLeftOpen) only, text hidden via `sr-only`

- App name: `text-sm font-semibold text-sidebar-foreground`
- Separator between header and nav (use existing `Separator` component)

### Component Architecture
**Source:** step-2 (section 9), step-1 (section 7)

File: `src/components/Sidebar.tsx` (top-level, not nested in subdirectory)

```
Sidebar (aside)
  SidebarHeader (div)
    Toggle Button (Button ghost icon-sm)
    App Name (span, sr-only when collapsed)
  Separator
  TooltipProvider (wraps nav section)
    SidebarNav (nav aria-label="Main navigation" id="sidebar-nav")
      NavItemList (ul role="list")
        NavItem (li) x4
          Tooltip (conditional: only when collapsed)
            Link (TanStack Router)
              Icon (lucide-react, aria-hidden)
              Label (span, sr-only when collapsed)
  MobileSheet (Sheet, visible only below md)
```

### Why Custom Sidebar (Not shadcn Sidebar Component)
**Source:** step-2 (section 10)

1. shadcn SidebarProvider has its own `open` state -- conflicts with Zustand `sidebarCollapsed`
2. Full shadcn Sidebar pulls Collapsible, Sheet, and many sub-components -- excessive for 4 items
3. Custom sidebar is simpler to tune and maintain

Use FROM shadcn: `Button`, `Tooltip`, `Separator`, `Sheet`, design tokens. All already installed.

### Code Style
**Source:** step-1 (section 6), verified against codebase

- No semicolons
- Single quotes (project code; shadcn components use double quotes)
- 2-space indent
- Named function exports (not default)
- PascalCase component names
- `cn()` from `@/lib/utils` for conditional classes
- `@/` import alias throughout

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Collapsed width: w-12 (48px, task spec) or w-16 (64px, research recommendation for WCAG 2.5.5)? | Use w-16 (64px) for WCAG touch target compliance | Overrides task 41 description. 64px gives 44x44px touch targets with proper padding. |
| Is responsive behavior (tablet auto-collapse, mobile Sheet overlay) in scope for task 41? | Yes, include responsive behavior in this task | Adds tablet auto-collapse (CSS `max-lg:w-16`) and mobile Sheet overlay to deliverables. Increases scope. |
| Sidebar header: toggle button only, or include "llm-pipeline" branding text? | Include branding text + toggle button. Text shown when expanded, hidden when collapsed. | Header section has two elements instead of one. Text uses sr-only pattern when collapsed. |

## Assumptions Validated

- [x] Root layout placeholder aside exists at `__root.tsx` with correct classes (verified source)
- [x] `useUIStore` has `sidebarCollapsed` and `toggleSidebar` already implemented and persisted (verified `stores/ui.ts`)
- [x] `lucide-react` is the project icon library, not heroicons (verified `package.json`, grep of all imports)
- [x] Design tokens (`bg-sidebar`, `bg-sidebar-accent`, etc.) exist in both light and dark themes (verified `index.css`)
- [x] `Button` component has `ghost` variant and `icon-sm` size (verified `button.tsx`)
- [x] `Tooltip` component is Radix-based with `TooltipProvider` defaulting `delayDuration=0` (verified `tooltip.tsx`)
- [x] `Separator` component exists (verified file exists)
- [x] `Sheet` component exists with `side="left"` support (verified `sheet.tsx`)
- [x] TanStack Router `Link` from `@tanstack/react-router` v1.161.3 supports `activeProps`/`inactiveProps`
- [x] All 4 nav routes are leaf routes -- exact matching (no `fuzzy`) is correct
- [x] `cn()` utility at `@/lib/utils` used for conditional class merging (verified across codebase)
- [x] No semicolons, single quotes, named exports code style (verified across codebase)
- [x] `selectedStepId` is `number | null`, not `string | null` (task 32 deviation, verified `stores/ui.ts`)

## Open Items

- Keyboard shortcut for sidebar toggle (e.g., Cmd+B) not discussed in task 41 or research. Common pattern but not required. Defer unless requested.
- Mobile Sheet overlay adds a hamburger `Menu` button -- placement in mobile header bar not fully specified. Likely in a top bar that only renders below `md`. Implementation detail to resolve during coding.
- `TooltipProvider` may already exist higher in the component tree (e.g., `main.tsx`). If so, the sidebar's `TooltipProvider` is redundant but harmless. Check during implementation.
- Tablet auto-collapse via CSS (`max-lg:w-16`) means `sidebarCollapsed` Zustand state and CSS override can conflict (user toggles to expanded, but CSS forces collapsed below lg). This is acceptable -- CSS wins, Zustand state is preserved for when the user returns to desktop width.

## Recommendations for Planning

1. **File creation**: Single file `src/components/Sidebar.tsx` containing all sidebar logic (header, nav, mobile sheet). Extract sub-components only if file exceeds ~200 lines.
2. **Replace root layout placeholder**: Modify `__root.tsx` to import `<Sidebar />` and remove the inline `<aside>`. Keep `shrink-0` on the Sidebar's aside element.
3. **Use `activeProps`/`inactiveProps`** on Link rather than `useMatchRoute` for initial implementation. Simpler and handles `aria-current` automatically.
4. **Label hiding**: Use `sr-only` exclusively. Do NOT use conditional rendering (`{!collapsed && <span>}`) or `opacity-0` -- these break screen reader access.
5. **NavItems array**: Type the `to` field using the route literal union from `routeTree.gen.ts` for compile-time safety.
6. **Responsive implementation order**: Build desktop collapse/expand first, then add CSS `max-lg:w-16` for tablet, then mobile Sheet overlay. Each is additive.
7. **Test the toggle persistence**: Verify `sidebarCollapsed` survives page reload via the existing Zustand persist middleware. No new code needed for this.
8. **Icon verification**: Import `List`, `FileText`, `Box`, `PanelLeftClose`, `PanelLeftOpen`, `Menu` from lucide-react. Verify they render correctly at `size-5`.
