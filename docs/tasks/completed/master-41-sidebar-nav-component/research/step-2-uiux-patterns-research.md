# UI/UX Patterns Research: Sidebar Navigation Component (Task 41)

## 1. Collapse/Expand Animation Patterns

### Width Transition Approach

The standard pattern for collapsible sidebars uses CSS `transition` on `width`:

```css
/* Tailwind utility classes */
.sidebar {
  transition-property: all;
  transition-duration: 200ms;
  transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1); /* ease-in-out */
}
```

In Tailwind: `transition-all duration-200` (as specified in task description).

### Collapsed vs Expanded Widths

| State | Width | Tailwind | Pixels | Rationale |
|-------|-------|----------|--------|-----------|
| Expanded | w-60 | `width: 15rem` | 240px | Room for icon + label + padding |
| Collapsed | w-16 | `width: 4rem` | 64px | 48px icon area + 8px horizontal padding each side |

**Note on w-12 vs w-16**: Task description says `w-12` (48px) for collapsed state. However, 48px leaves only ~32px for the icon after padding, making touch targets tight. Step-1 research recommends `w-16` (64px) which provides a comfortable 44x44px touch target (WCAG 2.5.5 Target Size) with proper padding. Using `w-16` aligns with WCAG guidance and common sidebar patterns (e.g., shadcn sidebar icon rail defaults to ~48-64px).

**Recommendation**: Use `w-16` for collapsed state. This gives comfortable icon centering and meets touch target minimums without extra calculation.

### Overflow & Label Clipping

During width transition, labels must not wrap or overflow:

```tsx
<aside className={cn(
  'transition-all duration-200 overflow-hidden',
  sidebarCollapsed ? 'w-16' : 'w-60'
)}>
```

Nav item labels should use `whitespace-nowrap` and `opacity` transition for smooth fade:

```tsx
<span className={cn(
  'ml-3 whitespace-nowrap transition-opacity duration-200',
  sidebarCollapsed ? 'opacity-0 w-0' : 'opacity-100'
)}>
  {label}
</span>
```

### Alternative: Transform-Based Animation

Some implementations use `transform: translateX(-100%)` for the label portion rather than width changes. This avoids layout recalculation and is GPU-accelerated. However, the width-based approach is simpler with Tailwind utilities and the sidebar only has 4 items (no performance concern).

**Verdict**: Width-based transition with `transition-all duration-200` is appropriate for this use case.

## 2. Icon-Only vs Icon+Label States

### Layout Pattern

**Expanded state**: Horizontal flex row with icon (fixed size) + label (flex-1).

```
[  icon  |  Label Text        ]
```

**Collapsed state**: Icon centered vertically and horizontally within the nav item.

```
[ icon ]
```

### Implementation Pattern

Each nav item should be a flex container that adapts:

```tsx
<Link
  to={item.to}
  className={cn(
    'flex items-center rounded-md transition-colors',
    sidebarCollapsed ? 'justify-center p-2' : 'px-3 py-2 gap-3'
  )}
>
  <item.icon className="size-5 shrink-0" />
  {!sidebarCollapsed && (
    <span className="truncate text-sm">{item.label}</span>
  )}
</Link>
```

### Icon Sizing

Lucide icons should use `size-5` (20px) consistently across all nav items. This is the standard size used in shadcn sidebar components and aligns with the existing `[&_svg:not([class*='size-'])]:size-4` button default (nav items are slightly larger than button icons).

## 3. Active Route Indicator Patterns

### Common Patterns (Ranked by Effectiveness)

1. **Background highlight + left border accent** (RECOMMENDED)
   - Most discoverable, works in both expanded and collapsed states
   - Background: `bg-sidebar-accent` (oklch 0.269 in dark = subtle gray-700 equivalent)
   - Left border: 2-3px `border-l-2 border-sidebar-primary` (blue accent)
   - Provides both color and spatial cue

