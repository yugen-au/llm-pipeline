# Research Summary

## Executive Summary

Consolidated and validated research from two domain agents analyzing the frontend codebase (step-1: component inventory/structure, step-2: test infrastructure/patterns) for task 55 (Write Frontend Component Tests).

**Key finding:** Test infrastructure is 100% ready -- zero new dependencies needed. 9 test files exist (88 passing, 3 failing in StatusBadge). 14 untested components + 2 pure functions identified. Established pattern uses hook-level `vi.mock()` (NOT QueryClientProvider wrapping), co-located test files, and consistent loading/error/empty state coverage.

**Corrections applied:** Research misidentified which 3 StatusBadge tests fail. Research also didn't flag the task-55 description's deviation from established patterns. Both corrected below.

## Domain Findings

### Test Infrastructure (Complete, Ready)
**Source:** step-2, validated against `vitest.config.ts`, `src/test/setup.ts`, `package.json`, `tsconfig.app.json`

- Vitest 3.2 with `globals: true`, `jsdom` environment, `@/` path alias -- all verified
- Setup file imports `@testing-library/jest-dom/vitest` + polyfills 4 Radix jsdom gaps (pointerCapture x3, scrollIntoView)
- All test deps installed: `@testing-library/react@16`, `@testing-library/user-event@14`, `@testing-library/jest-dom@6`, `@vitest/coverage-v8@3.2`, `jsdom@26`
- TypeScript types configured: `vitest/globals`, `@testing-library/jest-dom/vitest`
- Scripts: `npm test` (watch), `npm run test:coverage` (single run with v8 coverage)
- **No new packages, config, or setup needed.**

### Existing Tests (9 files, 91 tests)
**Source:** step-1, step-2, validated by running `npx vitest run`

| File | Tests | Status |
|------|-------|--------|
| `src/test/smoke.test.ts` | 2 | Passing |
| `src/lib/time.test.ts` | 16 | Passing |
| `src/components/runs/RunsTable.test.tsx` | 12 | Passing |
| `src/components/runs/StepTimeline.test.tsx` | 16 | Passing |
| `src/components/runs/FilterBar.test.tsx` | 6 | Passing |
| `src/components/runs/Pagination.test.tsx` | 11 | Passing |
| `src/components/runs/StepDetailPanel.test.tsx` | 11 | Passing |
| `src/components/runs/ContextEvolution.test.tsx` | 6 | Passing |
| `src/components/runs/StatusBadge.test.tsx` | 5 | **3 FAILING** |

### StatusBadge Failures (Correction from Research)
**Source:** step-2 (corrected), validated by test run output

Research step-2 claimed failures on: completed, failed, unknown. **Actual failures:** running, completed, failed. The unknown test PASSES (variant="secondary" matches fallback).

Root cause confirmed: Component was refactored from hardcoded Tailwind classes to semantic CSS custom properties. Tests assert stale values:
- `running`: expects `border-amber-500` / `text-amber-600`, actual is `border-status-running` / `text-status-running`
- `completed`: expects `border-green-500` / `text-green-600`, actual is `border-status-completed` / `text-status-completed`
- `failed`: expects `dataset.variant === 'destructive'`, actual is `variant="outline"` with `border-status-failed` / `text-status-failed`

Component also has `skipped` and `pending` statuses not currently tested.

### Established Testing Patterns (6 patterns)
**Source:** step-1, step-2, validated against FilterBar.test.tsx, RunsTable.test.tsx, StepDetailPanel.test.tsx

