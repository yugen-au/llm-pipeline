# Frontend Architecture Research: Sidebar Navigation Component (Task 41)

## 1. Existing Root Layout

**File**: `llm_pipeline/ui/frontend/src/routes/__root.tsx`

Current layout has a placeholder `<aside>` ready for the Sidebar component:

```tsx
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
```

The `<aside>` element and its classes should be moved INTO the Sidebar component. The root layout will import `<Sidebar />` and render it in place of the `<aside>`.

## 2. Route Structure (routeTree.gen.ts)

Routes registered in `FileRoutesByTo`:

| Path | Route File | Nav Item |
|------|-----------|----------|
| `/` | `routes/index.tsx` | Runs |
| `/live` | `routes/live.tsx` | Live |
| `/prompts` | `routes/prompts.tsx` | Prompts |
| `/pipelines` | `routes/pipelines.tsx` | Pipelines |
| `/runs/$runId` | `routes/runs/$runId.tsx` | NOT in nav (detail page) |

The `FileRoutesByTo.to` type is: `'/' | '/live' | '/pipelines' | '/prompts' | '/runs/$runId'`

## 3. TanStack Router Active Route Matching

**Package**: `@tanstack/react-router` v1.161.3

The `useMatchRoute` hook returns a function that checks if a route is active:

```tsx
import { Link, useMatchRoute } from '@tanstack/react-router'

const matchRoute = useMatchRoute()
const isActive = matchRoute({ to: '/live' })  // truthy if /live is active
```

For the index route `/`, matching without `fuzzy` ensures it only matches `/` exactly (not `/runs/123`). For other routes (`/live`, `/prompts`, `/pipelines`), exact matching is also correct since they're leaf routes.

`Link` component from `@tanstack/react-router` handles navigation. Both are already used across the codebase (e.g., `runs/$runId.tsx` uses `Link`).

## 4. Zustand UI Store

**File**: `llm_pipeline/ui/frontend/src/stores/ui.ts`

Already implements all needed sidebar state:

```typescript
interface UIState {
  sidebarCollapsed: boolean    // persisted
  theme: Theme                 // persisted ('dark' | 'light')
  selectedStepId: number | null
  stepDetailOpen: boolean
  toggleSidebar: () => void    // flips sidebarCollapsed
  setTheme: (theme: Theme) => void
  selectStep: (stepId: number | null) => void
  closeStepDetail: () => void
}
```

- Persist key: `'llm-pipeline-ui'`
- Partialize: only `sidebarCollapsed` and `theme` persisted
- Middleware chain: `devtools(persist(...))`
- `onRehydrateStorage` applies dark class on load

**Usage in Sidebar**: `const { sidebarCollapsed, toggleSidebar } = useUIStore()`

## 5. Icon Library

**Package**: `lucide-react` v0.575.0 (installed in dependencies)

The project does NOT use `@heroicons`. Task 41 description references heroicons but this is outdated. All existing components use lucide-react:
- `live.tsx`: `Play`
- `JsonDiff.tsx`, `JsonTree.tsx`, `StrategySection.tsx`: `ChevronRight`, `ChevronDown`
- `runs/$runId.tsx`: `ArrowLeft`
- UI components: `CheckIcon`, `ChevronDownIcon`, `XIcon`

**Equivalent lucide icons for nav items**:

| Task Desc (heroicons) | lucide-react Equivalent | Import |
|----------------------|------------------------|--------|
| `ListBulletIcon` | `List` | `import { List } from 'lucide-react'` |
| `PlayIcon` | `Play` | already used in live.tsx |
| `DocumentTextIcon` | `FileText` | `import { FileText } from 'lucide-react'` |
| `CubeIcon` | `Box` | `import { Box } from 'lucide-react'` |
| collapse toggle | `PanelLeftClose` / `PanelLeftOpen` | sidebar collapse/expand |

## 6. Styling Conventions

### Design Token System (Tailwind v4 + shadcn)

The project uses oklch-based CSS custom properties, NOT raw gray classes. This is an enforced convention from task 30.

**Sidebar-specific tokens** (already defined in `index.css`):

