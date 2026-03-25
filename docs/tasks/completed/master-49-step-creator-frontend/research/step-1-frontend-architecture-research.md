# Frontend Architecture Research -- Task 49 (Step Creator Frontend View)

## 1. Project Structure

Frontend root: `llm_pipeline/ui/frontend/`

```
src/
  api/            # REST client, TanStack Query hooks, types
  components/     # UI components (domain + shared)
    ui/           # shadcn/ui primitives (Badge, Button, Card, Tabs, Sheet, etc.)
    runs/         # Run domain (StepDetailPanel, StepTimeline, FilterBar, etc.)
    pipelines/    # Pipeline domain
    prompts/      # Prompt domain
    live/         # Live execution (EventStream, InputForm, PipelineSelector)
  hooks/          # Custom hooks (use-media-query)
  lib/            # Utilities (cn, time formatters)
  routes/         # TanStack Router file-based routes
  stores/         # Zustand stores (ui, filters, websocket)
  test/           # Test setup
```

## 2. Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | React | 19.2+ |
| Build | Vite | 7.3+ |
| Routing | TanStack Router | 1.161.3 (file-based, autoCodeSplitting) |
| Server state | TanStack Query | 5.90+ |
| Client state | Zustand | 5.0+ |
| Styling | Tailwind CSS | 4.2+ (via @tailwindcss/vite plugin) |
| UI primitives | shadcn/ui (Radix) | radix-ui 1.4.3 |
| Validation | Zod | 4.3+ |
| Icons | Lucide React | 0.575+ |
| TypeScript | TS | 5.9.3 |
| Testing | Vitest + RTL + jsdom | vitest 3.2+ |
| Font | JetBrains Mono Variable | monospace |

## 3. Routing

### Pattern
TanStack Router with **file-based routing** and **autoCodeSplitting** enabled in Vite plugin. Routes auto-generate `routeTree.gen.ts`. Each route file exports `Route = createFileRoute('/path')({ component: Component })`.

### Existing routes
| Path | File | Description |
|------|------|-------------|
| `/` | `routes/index.tsx` | Run list with filters, pagination |
| `/live` | `routes/live.tsx` | Live pipeline execution (3-col layout) |
| `/pipelines` | `routes/pipelines.tsx` | Pipeline list + detail (2-col layout) |
| `/prompts` | `routes/prompts.tsx` | Prompt list + viewer (2-col layout) |
| `/runs/$runId` | `routes/runs/$runId.tsx` | Run detail with step timeline |

### Route creation pattern
```typescript
import { createFileRoute } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'

const searchSchema = z.object({
  key: fallback(z.string(), '').default(''),
})

export const Route = createFileRoute('/path')({
  validateSearch: zodValidator(searchSchema),
  component: PageComponent,
})
```

### New route for creator
File: `src/routes/creator.tsx` -- will auto-register as `/creator` in routeTree.gen.ts after TanStack Router plugin processes it.

## 4. State Management

### Zustand stores (UI-only state)
| Store | File | Purpose |
|-------|------|---------|
| `useUIStore` | `stores/ui.ts` | sidebar, theme, selectedStepId, stepDetailOpen. Persists sidebar+theme to localStorage. |
| `useFiltersStore` | `stores/filters.ts` | Run list filters (pipelineName, date range). Ephemeral. |
| `useWsStore` | `stores/websocket.ts` | WS connection status, error, reconnect count. Ephemeral. |

### TanStack Query (server state)
- All REST data fetched via hooks returning `useQuery` / `useMutation`
- Centralized query key factory: `src/api/query-keys.ts`
- Global defaults: `staleTime: 30_000`, `retry: 2`, `refetchOnWindowFocus: false`
- Dynamic staleTime pattern: terminal runs get `Infinity`, active runs get short stale + polling
- Single mutation exists: `useCreateRun` in `runs.ts` (useMutation + invalidateQueries on success)

### Pattern for creator
New hooks needed in a new `src/api/creator.ts` file:
- `useGenerateStep()` -- mutation, POST /api/creator/generate
- `useTestDraft()` -- mutation, POST /api/creator/test/{draft_id}
- `useAcceptDraft()` -- mutation, POST /api/creator/accept/{draft_id}
- `useDrafts()` -- query, GET /api/creator/drafts
- `useDraft(draftId)` -- query, GET /api/creator/drafts/{draft_id}

