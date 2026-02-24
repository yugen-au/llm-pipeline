# Step 2: Data Layer Research -- Step Detail Panel

## Executive Summary

The Step Detail Panel's 7 tabs are fed by two primary data sources: (1) the `GET /api/runs/{runId}/steps/{stepNumber}` endpoint (StepDetail model), and (2) the `GET /api/runs/{runId}/events` endpoint (EventItem[] with nested event_data). Step-level data (prompt keys, model, timing, result_data, context_snapshot) comes from StepDetail. Event-level data (rendered prompts, raw LLM responses, extraction details, context diffs) comes from events filtered client-side by `event_data.step_name`. Two semantic ambiguities need CEO clarification before implementation: what "Input" means and what "Instructions" means in the tab context.

---

## 1. API Endpoints & Hooks

### 1.1 Step Detail Endpoint

**Endpoint:** `GET /api/runs/{run_id}/steps/{step_number}`
**Backend:** `llm_pipeline/ui/routes/steps.py` -> `get_step()`
**Hook:** `useStep(runId, stepNumber, runStatus?)` in `src/api/steps.ts`
**Response type:** `StepDetail`

```typescript
interface StepDetail {
  step_name: string
  step_number: number
  pipeline_name: string
  run_id: string
  input_hash: string
  result_data: Record<string, unknown>       // serialized step results
  context_snapshot: Record<string, unknown>   // {step_name: serialized_results}
  prompt_system_key: string | null
  prompt_user_key: string | null
  prompt_version: string | null
  model: string | null
  execution_time_ms: number | null
  created_at: string
}
```

**Caching:** `staleTime: Infinity` for terminal runs, `30_000` for active. No polling.

### 1.2 Events Endpoint

**Endpoint:** `GET /api/runs/{run_id}/events?event_type=&offset=&limit=`
**Backend:** `llm_pipeline/ui/routes/events.py` -> `list_events()`
**Hook:** `useEvents(runId, filters?, runStatus?)` in `src/api/events.ts`
**Response type:** `EventListResponse`

```typescript
interface EventItem {
  event_type: string
  pipeline_name: string
  run_id: string
  timestamp: string
  event_data: Record<string, unknown>  // FULL serialized event payload via to_dict()
}

interface EventListResponse {
  items: EventItem[]
  total: number
  offset: number
  limit: number
}
```

**Caching:** `staleTime: Infinity` for terminal, `5_000` for active. Polls every 3s for active runs.

### 1.3 Context Evolution Endpoint

**Endpoint:** `GET /api/runs/{run_id}/context`
**Hook:** `useRunContext(runId, status?)` in `src/api/runs.ts`
**Response type:** `ContextEvolutionResponse`

```typescript
interface ContextSnapshot {
  step_name: string
  step_number: number
  context_snapshot: Record<string, unknown>
}

interface ContextEvolutionResponse {
  run_id: string
  snapshots: ContextSnapshot[]
}
```

### 1.4 Steps List Endpoint

**Endpoint:** `GET /api/runs/{run_id}/steps`
**Hook:** `useSteps(runId, runStatus?)` in `src/api/steps.ts`
**Response type:** `StepListResponse`

Already used by RunDetailPage for StepTimeline. Not directly needed by StepDetailPanel but provides step list for navigation context.

### 1.5 Query Keys

```typescript
queryKeys.runs.step(runId, stepNumber)   // ['runs', runId, 'steps', stepNumber]
queryKeys.runs.events(runId, filters)    // ['runs', runId, 'events', filters]
queryKeys.runs.context(runId)            // ['runs', runId, 'context']
```

---

## 2. Backend Data Models

### 2.1 PipelineStepState (DB table: pipeline_step_states)

**File:** `llm_pipeline/state.py`

| Field | Type | Description |
|-------|------|-------------|
| id | int (PK) | Auto-increment |
| pipeline_name | str | Pipeline identifier |
| run_id | str (UUID) | Run identifier |
| step_name | str | Step identifier |
| step_number | int | Execution order (1-based) |
| input_hash | str | Hash of step inputs for caching |
| result_data | JSON | Serialized step results |
| context_snapshot | JSON | `{step_name: serialized_instructions}` |
| prompt_system_key | str? | System prompt key used |
| prompt_user_key | str? | User prompt key used |
| prompt_version | str? | Prompt version for cache invalidation |
| model | str? | LLM model name |
| execution_time_ms | int? | Step execution duration |
| created_at | datetime | UTC timestamp |

