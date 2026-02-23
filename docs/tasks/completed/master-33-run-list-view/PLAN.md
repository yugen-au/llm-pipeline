# PLANNING

## Summary

Implement the Run List View for the llm-pipeline UI: a paginated, filterable table of pipeline runs at the `/` route. Adds vitest + testing-library infrastructure first (no frontend test runner exists), installs required shadcn/ui components, then builds StatusBadge, FilterBar, Pagination, and RunsTable components before wiring them into the existing `src/routes/index.tsx` placeholder. Status filtering and pagination live in URL search params (already scaffolded with Zod in index.tsx). Pipeline name and date range filters come from the Zustand `useFiltersStore`. The route merges both sources into `RunListParams` for `useRuns()`.

## Plugin & Agents

**Plugin:** frontend-mobile-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Infrastructure**: Vitest setup and shadcn component installation
2. **Components**: StatusBadge, FilterBar, Pagination, time utility (concurrent)
3. **RunsTable**: Table component consuming leaf components
4. **Route wire-up**: Connect all components into index.tsx RunListPage

## Architecture Decisions

### Filter State Split: URL Params vs Zustand
**Choice:** `page` and `status` in URL search params (TanStack Router Zod schema); `pipelineName`, `startedAfter`, `startedBefore` in Zustand `useFiltersStore` (ephemeral, no persist).
**Rationale:** Matches existing `src/routes/index.tsx` Zod schema (already has `page` + `status` params) and `src/stores/filters.ts` (already holds pipeline name + date range). Bookmarkable status/page without exposing ephemeral date pickers in the URL.
**Alternatives:** All in URL (makes date pickers bookmarkable but adds Zod complexity); all in Zustand (breaks back/forward for status filter).

### Relative Timestamps: Native Intl, No External Library
**Choice:** Custom `src/lib/time.ts` using `Date` + `Intl.RelativeTimeFormat`.
**Rationale:** No date utility library in package.json (verified). `date-fns` not installed. Native `Intl.RelativeTimeFormat` covers all needed relative units. Tooltip shows absolute via `Intl.DateTimeFormat`.
**Alternatives:** Install `date-fns` (unnecessary dep for simple relative formatting).

### Pagination: URL-param page, offset computed locally
**Choice:** Page is 1-indexed in URL (`page` param), offset sent to API as `(page - 1) * PAGE_SIZE`. PAGE_SIZE constant = 25.
**Rationale:** CEO confirmed PAGE_SIZE=25. index.tsx already validates `page` as `z.number().int().min(1)` with fallback 1. Pagination component calls `useNavigate` to update `page` param.
**Alternatives:** Offset directly in URL (less human-readable).

### StatusBadge: Strict 3-status, fallback gray
**Choice:** Map `running` -> blue, `completed` -> green, `failed` -> red. Unknown values -> gray (no named "pending" case).
**Rationale:** CEO confirmed strict 3-status only. Backend `state.py` documents exactly running/completed/failed. `RunStatus` type in types.ts confirms no pending. Fallback gray handles any future unknown without crashing.
**Alternatives:** Include "pending" case (CEO explicitly rejected).

### Row Click Navigation: useNavigate to /runs/$runId
**Choice:** Each table row has `onClick={() => navigate({ to: '/runs/$runId', params: { runId: run.run_id } })}`.
**Rationale:** Downstream task 34 implements Run Detail at `/runs/$runId` (route already exists at `src/routes/runs/$runId.tsx`). TanStack Router type-safe `useNavigate` preferred over plain `<Link>` wrapping `<tr>`.
**Alternatives:** Wrap row in Link element (breaks HTML semantics for table rows).

### Vitest Config: Separate vitest.config.ts, jsdom environment
**Choice:** Create `vitest.config.ts` extending vite.config settings with `environment: 'jsdom'` and `setupFiles: ['./src/test/setup.ts']`. Setup file imports `@testing-library/jest-dom/vitest`.
**Rationale:** Vitest recommends separate config file for non-test Vite builds to avoid test globals leaking. jsdom needed for DOM APIs in component tests. `@testing-library/jest-dom/vitest` is the correct import for Vitest (not jest variant).
**Alternatives:** Inline test config in vite.config.ts (mixes concerns, affects build).

## Implementation Steps

### Step 1: Vitest infrastructure setup
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /websites/testing-library
**Group:** A

