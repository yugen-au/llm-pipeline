# PLANNING

## Summary

Write React Testing Library tests for key frontend components in `llm_pipeline/ui/frontend/src/`. Fix 3 failing StatusBadge tests (stale assertions after CSS class refactor), write tests for 14 untested components grouped by tier (pure functions, presentational, hook-dependent, route pages), and add tiered smoke/boundary tests for Sidebar, JsonTree, and StrategySection. All tests use the existing Vitest+jsdom+RTL+jest-dom+user-event infra with the established hook-level `vi.mock()` pattern and co-located test file placement.

## Plugin & Agents

**Plugin:** javascript-typescript
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Fix StatusBadge** - Unblock the suite by updating 3 failing assertions to semantic CSS classes and adding missing skipped/pending status tests.
2. **Pure Functions** - Unit test `toSearchParams`, `ApiError` (src/api/types.ts), and `validateForm` (src/components/live/InputForm.tsx).
3. **Tier 1 Presentational** - Test pure/presentational components: JsonDiff, FormField, InputForm, EventStream, PromptFilterBar, PromptList, PipelineList.
4. **Tier 2 Hook-Dependent** - Test components with internal data-fetching hooks: PipelineSelector, PromptViewer, PipelineDetail.
5. **Tiered Smoke/Boundary** - Smoke tests for Sidebar and StrategySection; boundary tests for JsonTree.
6. **Route Pages** - Integration-style tests for RunListPage and RunDetailPage using hook-level mocking.

## Architecture Decisions

### Test File Placement
**Choice:** Co-locate test files next to source files (e.g., `FormField.tsx` -> `FormField.test.tsx` in same directory).
**Rationale:** All 9 existing test files follow co-location pattern. Task 55's description suggesting `src/__tests__/` predates the actual codebase pattern and is superseded by what was actually built.
**Alternatives:** Centralized `src/__tests__/` directory (rejected - contradicts established pattern).

### Hook Mocking vs QueryClientProvider
**Choice:** Mock TanStack Query hooks at module level with `vi.mock()`.
**Rationale:** All 6 existing component test files that depend on data hooks use `vi.mock()` exclusively. This avoids QueryClient setup, makes tests synchronous, and isolates component rendering from cache behavior. Validated in FilterBar.test.tsx, StepDetailPanel.test.tsx, RunsTable.test.tsx.
**Alternatives:** `QueryClientProvider` wrapping (rejected - contradicts established pattern, adds complexity with no benefit for unit-style component tests).

### Tiered Test Depth for Complex Components
**Choice:** Sidebar=smoke only, JsonTree=boundary only (null/empty/simple object), StrategySection=smoke only.
**Rationale:** CEO directive confirmed. These components are recursive/complex with extensive Radix UI and router dependencies. Full interaction tests would be brittle and high-maintenance. Smoke tests still catch regressions in basic rendering.
**Alternatives:** No tests (rejected - blind spots), full interaction tests (rejected - brittleness risk per CEO).

### StatusBadge Fix Approach
**Choice:** Update assertions to match current semantic CSS classes (`border-status-*`, `text-status-*`), fix `failed` variant from `destructive` to `outline`, add `skipped` and `pending` status tests.
**Rationale:** Component source confirms all statuses now use `variant="outline"` with `className: 'border-status-{status} text-status-{status}'`. The `unknown-state` fallback correctly returns `variant="secondary"`. The VALIDATED_RESEARCH.md confirms actual failing tests are `running`, `completed`, `failed` (not `unknown`).
**Alternatives:** Revert component to Tailwind color classes (rejected - out of scope, breaks design intent).

### Fake Timers Usage
**Choice:** Use `vi.useFakeTimers()` in `beforeEach` for components using time utilities, call `vi.useRealTimers()` before `userEvent.setup()` for Radix interaction tests.
**Rationale:** Established pattern in StepDetailPanel.test.tsx. Radix UI components deadlock with fake timers during pointer events. EventStream uses `formatRelative` from `@/lib/time` requiring the existing time mock pattern.
**Alternatives:** Real timers only (rejected - flaky tests due to time-dependent output).

## Implementation Steps

### Step 1: Fix StatusBadge failing tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** A

