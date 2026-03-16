# Step 2: Frontend Step UI Research

## Summary

The StepDetailPanel is fully wired with 7 tabs. The "Prompts" tab already renders rendered system+user prompts from `llm_call_starting` events. The "Response" tab already renders `raw_response` and `parsed_result` from `llm_call_completed` events. The current "Input" tab shows previous-step context snapshots, NOT prompts. If "input/output tabs are empty" refers to the literal "Input" tab, that's by design (context view). If it refers to Prompts/Response, the issue is likely backend (events not persisted) rather than frontend.

---

## Component Architecture

### StepDetailPanel (`llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`)

- **Public component**: `StepDetailPanel` - Sheet overlay triggered by step selection
- **Internal component**: `StepContent` - mounts when sheet is open + stepNumber non-null
- **7 private tab components**: InputTab, PromptsTab, ResponseTab, InstructionsTab, ContextDiffTab, ExtractionsTab, MetaTab

### Tab-to-Data Mapping

| Tab Name (UI) | Tab value | Data Source | What it Shows |
|---|---|---|---|
| **Meta** | `meta` | `useStep()` + events | Step metadata (name, number, model, duration, cache, strategy, validation errors) |
| **Input** | `input` | `useRunContext()` | Previous step's context_snapshot. Shows "No prior context" for step 1. NOT prompts. |
| **Prompts** | `prompts` | `useStepEvents()` filtered `llm_call_starting` | `rendered_system_prompt` + `rendered_user_prompt` per LLM call |
| **Response** | `response` | `useStepEvents()` filtered `llm_call_completed` | `raw_response` + `parsed_result` per LLM call |
| **Instructions** | `instructions` | `useStepInstructions()` | Registered prompt templates from pipeline config (static content) |
| **Context** | `context` | `useRunContext()` + events `context_updated` | JSON diff before/after step with new_keys badges |
| **Extractions** | `extractions` | events `extraction_completed` + `extraction_error` | Extraction class, model, instance count, duration, errors |

### Default Tab

Default tab is `meta` (line 461: `<Tabs defaultValue="meta">`).

---

## Data Fetching Hooks (inside StepContent)

### 1. `useStep(runId, stepNumber, runStatus)` -> `StepDetail`
- **Endpoint**: `GET /api/runs/{runId}/steps/{stepNumber}`
- **Returns**: step_name, step_number, pipeline_name, run_id, input_hash, result_data, context_snapshot, prompt_system_key, prompt_user_key, prompt_version, model, execution_time_ms, created_at
- **Caching**: `staleTime: Infinity` for terminal runs, 30s otherwise

### 2. `useStepEvents(runId, stepName, runStatus)` -> `EventListResponse`
- **Endpoint**: `GET /api/runs/{runId}/events?step_name={stepName}`
- **Wrapper around**: `useEvents()` with `step_name` filter
- **Returns**: EventItem[] with event_type + event_data dict
- **Guard**: Disabled until stepName is truthy (waits for useStep to resolve)
- **Caching**: `staleTime: Infinity` for terminal, 5s + 3s polling for active runs

### 3. `useStepInstructions(pipelineName, stepName)` -> `StepPromptsResponse`
- **Endpoint**: `GET /api/pipelines/{pipelineName}/steps/{stepName}/prompts`
- **Returns**: StepPromptItem[] with prompt_key, prompt_type, content, required_variables, version
- **Caching**: `staleTime: Infinity` (static pipeline config)
- **Guard**: Disabled until both pipelineName and stepName truthy

### 4. `useRunContext(runId, status)` -> `ContextEvolutionResponse`
- **Endpoint**: `GET /api/runs/{runId}/context`
- **Returns**: ContextSnapshot[] with step_name, step_number, context_snapshot
- **Caching**: `staleTime: Infinity` for terminal, 30s otherwise

---

## TypeScript Interfaces (`api/types.ts`)

### Core types used by tabs:

