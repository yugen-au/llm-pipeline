# Research Summary

## Executive Summary

Both research files (Step 1: frontend patterns, Step 2: API & data layer) are high quality -- 95%+ of claims verified against actual codebase. All TypeScript types, backend endpoints, hooks, Zustand stores, shadcn components, and layout patterns confirmed. Two items need creation (usePromptDetail hook, queryKeys.prompts.detail factory). The key ambiguity -- "pipeline filter" -- is resolved: CEO wants actual pipeline name filtering via client-side cross-reference with introspection data. Full scroll (no pagination) with URL-param-based selection confirmed.

## Domain Findings

### Frontend Tech Stack
**Source:** step-1-frontend-patterns-research.md

Verified versions: React 19.2, TanStack Router 1.161.3, TanStack Query ^5.90.21, Zustand ^5.0.11, Tailwind ^4.2.0, Vite ^7.3.1. Path alias `@/` -> `./src/*` confirmed. All shadcn/ui components listed (Card, Badge, Button, Select, ScrollArea, Sheet, Tabs, Separator, Tooltip, Table, Input, Label, Checkbox, Textarea) are installed.

### Routing & Search Params
**Source:** step-1-frontend-patterns-research.md

File-based routing via `createFileRoute`. Search param validation uses zod + `@tanstack/zod-adapter` (confirmed in `$runId.tsx`). prompts.tsx stub exists -- needs full replacement. Selected prompt will use URL search params (CEO confirmed bookmarkable).

### State Management
**Source:** step-1-frontend-patterns-research.md

- TanStack Query: staleTime 30s, retry 2, refetchOnWindowFocus false (exact match in queryClient.ts)
- Zustand stores: `ui.ts` (devtools+persist, sidebar/theme/step selection), `filters.ts` (devtools only, ephemeral)
- Pattern: `create<State>()(devtools(persist(...)))` with named devtools

### Prompt Data Model
**Source:** step-2-api-data-layer-research.md

All fields in `llm_pipeline/db/prompt.py` verified exactly: id, prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables (JSON), description, version, is_active, created_at, updated_at, created_by. Constraints: UniqueConstraint(prompt_key, prompt_type), composite index on (category, step_name), index on is_active. **No pipeline_name field exists on Prompt model.**

### Backend API Endpoints
**Source:** step-2-api-data-layer-research.md

All verified:
- `GET /api/prompts` -- PromptListResponse { items, total, offset, limit } with filters: category, step_name, prompt_type, is_active (default True), offset, limit (50, max 200)
- `GET /api/prompts/{prompt_key}` -- PromptDetailResponse { prompt_key, variants[] } -- returns ALL variants regardless of is_active
- `GET /api/pipelines/{name}/steps/{step_name}/prompts` -- StepPromptsResponse, uses introspection to find declared prompt keys per step
- `GET /api/pipelines` -- PipelineListResponse { pipelines[] } with name, strategy_count, step_count
- `GET /api/pipelines/{name}` -- PipelineMetadata with strategies[].steps[].system_key, user_key

### Frontend API Layer
**Source:** step-1 + step-2

Verified existing:
- `usePrompts(filters)` in `src/api/prompts.ts` -- works, calls GET /api/prompts
- `usePipelines()` in `src/api/pipelines.ts` -- fetches all pipelines
- `usePipeline(name)` in `src/api/pipelines.ts` -- fetches single pipeline metadata (enabled when name truthy)
- `useStepInstructions(pipelineName, stepName)` in `src/api/pipelines.ts`
- All TypeScript types in `src/api/types.ts` match backend exactly
- `queryKeys.prompts.all` and `.list(filters)` exist; `queryKeys.pipelines.all`, `.detail(name)`, `.stepPrompts(name, stepName)` exist

Verified missing:
- `usePromptDetail(promptKey)` hook -- needs creation
- `queryKeys.prompts.detail(key)` factory -- needs creation

### Layout Patterns
**Source:** step-1-frontend-patterns-research.md

All layout precedents confirmed:
- RunDetailPage: `flex min-h-0 flex-1 gap-4` with `w-80 shrink-0` sidebar
- LivePage: desktop 3-col grid + mobile tabs
- Root: `flex h-screen bg-background text-foreground overflow-hidden` with `w-60` aside
- Monospace: `<pre className="whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs">`
- Filter: `ALL_SENTINEL = '__all'` pattern in shadcn Select (confirmed in FilterBar.tsx)
- Loading: `animate-pulse rounded bg-muted` skeletons
- Error: `text-sm text-destructive`
- Empty: `text-sm text-muted-foreground`

### Pipeline Filter Feasibility
**Source:** CEO answer + cross-reference analysis

CEO wants filtering by actual pipeline name (e.g. "RateCardExtractionPipeline"). This is **feasible without backend changes** via client-side cross-reference:

1. `usePipelines()` returns list of pipeline names (already exists)
2. `usePipeline(name)` returns `PipelineMetadata` with `strategies[].steps[].system_key` and `user_key` -- these are prompt_key values
3. Strategy: fetch all pipelines, build a `Map<prompt_key, pipeline_name[]>` lookup, then filter the full prompt list client-side by matching prompt.prompt_key against the lookup