1. **Hook mocking at module level** -- `vi.mock('@/api/module', () => ({ useHook: (...args) => mockUseHook(...args) }))`. All 6 component test files use this consistently. NOT QueryClientProvider wrapping.
2. **Router mocking** -- `vi.mock('@tanstack/react-router', () => ({ useNavigate: () => mockNavigate }))`
3. **Time utility mocking** -- `vi.mock('@/lib/time', async (importOriginal) => ...)` with deterministic stubs
4. **Fake timers + Radix workaround** -- `vi.useFakeTimers()` in beforeEach, `vi.useRealTimers()` before `userEvent.setup()` for Radix interactions
5. **Radix portal queries** -- `document.querySelector('[data-slot="sheet-content"]')` for Sheet/Dialog
6. **Loading/error/empty state triad** -- Every component test covers: `.animate-pulse` skeletons, `.text-destructive` error messages, `.text-muted-foreground` empty states

**Radix Select interaction pattern** (from FilterBar.test.tsx): `screen.getByRole('combobox', { name: /label/i })` for trigger, `screen.getByRole('option', { name: 'Value' })` for items, `userEvent.click()` for selection.

### Task 55 Description Deviation (Flagged)
**Source:** task-55 details vs established codebase patterns

Task 55 description suggests:
- Test files in `src/__tests__/` directory
- Wrapping components in `QueryClientProvider`

Established codebase pattern (validated):
- Co-located test files (e.g. `StatusBadge.test.tsx` next to `StatusBadge.tsx`)
- Hook-level `vi.mock()` instead of QueryClientProvider

**Decision: Follow established codebase patterns.** The task description is from initial project setup and predates the actual test infrastructure.

### Component Inventory (Untested)
**Source:** step-1, all components validated against source files

#### Tier 1: Pure/Presentational (no internal data fetching)

| # | Component | Props (validated) | Key Test Concerns |
|---|-----------|-------------------|-------------------|
| 1 | `JsonDiff` | `before, after, maxDepth?` | Uses `microdiff` lib. Renders CREATE(+green)/REMOVE(-red)/CHANGE(yellow) diffs. Empty state: "No changes". Collapsible branches via useState. |
| 2 | `FormField` | `name, fieldSchema: JsonSchema, value, onChange, error: string\|undefined, required` | Renders different inputs per `fieldSchema.type`: string->Input, integer/number->Input[type=number], boolean->Checkbox, fallback->Textarea(JSON). Sets `aria-invalid` on error. |
| 3 | `InputForm` | `schema: JsonSchema\|null, values, onChange, fieldErrors, isSubmitting` | Returns null when schema=null. Renders FormField per property. Wraps in `<fieldset disabled={isSubmitting}>`. Exports `validateForm()` pure function. Has `data-testid="input-form"`. |
| 4 | `EventStream` | `events: EventItem[], wsStatus: WsConnectionStatus, runId: string\|null` | 3 empty states: no runId, no events, events. ConnectionIndicator maps 6 WsConnectionStatus values. Uses `formatRelative` from `@/lib/time` (needs time mock). Auto-scroll via useEffect. |
| 5 | `PromptFilterBar` | `promptTypes[], pipelineNames[], selectedType, selectedPipeline, onTypeChange, onPipelineChange, searchText, onSearchChange` | Uses `ALL_SENTINEL = '__all'` pattern. Contains Input + 2 Select dropdowns. |
| 6 | `PromptList` | `prompts: Prompt[], selectedKey, onSelect, isLoading, error: Error\|null` | NOTE: receives `error: Error\|null` not `isError: boolean`. Loading/error/empty/data states. Selection highlight. |
| 7 | `PipelineList` | `pipelines: PipelineListItem[], selectedName, onSelect, isLoading, error: Error\|null` | NOTE: receives `error: Error\|null` not `isError: boolean`. Shows destructive badge when `pipeline.error != null` (mutually exclusive with step count badge). |
| 8 | `StrategySection` | `strategy: PipelineStrategyMetadata, pipelineName` | Recursive: StepRow accordion children. Error state when strategy.error present. Step rows expand to show prompt keys, schemas (JsonTree), extractions. **CEO scope: smoke test only.** |
| 9 | `JsonTree` | `data: Record<string,unknown>\|unknown[]\|null, depth?` | Recursive: JsonTreeNode. PrimitiveValue color-coded by type. Auto-expand depth < 2. Null guard returns italic "null". **CEO scope: boundary tests only (empty, null, simple object, single-level).** |