**Note:** Steps only appear in DB after completion. No in-progress step state. No status column.

### 2.2 PipelineEventRecord (DB table: pipeline_events)

**File:** `llm_pipeline/events/models.py`

| Field | Type | Description |
|-------|------|-------------|
| id | int (PK) | Auto-increment |
| run_id | str | Run identifier |
| event_type | str | Snake_case event type |
| pipeline_name | str | Pipeline identifier |
| timestamp | datetime | UTC emission time |
| event_data | JSON | Full event.to_dict() payload |

**Key insight:** `event_data` contains ALL fields from the concrete event class. Top-level columns (run_id, event_type, pipeline_name, timestamp) are duplicated from event_data for query efficiency.

---

## 3. Event Types & Payloads

**File:** `llm_pipeline/events/types.py`

31 concrete event types across 9 categories. Events relevant to StepDetailPanel tabs:

### 3.1 LLM Call Events (category: llm_call)

**LLMCallPrepared** -- emitted when calls are prepared for a step
```python
# event_data fields (beyond base):
step_name: str | None
call_count: int
system_key: str | None
user_key: str | None
```

**LLMCallStarting** -- emitted when individual LLM call begins
```python
# event_data fields:
step_name: str | None
call_index: int
rendered_system_prompt: str    # FULL rendered system prompt text
rendered_user_prompt: str      # FULL rendered user prompt text
```

**LLMCallCompleted** -- emitted when individual LLM call completes
```python
# event_data fields:
step_name: str | None
call_index: int
raw_response: str | None       # Raw LLM text response
parsed_result: dict | None     # Pydantic-parsed structured result
model_name: str | None         # Actual model used
attempt_count: int             # Number of attempts (retries)
validation_errors: list[str]   # Pydantic validation errors
```

**LLMCallRetry** -- emitted on retry
```python
step_name: str | None
attempt: int
max_retries: int
error_type: str
error_message: str
```

**LLMCallFailed** -- emitted when LLM call fails after exhausting retries
```python
step_name: str | None
max_retries: int
last_error: str
```

**LLMCallRateLimited** -- emitted when rate-limited
```python
step_name: str | None
attempt: int
wait_seconds: float
backoff_type: str
```

### 3.2 Step Lifecycle Events (category: step_lifecycle)

**StepStarted**
```python
step_name: str | None
step_number: int
system_key: str | None
user_key: str | None
```

**StepCompleted**
```python
step_name: str | None
step_number: int
execution_time_ms: float
```

**StepSkipped**
```python
step_name: str | None
step_number: int
reason: str
```

**StepSelected**
```python
step_name: str | None
step_number: int
strategy_name: str
```

### 3.3 Extraction Events (category: extraction)

**ExtractionStarting**
```python
step_name: str | None
extraction_class: str
model_class: str
```

**ExtractionCompleted**
```python
step_name: str | None
extraction_class: str
model_class: str
instance_count: int
execution_time_ms: float
```

**ExtractionError**
```python
step_name: str | None
extraction_class: str
error_type: str
error_message: str
validation_errors: list[str]
```

### 3.4 Transformation Events (category: transformation)

**TransformationStarting**
```python
step_name: str | None
transformation_class: str
cached: bool
```

**TransformationCompleted**
```python
step_name: str | None
data_key: str
execution_time_ms: float
cached: bool
```

### 3.5 Instructions & Context Events (category: instructions_context)

**InstructionsStored**
```python
step_name: str | None
instruction_count: int
```

**InstructionsLogged**
```python
step_name: str | None
logged_keys: list[str]
```

**ContextUpdated**
```python
step_name: str | None
new_keys: list[str]
context_snapshot: dict        # Full pipeline context AFTER this step
```

### 3.6 Cache Events (category: cache)

**CacheLookup / CacheHit / CacheMiss**
```python
step_name: str | None
input_hash: str
# CacheHit adds: cached_at: datetime
```

**CacheReconstruction**
```python
step_name: str | None
model_count: int
instance_count: int
```

### 3.7 State Events (category: state)

**StateSaved**
```python
step_name: str | None
step_number: int
input_hash: str
execution_time_ms: float
```

---

## 4. Tab-to-Data Mapping

