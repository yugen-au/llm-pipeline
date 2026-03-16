# IMPLEMENTATION - STEP 2: FRONTEND TAB REWIRE
**Status:** completed

## Summary
Swapped data sources between Instructions and Prompts tabs in StepDetailPanel. Instructions tab now shows `instructions_schema` JSON from pipeline metadata (via `usePipeline` hook). Prompts tab now shows prompt templates with `{variable}` placeholders from `useStepInstructions`. Removed `LLMCallStartingData` import (no longer used).

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`, `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`
Added `usePipeline` import; rewrote `PromptsTab` to accept `StepPromptItem[]` with loading/error states (moved from old InstructionsTab); rewrote `InstructionsTab` to accept `instructionsSchema` and `instructionsClass` from pipeline metadata; added `usePipeline` hook call and `stepMeta` derivation in `StepContent`; swapped prop wiring in tab content area; removed unused `LLMCallStartingData` import.

```
# Before (PromptsTab)
function PromptsTab({ events }: { events: EventItem[] }) {
  const calls = filterEvents<LLMCallStartingData>(events, 'llm_call_starting')
  // ... rendered system/user prompts from events

# After (PromptsTab)
function PromptsTab({ prompts, isLoading, isError }: { prompts: StepPromptItem[] | undefined; isLoading: boolean; isError: boolean }) {
  // ... renders prompt templates with badges, prompt_type, prompt_key, content
```

```
# Before (InstructionsTab)
function InstructionsTab({ prompts, isLoading, isError }: { prompts: StepPromptItem[] | undefined; ... }) {
  // ... rendered prompt items with badges

# After (InstructionsTab)
function InstructionsTab({ instructionsSchema, instructionsClass }: { instructionsSchema: Record<string, unknown> | null; instructionsClass: string | null }) {
  // ... renders JSON schema as <pre> block with class badge above
```

```
# Before (StepContent wiring)
<PromptsTab events={events} />
<InstructionsTab prompts={instructionsResponse?.prompts} isLoading={instructionsLoading} isError={instructionsError} />

# After (StepContent wiring)
<PromptsTab prompts={instructionsResponse?.prompts} isLoading={instructionsLoading} isError={instructionsError} />
<InstructionsTab instructionsSchema={stepMeta?.instructions_schema ?? null} instructionsClass={stepMeta?.instructions_class ?? null} />
```

### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
Added `mockUsePipeline` mock function alongside existing mocks. Added it to `beforeEach` reset and default return value so existing tests pass with the new `usePipeline` hook call.

```
# Before
vi.mock('@/api/pipelines', () => ({
  useStepInstructions: (...args: unknown[]) => mockUseStepInstructions(...args),
}))

# After
const mockUsePipeline = vi.fn()
vi.mock('@/api/pipelines', () => ({
  useStepInstructions: (...args: unknown[]) => mockUseStepInstructions(...args),
  usePipeline: (...args: unknown[]) => mockUsePipeline(...args),
}))
```

## Decisions
### stepMeta derivation via flatMap across all strategies
**Choice:** `pipelineResponse?.strategies?.flatMap(s => s.steps).find(s => s.step_name === step?.step_name)`
**Rationale:** Step names are unique within a pipeline (enforced by PipelineConfig). flatMap avoids nested loops and handles single or multi-strategy pipelines uniformly.

### Minimal test mock update (not full test rewrite)
**Choice:** Added only the `usePipeline` mock needed to unbreak existing tests; deferred comprehensive test assertions to step 3.
**Rationale:** Contract says implement only step 2. Step 3 is explicitly scoped for test updates with new assertions for schema rendering and prompt template rendering.

## Verification
[x] TypeScript type check passes (`npx tsc --noEmit`)
[x] All 10 existing StepDetailPanel tests pass
[x] No regressions -- same test count, same pass count
[x] `LLMCallStartingData` import removed (no longer used)
[x] `usePipeline` hook correctly guarded with `?? null` for loading states

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] usePipeline fires with empty string before step loads (LOW) -- `usePipeline(step?.pipeline_name ?? '')` passes empty string initially, creating unused cache entry

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/api/pipelines.ts`
Widened `usePipeline` param type from `string` to `string | undefined`. The `queryKey` still uses `?? ''` internally (required by TanStack Query's key serialization) but `enabled: Boolean(name)` prevents the query from firing when `name` is `undefined`.

```
# Before
export function usePipeline(name: string) {

# After
export function usePipeline(name: string | undefined) {
```

#### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`
Removed `?? ''` fallback -- now passes `undefined` when `step` is not yet loaded, avoiding a phantom `['pipelines', '']` cache entry.

```
# Before
} = usePipeline(step?.pipeline_name ?? '')

# After
} = usePipeline(step?.pipeline_name)
```

### Verification
[x] TypeScript type check passes (`npx tsc --noEmit`)
[x] All 16 StepDetailPanel tests pass
[x] No regressions