```typescript
// StepDetail - from GET /api/runs/{runId}/steps/{stepNumber}
interface StepDetail {
  step_name: string; step_number: number; pipeline_name: string;
  run_id: string; input_hash: string; result_data: Record<string, unknown>;
  context_snapshot: Record<string, unknown>;
  prompt_system_key: string | null; prompt_user_key: string | null;
  prompt_version: string | null; model: string | null;
  execution_time_ms: number | null; created_at: string;
}

// EventItem - generic event container
interface EventItem {
  event_type: string; pipeline_name: string; run_id: string;
  timestamp: string; event_data: Record<string, unknown>;
}

// LLMCallStartingData - type-narrowed from event_data
interface LLMCallStartingData {
  call_index: number;
  rendered_system_prompt: string;
  rendered_user_prompt: string;
}

// LLMCallCompletedData - type-narrowed from event_data
interface LLMCallCompletedData {
  call_index: number; raw_response: string | null;
  parsed_result: Record<string, unknown> | null;
  model_name: string | null; attempt_count: number;
  validation_errors: string[];
}
```

### Type narrowing mechanism:
- `eventData<T>(event)` casts `event.event_data as T` (no runtime validation)
- `filterEvents<T>(events, type)` filters by `event_type` string then casts

---

## State Management

### UI State (`stores/ui.ts`) - Zustand
- `selectedStepId: number | null` - currently selected step number
- `stepDetailOpen: boolean` - panel visibility
- `selectStep(stepId)` - sets both selectedStepId and opens panel
- `closeStepDetail()` - resets both to null/false
- Ephemeral state (not persisted to localStorage)

### Data State - TanStack Query
- All API data lives in TanStack Query cache
- Query keys namespaced: `['runs', runId, 'steps', stepNumber]`, `['runs', runId, 'events', filters]`
- WebSocket events appended to event cache via `queryClient.setQueryData`
- Terminal run data cached with `staleTime: Infinity`

---

## WebSocket Integration

- `useWebSocket(runId)` in `$runId.tsx` connects to `/ws/runs/{runId}`
- Pipeline events streamed in real-time, appended to TanStack event cache
- Step-scoped events trigger invalidation of steps list query
- Control messages (heartbeat, stream_complete, replay_complete) update Zustand ws store

---

## Key Finding: Tab Name vs User Expectation Mismatch

The user's request says "input tab = raw system+user prompts" and "output tab = raw LLM response". Mapping:

| User's Term | Closest Existing Tab | Tab Value | Status |
|---|---|---|---|
| "Input" (prompts) | **Prompts** | `prompts` | FULLY IMPLEMENTED - renders rendered_system_prompt + rendered_user_prompt |
| "Output" (response) | **Response** | `response` | FULLY IMPLEMENTED - renders raw_response + parsed_result |

The literal "Input" tab (value=`input`) shows **context from previous step**, not prompts. This is a naming/UX mismatch.

---

## Empty Tab Analysis

If Prompts/Response tabs show "No LLM calls recorded" / "No LLM responses recorded", possible causes:

1. **Backend not emitting events**: `LLMCallStarting`/`LLMCallCompleted` not fired during pipeline execution
2. **Events not persisted**: `SQLiteEventHandler.emit()` failing silently (CompositeEmitter isolates failures)
3. **step_name filter mismatch**: Events stored with `step_name=None` or wrong name, so `?step_name=X` query returns nothing
4. **Cache hit path**: When cache hits, the pipeline skips LLM calls entirely (no `llm_call_starting`/`llm_call_completed` events)
5. **Agent steps**: Tool-calling agent steps may not emit these specific events

---

## Existing Tests (`StepDetailPanel.test.tsx`)

- 8 tests covering: closed state, open state, 7 tabs rendered, loading skeleton, error state, close button, null stepNumber, tab switching
- Tests mock all 4 hooks (useStep, useStepEvents, useStepInstructions, useRunContext)
- Default mock returns empty events, so tabs are tested structurally but not with real event data

---

## No TODOs or Placeholders Found

Searched for TODO/FIXME/HACK/placeholder in StepDetailPanel.tsx: none found. All tab content components are complete implementations, not stubs.

---

## Possible Solutions (for implementation phase)

### If issue is tab naming (user wants "Input"/"Output" labels for prompts/responses):
- Rename "Prompts" tab to "Input" and "Response" tab to "Output"
- Rename current "Input" tab to "Context In" or merge into Context tab
- Minimal code change (tab labels + values only)

### If issue is backend events not being stored:
- Requires backend investigation (step-1 research scope)
- Check SQLiteEventHandler is wired into CompositeEmitter
- Verify step_name is populated on LLMCallStarting/LLMCallCompleted events

### If both (rename + fix backend):
- Frontend tab rename is trivial
- Backend event emission fix is the real work
