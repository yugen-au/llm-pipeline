# Research Summary

## Executive Summary

Validated 3 research files against actual codebase. Backend introspection API (task 24) and frontend hooks (task 31) are fully implemented and match research descriptions with minor corrections. Three TS type mismatches confirmed (PipelineListItem missing fields + nullability, PipelineStepMetadata nullability). One research error found: PipelineStrategyMetadata.error field already exists in types.ts despite research claiming it's missing. Internal contradiction in step-2 research (section 9 says types match, section 8 lists mismatches). Test count is 21 not 20. No blocking gaps -- remaining questions are design/UX decisions.

## Domain Findings

### Backend Introspection Layer
**Source:** step-1-pipeline-architecture-research.md, step-3-api-design-research.md

Verified against `llm_pipeline/ui/routes/pipelines.py` and `llm_pipeline/introspection.py`:
- All 3 endpoints exist: GET /api/pipelines, GET /api/pipelines/{name}, GET /api/pipelines/{name}/steps/{step_name}/prompts
- 6 Pydantic response models match research exactly (PipelineListItem, PipelineListResponse, StepMetadata, StrategyMetadata, PipelineMetadata, StepPromptItem, StepPromptsResponse)
- PipelineIntrospector caches by `id(cls)` -- confirmed L200-201
- Per-pipeline error isolation on list endpoint -- confirmed L107-112
- Cross-pipeline prompt leakage prevention via declared_keys scoping -- confirmed L150-162
- App wiring: `create_app(introspection_registry=...)` stores on `app.state.introspection_registry` -- confirmed in app.py L65
- All endpoints are sync def (not async) -- confirmed

### Frontend Hooks & Query Layer
**Source:** step-2-frontend-patterns-research.md, step-3-api-design-research.md

Verified against `src/api/pipelines.ts`, `src/api/query-keys.ts`, `src/api/client.ts`, `src/queryClient.ts`:
- 3 hooks exist: usePipelines(), usePipeline(name), useStepInstructions(pipelineName, stepName)
- Query key factory matches: pipelines.all/detail/stepPrompts
- usePipelines: queryKey=['pipelines'], no enabled guard -- confirmed
- usePipeline: queryKey=['pipelines', name], enabled=Boolean(name) -- confirmed
- useStepInstructions: staleTime=Infinity, enabled=Boolean(pipelineName && stepName) -- confirmed
- apiClient prepends /api, throws typed ApiError -- confirmed
- QueryClient: staleTime=30_000, retry=2, refetchOnWindowFocus=false -- confirmed
- usePipelines() returns `{ pipelines: PipelineListItem[] }` (wrapped), not bare array -- confirmed

### TypeScript Type Mismatches (Corrected)
**Source:** step-1-pipeline-architecture-research.md (with corrections)

Verified against `src/api/types.ts` lines 287-371 vs `llm_pipeline/ui/routes/pipelines.py` lines 22-77:

| TS Interface | Claimed Issue | Verified |
| --- | --- | --- |
| PipelineListItem | Missing `registry_model_count`, `error` fields | CONFIRMED -- lines 366-371 only have name, strategy_count, step_count, has_input_schema |
| PipelineListItem | `strategy_count`/`step_count` typed as `number` not `number \| null` | CONFIRMED -- lines 368-369 |
| PipelineStrategyMetadata | Missing `error` field | **WRONG** -- line 344 already has `error: string \| null` |
| PipelineStepMetadata | `system_key`/`user_key` typed as `string` not `string \| null` | CONFIRMED -- lines 323-324 |

**Corrected required TS type fixes for task 40:**
1. PipelineListItem: add `registry_model_count: number | null`, add `error: string | null`, change `strategy_count`/`step_count` to `number | null`
2. PipelineStepMetadata: change `system_key`/`user_key` to `string | null`
3. PipelineStrategyMetadata: NO CHANGE NEEDED (error field already present)