New query keys needed in `query-keys.ts`:
```typescript
creator: {
  all: ['creator'] as const,
  drafts: () => ['creator', 'drafts'] as const,
  draft: (id: number) => ['creator', 'drafts', id] as const,
}
```

## 5. API Client Pattern

### apiClient wrapper (`src/api/client.ts`)
```typescript
async function apiClient<T>(path: string, options?: RequestInit): Promise<T>
```
- Prepends `/api` to path
- Throws typed `ApiError(status, detail)` on non-OK
- Vite dev proxy: `/api` -> `http://localhost:8642`, `/ws` -> `ws://localhost:8642`

### Types (`src/api/types.ts`)
All TypeScript interfaces mirror backend Pydantic response models. New types needed for creator:
- `GenerateRequest`, `GenerateResponse` (matching backend)
- `TestRequest`, `TestResponse`
- `AcceptRequest`, `AcceptResponse`
- `DraftItem`, `DraftListResponse`

### Mutation pattern (from useCreateRun)
```typescript
export function useCreateRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (req: TriggerRunRequest) =>
      apiClient<TriggerRunResponse>('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.runs.all })
    },
  })
}
```

## 6. Backend Creator API Endpoints (Task 48, Done)

File: `llm_pipeline/ui/routes/creator.py`

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | `/api/creator/generate` | 202 | Background step generation. Returns `{ run_id, draft_name, status }`. Creates PipelineRun + DraftStep, broadcasts WS run_created. |
| POST | `/api/creator/test/{draft_id}` | 200 | Sync sandbox test. Merges code_overrides, persists, runs StepSandbox. Returns `TestResponse`. Can block up to 60s (Docker). |
| POST | `/api/creator/accept/{draft_id}` | 200 | Accept draft: writes files, registers prompts, optionally modifies pipeline. Returns `AcceptResponse`. |
| GET | `/api/creator/drafts` | 200 | List all drafts ordered by created_at desc. Returns `DraftListResponse`. |
| GET | `/api/creator/drafts/{draft_id}` | 200 | Get single draft. Returns `DraftItem`. |

### Key behaviors
- Generate is 202+background (matches trigger_run pattern). Creates PipelineRun for "step_creator" pipeline, uses UIBridge+CompositeEmitter for WS events.
- Test merges `code_overrides` into `DraftStep.generated_code` and persists BEFORE running sandbox ("test and save" semantics).
- Accept calls `StepIntegrator` which owns commit/rollback.
- DraftStep.generated_code is a dict with keys: `{step_name}_step.py`, `{step_name}_instructions.py`, `{step_name}_prompts.py`, optionally `{step_name}_extraction.py`.

## 7. StepDetailPanel Component

File: `src/components/runs/StepDetailPanel.tsx`

### Props
```typescript
interface StepDetailPanelProps {
  runId: string
  stepNumber: number | null
  open: boolean
  onClose: () => void
  runStatus?: string
}
```

### Structure
- Outer: shadcn `Sheet` (slide-over overlay, 600px width)
- Inner: `StepContent` component (mounts only when open && stepNumber != null)
- Data sources (4 hooks): `useStep`, `useStepEvents`, `useStepInstructions`, `useRunContext`
- 7 tabs: Meta, Input, Prompts, Response, Instructions, Context, Extractions
- Each tab has a private component (MetaTab, InputTab, PromptsTab, etc.)

### Reuse considerations for task 49
StepDetailPanel is tightly coupled to pipeline run step data (StepDetail type, EventItem events). The creator's test results (`SandboxResult`: import_ok, security_issues, output, errors, modules_found) have a completely different shape. Direct reuse of StepDetailPanel as-is is not possible. Options:
1. Show the generation PipelineRun's steps via StepDetailPanel (shows meta-pipeline progress)
2. Build new results panel for sandbox test output
3. Extract visual patterns (tabs, layout, scroll areas) but new data bindings

## 8. Tabs Component Pattern

File: `src/components/ui/tabs.tsx` (shadcn/ui, Radix Tabs primitive)