2. **Background highlight only**
   - Simpler, common in Material Design
   - `bg-sidebar-accent text-sidebar-accent-foreground`
   - Works but less distinctive in icon-only mode

3. **Left border only**
   - GitHub-style indicator
   - Bold visual cue but less discoverable in icon-only mode

4. **Text weight/color change**
   - Subtle, often insufficient as sole indicator
   - Good as supplementary signal (e.g., `font-medium` on active)

### Recommended Active State Styling

```tsx
const activeClasses = 'bg-sidebar-accent text-sidebar-accent-foreground border-l-2 border-sidebar-primary font-medium'
const inactiveClasses = 'text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground border-l-2 border-transparent'
```

The `border-transparent` on inactive items prevents layout shift when the active border appears.

### Hover State

Hover should be a lighter version of the active state:
- `hover:bg-sidebar-accent/50` (50% opacity of accent background)
- Transition: `transition-colors` for smooth hover feedback

### Focus State

Focus ring should use sidebar-ring token:
- `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring`
- Or rely on the existing Button component's focus-visible styles if wrapping with Button

## 4. Keyboard Navigation & ARIA Attributes

### Landmark Structure

```html
<aside aria-label="Application sidebar">
  <div><!-- header: logo + toggle --></div>
  <nav aria-label="Main navigation">
    <ul role="list">
      <li><a href="/" aria-current="page">Runs</a></li>
      <li><a href="/live">Live</a></li>
      ...
    </ul>
  </nav>
</aside>
```

Key ARIA attributes:

| Element | Attribute | Value | Purpose |
|---------|-----------|-------|---------|
| `<nav>` | `aria-label` | `"Main navigation"` | Identifies nav landmark for screen readers |
| Active `<Link>` | `aria-current` | `"page"` | Indicates current page in navigation |
| Toggle button | `aria-expanded` | `true/false` | Communicates sidebar expansion state |
| Toggle button | `aria-label` | `"Collapse sidebar"` / `"Expand sidebar"` | Describes toggle action |
| Toggle button | `aria-controls` | `"sidebar-nav"` | Associates button with controlled region |
| `<nav>` | `id` | `"sidebar-nav"` | Target of aria-controls |

### TanStack Router Active Link

TanStack Router `Link` component supports `activeProps` for active state attributes:

```tsx
<Link
  to={item.to}
  activeProps={{
    'aria-current': 'page',
    className: activeClasses,
  }}
  inactiveProps={{
    className: inactiveClasses,
  }}
>
```

However, `useMatchRoute` gives more control (e.g., custom fuzzy logic per route). Either approach works; `useMatchRoute` is already documented in step-1 research.

### Keyboard Interaction Pattern

| Key | Behavior |
|-----|----------|
| Tab | Moves focus through sidebar items in DOM order |
| Enter/Space | Activates focused link or toggle button |
| Escape | No special behavior (sidebar stays open) |

The natural DOM order (toggle button -> nav links top to bottom) creates a logical tab order per WCAG 2.4.3.

### Screen Reader Announcements

When sidebar collapses:
- Toggle button's `aria-expanded` changes, announced automatically
- Nav links remain in the DOM and focusable (labels still present in DOM for screen readers even if visually hidden)
- Tooltips provide visual labels but screen readers get the text from the link's child content

**Important**: Even when collapsed, the label text should remain in the DOM (hidden visually with `sr-only` or `opacity-0`) so screen readers can still announce link purposes. Do NOT use `display: none` or `aria-hidden` on labels.

```tsx
<Link to={item.to}>
  <item.icon className="size-5 shrink-0" aria-hidden="true" />
  <span className={cn(
    sidebarCollapsed && 'sr-only'
  )}>
    {item.label}
  </span>
</Link>
```

## 5. Tooltip Patterns for Collapsed Icon-Only State

### When to Show Tooltips

- ONLY when `sidebarCollapsed === true`
- On hover over nav item icons
- On keyboard focus of nav items (Radix Tooltip handles this automatically)

