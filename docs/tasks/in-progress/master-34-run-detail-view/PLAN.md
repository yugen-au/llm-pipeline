# PLANNING

## Summary

Implement the Run Detail View (task 34) by populating the existing `runs/$runId.tsx` placeholder route with a run header, step timeline, context evolution panel, and a minimal step detail slide-over. WebSocket is wired for live step updates. Task 35 owns the full 7-tab StepDetailPanel; task 36 upgrades ContextEvolution with JsonDiff. All code follows task 33 conventions: named function exports, Tailwind-only styling, cn() utility, loading/error/empty state pattern.

## Plugin & Agents

**Plugin:** frontend-mobile-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Shared utilities**: Extract formatDuration to time.ts, extend StatusBadge for step statuses, install missing shadcn components
2. **Components**: Build StepTimeline, ContextEvolution, StepDetailPanel skeleton in parallel
3. **Route assembly**: Wire all components into RunDetailPage with useWebSocket
4. **Tests**: Vitest component tests for all new files

## Architecture Decisions

### StepDetailPanel as div-based slide-over
**Choice:** Implement StepDetailPanel as a fixed-position div slide-over without shadcn Sheet
**Rationale:** Task 35 installs Sheet and replaces StepDetailPanel entirely. Building a div-based minimal container avoids Sheet dependency while giving task 35 a clear replacement target. Only shows: step name, step number, model, timing.
**Alternatives:** Install Sheet now - rejected because task 35 explicitly owns Sheet installation and will rewrite the component anyway.

### Inline step status derivation in StepTimeline
**Choice:** Derive step status (running/completed/skipped) via useMemo inside StepTimeline using events query data
**Rationale:** Single consumer of this logic. No other component in task 34 (or tasks 35/36) requires step status derivation. A separate hook would be premature abstraction. Logic: scan events.items for step_started events without a matching step_completed or step_failed for the same step_name.
**Alternatives:** `useStepStatuses(runId)` hook - deferred until a second consumer exists.

### ContextEvolution as always-expanded list
**Choice:** Render each step context snapshot as always-visible pre-formatted JSON under a step_name heading in a ScrollArea
**Rationale:** Task 36 redesigns this component with JsonDiff and collapsible nodes. Task 34 should provide a minimal readable implementation that task 36 can replace wholesale. Always-expanded avoids state management overhead for a temporary design.
**Alternatives:** Collapsible via HTML details/summary - not worth the complexity for a temporary implementation.

### StatusBadge extended for step-specific statuses
**Choice:** Add 'skipped' and 'pending' entries to statusConfig in StatusBadge.tsx
**Rationale:** StatusBadge already accepts `RunStatus | (string & {})` with unknown-status fallback. Adding step-specific statuses to the typed config map provides correct colors. No new component needed.
**Alternatives:** Separate StepStatusBadge component - rejected as unnecessary duplication.

### formatDuration extracted to time.ts
**Choice:** Add `export function formatDuration(ms: number | null): string` to src/lib/time.ts and update RunsTable to import it
**Rationale:** VALIDATED_RESEARCH identifies this as a planned extraction. StepTimeline needs duration formatting. Keeping a private copy in RunsTable while adding another in StepTimeline violates DRY. time.ts already exists for time utilities.
**Alternatives:** Keep private copy in RunsTable + add another in StepTimeline - rejected (duplication).

## Implementation Steps