### 4.1 Prompts Tab
**Source:** Events (LLMCallStarting, LLMCallPrepared)
- `event_data.rendered_system_prompt` -- full rendered system prompt
- `event_data.rendered_user_prompt` -- full rendered user prompt
- `event_data.call_index` -- which call (for multi-call steps like consensus)
- StepDetail.prompt_system_key, prompt_user_key, prompt_version (keys, not rendered text)
- **Note:** Multiple LLMCallStarting events possible per step (consensus calls)

### 4.2 LLM Response Tab
**Source:** Events (LLMCallCompleted)
- `event_data.raw_response` -- raw LLM text
- `event_data.parsed_result` -- Pydantic-parsed JSON
- `event_data.call_index` -- which call
- `event_data.model_name` -- model used
- `event_data.attempt_count` -- retry count
- `event_data.validation_errors` -- parsing errors
- **Note:** Multiple LLMCallCompleted events possible per step

### 4.3 Context Diff Tab
**Source:** ContextEvolution API + Events (ContextUpdated)
- ContextEvolution snapshots: previous step's context vs current step's context
- ContextUpdated event: `event_data.new_keys` (what changed), `event_data.context_snapshot` (full context after)
- Diff can be computed client-side between consecutive snapshots

### 4.4 Extractions Tab
**Source:** Events (ExtractionStarting, ExtractionCompleted, ExtractionError)
- `event_data.extraction_class` -- extraction class name
- `event_data.model_class` -- DB model class
- `event_data.instance_count` -- number of instances extracted
- `event_data.execution_time_ms` -- extraction timing
- `event_data.error_type`, `event_data.error_message` -- if extraction failed

### 4.5 Meta Tab
**Source:** StepDetail + Events (LLMCallCompleted, StepCompleted, StateSaved, CacheHit/Miss)
- StepDetail.model -- model name
- StepDetail.execution_time_ms -- total step duration
- StepDetail.created_at -- timestamp
- StepDetail.input_hash -- cache key
- LLMCallCompleted.validation_errors -- any parsing issues
- LLMCallCompleted.attempt_count -- retry info
- CacheHit/CacheMiss -- whether step used cache
- StepSelected.strategy_name -- which strategy selected this step

### 4.6 Input Tab (AMBIGUOUS -- needs CEO clarification)
**See Question 1 below.**

### 4.7 Instructions Tab (AMBIGUOUS -- needs CEO clarification)
**See Question 2 below.**

---

## 5. Existing Frontend Infrastructure

### 5.1 Current StepDetailPanel (Task 34 Skeleton)
**File:** `src/components/runs/StepDetailPanel.tsx`
- Div-based fixed slide-over (not shadcn Sheet)
- Props: `{ runId, stepNumber: number|null, open, onClose, runStatus? }`
- StepContent child component guards useStep call
- Shows: step_name, step_number, model, duration, created_at
- Has `{/* Task 35: replace with tabbed implementation */}` placeholder
- Focus trap, Escape key, backdrop already implemented

### 5.2 Installed shadcn/ui Components
Installed: badge, button, select, table, tooltip, card, separator, scroll-area
**NOT installed (needed for task 35):** Sheet, Tabs

### 5.3 UI Store
**File:** `src/stores/ui.ts`
- `selectedStepId: number | null`
- `stepDetailOpen: boolean`
- `selectStep(stepId: number | null)` -- sets both
- `closeStepDetail()` -- resets both

### 5.4 RunDetailPage Integration
**File:** `src/routes/runs/$runId.tsx`
- Already fetches: useRun, useSteps, useEvents, useRunContext, useWebSocket
- Events are already in the TanStack Query cache (keyed by `queryKeys.runs.events(runId, {})`)
- StepDetailPanel receives: runId, stepNumber, open, onClose, runStatus

---

## 6. Identified Gaps

### 6.1 No useStepEvents Hook
Task 35 description references `useStepEvents(runId, selectedStepId)` but it does not exist. The existing `useEvents` fetches ALL events for a run. Step-level filtering must happen client-side via `event_data.step_name`.

**Options:**
(a) Create a `useStepEvents(runId, stepNumber)` hook that derives from the `useEvents` cache, filtering by `event_data.step_name` matching the step's name (requires knowing step_name from step_number, which means useStep must resolve first)
(b) Add `step_name` query parameter to backend events API for server-side filtering
(c) Filter inline in the component using useEvents data already cached by RunDetailPage

**Recommendation:** Option (a) -- a derived hook provides clean separation. The RunDetailPage already caches all events; the derived hook can use `useQuery` with `select` to filter, or use `queryClient.getQueryData()`.