### Implementation with Existing Tooltip Component

The project already has `@/components/ui/tooltip` (Radix-based). Pattern:

```tsx
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

function NavItem({ item, isActive, sidebarCollapsed }) {
  const linkContent = (
    <Link to={item.to} className={cn(...)}>
      <item.icon className="size-5 shrink-0" aria-hidden="true" />
      <span className={cn(sidebarCollapsed && 'sr-only')}>
        {item.label}
      </span>
    </Link>
  )

  if (!sidebarCollapsed) return linkContent

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {linkContent}
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {item.label}
      </TooltipContent>
    </Tooltip>
  )
}
```

### Tooltip Positioning

- `side="right"` -- tooltip appears to the right of the collapsed sidebar
- `sideOffset={8}` -- 8px gap between sidebar edge and tooltip
- Arrow: the existing TooltipContent renders an arrow automatically

### TooltipProvider Placement

Wrap the entire sidebar (or the nav items section) in a single `<TooltipProvider delayDuration={0}>` for instant tooltips. The existing tooltip.tsx already defaults delayDuration to 0.

### Known Radix Issue: data-state Conflicts

When Tooltip wraps another Radix component (like Collapsible), `data-state` attributes can conflict. This is NOT a concern for our use case since nav links are not Radix primitives -- they are plain TanStack Router `Link` components.

## 6. Responsive Breakpoint Behavior

### Breakpoint Strategy

| Breakpoint | Width | Sidebar Behavior |
|-----------|-------|-----------------|
| Desktop | >= 1024px (`lg`) | Full sidebar, user-controlled collapse/expand |
| Tablet | 768-1023px (`md`) | Auto-collapsed to icon-only, expandable on toggle |
| Mobile | < 768px (`sm`) | Hidden entirely, overlay via Sheet component |

### Desktop (lg+)

Default experience. Sidebar respects `sidebarCollapsed` from Zustand (persisted). User toggles via button.

### Tablet (md to lg)

Auto-collapse sidebar on this breakpoint. This can be handled:

**Option A**: CSS-only with responsive Tailwind classes on the aside:
```tsx
className={cn(
  'transition-all duration-200',
  sidebarCollapsed ? 'w-16' : 'w-60',
  'max-lg:w-16' // force collapsed below lg breakpoint
)}
```

**Option B**: JS-based using `useMediaQuery` hook + Zustand store update on mount/resize.

**Recommendation**: Option A (CSS-only) is simpler and avoids flash-of-wrong-state. The Zustand `sidebarCollapsed` persisted state controls desktop behavior; CSS overrides force collapsed below `lg`.

### Mobile (below md)

Mobile sidebar should use the existing `Sheet` component (`@/components/ui/sheet`) as a slide-out overlay. This is standard for mobile navigation:

```tsx
// Conceptual -- mobile uses Sheet instead of aside
<Sheet>
  <SheetTrigger asChild>
    <Button variant="ghost" size="icon" className="md:hidden">
      <Menu className="size-5" />
    </Button>
  </SheetTrigger>
  <SheetContent side="left" className="w-60 bg-sidebar">
    {/* Same nav items */}
  </SheetContent>
</Sheet>
```

**Note**: Mobile overlay behavior may be deferred if not in scope for task 41. The desktop/tablet collapsed behavior is the core deliverable.

## 7. Visual Design Patterns for Dark Developer Dashboards

### Reference Patterns

Developer tool dashboards (VS Code, GitHub, Linear, Vercel) share these sidebar conventions:

1. **Subtle background differentiation**: Sidebar is 1-2 shades darker than main content area. Our tokens achieve this: `--sidebar: oklch(0.205)` vs `--background: oklch(0.145)` (sidebar is actually slightly lighter than background in dark mode, creating a panel effect).

2. **Minimal borders**: Single 1px right border with low opacity. Our token: `--sidebar-border: oklch(1 0 0 / 10%)`.