#### Tier 2: Components with Internal Data Fetching Hooks

| # | Component | Hook | Props (validated) | Mock Shape |
|---|-----------|------|-------------------|------------|
| 10 | `PipelineSelector` | `usePipelines()` | `selectedPipeline, onSelect, disabled?` | `{ data: { pipelines: PipelineListItem[] }, isLoading, isError }` |
| 11 | `PromptViewer` | `usePromptDetail(key)` | `promptKey: string\|null` | `{ data: { prompt_key, variants: PromptVariant[] }, isLoading, error }`. Has `highlightVariables()` internal function. 5 states: no key, loading, error, single variant (no tabs), multi variant (Tabs). |
| 12 | `PipelineDetail` | `usePipeline(name)` | `pipelineName: string\|null` | `{ data: PipelineMetadata, isLoading, error }`. Renders: name, registry_models badges, execution_order, pipeline_input_schema (JsonTree), strategies (StrategySection[]). |

#### Tier 3: Route Pages

| # | Route | Hooks to Mock | Complexity |
|---|-------|---------------|------------|
| 13 | `routes/index.tsx` (RunListPage) | `useRuns`, `useNavigate`, `Route.useSearch`, `useFiltersStore` | Medium -- composes RunsTable + FilterBar + Pagination |
| 14 | `routes/runs/$runId.tsx` (RunDetailPage) | `useRun`, `useSteps`, `useEvents`, `useRunContext`, `useWebSocket`, `useUIStore`, `Route.useParams`, `Link` | High -- 4 data hooks + WS + store + time formatting |

#### Tier 4: Smoke-Only Components (CEO directive)

| # | Component | Test Depth | Rationale |
|---|-----------|-----------|-----------|
| 15 | `Sidebar` | Smoke: renders, 4 nav items present | Needs router mock (Link), media query mock, Zustand store mock. No interaction tests. |

#### Pure Functions

| # | Function | Location | Test Type |
|---|----------|----------|-----------|
| 16 | `toSearchParams` | `src/api/types.ts` | Unit: omit null/undefined, encode params, empty -> "" |
| 17 | `ApiError` | `src/api/types.ts` | Unit: constructor sets name/status/detail, extends Error |
| 18 | `validateForm` | `src/components/live/InputForm.tsx` | Unit: required field validation, type validation |

### Zustand Stores (Context for Route Page Tests)
**Source:** step-1, validated against store files

- `useWsStore` (`stores/websocket.ts`): `WsConnectionStatus` has 6 values: idle, connecting, connected, replaying, closed, error
- `useFiltersStore` (`stores/filters.ts`): pipelineName, startedAfter, startedBefore + actions
- `useUIStore` (`stores/ui.ts`): sidebarCollapsed, theme, selectedStepId, stepDetailOpen + actions. Persists to localStorage.

For tests: mock stores at module level same as hooks, OR use actual Zustand stores (they work without providers). Existing tests don't test stores directly -- mocking is the established approach.

### Sidebar Mocking Requirements (Validated)
**Source:** step-1, validated against Sidebar.tsx and use-media-query.ts

Sidebar requires 3 mocks:
1. `@tanstack/react-router` -- `Link` component (renders `<a>` with `to` prop)
2. `@/hooks/use-media-query` -- `useMediaQuery` returns boolean
3. `@/stores/ui` -- `useUIStore` with selector pattern

