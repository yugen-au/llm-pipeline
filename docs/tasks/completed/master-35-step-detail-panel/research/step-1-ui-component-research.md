# UI Component Research - Task 35: Step Detail Panel with Tabs

## Executive Summary

Task 34 created a minimal div-based StepDetailPanel skeleton with placeholder comment `{/* Task 35: replace with tabbed implementation */}`. Task 35 must replace it with shadcn Sheet + Tabs containing 7 data tabs. All data hooks exist. Two shadcn components (Sheet, Tabs) must be installed. Two ambiguities require CEO input: Input tab data source and Instructions tab content depth.

## Existing StepDetailPanel (Task 34 Skeleton)

**File:** `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`

### Current Implementation
- Div-based fixed slide-over (`fixed inset-y-0 right-0 z-50 w-96`)
- Custom backdrop (`fixed inset-0 z-40 bg-black/50`)
- Manual focus trap, Escape handler, close button
- `StepContent` child component guards `useStep` call (only mounts when panel open)
- Shows: step_name, step_number, model, duration, created_at

### Props Interface (to preserve)
```typescript
interface StepDetailPanelProps {
  runId: string
  stepNumber: number | null
  open: boolean
  onClose: () => void
  runStatus?: string
}
```

### Consumer Site
`llm_pipeline/ui/frontend/src/routes/runs/$runId.tsx` line 203-209:
```tsx
<StepDetailPanel
  runId={runId}
  stepNumber={selectedStepId}
  open={stepDetailOpen}
  onClose={closeStepDetail}
  runStatus={run.status}
/>
```

### Task 34 SUMMARY Guidance
> "Task 35 should install Sheet and rewrite the panel with the full 7-tab layout. The `StepDetailPanelProps` interface (`runId`, `stepNumber`, `open`, `onClose`, `runStatus`) can be preserved as the public API."

### Existing Tests (8 tests)
`StepDetailPanel.test.tsx` tests: open/close states, loading skeleton, error message, close button click, null stepNumber, Escape key, backdrop click. Must be rewritten for Sheet-based component.

## shadcn/ui Components

### Installed
badge, button, card, scroll-area, select, separator, table, tooltip

### Need to Install
- **Sheet** - `npx shadcn@latest add sheet`
- **Tabs** - `npx shadcn@latest add tabs`

### shadcn Configuration
- Style: new-york/neutral
- RSC: false (Vite SPA)
- CSS variables: enabled
- Tailwind v4 with `@import "shadcn/tailwind.css"`
- Icon library: lucide
- Aliases: `@/components/ui`, `@/lib/utils`

### Sheet Component API (from context7)
```tsx
<Sheet open={open} onOpenChange={onClose}>
  <SheetContent side="right" className="w-[600px]">
    <SheetHeader>
      <SheetTitle>Step Detail</SheetTitle>
      <SheetDescription>Step {stepNumber}</SheetDescription>
    </SheetHeader>
    {/* content */}
  </SheetContent>
</Sheet>
```
Sheet provides: overlay, focus trap, Escape key, aria-modal, portal rendering. Replaces ALL custom accessibility code from the skeleton.

### Tabs Component API (from context7)
```tsx
<Tabs defaultValue="prompts">
  <TabsList>
    <TabsTrigger value="input">Input</TabsTrigger>
    <TabsTrigger value="prompts">Prompts</TabsTrigger>
    {/* ... */}
  </TabsList>
  <TabsContent value="input">{/* ... */}</TabsContent>
  <TabsContent value="prompts">{/* ... */}</TabsContent>
</Tabs>
```

## UI Store

**File:** `llm_pipeline/ui/frontend/src/stores/ui.ts`

```typescript
interface UIState {
  selectedStepId: number | null
  stepDetailOpen: boolean
  selectStep: (stepId: number | null) => void
  closeStepDetail: () => void
}
```

- `selectStep(id)` sets both `selectedStepId` and `stepDetailOpen`
- `closeStepDetail()` resets both to null/false
- Ephemeral state (not persisted to localStorage)

## Data Hooks Available

### useStep(runId, stepNumber, runStatus?)
**File:** `src/api/steps.ts`
- Returns `StepDetail` with: step_name, step_number, pipeline_name, run_id, input_hash, result_data, context_snapshot, prompt_system_key, prompt_user_key, prompt_version, model, execution_time_ms, created_at
- Dynamic staleTime: Infinity for terminal runs, 30s for active

### useEvents(runId, filters?, runStatus?)
**File:** `src/api/events.ts`
- Returns `EventListResponse { items: EventItem[], total, offset, limit }`
- EventItem: `{ event_type, pipeline_name, run_id, timestamp, event_data: Record<string, unknown> }`
- Default limit: 100 (backend)
- Events must be filtered client-side by `event_data.step_name` to isolate step-specific events

### Query Keys
```typescript
queryKeys.runs.step(runId, stepNumber)    // single step detail
queryKeys.runs.events(runId, filters)     // events list
```

## Backend Event Types Relevant to Tabs

All event data is serialized into `event_data: dict` via Python dataclass `asdict()`. Fields from the Python dataclass appear as top-level keys within `event_data`.

### LLMCallStarting (llm_call_starting)
```python
step_name: str | None
call_index: int
rendered_system_prompt: str
rendered_user_prompt: str
```

### LLMCallCompleted (llm_call_completed)
```python
step_name: str | None
call_index: int
raw_response: str | None
parsed_result: dict | None
model_name: str | None
attempt_count: int
validation_errors: list[str]
```