### Step 1: Shared utilities - formatDuration + StatusBadge
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/ui/frontend/src/lib/time.ts`, add exported `formatDuration(ms: number | null): string` function (returns em dash for null, seconds with 1 decimal otherwise - matching RunsTable's private implementation)
2. In `llm_pipeline/ui/frontend/src/lib/time.test.ts`, add test cases for `formatDuration`: null returns em dash, 0 returns '0.0s', 1500 returns '1.5s', 60000 returns '60.0s'
3. In `llm_pipeline/ui/frontend/src/components/runs/RunsTable.tsx`, remove the private `formatDuration` function and import `formatDuration` from `@/lib/time`
4. In `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx`, add step-specific statuses to `statusConfig`: `skipped` (secondary variant, muted text), `pending` (secondary variant, muted text). Update the type annotation from `Record<RunStatus, BadgeConfig>` to `Record<string, BadgeConfig>` to accommodate step statuses without importing a new union type.

### Step 2: Install shadcn components
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** A

1. Run `npx shadcn@latest add card` from `llm_pipeline/ui/frontend/` to install Card, CardHeader, CardContent, CardTitle components
2. Run `npx shadcn@latest add separator` from `llm_pipeline/ui/frontend/` to install Separator component
3. Run `npx shadcn@latest add scroll-area` from `llm_pipeline/ui/frontend/` to install ScrollArea component
4. Verify the three new component files exist: `src/components/ui/card.tsx`, `src/components/ui/separator.tsx`, `src/components/ui/scroll-area.tsx`

### Step 3: StepTimeline component
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/runs/StepTimeline.tsx`
2. Define `StepStatus` type: `'completed' | 'running' | 'failed' | 'skipped' | 'pending'`
3. Define interface `StepTimelineItem` with fields: `step_name: string`, `step_number: number`, `status: StepStatus`, `execution_time_ms: number | null`, `model: string | null`
4. Define interface `StepTimelineProps` with: `items: StepTimelineItem[]`, `isLoading: boolean`, `isError: boolean`, `selectedStepId: number | null`, `onSelectStep: (stepNumber: number) => void`
5. Implement `deriveStepStatus` utility function: given `StepListItem[]` from DB and `EventItem[]` from events cache, return merged `StepTimelineItem[]`. Logic: all DB steps = 'completed'; scan events for step_started without matching step_completed/step_failed = 'running' step (add if not in DB); scan for step_skipped events = 'skipped' (override if in DB as completed to handle edge case).
6. Implement loading skeleton: 4 skeleton rows with animate-pulse divs
7. Implement error state: single row with text-destructive "Failed to load steps"
8. Implement empty state: "No steps recorded" with text-muted-foreground
9. Implement step row: step number badge, step name, StatusBadge for status, formatDuration for timing, model as muted small text. Selected step highlighted with bg-muted/50. Cursor-pointer, hover bg-muted/30.
10. Export named `export function StepTimeline(props: StepTimelineProps)`

### Step 4: ContextEvolution component
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.tsx`
2. Define interface `ContextEvolutionProps` with: `snapshots: ContextSnapshot[]`, `isLoading: boolean`, `isError: boolean`
3. Import `ContextSnapshot` from `@/api/types`, `ScrollArea` from `@/components/ui/scroll-area`
4. Implement loading state: 3 skeleton blocks with animate-pulse
5. Implement error state: text-destructive "Failed to load context"
6. Implement empty state: "No context snapshots" with text-muted-foreground
7. Implement snapshot list: for each snapshot, render step_name as `h4` with step_number, followed by `pre` tag with `JSON.stringify(snapshot.context_snapshot, null, 2)`. Use `text-xs font-mono` for pre, `overflow-x-auto` wrapper. Separate snapshots with a thin border.
8. Wrap entire list in `ScrollArea` with `h-full` class for vertical scroll
9. Export named `export function ContextEvolution(props: ContextEvolutionProps)`

### Step 5: StepDetailPanel skeleton
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`
2. Define interface `StepDetailPanelProps` with: `runId: string`, `stepNumber: number | null`, `open: boolean`, `onClose: () => void`, `runStatus?: string`
3. Import `useStep` from `@/api/steps`, `formatDuration` from `@/lib/time`, `formatAbsolute` from `@/lib/time`
4. Implement panel as fixed right-side div: `fixed inset-y-0 right-0 w-96 bg-background border-l border-border shadow-xl transition-transform duration-200`. Apply `translate-x-0` when open, `translate-x-full` when closed.
5. Implement close button: X button in panel header using `Button` variant ghost with aria-label "Close step detail"
6. When `stepNumber` is null or not `open`: render closed (translated out)
7. When open and stepNumber provided: call `useStep(runId, stepNumber, runStatus)`. Show loading spinner while loading. Show error message on error.
8. Render step data when loaded: step_name as panel title, step_number as subtitle, model (or em dash), execution_time_ms via formatDuration, created_at via formatAbsolute. Add placeholder comment: `{/* Task 35: replace with tabbed implementation */}`
9. Export named `export function StepDetailPanel(props: StepDetailPanelProps)`

### Step 6: RunDetailPage assembly
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** C