1. Read `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.test.tsx` and `StatusBadge.tsx` in full.
2. Update the `'running'` test: replace `toHaveClass('border-amber-500')` and `toHaveClass('text-amber-600')` with `toHaveClass('border-status-running')` and `toHaveClass('text-status-running')`.
3. Update the `'completed'` test: replace `toHaveClass('border-green-500')` and `toHaveClass('text-green-600')` with `toHaveClass('border-status-completed')` and `toHaveClass('text-status-completed')`.
4. Update the `'failed'` test: remove `expect(badge.dataset.variant).toBe('destructive')`, add `toHaveClass('border-status-failed')` and `toHaveClass('text-status-failed')`.
5. Add test for `'skipped'` status: assert `toHaveClass('border-status-skipped')` and `toHaveClass('text-status-skipped')`.
6. Add test for `'pending'` status: assert `toHaveClass('border-status-pending')` and `toHaveClass('text-status-pending')`.
7. Verify test for `'unknown-state'` still correctly asserts `badge.dataset.variant === 'secondary'` (this test passes; keep unchanged).

### Step 2: Pure function unit tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest
**Group:** B

1. Read `llm_pipeline/ui/frontend/src/api/types.ts` in full to confirm `toSearchParams` signature and `ApiError` constructor.
2. Read `llm_pipeline/ui/frontend/src/components/live/InputForm.tsx` in full to confirm `validateForm` signature and logic.
3. Create `llm_pipeline/ui/frontend/src/api/types.test.ts`:
   - `describe('toSearchParams')`: test empty object -> `""`, single param -> `"?key=value"`, multiple params, omits `null` values, omits `undefined` values, encodes special characters.
   - `describe('ApiError')`: test constructor sets `name='ApiError'`, sets `status`, sets `detail`, extends `Error` (instanceof check).
4. Create `llm_pipeline/ui/frontend/src/components/live/validateForm.test.ts` (or add to InputForm.test.tsx -- see Step 4):
   - Tests for required field missing -> error returned, required field present -> no error, type validation for integer field with non-numeric string -> error, valid values -> empty errors object.

### Step 3: JsonDiff presentational component tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** B

1. Read `llm_pipeline/ui/frontend/src/components/JsonDiff.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/JsonDiff.test.tsx`:
   - `'shows "No changes" for identical objects'`: render with same before/after, assert `screen.getByText('No changes')`.
   - `'shows CREATE entry with + prefix for added key'`: `before={{}}, after={{b:2}}`, assert `+` indicator and `b` key visible.
   - `'shows REMOVE entry with - prefix for deleted key'`: `before={{a:1}}, after={{}}`, assert `-` indicator and `a` key visible.
   - `'shows CHANGE entry for modified value'`: `before={{a:1}}, after={{a:2}}`, assert both values visible with change indicator.
   - `'renders nested object diffs'`: test with nested object to confirm recursive rendering doesn't crash.
   - `'respects maxDepth prop'`: provide shallow object with `maxDepth={1}`, assert component renders without error.

### Step 4: FormField and InputForm tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** B

1. Read `llm_pipeline/ui/frontend/src/components/live/FormField.tsx` in full.
2. Read `llm_pipeline/ui/frontend/src/components/live/InputForm.tsx` in full.
3. Create `llm_pipeline/ui/frontend/src/components/live/FormField.test.tsx`:
   - `'renders Input for string type'`: fieldSchema.type='string', assert `<input>` element present.
   - `'renders number Input for integer type'`: fieldSchema.type='integer', assert `input[type="number"]`.
   - `'renders Checkbox for boolean type'`: fieldSchema.type='boolean', assert `input[type="checkbox"]`.
   - `'renders Textarea as fallback for object type'`: fieldSchema.type='object', assert `<textarea>`.
   - `'shows required indicator when required=true'`: assert `*` indicator visible.
   - `'shows error message and aria-invalid when error prop set'`: assert error text visible, input has `aria-invalid="true"`.
   - `'shows description when fieldSchema.description present'`: assert description text visible.
   - `'calls onChange on input change'`: fire change event, assert mock called with new value.
4. Create `llm_pipeline/ui/frontend/src/components/live/InputForm.test.tsx`:
   - `'returns null when schema is null'`: render with schema=null, assert container is empty.
   - `'renders data-testid="input-form" when schema present'`: assert `screen.getByTestId('input-form')`.
   - `'renders FormField for each property in schema'`: schema with 2 properties, assert 2 inputs rendered.
   - `'disables fieldset when isSubmitting=true'`: assert `fieldset` has `disabled` attribute.
   - `'calls onChange when field changes'`: simulate user input, assert onChange called.
   - `describe('validateForm')`: required field missing -> returns `{fieldName: 'required error'}`, all valid -> returns `{}`.

### Step 5: EventStream tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** B