### 6.2 Events API Lacks step_name Filter
Backend `EventListParams` only supports: `event_type`, `offset`, `limit`. No `step_name` filter.

**Impact:** Client-side filtering works for most runs but could be inefficient for runs with 100+ events if pagination truncates before reaching all events for a given step.

**Mitigation:** For task 35, use client-side filtering with a higher default limit. The `useEvents` hook in RunDetailPage already fetches with default params (limit=100). Consider increasing to limit=500 for the panel use case, or fetch all events.

### 6.3 No Step Status in DB
PipelineStepState has no status column. Steps only appear after completion. This is already handled by task 34's `deriveStepStatus` utility for the timeline. The StepDetailPanel can assume the selected step is either "completed" (in DB) or "running" (derived from WS events).

### 6.4 context_snapshot Field Semantics
`PipelineStepState.context_snapshot` is set to `{step.step_name: serialized_instructions}` in `_save_step_state()`. This is the step's OWN serialized results keyed by step_name, NOT the full pipeline context at that point. The full pipeline context is available via:
- `ContextEvolution` API (snapshots per step -- but these are also `{step_name: serialized}`)
- `ContextUpdated` event's `context_snapshot` field (full pipeline context after step execution)

### 6.5 Event Pagination for Large Runs
Default limit is 100 events. A step with consensus (multiple LLM calls + retries) could generate 10+ events per step. A 10-step pipeline could easily have 50-100+ events. The events for the last steps might be on page 2+.

**Mitigation:** Either fetch with limit=500, or implement scroll-based pagination in the panel.

### 6.6 TypeScript Types for Event Data
`EventItem.event_data` is typed as `Record<string, unknown>`. There are no TypeScript interfaces for specific event payloads (e.g., LLMCallStartingData, LLMCallCompletedData). Task 35 will need to define these or use type assertions.

**Recommendation:** Create discriminated event_data interfaces keyed by event_type for type safety.

---

## 7. Upstream Task 34 Deviations

Relevant deviations from task 34 (documented in SUMMARY.md):
- StepDetailPanel uses div-based slide-over (not Sheet) -- task 35 replaces with Sheet+Tabs
- StepContent child component pattern guards useStep hook call
- Props interface `{ runId, stepNumber: number|null, open, onClose, runStatus? }` can be preserved
- `deriveStepStatus` exists for step status from WS events
- RunDetailPage already wires useWebSocket and caches events

---

## 8. Questions Requiring CEO Input

### Question 1: What data should the "Input" tab show?

**Context:** `StepDetail.result_data` contains the step's serialized results (OUTPUT). `StepDetail.context_snapshot` contains `{step_name: serialized_instructions}` (also output-oriented). Neither field directly represents the step's INPUT (i.e., what the step received to work with).

**Options:**
(a) Show `StepDetail.result_data` -- the step's own results (misleadingly named "Input" tab)
(b) Show the previous step's `ContextUpdated.context_snapshot` from events -- the pipeline context when this step started executing (true input)
(c) Show `StepDetail.context_snapshot` -- the step's `{step_name: results}` blob
(d) Skip the Input tab entirely and rename to "Results" or "Output"

### Question 2: What data should the "Instructions" tab show?

**Context:** The concept of "instructions" in the pipeline has multiple meanings:
- **Prompt keys** (StepDetail.prompt_system_key/prompt_user_key) -- which prompts were used
- **Instruction events** (InstructionsStored.instruction_count, InstructionsLogged.logged_keys) -- what instruction keys were processed during step execution
- **Pipeline metadata** (PipelineStepMetadata.instructions_class/instructions_schema) -- the step's instruction class definition. BUT this comes from the pipelines introspection API which does not exist yet (task 24).

**Options:**
(a) Show prompt keys + InstructionsStored/InstructionsLogged event data
(b) Show only prompt keys from StepDetail (minimal, available now)
(c) Defer tab until pipeline introspection API exists (task 24)
(d) Show rendered prompts here instead of in the Prompts tab, and rename Prompts tab to something else

### Question 3: Event pagination strategy for Step Detail Panel?

**Context:** `useEvents` defaults to limit=100. Large runs may exceed this. Events for a specific step are scattered throughout the run's event timeline.

**Options:**
(a) Fetch with limit=500 (max allowed by backend) -- simple, covers most cases
(b) Add step_name filter to backend events API -- clean but requires backend change
(c) Use all-events cache from RunDetailPage (already fetched) and accept pagination gaps
(d) Fetch all pages client-side (multiple requests until total is covered)