### InstructionsLogged (instructions_logged)
```python
step_name: str | None
logged_keys: list[str]
```

### InstructionsStored (instructions_stored)
```python
step_name: str | None
instruction_count: int
```

### ContextUpdated (context_updated)
```python
step_name: str | None
new_keys: list[str]
context_snapshot: dict
```

### ExtractionStarting (extraction_starting)
```python
step_name: str | None
extraction_class: str
model_class: str
```

### ExtractionCompleted (extraction_completed)
```python
step_name: str | None
extraction_class: str
model_class: str
instance_count: int
execution_time_ms: float
```

### ExtractionError (extraction_error)
```python
step_name: str | None
extraction_class: str
error_type: str
error_message: str
validation_errors: list[str]
```

### StepStarted (step_started)
```python
step_name: str | None
step_number: int
system_key: str | None
user_key: str | None
```

### StateSaved (state_saved)
```python
step_name: str | None
step_number: int
input_hash: str
execution_time_ms: float
```

## Tab Data Mapping

| Tab | Primary Data Source | Secondary Source | Notes |
|---|---|---|---|
| Input | StepDetail.context_snapshot | -- | **AMBIGUOUS: see Q1** |
| Prompts | LLMCallStarting events | StepDetail.prompt_system_key/user_key | rendered_system_prompt + rendered_user_prompt from events; keys from StepDetail |
| LLM Response | LLMCallCompleted events | -- | raw_response + parsed_result + model_name + validation_errors |
| Instructions | InstructionsLogged events | InstructionsStored events | **AMBIGUOUS: see Q2** |
| Context Diff | ContextUpdated events | StepDetail.context_snapshot | new_keys + snapshot; actual diff display deferred to task 36 |
| Extractions | ExtractionStarting/Completed/Error events | -- | Class names, counts, timing, errors |
| Meta | StepDetail fields | LLMCallCompleted.attempt_count | model, timing, input_hash, prompt keys, created_at |

## Client-Side Event Filtering Strategy

No backend step_name filter exists on the events endpoint (confirmed in task 34 research). Must filter client-side:

```typescript
const stepEvents = events?.items.filter(
  (e) => e.event_data?.step_name === step?.step_name
) ?? []
```

Default limit of 100 covers typical runs (~5-10 events per step, ~5-10 steps = 25-100 events). For large runs, may need increased limit param.

## Existing Viewer Components

**None exist.** No JsonViewer, PromptViewer, or CodeViewer components in the codebase. The only JSON rendering is in ContextEvolution.tsx:
```tsx
<pre className="text-xs font-mono whitespace-pre-wrap break-all rounded bg-muted p-3">
  {JSON.stringify(snapshot.context_snapshot, null, 2)}
</pre>
```

Task 35 should create reusable viewer sub-components within the StepDetailPanel file or as separate files:
- JSON display: `<pre>` with monospace font, bg-muted, overflow handling
- Prompt display: system/user sections with labeled headers
- These can be extracted to shared components later if task 37/49 needs them

## Component Architecture Patterns (from codebase)

1. Named function exports (no default)
2. Props interface defined above component
3. Tailwind-only styling with `cn()` utility
4. Loading: `animate-pulse` skeleton divs
5. Error: `text-sm text-destructive` paragraph
6. Empty: `text-muted-foreground` paragraph
7. Test files co-located (`ComponentName.test.tsx`)
8. No React.memo unless profiling shows need

## Layout Context

Root layout (`__root.tsx`):
```
flex h-screen
  aside w-60 (sidebar placeholder)
  main flex-1 overflow-auto
    RunDetailPage (flex h-full flex-col)
      Card (header)
      flex min-h-0 flex-1 (body)
        CardContent flex-1 (StepTimeline)
        div w-80 (ContextEvolution)
      StepDetailPanel (overlay, currently w-96, task 35 spec: w-[600px])
```

Sheet renders via portal so it overlays everything. Width 600px is reasonable for 7-tab content display.

## Downstream Task Dependencies

### Task 37 (Live Execution) - pending, depends on 35
- Reuses `<StepDetailPanel />` in the right column of a 3-column grid
- Must accept same props interface

### Task 49 (Step Creator) - pending, depends on 35
- Shows `<StepDetailPanel results={testResults} />` which suggests a different data source mode
- This is task 49's responsibility to handle, but worth noting the component may need extensibility

## Deviations from Task 34

The task 34 implementation deviated from the original task 35 description in these ways relevant to us:
1. Panel uses div-based slide-over instead of Sheet (intentional -- deferred to task 35)
2. Props use `stepNumber: number | null` instead of consuming from useUIStore directly (component is prop-driven, store consumed in parent)
3. Panel width is w-96 (384px), task 35 spec says w-[600px]

## Recommendations

1. Install shadcn Sheet + Tabs as first step
2. Replace div-based panel entirely with Sheet (removes ~50 lines of custom a11y code)
3. Keep `StepDetailPanelProps` interface unchanged for backward compat with RunDetailPage
4. Create a `useStepEvents(runId, stepName)` convenience hook or inline filtering
5. Build each tab as a small private component within StepDetailPanel.tsx initially; extract if they grow
6. Use `<ScrollArea>` (already installed) within TabsContent for overflow handling
7. Rewrite tests for Sheet-based rendering (Radix portal requires different query strategies)
8. Context Diff tab: show new_keys list + raw context_snapshot; defer diff visualization to task 36