1. In `llm_pipeline/ui/frontend/package.json`, add devDependencies: `vitest`, `@vitest/coverage-v8`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`. Add script `"test": "vitest"` and `"test:coverage": "vitest run --coverage"`.
2. Create `llm_pipeline/ui/frontend/vitest.config.ts`: import `defineConfig` from vitest/config, import vite plugins (tanstackRouter, react, tailwindcss), set `environment: 'jsdom'`, `setupFiles: ['./src/test/setup.ts']`, `globals: true`, include `src/**/*.{test,spec}.{ts,tsx}`, exclude node_modules.
3. Create `llm_pipeline/ui/frontend/src/test/setup.ts`: import `@testing-library/jest-dom/vitest` to extend expect matchers.
4. Run `npm install` in `llm_pipeline/ui/frontend/` to lock new devDependencies.

### Step 2: Install shadcn/ui components
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** B

1. From `llm_pipeline/ui/frontend/`, run `npx shadcn@latest add table badge button select tooltip` to generate: `src/components/ui/table.tsx`, `src/components/ui/badge.tsx`, `src/components/ui/button.tsx`, `src/components/ui/select.tsx`, `src/components/ui/tooltip.tsx`.
2. Verify `components.json` style (new-york), baseColor (neutral), and cssVariables remain unchanged after install.
3. Confirm `src/components/ui/` contains all 5 generated files.

### Step 3: Time utility + unit tests
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/lib/time.ts` with two exported functions:
   - `formatRelative(isoString: string): string` - returns human-readable relative string (e.g. "3 minutes ago", "2 hours ago", "5 days ago") using `Intl.RelativeTimeFormat('en', { numeric: 'auto' })`. Picks the largest unit where the absolute value >= 1 (seconds < 60 -> "X seconds ago", < 3600 -> "X minutes ago", < 86400 -> "X hours ago", else "X days ago").
   - `formatAbsolute(isoString: string): string` - returns locale date+time string for tooltip use via `Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(isoString))`.
2. Create `llm_pipeline/ui/frontend/src/lib/time.test.ts` with unit tests: relative times for seconds/minutes/hours/days boundaries, absolute format sanity check, graceful handling of future dates.

### Step 4: StatusBadge component + tests
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx`. Import `Badge` from `@/components/ui/badge`. Props: `status: string`. Map status to variant + label:
   - `'running'` -> yellow/amber variant (use `cn` + custom Tailwind classes since Badge variants may not include yellow), label "running"
   - `'completed'` -> green variant, label "completed"
   - `'failed'` -> destructive/red variant, label "failed"
   - fallback -> secondary/gray variant, label = status value
   Note: shadcn Badge has variants `default | secondary | destructive | outline`. Use `outline` + color override classes for running (amber) and completed (green) since those aren't built-in variants. Apply via `cn()` and Tailwind OKLCH tokens from index.css.
2. Create `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.test.tsx`. Test: renders correct text for each of 3 statuses, renders fallback for unknown status, applies expected CSS classes.

### Step 5: Pagination component + tests
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /tanstack/router, /shadcn-ui/ui
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/components/runs/Pagination.tsx`. Props: `total: number`, `page: number`, `pageSize: number`. Compute `totalPages = Math.ceil(total / pageSize)`. Import `Button` from `@/components/ui/button`. Import `useNavigate` from `@tanstack/react-router`. On prev/next click, call `navigate({ to: '/', search: (prev) => ({ ...prev, page: page - 1 }) })` / `navigate({ to: '/', search: (prev) => ({ ...prev, page: page + 1 }) })`. Show "Page X of Y" label. Disable prev when page=1, disable next when page=totalPages or total=0. Also show record range: "Showing X-Y of Z".
2. Create `llm_pipeline/ui/frontend/src/components/runs/Pagination.test.tsx`. Test: renders correct page label, disables prev on page 1, disables next on last page, calls navigate with correct params on button click.