Additional complexity: Sidebar uses Radix `Sheet` (mobile), `Tooltip` (collapsed desktop), `TooltipProvider`. For smoke test, these render fine in jsdom with existing polyfills.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| StatusBadge 3 pre-existing failing tests: fix as part of task 55, or track separately? | Fix as part of task 55 | StatusBadge fix is IN SCOPE. Update assertions to semantic classes + add missing `skipped`/`pending` status tests. |
| Focus on untested pure/presentational components, or also cover route pages? | BOTH -- cover untested components AND route-level pages (RunListPage, RunDetailPage) | Scope is larger than research initially recommended. Route pages require heavier mocking (4+ hooks each). Plan must include both tiers. |
| Exclude Sidebar/JsonTree/StrategySection due to complexity? | Include ALL but with tiered test depth: Sidebar=smoke, JsonTree=boundary, StrategySection=smoke | No blind spots, but no brittle deep tests either. Tiered depth avoids both failure modes. |

## Assumptions Validated

- [x] Test infra complete -- vitest.config.ts, setup.ts, all deps installed, tsconfig types configured
- [x] Hook mocking pattern is THE established approach (not QueryClientProvider) -- verified across all 6 component test files
- [x] Co-located test files is THE established approach (not src/__tests__/) -- verified across all 9 test files
- [x] StatusBadge failures caused by stale assertions after semantic CSS refactor -- confirmed by test run + component source
- [x] All 14 untested components exist at documented paths with documented props
- [x] usePipelines() returns `{ pipelines: PipelineListItem[] }` via apiClient generic -- PipelineSelector's `data?.pipelines` access is correct
- [x] EventStream is pure presentational (no internal hooks) -- can be tested by passing props directly
- [x] PromptList and PipelineList receive `error: Error | null` (not `isError: boolean`) -- affects mock setup
- [x] Radix Select tested via role queries: combobox for trigger, option for items (FilterBar.test.tsx pattern)
- [x] WsConnectionStatus has 6 values (idle, connecting, connected, replaying, closed, error) -- important for exhaustive EventStream/ConnectionIndicator testing
- [x] Sidebar needs 3 mocks (router Link, useMediaQuery, useUIStore) -- CEO approved smoke-only scope
- [x] No MSW needed -- hook mocking eliminates HTTP-level mocking requirement
- [x] Fake timer + Radix deadlock workaround documented and proven (vi.useRealTimers() before userEvent.setup())

## Open Items

- None. All scope questions resolved by CEO. All research claims validated against codebase.

## Recommendations for Planning

1. **Fix StatusBadge first** -- unblock the test suite (currently 3 failures). Update assertions to semantic classes (`border-status-*`, `text-status-*`), fix variant assertions (`outline` not `destructive`), add `skipped` and `pending` status tests.
2. **Start with pure functions** -- `toSearchParams`, `ApiError`, `validateForm` are trivial wins that establish momentum and catch regressions in utility code.
3. **Then Tier 1 presentational components** -- JsonDiff, FormField, InputForm, EventStream, PromptFilterBar, PromptList, PipelineList. These are the highest-ROI tests (complex rendering logic, zero mock setup beyond props).
4. **Then Tier 2 hook-dependent components** -- PipelineSelector, PromptViewer, PipelineDetail. Follow established `vi.mock()` pattern.
5. **Then Tier 4 smoke tests** -- Sidebar (smoke), JsonTree (boundary), StrategySection (smoke). Minimal assertions per CEO directive.
6. **Route pages last** -- RunListPage and RunDetailPage require the most mocking (4-8 hooks each). By this point all child components are tested, so route tests focus on composition and navigation.
7. **Follow established patterns exactly** -- co-located files, hook mocking, loading/error/empty triad, Radix portal queries, time mock stubs. Do NOT introduce new patterns (QueryClientProvider, MSW, src/__tests__/).
8. **EventStream needs time mock** -- uses `formatRelative` from `@/lib/time`. Follow existing `vi.mock('@/lib/time', ...)` pattern for deterministic output.
9. **PromptList/PipelineList mock shape differs** -- these receive `error: Error | null` not `isError: boolean`. Mock must pass `new Error('msg')` for error state tests.
10. **PipelineList badge mutual exclusivity** -- when `pipeline.error != null`, destructive "error" badge replaces step count badge. Test both paths.