Usage pattern (from StepDetailPanel, LivePage):
```tsx
<Tabs defaultValue="meta" className="flex min-h-0 flex-1 flex-col">
  <TabsList className="mx-4 mt-3 shrink-0 flex-wrap">
    <TabsTrigger value="meta">Meta</TabsTrigger>
    <TabsTrigger value="input">Input</TabsTrigger>
  </TabsList>
  <TabsContent value="meta"><MetaTab /></TabsContent>
  <TabsContent value="input"><InputTab /></TabsContent>
</Tabs>
```

Both `variant="default"` (solid bg) and `variant="line"` (underline indicator) available.

## 9. Monaco Editor

### Current state
**Not installed.** No `@monaco-editor/react` in package.json. No existing Monaco usage. The only "monaco" reference in the codebase is in the CSS font stack (`Monaco` as a fallback monospace font).

### Installation
```bash
npm install @monaco-editor/react
```

### Lazy loading pattern
Only existing lazy pattern: `ReactQueryDevtools` in `main.tsx` uses `React.lazy()` + `Suspense`.

TanStack Router's `autoCodeSplitting: true` already code-splits routes automatically. Monaco should be additionally lazy-loaded within the creator route since it's ~2MB:
```tsx
const MonacoEditor = lazy(() => import('@monaco-editor/react'))

// Usage:
<Suspense fallback={<EditorSkeleton />}>
  <MonacoEditor language="python" value={code} onChange={handleChange} />
</Suspense>
```

### Vite manual chunks
`vite.config.ts` already has `manualChunks` for react, router, query. Monaco should get its own chunk:
```typescript
if (id.includes('node_modules/monaco-editor/')) {
  return 'monaco'
}
```

## 10. Three-Column Layout Pattern

### Precedent: LivePage (`routes/live.tsx`)
Desktop (lg+): `grid grid-cols-3 gap-4` with column content extracted as variables for reuse in mobile tabs.
Mobile (below lg): Tab-based layout with same content.

```tsx
<div className="flex h-full flex-col gap-4 p-6">
  <div>
    <h1>Page Title</h1>
    <p>Subtitle</p>
  </div>
  {/* Desktop: 3-col grid */}
  <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-3 lg:gap-4">
    <div className="overflow-auto">{col1}</div>
    <div className="overflow-hidden">{col2}</div>
    <div className="overflow-hidden">{col3}</div>
  </div>
  {/* Mobile: tabs */}
  <div className="flex min-h-0 flex-1 flex-col lg:hidden">
    <Tabs>...</Tabs>
  </div>
</div>
```

## 11. Sidebar Navigation

File: `src/components/Sidebar.tsx`

Nav items defined as array:
```typescript
const navItems: NavItem[] = [
  { to: '/', label: 'Runs', icon: List },
  { to: '/live', label: 'Live', icon: Play },
  { to: '/prompts', label: 'Prompts', icon: FileText },
  { to: '/pipelines', label: 'Pipelines', icon: Box },
]
```

Creator needs to be added here. Requires icon selection from Lucide.

NavItem type uses `keyof FileRoutesByTo` for type-safe routing -- the route must exist in the generated route tree.

## 12. Testing Patterns

### Setup
- `vitest.config.ts`: globals, jsdom, setup file with Radix polyfills
- Test files colocated: `Component.test.tsx` next to `Component.tsx`
- Route tests: `routes/index.test.tsx`, `routes/runs/$runId.test.tsx`

### Hook mocking pattern (from StepDetailPanel.test.tsx)
```typescript
const mockUseStep = vi.fn()
vi.mock('@/api/steps', () => ({
  useStep: (...args: unknown[]) => mockUseStep(...args),
}))

beforeEach(() => {
  mockUseStep.mockReset()
  mockUseStep.mockReturnValue({ data: mockData, isLoading: false, isError: false })
})
```

### Rendering
```typescript
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
render(<Component {...props} />)
```

No router wrapper needed for non-route components. Route components may need `RouterProvider` or custom wrappers.

## 13. Generated Code Artifact Keys

From `llm_pipeline/creator/models.py` -- `GeneratedStep.from_draft()`:

| Dict key pattern | GeneratedStep field | Monaco tab label (proposed) |
|------------------|--------------------|-----------------------------|
| `{name}_step.py` | `step_code` | Step |
| `{name}_instructions.py` | `instructions_code` | Instructions |
| `{name}_prompts.py` | `prompts_code` | Prompts |
| `{name}_extraction.py` (optional) | `extraction_code` | Extraction |

All values are Python source code strings. Monaco language: `python` for all tabs.

The `all_artifacts` field is the full dict. When code_overrides are sent via test endpoint, keys in the dict are updated (e.g., `{"my_step_step.py": "new code..."}`).

## 14. WebSocket Integration for Generate

Generate endpoint creates a PipelineRun for "step_creator" pipeline and broadcasts `run_created` WS event. The existing `useWebSocket(runId)` hook can track progress. The generation run_id is returned in `GenerateResponse.run_id`.

Flow:
1. User clicks Generate -> `useGenerateStep.mutate()`
2. Backend returns 202 with `{ run_id, draft_name }`
3. Frontend connects `useWebSocket(run_id)` to track meta-pipeline progress
4. WS events stream in (step_started, llm_call_starting, llm_call_completed, step_completed, etc.)
5. On `stream_complete` -> poll/fetch draft to get populated generated_code

## 15. DraftStep Data Shape

Backend model (`llm_pipeline/state.py`):
```python
class DraftStep(SQLModel, table=True):
    id: int (PK)
    name: str (unique, max 100)
    description: str | None
    generated_code: dict (JSON)  # {"{name}_step.py": "...", ...}
    test_results: dict | None (JSON)  # SandboxResult dump
    validation_errors: dict | None (JSON)
    status: str  # draft, tested, accepted, error
    run_id: str | None (max 36)
    created_at: datetime
    updated_at: datetime
```

API response (`DraftItem`): id, name, description, status, run_id, created_at, updated_at. Note: generated_code and test_results are NOT included in list/detail responses (kept lightweight per task 48 recommendation #5). A `DraftDetail` model may be needed for task 49.

## 16. Upstream Task Deviations

### Task 48 (Creator API Endpoints) -- relevant deviations
- `DraftItem` response model intentionally omits `generated_code` and `test_results` to keep list responses lightweight. Task 48 recommendation #5 suggests adding `DraftDetail` model when task 49 requirements are clearer.
- Generate background task reads `ctx.get("all_artifacts", {})` (fixed from initial bug that used wrong key).
- Code overrides persist to DraftStep.generated_code on test ("test and save" semantics).

### Task 35 (Step Detail Panel) -- relevant deviations
- StepDetailPanel uses Sheet (slide-over overlay), not inline panel.
- 4 data sources via hooks: useStep, useStepEvents, useStepInstructions, useRunContext.
- Tab order: meta first (default), then input, prompts, response, instructions, context, extractions.

## 17. Open Questions for CEO

### Q1: StepDetailPanel "reuse" in results panel (CRITICAL)
Task 49 spec says "Right: Results panel (reuse StepDetail)". StepDetailPanel is a Sheet overlay that fetches its own data via (runId, stepNumber) hooks. Its data shape (StepDetail, EventItem) is incompatible with creator test results (SandboxResult: import_ok, security_issues, output, errors, modules_found).

Options:
- **(a)** Use StepDetailPanel to show the generation PipelineRun's meta-pipeline step details (shows AI generation progress, not test results)
- **(b)** Build a new inline results panel for sandbox test output with similar visual style (tabs/cards/badges)
- **(c)** Both: StepDetailPanel overlay for generation progress + inline results panel for test output
- **(d)** Extract tab/layout patterns from StepDetailPanel into shared components, build new data bindings for creator context

### Q2: Draft list/picker or fresh form only?
Should the creator page support resuming existing drafts (draft picker/list), or just new creation with fresh form? This affects whether we need a left sidebar with draft list (like prompts page) or a simple form.

### Q3: GET /api/creator/drafts/{id} response -- needs generated_code and test_results?
Current DraftItem response omits generated_code and test_results (task 48 intentional). The frontend needs these to populate Monaco editor and results panel. Options:
- **(a)** Add a DraftDetail endpoint/model that includes full fields (task 48 recommendation #5)
- **(b)** Fetch generated_code separately via a new endpoint
- **(c)** Only show generated_code from the generate mutation response, never re-fetch from backend