3. **Monochrome with accent**: Nav items are white/gray; only the active indicator uses color (sidebar-primary: blue accent in dark mode). This keeps the UI calm.

4. **Compact vertical spacing**: Nav items are tightly spaced with small padding (`py-2 px-3`) and consistent heights.

5. **Header/branding area**: Top of sidebar has app name/logo. In collapsed state, this shrinks to icon or single letter.

### Sidebar Header Design

**Expanded**:
```
[  PanelLeftClose  ]  llm-pipeline
```

**Collapsed**:
```
[ PanelLeftOpen ]
```

The app name uses `text-sm font-semibold text-sidebar-foreground`. In collapsed state, the name is hidden (same pattern as nav labels).

### Nav Item Height Consistency

All nav items should have consistent height: `h-9` (36px) matches the Button component's default size. This creates uniform visual rhythm.

### Separator Between Header and Nav

Use a subtle border or the existing Separator component between the header (branding + toggle) and the navigation list.

## 8. Design Token Mapping Summary

| UI Element | Expanded Token | Collapsed Token | Notes |
|-----------|---------------|----------------|-------|
| Sidebar background | `bg-sidebar` | `bg-sidebar` | Same |
| Sidebar right border | `border-sidebar-border` | `border-sidebar-border` | Same |
| Nav item text (default) | `text-sidebar-foreground` | N/A (icon inherits) | |
| Nav item text (active) | `text-sidebar-accent-foreground` | N/A | |
| Nav item background (active) | `bg-sidebar-accent` | `bg-sidebar-accent` | Same |
| Nav item background (hover) | `bg-sidebar-accent/50` | `bg-sidebar-accent/50` | Half opacity |
| Active border accent | `border-sidebar-primary` | `border-sidebar-primary` | Left border 2px |
| Focus ring | `ring-sidebar-ring` | `ring-sidebar-ring` | Same |
| Header text | `text-sidebar-foreground` | Hidden | App name |
| Muted text | `text-muted-foreground` | N/A | Sub-labels if needed |
| Tooltip background | `bg-foreground` | `bg-foreground` | Existing tooltip style |
| Tooltip text | `text-background` | `text-background` | Inverted for contrast |

## 9. Component Hierarchy Recommendation

```
Sidebar (aside)
  SidebarHeader (div)
    Toggle Button (Button ghost icon-sm)
    App Name (span, hidden when collapsed)
  Separator
  SidebarNav (nav aria-label="Main navigation")
    NavItemList (ul role="list")
      NavItem (li) x4
        TooltipWrapper (conditional, only when collapsed)
          Link (TanStack Router Link)
            Icon (lucide-react)
            Label (span, sr-only when collapsed)
```

This is a flat, simple hierarchy. No nested groups or collapsible sections needed for 4 nav items.

## 10. Shadcn Sidebar Component Decision

### Why NOT Use shadcn/ui Sidebar

The shadcn sidebar is a comprehensive system (SidebarProvider, SidebarContent, SidebarMenu, SidebarMenuButton, SidebarGroup, etc.) designed for complex, multi-section sidebars with:
- Group collapsibility
- Nested sub-menus
- Mobile sheet overlay built-in
- Internal state via React context (SidebarProvider)

For task 41's requirements (4 nav items, single level), this is excessive. More importantly:

1. **State conflict**: shadcn SidebarProvider manages its own `open` state. We already have `useUIStore.sidebarCollapsed` in Zustand with persist. Using both creates dual state sources.
2. **Bundle size**: shadcn Sidebar pulls in Collapsible, Sheet, and multiple sub-components.
3. **Flexibility**: A custom sidebar is easier to tune to exact design requirements.

### What TO Use from shadcn

- `Tooltip` component (already installed) for collapsed icon tooltips
- `Button` component (already installed) for the toggle button
- `Separator` component (already installed) for header/nav division
- Design tokens from `index.css` (sidebar-*, accent-*, etc.)

This gives us the shadcn design system benefits without the overhead of the full Sidebar component.