1. Replace contents of `llm_pipeline/ui/frontend/src/routes/runs/$runId.tsx` - preserve the existing `Route` export with its Zod search schema and `createFileRoute` call
2. Add imports: `useRun` from `@/api/runs`, `useRunContext` from `@/api/runs`, `useSteps` from `@/api/steps`, `useEvents` from `@/api/events`, `useWebSocket` from `@/api/websocket`, `useUIStore` from `@/stores/ui`, `StepTimeline` + `deriveStepStatus` from components, `ContextEvolution`, `StepDetailPanel`, `StatusBadge` from components, `Card`, `CardHeader`, `CardContent`, `CardTitle` from shadcn, `formatDuration`, `formatAbsolute`, `formatRelative` from time, `Tooltip*` from shadcn
3. Wire `useWebSocket(runId)` at top of `RunDetailPage` - returns `{ status, error }` for optional connection indicator
4. Fetch run: `useRun(runId)` - use for header data and pass status to child hooks
5. Fetch steps: `useSteps(runId, run?.status)` - source for StepTimeline DB steps
6. Fetch events: `useEvents(runId, {}, run?.status)` - source for WS event correlation
7. Fetch context: `useRunContext(runId, run?.status as RunStatus)` - source for ContextEvolution
8. Get UI state: `const { selectedStepId, stepDetailOpen, selectStep, closeStepDetail } = useUIStore()`
9. Derive `timelineItems` via `deriveStepStatus(steps?.items ?? [], events?.items ?? [])` wrapped in useMemo
10. Implement run header: Card with pipeline_name, run_id (truncated 8 chars with Tooltip for full), StatusBadge, started_at (relative + absolute tooltip), total_time_ms via formatDuration. Back link to '/' using TanStack Router Link.
11. Implement page body: flex layout - StepTimeline takes remaining space (flex-1), ContextEvolution as fixed-width right column (w-80). StepDetailPanel rendered at page level as overlay.
12. Pass `onSelectStep={selectStep}` to StepTimeline, `selectedStepId` for highlight state.
13. Handle run-level loading state: full-page skeleton when `useRun` is loading. Handle run not found (404): "Run not found" error message with link back.
14. Use `run?.status` as string (not cast to RunStatus) for hooks that accept `string` param; cast to `RunStatus` only where type requires it.

### Step 7: Component tests
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Create `llm_pipeline/ui/frontend/src/components/runs/StepTimeline.test.tsx`. Tests: renders step rows with name/number/status/duration; loading skeleton shows animate-pulse elements; error state shows error text; empty state shows "No steps recorded"; selected step has highlight class; onSelectStep called on row click; deriveStepStatus unit tests (running step from events, skipped step, completed from DB, fallback for empty events).
2. Create `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx`. Tests: renders step names as headers; renders JSON snapshots; loading state shows skeleton; error state shows error text; empty state shows "No context snapshots".
3. Create `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`. Tests: renders closed when open=false; renders panel content when open=true and step loaded; shows loading when useStep loading; shows error on useStep error; onClose called on close button click. Mock useStep hook.
4. All test files: mock @tanstack/react-router (useNavigate if needed), mock @/lib/time (formatRelative/formatAbsolute/formatDuration), mock hooks (useStep), use vi.useFakeTimers/vi.setSystemTime pattern from RunsTable.test.tsx.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| shadcn add command fails in CI or needs interactive prompt | Medium | Use `npx shadcn@latest add --yes card separator scroll-area` with --yes flag; verify component files post-install |
| WS event cache not yet populated when StepTimeline mounts (race between useEvents REST fetch and WS stream) | Low | deriveStepStatus falls back gracefully to DB steps only when events.items is empty; WS will eventually populate and trigger re-render |
| step_started event_data.step_name field absent or differently cased | Medium | Validate against actual event_data shape from step-2 research before writing deriveStepStatus; add defensive null-check |
| StepDetailPanel fixed positioning may overlap page content unintentionally | Low | Use z-50 on the panel; StepTimeline and ContextEvolution use padding-right when panel is open |
| RunsTable formatDuration removal breaks RunsTable tests | Low | RunsTable tests don't test formatDuration directly (tested via rendered output '1.5s'); import change is transparent |
| useWebSocket triggers re-renders on every WS event in RunDetailPage | Low | useWebSocket returns stable status/error from Zustand; React Query cache updates only trigger re-renders in components that subscribe to the relevant query |

## Success Criteria

- [ ] Route `/runs/:runId` renders run header with pipeline_name, status badge, run_id, and timing
- [ ] StepTimeline renders all completed steps from useSteps with correct status colors
- [ ] StepTimeline shows "running" step derived from WS events when run is active
- [ ] Clicking a step opens StepDetailPanel with step name, number, model, and timing
- [ ] StepDetailPanel closes via X button and updates useUIStore
- [ ] ContextEvolution renders raw JSON per step snapshot
- [ ] useWebSocket is wired and step list updates live for active runs
- [ ] formatDuration exported from time.ts, RunsTable imports from there
- [ ] StatusBadge renders 'skipped' and 'pending' with correct styles
- [ ] All new components have loading, error, and empty states
- [ ] shadcn card, separator, scroll-area installed and used
- [ ] All vitest tests pass with no new warnings
- [ ] TypeScript build passes with no new errors

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Multiple concurrent component files + shadcn installation + WS integration creates moderate coordination complexity. The StepDetailPanel div-based slide-over is a temporary design explicitly targeted for replacement in task 35, which reduces risk of bad architecture but adds implementation coupling risk. formatDuration extraction touches existing tested code (RunsTable).
**Suggested Exclusions:** review