### Step 6: FilterBar component + tests
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /tanstack/router, /shadcn-ui/ui
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/components/runs/FilterBar.tsx`. Import `Select, SelectContent, SelectItem, SelectTrigger, SelectValue` from `@/components/ui/select`. Import `Route` from the index route (or accept `status` + `onStatusChange` as props to keep component testable). Use props pattern: `status: string`, `onStatusChange: (status: string) => void`. Renders a Select with options: All (empty string), Running, Completed, Failed. On change, call `onStatusChange`. This keeps FilterBar pure/testable; the parent route owns navigation.
2. Create `llm_pipeline/ui/frontend/src/components/runs/FilterBar.test.tsx`. Test: renders all 4 options, calls onStatusChange with correct value on selection, shows "All" when status=''.

### Step 7: RunsTable component + tests
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui, /tanstack/router
**Group:** D

1. Create `llm_pipeline/ui/frontend/src/components/runs/RunsTable.tsx`. Import `Table, TableHeader, TableBody, TableRow, TableHead, TableCell` from `@/components/ui/table`. Import `Tooltip, TooltipContent, TooltipProvider, TooltipTrigger` from `@/components/ui/tooltip`. Import `StatusBadge` from `./StatusBadge`. Import `formatRelative`, `formatAbsolute` from `@/lib/time`. Import `useNavigate` from `@tanstack/react-router`. Props: `runs: RunListItem[]`, `isLoading: boolean`, `isError: boolean`. Columns: Run ID (first 8 chars in `<code>`, full ID in Tooltip), Pipeline, Started (formatRelative in cell, formatAbsolute in Tooltip), Status (StatusBadge), Steps (step_count ?? '—'), Duration (total_time_ms formatted as seconds, or '—').
2. Loading state: render skeleton rows (5 rows, cells show pulsing div via `animate-pulse bg-muted`).
3. Error state: render single row spanning all columns with `text-destructive` error message.
4. Empty state: render single row spanning all columns with `text-muted-foreground` "No runs found" message.
5. Row click: `onClick={() => navigate({ to: '/runs/$runId', params: { runId: run.run_id } })}` with `cursor-pointer hover:bg-muted/50` on TableRow.
6. Create `llm_pipeline/ui/frontend/src/components/runs/RunsTable.test.tsx`. Test: renders column headers, renders run rows with truncated run ID, shows StatusBadge, navigates on row click, shows loading skeleton when isLoading, shows error message when isError, shows empty state when runs=[].

### Step 8: Wire up index.tsx RunListPage
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** E

1. Replace `IndexPage` in `llm_pipeline/ui/frontend/src/routes/index.tsx` with `RunListPage` component (keep same export/Route name). Add `PAGE_SIZE = 25` constant.
2. Inside `RunListPage`: call `Route.useSearch()` to get `{ page, status }` URL params. Call `useFiltersStore()` to get `{ pipelineName, startedAfter, startedBefore }`. Compose `RunListParams`: `{ status: status || undefined, pipeline_name: pipelineName || undefined, started_after: startedAfter || undefined, started_before: startedBefore || undefined, offset: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE }`. Call `useRuns(params)`.
3. Import `useNavigate` from `@tanstack/react-router` for status filter changes. Pass `status` + `onStatusChange` to FilterBar, where `onStatusChange` calls `navigate({ to: '/', search: (prev) => ({ ...prev, status: newStatus, page: 1 }) })` (reset to page 1 on filter change).
4. Render: `<div className="flex flex-col h-full p-6">` containing `<h1>`, `<FilterBar .../>`, `<RunsTable runs={data?.items ?? []} isLoading={isLoading} isError={isError} />`, `<Pagination total={data?.total ?? 0} page={page} pageSize={PAGE_SIZE} />`.
5. Add imports: `useRuns` from `@/api/runs`, `useFiltersStore` from `@/stores/filters`, `RunsTable` from `@/components/runs/RunsTable`, `FilterBar` from `@/components/runs/FilterBar`, `Pagination` from `@/components/runs/Pagination`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `npx shadcn@latest add` modifies package.json in unexpected ways or installs conflicting deps | Medium | Run in isolated step B; verify components.json and UI files after; check for dep conflicts |
| TanStack Router `useNavigate` search param updates in tests require mock router context | Medium | Wrap test renders in `createMemoryHistory` + `RouterProvider` or use a minimal test router wrapper; test Pagination/FilterBar with prop callbacks to avoid router dependency |
| Badge component has no built-in amber/green variants; custom colors may not match design tokens | Low | Use `cn()` with explicit Tailwind OKLCH color classes from index.css (e.g. `text-amber-400 border-amber-400`); verify visually |
| Vitest + `@testing-library/jest-dom` version mismatch with React 19 | Low | Pin compatible versions: vitest ^2.x, @testing-library/react ^16.x (React 19 support), jest-dom ^6.x |
| `formatRelative` timezone edge cases causing flaky tests | Low | Test relative times with fixed Date.now() mock via `vi.setSystemTime()` |
| `data?.items` undefined on initial load causes RunsTable to receive undefined | Low | Default prop to `[]` in RunsTable: `runs={data?.items ?? []}` in index.tsx |

## Success Criteria

- [ ] `npm test` runs successfully with vitest in `llm_pipeline/ui/frontend/`
- [ ] `npx shadcn@latest add table badge button select tooltip` generates 5 files in `src/components/ui/`
- [ ] `StatusBadge` renders correct color/label for running, completed, failed, and unknown input
- [ ] `FilterBar` renders 4 options (All, Running, Completed, Failed) and calls `onStatusChange` on selection
- [ ] `Pagination` disables prev on page 1, disables next on last page, shows correct record range
- [ ] `RunsTable` renders all 6 columns with correct data, truncates run ID to 8 chars, shows full ID in tooltip
- [ ] `RunsTable` shows loading skeleton on `isLoading=true`, error message on `isError=true`, "No runs found" on empty array
- [ ] Row click navigates to `/runs/${runId}` via TanStack Router
- [ ] `index.tsx` `IndexPage` replaced with `RunListPage` that calls `useRuns()` with merged URL params + Zustand filters
- [ ] Status filter change resets page to 1 in URL params
- [ ] `PAGE_SIZE` constant = 25 used consistently in index.tsx and Pagination
- [ ] All component tests pass (StatusBadge, FilterBar, Pagination, RunsTable, time utils)

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** shadcn component installation via `npx` is an external side-effect that can fail or modify files unexpectedly. TanStack Router's navigate-in-tests pattern requires router context setup which adds test complexity. Core component logic is straightforward with well-understood patterns.
**Suggested Exclusions:** review