1. Read `llm_pipeline/ui/frontend/src/components/live/EventStream.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/live/EventStream.test.tsx`:
   - Mock `@/lib/time` using `vi.mock('@/lib/time', async (importOriginal) => ...)` returning deterministic `formatRelative`.
   - `'shows "Waiting for run..." when runId is null'`: assert text present.
   - `'shows "No events yet" when events array is empty and runId present'`: runId='r1', events=[], assert text.
   - `'renders event rows when events present'`: pass 2 EventItem objects, assert event type and step name visible.
   - `'ConnectionIndicator: shows "idle" status'`: wsStatus='idle', assert label visible.
   - `'ConnectionIndicator: shows "connected" status'`: wsStatus='connected', assert label.
   - `'ConnectionIndicator: shows "error" status'`: wsStatus='error', assert label.
   - `'ConnectionIndicator: shows "connecting" status'`: wsStatus='connecting', assert label.
   - `'ConnectionIndicator: shows "replaying" status'`: wsStatus='replaying', assert label.
   - `'ConnectionIndicator: shows "closed" status'`: wsStatus='closed', assert label.

### Step 6: PromptFilterBar tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** C

1. Read `llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.test.tsx`:
   - `'renders search input'`: assert `input` or `textbox` role present.
   - `'calls onSearchChange on input'`: fire change event, assert mock called.
   - `'shows "All Types" option in type select'`: open combobox, assert "All" option present.
   - `'calls onTypeChange with value on selection'`: open type select, click option, assert mock called.
   - `'shows "All Pipelines" option in pipeline select'`: open combobox, assert "All" option present.
   - `'calls onPipelineChange with value on selection'`: open pipeline select, click option, assert mock called.
   - `'populates type options from promptTypes prop'`: pass promptTypes=['chat','embed'], open select, assert both visible.

### Step 7: PromptList tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** C

1. Read `llm_pipeline/ui/frontend/src/components/prompts/PromptList.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/prompts/PromptList.test.tsx`:
   - Note: component receives `error: Error | null` not `isError: boolean`. Mock must pass `new Error('msg')`.
   - `'shows loading skeleton when isLoading=true'`: assert `.animate-pulse` elements present.
   - `'shows error message when error is an Error object'`: pass `error={new Error('load failed')}`, assert text with `.text-destructive`.
   - `'shows empty state when prompts=[]'`: assert "No prompts" or similar text with `.text-muted-foreground`.
   - `'renders a button per prompt'`: pass 2 Prompt objects, assert 2 clickable items.
   - `'highlights selected prompt'`: pass selectedKey matching one prompt, assert highlight class on that item.
   - `'calls onSelect with prompt key on click'`: click a prompt button, assert mock called with correct key.

### Step 8: PipelineList tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** C

1. Read `llm_pipeline/ui/frontend/src/components/pipelines/PipelineList.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/pipelines/PipelineList.test.tsx`:
   - Note: component receives `error: Error | null`. Note badge mutual exclusivity: when `pipeline.error != null`, show destructive badge; otherwise show step count badge.
   - `'shows loading skeleton when isLoading=true'`.
   - `'shows error message when error is an Error object'`: `error={new Error('fail')}`, assert `.text-destructive`.
   - `'shows empty state when pipelines=[]'`.
   - `'renders a button per pipeline'`: pass 2 PipelineListItem objects, assert 2 items.
   - `'shows step count badge when pipeline has no error'`: assert step count badge visible, no destructive badge.
   - `'shows destructive error badge instead of step count when pipeline.error != null'`: assert destructive badge, no step count badge.
   - `'calls onSelect on click'`: click item, assert mock called with pipeline name.
   - `'highlights selected pipeline'`: pass selectedName matching one pipeline, assert highlight class.

### Step 9: PipelineSelector tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** D

1. Read `llm_pipeline/ui/frontend/src/components/live/PipelineSelector.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/live/PipelineSelector.test.tsx`:
   - Mock `usePipelines` from `@/api/pipelines` using `vi.mock()`. Mock shape: `{ data: { pipelines: PipelineListItem[] }, isLoading, isError }`.
   - `'shows loading skeleton when isLoading=true'`.
   - `'shows error state when isError=true'`.
   - `'shows "No pipelines registered" when pipelines=[]'`.
   - `'renders Select with pipeline options when data present'`: pass 2 pipelines, open combobox, assert both options visible.
   - `'calls onSelect with pipeline name on selection'`: select option, assert mock called.
   - `'disables Select when disabled=true'`: assert combobox is disabled.

### Step 10: PromptViewer tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** D