| Token | CSS Variable | Usage |
|-------|-------------|-------|
| `bg-sidebar` | `--sidebar` | Sidebar background |
| `text-sidebar-foreground` | `--sidebar-foreground` | Sidebar text |
| `bg-sidebar-primary` | `--sidebar-primary` | Primary elements in sidebar |
| `text-sidebar-primary-foreground` | `--sidebar-primary-foreground` | Text on primary elements |
| `bg-sidebar-accent` | `--sidebar-accent` | Active/hover highlight |
| `text-sidebar-accent-foreground` | `--sidebar-accent-foreground` | Text on active/hover |
| `border-sidebar-border` | `--sidebar-border` | Sidebar borders |
| `ring-sidebar-ring` | `--sidebar-ring` | Focus ring |

**Dark mode values** (from `.dark` in index.css):
- `--sidebar`: `oklch(0.205 0 0)` (dark gray)
- `--sidebar-foreground`: `oklch(0.985 0 0)` (near white)
- `--sidebar-accent`: `oklch(0.269 0 0)` (slightly lighter gray)
- `--sidebar-border`: `oklch(1 0 0 / 10%)` (subtle white border)

### General Styling Patterns

- `cn()` utility from `@/lib/utils` for conditional class merging
- Button component has `ghost` variant and `icon`/`icon-sm`/`icon-xs` sizes (useful for collapse toggle)
- Page content uses `p-6` padding, `gap-4` spacing
- Transition classes: `transition-all duration-200` (task spec suggests this for sidebar width)
- Rounded corners: `rounded-md`, `rounded-xl` used in various components

### Code Style

- No semicolons
- Single quotes for strings
- 2-space indent
- Named function exports (not default exports)
- Components: PascalCase named functions

## 7. Component Patterns

### File Location

New file: `src/components/Sidebar.tsx`

Top-level component (not nested in a subdirectory) since it's a global layout component, not feature-specific.

### Import Alias

All imports use `@/` alias:
```typescript
import { useUIStore } from '@/stores/ui'
import { cn } from '@/lib/utils'
```

### Existing Component Patterns

Components follow this pattern:
- Interface props defined above component
- Named function export
- Tailwind classes inline (no CSS modules)
- `cn()` for conditional classes

## 8. Integration Point: __root.tsx

The Sidebar will be imported in `__root.tsx` replacing the placeholder:

```tsx
import { Sidebar } from '@/components/Sidebar'

function RootLayout() {
  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
```

The sidebar handles its own width (w-60 collapsed vs w-12) and styling internally.

## 9. Upstream Task Deviations

### Task 30 (TanStack Router Routes) - DONE
- No deviations. All architecture followed as planned.
- Key note: "All new/modified files use design tokens, not raw gray classes"

### Task 32 (Zustand UI Stores) - DONE
- Minor deviation: `main.tsx` uses bare `import '@/stores/ui'` instead of `import { useUIStore }` to avoid unused import warning. Functionally identical.
- `selectedStepId` typed as `number | null` (not `string | null` as originally planned)

## 10. Out of Scope (Downstream Task 44)

Task 44 (Build Frontend for Production) configures vite build output, bundle chunking, and static file serving. No sidebar-specific concerns. The sidebar component is just another React component that will be bundled normally.

## 11. Key Implementation Decisions (Pre-Resolved)

| Decision | Resolution | Basis |
|----------|-----------|-------|
| Icon library | `lucide-react` | Package.json, existing usage across all components |
| Styling approach | Design tokens (`bg-sidebar`, `bg-sidebar-accent`) | Enforced convention from task 30 |
| Active route API | `useMatchRoute()` without `fuzzy` | Exact paths, Context7 docs |
| Width values | `w-60` (expanded), `w-16` (collapsed) | Task spec + root layout precedent |
| Transition | `transition-all duration-200` | Task spec |
| Toggle button | `Button` component with `ghost` variant, `icon-sm` size | Existing Button API |
| Collapse toggle icon | `PanelLeftClose`/`PanelLeftOpen` from lucide-react | Semantic fit for sidebar collapse |