### Frontend Infrastructure
**Source:** step-2-frontend-patterns-research.md

Verified against actual file system and source:
- Route files: __root.tsx, index.tsx, live.tsx, pipelines.tsx (stub), prompts.tsx, runs/ -- confirmed
- TanStack Router file-based routing via `@tanstack/router-plugin/vite` with `autoCodeSplitting: true` -- confirmed in vite.config.ts
- shadcn/ui components available: badge, button, card, checkbox, input, label, scroll-area, select, separator, sheet, table, tabs, textarea, tooltip -- confirmed (14 components)
- Zustand stores: filters.ts, ui.ts, websocket.ts -- confirmed
- No `src/components/pipelines/` directory exists yet -- confirmed
- Root layout: sidebar (w-60, placeholder for task 41) + main area -- confirmed
- Prompts page uses URL search params (?key=) for selection with zodValidator -- confirmed pattern

### Testing
**Source:** step-3-api-design-research.md

- Research claims 20 pipeline tests. Actual count: **21** (grep -c "def test_" returns 21). Minor discrepancy.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| [pending - see Questions below] | [awaiting CEO input] | [TBD] |

## Assumptions Validated
- [x] Backend GET /api/pipelines returns PipelineListResponse with per-pipeline error isolation
- [x] Backend GET /api/pipelines/{name} returns full PipelineMetadata matching introspector output
- [x] Backend GET /api/pipelines/{name}/steps/{step_name}/prompts requires DB session and scopes by declared keys
- [x] Frontend usePipelines() hook exists with correct query key and no enabled guard
- [x] Frontend usePipeline(name) hook exists with enabled=Boolean(name) guard
- [x] Frontend useStepInstructions() hook exists with staleTime=Infinity
- [x] Query key factory has hierarchical pipelines.all/detail/stepPrompts keys
- [x] pipelines.tsx is an empty stub ready for replacement
- [x] PipelineStrategyMetadata already has error field (research was wrong about this being missing)
- [x] PipelineListItem IS missing registry_model_count and error fields
- [x] PipelineListItem strategy_count/step_count need nullability fix
- [x] PipelineStepMetadata system_key/user_key need nullability fix
- [x] No src/components/pipelines/ directory exists yet
- [x] All 14 shadcn/ui components listed in research are available
- [x] TanStack Router file-based routing with autoCodeSplitting confirmed
- [x] apiClient prepends /api and throws typed ApiError on non-OK
- [x] Existing pattern: prompts page uses URL search params for selection state
- [x] Task 51 (Visual Pipeline Editor) depends on task 40 and is OUT OF SCOPE

## Open Items
- Route restructuring decision: flat `pipelines.tsx` vs directory `pipelines/index.tsx` (see Q1)
- Schema viewer complexity: JSON tree vs schema-aware table vs both (see Q2)
- Prompt key navigation: click-through to /prompts page or not (see Q3)
- @provisional tag cleanup scope confirmation (see Q4)
- Research internal contradiction: step-2 section 9 says "Response shapes match frontend types exactly" while section 8 of same document lists type mismatches. The mismatches are real.
- Test count: 21 not 20 as research claimed (non-blocking)

## Recommendations for Planning
1. Fix 2 TS interfaces (PipelineListItem: add 2 fields + fix 2 nullabilities; PipelineStepMetadata: fix 2 nullabilities) and remove @provisional tags as first implementation step
2. Follow existing prompts.tsx left-right panel pattern for consistency
3. Use URL search params (?pipeline=name) for selected pipeline state (matches prompts page pattern, enables shareable links)
4. Start with simple collapsible JSON tree for schema display; upgrade to schema-aware table later if needed
5. Create src/components/pipelines/ directory following existing domain component organization pattern
6. No new dependencies, Zustand stores, or backend changes needed
7. Keep flat pipelines.tsx route unless CEO decides nested routes are needed for task 40