1. Read `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.test.tsx`:
   - Mock `usePromptDetail` from `@/api/prompts`. Mock shape: `{ data: { prompt_key, variants: PromptVariant[] }, isLoading, error }`.
   - `'shows "Select a prompt" when promptKey=null'`.
   - `'shows loading skeleton when isLoading=true'`.
   - `'shows error state when error is set'`.
   - `'renders prompt content for single variant (no tabs)'`: 1 variant, assert content visible without Tabs.
   - `'renders Tabs for multiple variants'`: 2 variants, assert tab triggers visible.
   - `'highlights {variable} placeholders in content'`: content with `{name}` variable, assert highlighted span.

### Step 11: PipelineDetail tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** D

1. Read `llm_pipeline/ui/frontend/src/components/pipelines/PipelineDetail.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/pipelines/PipelineDetail.test.tsx`:
   - Mock `usePipeline` from `@/api/pipelines`. Mock shape: `{ data: PipelineMetadata, isLoading, error }`.
   - `'shows "Select a pipeline" when pipelineName=null'`.
   - `'shows loading skeleton when isLoading=true'`.
   - `'shows error state when error is set'`.
   - `'renders pipeline name, execution_order, and registry_models badges'`: pass metadata with these fields, assert visible.
   - `'renders JsonTree for pipeline_input_schema'`: assert schema keys visible in tree.
   - `'renders StrategySection for each strategy'`: 2 strategies, assert both strategy names visible.

### Step 12: Sidebar smoke test
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** E

1. Read `llm_pipeline/ui/frontend/src/components/Sidebar.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/Sidebar.test.tsx`:
   - Mock `@tanstack/react-router`: `Link` renders `<a href={to}>` (stub).
   - Mock `@/hooks/use-media-query`: `useMediaQuery` returns `false` (desktop mode).
   - Mock `@/stores/ui`: `useUIStore` returns `{ sidebarCollapsed: false, toggleSidebar: vi.fn() }`.
   - `'renders without crashing (smoke)'`: render Sidebar, assert no thrown errors.
   - `'shows 4 navigation items'`: assert 4 nav links visible (Runs, Live, Pipelines, Prompts or as named in component).
   - No interaction tests per CEO directive.

### Step 13: JsonTree boundary tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** E

1. Read `llm_pipeline/ui/frontend/src/components/pipelines/JsonTree.tsx` in full (note: file is in `live/` per step-1 research - verify actual path).
2. Create test file co-located with `JsonTree.tsx`:
   - `'renders italic "null" when data=null'`: assert italic null text.
   - `'renders empty tree for empty object {}'`: render with `data={}`, assert no errors.
   - `'renders empty tree for empty array []'`: render with `data=[]`, assert no errors.
   - `'renders primitive values at single level'`: `data={a: 'str', b: 42, c: true}`, assert all 3 keys visible.
   - No recursive depth tests, no expand/collapse interaction tests per CEO directive.

### Step 14: StrategySection smoke test
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** E

1. Read `llm_pipeline/ui/frontend/src/components/pipelines/StrategySection.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/components/pipelines/StrategySection.test.tsx`:
   - Mock `@tanstack/react-router`: `Link` renders `<a>` stub (StrategySection links to /prompts).
   - `'renders without crashing (smoke)'`: render with minimal PipelineStrategyMetadata, assert no thrown errors.
   - `'renders strategy display_name'`: assert strategy name text visible.
   - `'shows error badge when strategy.error is set'`: pass strategy with error field, assert error text/badge visible.
   - No StepRow expansion or accordion interaction tests per CEO directive.

### Step 15: RunListPage route tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** F

1. Read `llm_pipeline/ui/frontend/src/routes/index.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/routes/index.test.tsx`:
   - Mock `useRuns` from `@/api/runs`.
   - Mock `useNavigate` and `Route.useSearch` from `@tanstack/react-router`. `Route.useSearch` returns `{ page: 1, status: '' }`.
   - Mock `useFiltersStore` from `@/stores/filters` to return `{ pipelineName: null, startedAfter: null, startedBefore: null }`.
   - `'renders "Pipeline Runs" heading'`: assert heading visible.
   - `'shows loading skeleton when useRuns isLoading=true'`: assert `.animate-pulse` elements.
   - `'shows error state when useRuns isError=true'`.
   - `'renders runs table when data present'`: pass 2 RunListItem objects, assert table rows visible.
   - `'calls navigate on status filter change'`: interact with FilterBar, assert `mockNavigate` called with correct search params.
   - `'calls navigate on pagination change'`: click next page, assert `mockNavigate` called.

### Step 16: RunDetailPage route tests
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitest-dev/vitest, /testing-library/react-testing-library
**Group:** F