This is NOT contradictory -- it's a pure frontend join. No backend changes needed. The data path:
```
GET /api/pipelines -> pipeline names
GET /api/pipelines/{name} -> metadata.strategies[].steps[].system_key/user_key -> prompt_keys
GET /api/prompts (limit=200, no filters) -> all prompts
Client-side: filter prompts where prompt_key IN pipeline's prompt_keys
```

**Performance note:** With CEO's confirmation of 20-200 prompts and a small number of pipelines (typically 1-5), fetching all pipelines metadata + all prompts in parallel is acceptable. Pipeline metadata is static (staleTime: Infinity pattern already in useStepInstructions).

**Edge case:** A prompt may belong to multiple pipelines (shared prompt_key across pipelines). The lookup should be `prompt_key -> pipeline_name[]` (many-to-many).

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| What does "pipeline filter" mean? category, step_name, or actual pipeline name? | Actual pipeline name (e.g. RateCardExtractionPipeline) via cross-reference | Client-side join needed: fetch pipeline metadata to extract prompt_keys per pipeline, then filter prompts. No backend changes. Resolves contradiction between Step 1 (step_name) and Step 2 (category). |
| Should selected prompt be URL-param or ephemeral state? | URL params (bookmarkable) | Use zod-validated search params per $runId.tsx pattern. Route: `/prompts?key=prompt_key` |
| Pagination UX for left panel? | Full scroll, load all prompts in one call, client-side filtering | Set limit=200 (backend max) or omit pagination entirely. Native scroll. File-browser UX. No infinite scroll or page buttons. |

## Assumptions Validated

- [x] All TypeScript types match backend Pydantic response models exactly
- [x] Backend GET /api/prompts list endpoint is fully functional with filters
- [x] Backend GET /api/prompts/{prompt_key} detail endpoint is fully functional
- [x] usePrompts(filters) hook works and follows established patterns
- [x] No usePromptDetail hook exists -- must be created
- [x] No queryKeys.prompts.detail(key) -- must be created
- [x] shadcn/ui components (Card, Badge, Button, Select, ScrollArea) all installed
- [x] Zustand ui store handles theme (dark/light via .dark class on html)
- [x] cn() helper (clsx + twMerge) available at src/lib/utils.ts
- [x] prompts.tsx route stub exists -- overwrite with full implementation
- [x] ALL_SENTINEL = '__all' pattern for Radix Select exists in FilterBar.tsx
- [x] Pipeline introspection metadata exposes system_key and user_key per step (usable for prompt_key lookup)
- [x] usePipelines() and usePipeline(name) hooks exist and can provide pipeline -> prompt_key mapping
- [x] Prompt model has no pipeline_name field -- cross-reference is the correct approach
- [x] Dataset is small (20-200 prompts) -- full client-side load is appropriate

## Open Items

- Filter dropdown population: No backend endpoint returns distinct category or step_name values. Options: (a) derive from loaded prompts client-side (unique values from items[].category, items[].step_name), or (b) derive pipeline names from usePipelines(). Both are viable with full-scroll approach since all data is client-side.
- Variable highlighting regex mismatch: Backend uses `\{([a-zA-Z_][a-zA-Z0-9_]*)\}` (no dots). Step 1 research proposes `\{[\w.]+\}` (includes dots). Should use backend-compatible regex for consistency unless dot-variables are a real use case.
- Mobile responsiveness: Not addressed in research or task description. RunDetailPage has no mobile adaptation. Assume desktop-first split-pane is sufficient.

## Recommendations for Planning

1. **Pipeline filter via client-side cross-reference:** Fetch all pipeline metadata in parallel with prompts. Build prompt_key -> pipeline_name[] map. Use this to populate pipeline filter dropdown and filter displayed prompts. No backend changes needed.
2. **Full scroll with client-side filtering:** Fetch all prompts with `limit=200` (or increase to a safe max). Apply all filters (pipeline, type, category, step_name, search) in JS. Eliminates server round-trips on filter change.
3. **URL search params for selection:** Use zod-validated search params (`?key=prompt_key&tab=...`) following $runId.tsx pattern. Makes prompt detail views bookmarkable/shareable.
4. **Variable highlighting:** Use React-element splitting (not dangerouslySetInnerHTML). Use backend-compatible regex `\{([a-zA-Z_][a-zA-Z0-9_]*)\}`.
5. **New API artifacts (minimal):** Add queryKeys.prompts.detail(key) and usePromptDetail(promptKey) hook. ~20 lines total.
6. **Component structure:** PromptBrowser (route page) -> PromptFilterBar + PromptList (left panel) + PromptViewer (right panel). Follow RunDetailPage split-pane layout.
7. **Filter dropdowns populated from data:** Derive unique pipeline names from usePipelines(), derive unique categories/step_names from loaded prompts. No new backend endpoints needed.
8. **Skeleton/error/empty states:** Follow established patterns (animate-pulse skeletons, text-destructive errors, text-muted-foreground empty).