1. Read `llm_pipeline/ui/frontend/src/routes/runs/$runId.tsx` in full.
2. Create `llm_pipeline/ui/frontend/src/routes/runs/$runId.test.tsx`:
   - Mock `useRun`, `useRunContext` from `@/api/runs`.
   - Mock `useSteps` from `@/api/steps`.
   - Mock `useEvents` from `@/api/events`.
   - Mock `useWebSocket` from `@/api/websocket` returning no-op.
   - Mock `useUIStore` from `@/stores/ui` returning `{ selectedStepId: null, stepDetailOpen: false, selectStep: vi.fn(), closeStepDetail: vi.fn() }`.
   - Mock `Route.useParams` from `@tanstack/react-router` returning `{ runId: 'r1' }`.
   - Mock `Route.useSearch` returning `{ tab: 'steps' }`.
   - Mock `Link` from `@tanstack/react-router` as `<a>` stub.
   - Mock `@/lib/time` with deterministic stubs (formatRelative, formatAbsolute, formatDuration).
   - `'shows loading skeleton when useRun isLoading=true'`: assert `.animate-pulse` present.
   - `'shows run ID and status badge when data loaded'`: pass RunDetail with run_id and status, assert visible.
   - `'shows error state when useRun isError=true'`.
   - `'renders StepTimeline with steps'`: pass 2 StepDetail items, assert step names visible.
   - `'renders back navigation link'`: assert link/button with back navigation present.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Route pages use `Route.useSearch` and `Route.useParams` which are TanStack Router static methods on the Route object - may need to mock the `Route` export itself | High | Read source file carefully; if `Route.useSearch` is called directly, mock via `vi.mock('@tanstack/react-router', ...)` or mock the entire route module; fall back to exporting the Page component separately for testing |
| JsonTree actual file location may differ from research (research shows `live/` for some, `pipelines/` for others) | Medium | Read actual directory listings before creating test files; confirmed as `pipelines/` for JsonTree per step-1 research |
| PipelineDetail renders StrategySection which renders JsonTree - nested recursive components may cause deep render issues in jsdom | Medium | If render hangs/crashes, mock StrategySection in PipelineDetail tests with `vi.mock('./StrategySection', ...)` |
| StrategySection links to `/prompts` via TanStack Router `Link` - if not mocked, will throw "No route context" | High | Always mock `@tanstack/react-router` in any test file that renders components using `Link` |
| EventStream auto-scroll useEffect uses sentinel ref - may cause act() warnings | Low | Wrap renders in `act()` or use `waitFor()` if warnings appear; auto-scroll is non-critical to assert |
| Radix Select in PromptFilterBar (2 selects) may require `vi.useRealTimers()` before `userEvent.setup()` | Medium | Follow established FilterBar.test.tsx pattern: don't use fake timers in PromptFilterBar tests since no time dependency exists |
| PipelineSelector mock shape: `usePipelines()` returns `{ data: { pipelines: [...] } }` - incorrect nesting will cause runtime error | Medium | Per VALIDATED_RESEARCH.md: `data?.pipelines` access pattern is correct; mock as `{ data: { pipelines: [] }, isLoading: false, isError: false }` |

## Success Criteria

- [ ] `npm test` (or `npx vitest run`) in `llm_pipeline/ui/frontend/` exits with 0 failing tests.
- [ ] StatusBadge.test.tsx has 0 failing tests (currently 3 failing).
- [ ] New test files created co-located with their source files (not in `src/__tests__/`).
- [ ] Pure function tests cover `toSearchParams`, `ApiError`, and `validateForm`.
- [ ] All Tier 1 presentational components have test files: JsonDiff, FormField, InputForm, EventStream, PromptFilterBar, PromptList, PipelineList.
- [ ] All Tier 2 hook-dependent components have test files: PipelineSelector, PromptViewer, PipelineDetail.
- [ ] Sidebar has smoke test (renders, 4 nav items present).
- [ ] JsonTree has boundary tests (null, empty, simple object).
- [ ] StrategySection has smoke test (renders, display_name, error state).
- [ ] RunListPage has route-level test file.
- [ ] RunDetailPage has route-level test file.
- [ ] No new npm packages added to package.json.
- [ ] No QueryClientProvider wrapping in any new test file.
- [ ] No `src/__tests__/` directory created.

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All tests follow established patterns with zero architectural decisions remaining. No new dependencies, no schema changes, no integration points beyond existing test infra. The only unknowns are how `Route.useSearch`/`Route.useParams` are mocked for route pages (mitigated by reading source first), and whether nested recursive components cause render issues (mitigated by mocking child components if needed). These are implementation-level concerns, not architectural risks.
**Suggested Exclusions:** testing, review
