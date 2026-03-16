# Step 1: Backend Pipeline Research -- Step Input/Output Tabs

## 1. Pipeline Step Execution Flow

### 1.1 Entry Point: `PipelineConfig.execute()` (pipeline.py L455-972)

The main execution loop:
1. Creates `PromptService` from pipeline session
2. Validates `input_data` against `INPUT_DATA` schema if declared
3. Creates `PipelineRun` record in DB
4. Loops through step indices, selects strategy via `strategy.can_handle(context)`
5. For each step: creates step instance via `StepDefinition.create_step(pipeline)`
6. Checks cache, then either loads from cache or runs fresh LLM calls
7. Saves step state, runs extractions, updates context

### 1.2 Step Definition & Creation (strategy.py)

`StepDefinition` is a dataclass holding:
- `step_class`, `system_instruction_key`, `user_prompt_key`, `instructions` (output type)
- `extractions`, `transformation`, `context`, `agent_name`, `consensus_strategy`

`StepDefinition.create_step(pipeline)` (strategy.py L48-143):
- Auto-discovers prompt keys if None (checks DB for `step_name.strategy_name` then `step_name`)
- Instantiates the step class with `system_instruction_key`, `user_prompt_key`, `instructions`, `pipeline`
- Attaches `_extractions`, `_transformation`, `_context`, `_agent_name` to instance

### 1.3 LLM Call Lifecycle (pipeline.py L707-871)

For fresh (non-cached) execution:
1. `step.prepare_calls()` returns `List[StepCallParams]` (variables, array_validation, validation_context)
2. `step.get_agent(AGENT_REGISTRY)` returns `(output_type, tools)` from the agent registry
3. `build_step_agent()` constructs a pydantic-ai `Agent[StepDeps, Any]`
4. For each call_params:
   - Creates `StepDeps` with session, context, prompt_service, variable_resolver, etc
   - Calls `step.build_user_prompt(variables, prompt_service)` to render user prompt
   - Resolves system prompt for event emission (L778-804)
   - Calls `agent.run_sync(user_prompt, deps=step_deps, model=self._model)`
   - `run_result.output` is the parsed Pydantic model (the "instruction")
5. Instructions stored in `self._instructions[step.step_name]`

## 2. Prompt Rendering / Template Variable Injection

### 2.1 Prompt Storage

Prompts stored in `prompts` table (db/prompt.py `Prompt` model):
- `prompt_key`: unique identifier (e.g. `constraint_extraction`)
- `prompt_type`: `system` or `user`
- `content`: template string with `{variable_name}` placeholders
- `required_variables`: auto-extracted list of variable names
- `version`: for cache invalidation

### 2.2 System Prompt Rendering

**At agent runtime** via `@agent.instructions` decorator in `build_step_agent()` (agent_builders.py L134-160):
```
1. If variable_resolver available:
   - Resolve variable class via resolver.resolve(sys_key, 'system')
   - Instantiate variable class (no args)
   - Call prompt_service.get_system_prompt(prompt_key, variables=dict, variable_instance=instance)
2. Else: prompt_service.get_prompt(prompt_key, prompt_type='system') -- raw template, no variable injection
```

`PromptService.get_system_prompt()` (prompts/service.py L86-126):
- Fetches template from DB
- Calls `template.format(**variables)` -- Python str.format() substitution

### 2.3 User Prompt Rendering

**In execute() loop** via `step.build_user_prompt()` (step.py L238-265):
```
1. Extracts variables from StepCallParams["variables"] (Pydantic model or dict)
2. Calls prompt_service.get_user_prompt(user_key, variables=dict, variable_instance=instance)
```

`PromptService.get_user_prompt()` (prompts/service.py L128-168):
- Fetches template from DB
- Calls `template.format(**variables)` -- same as system prompt

### 2.4 Variable Resolution

`VariableResolver` (prompts/variables.py): Protocol with `resolve(prompt_key, prompt_type) -> Type[BaseModel] | None`. Host project implements to map prompt keys to variable classes. System variables auto-instantiated (no args), user variables come from `StepCallParams["variables"]`.

## 3. pydantic-ai Agent System

### 3.1 AgentRegistry (agent_registry.py)

Declarative registry mapping step_names to output types (and optional tools):
```python
class MyAgentRegistry(AgentRegistry, agents={
    "step_name": OutputModel,
    "tool_step": AgentSpec(ToolOutput, tools=[my_func]),
}):
    pass
```

### 3.2 build_step_agent() (agent_builders.py)

Constructs `Agent[StepDeps, Any]` with:
- Dynamic system prompt via `@agent.instructions` (resolved at runtime from DB)
- Output validators (not_found_validator, array_length_validator)
- Optional tools wrapped in `EventEmittingToolset`
- `defer_model_check=True` (model passed at run_sync time)

### 3.3 StepDeps (agent_builders.py L23-53)

Dependency injection container for agents:
- `session`, `pipeline_context`, `prompt_service`
- `run_id`, `pipeline_name`, `step_name`
- `event_emitter`, `variable_resolver`
- `array_validation`, `validation_context` (per-call)

### 3.4 AgentRunResult (pydantic-ai)

`agent.run_sync()` returns `AgentRunResult[OutputDataT]`:
- `.output`: parsed Pydantic model (the validated structured output)
- `.usage()`: `RunUsage` with `input_tokens`, `output_tokens`
- `.all_messages()`: `list[ModelMessage]` -- full message history including model responses
- `.new_messages()`: messages from this run only

**Raw response text** can be extracted from `run_result.all_messages()` by finding `ModelResponse` messages and extracting `TextPart.content` from their `.parts`. This is NOT currently done.

## 4. State Persistence

### 4.1 PipelineStepState (state.py L24-121)

Persisted per step execution:
| Field | Description | Relevant to Input/Output Tabs |
|---|---|---|
| `pipeline_name` | snake_case pipeline name | -- |
| `run_id` | UUID for the run | -- |
| `step_name` | step identifier | -- |
| `step_number` | execution order (1,2,3...) | -- |
| `input_hash` | hash of step inputs (for cache) | -- |
| `result_data` | JSON: serialized instructions (model_dump) | **YES -- this is the parsed LLM output** |
| `context_snapshot` | JSON: pipeline context at this point | YES (Input tab shows previous step's context) |
| `prompt_system_key` | prompt key string (NOT rendered content) | NO (key only, not rendered) |
| `prompt_user_key` | prompt key string (NOT rendered content) | NO (key only, not rendered) |
| `prompt_version` | version for cache invalidation | -- |
| `model` | LLM model name | -- |
| `execution_time_ms` | step duration | -- |
| `input_tokens` / `output_tokens` / `total_tokens` / `total_requests` | token usage | -- |

**NOT stored in PipelineStepState:**
- Rendered system prompt (after variable injection)
- Rendered user prompt (after variable injection)
- Raw LLM response text (before parsing)

### 4.2 PipelineRun (state.py L162-196)

Run-level tracking: `run_id`, `pipeline_name`, `status`, `started_at`, `completed_at`, `step_count`, `total_time_ms`.

### 4.3 PipelineRunInstance (state.py L124-159)

Tracks DB instances created by runs (polymorphic: `model_type` + `model_id`).

## 5. Event System -- Where Rendered Prompts & Responses ARE Captured

### 5.1 Event Types (events/types.py)

Key events for input/output tabs:

**`LLMCallStarting`** (L322-330):
- `rendered_system_prompt: str` -- **fully rendered system prompt with variables injected**
- `rendered_user_prompt: str` -- **fully rendered user prompt with variables injected**
- `call_index: int`

**`LLMCallCompleted`** (L333-351):
- `raw_response: str | None` -- **ALWAYS None (hardcoded at pipeline.py L857 and L1281)**
- `parsed_result: dict[str, Any] | None` -- instruction.model_dump() (structured output)
- `model_name`, `attempt_count`, `validation_errors`
- `input_tokens`, `output_tokens`, `total_tokens`

### 5.2 How Events Are Emitted (pipeline.py L778-869)

System prompt rendering for events (L778-812):
```python
# Resolve system prompt (duplicates agent_builders logic)
if variable_resolver:
    var_class = variable_resolver.resolve(sys_key, 'system')
    if var_class:
        sys_vars = var_class()
        rendered_system = prompt_service.get_system_prompt(...)
    else:
        rendered_system = prompt_service.get_prompt(sys_key, 'system')
else:
    rendered_system = prompt_service.get_prompt(sys_key, 'system')

self._emit(LLMCallStarting(
    rendered_system_prompt=rendered_system,
    rendered_user_prompt=user_prompt,  # already rendered at L773-776
))
```

LLMCallCompleted emission (L851-869):
```python
self._emit(LLMCallCompleted(
    raw_response=None,  # <-- ALWAYS None
    parsed_result=instruction.model_dump(),
))
```

### 5.3 Event Persistence (events/handlers.py)

`SQLiteEventHandler`: persists each event as `PipelineEventRecord` row:
- `event_data`: full serialized event payload (JSON) -- **includes rendered_system_prompt and rendered_user_prompt**
- Stored in `pipeline_events` table

`CompositeEmitter`: dispatches to multiple handlers (logging, in-memory, SQLite).

`UIBridge` (ui/bridge.py): forwards events to WebSocket clients for real-time streaming.

### 5.4 Event Availability

Events are ONLY emitted when `event_emitter` is configured on the pipeline. The UI trigger (runs.py L238-241) always creates a `UIBridge`, but UI also needs `SQLiteEventHandler` for persistence (configured in app setup).

## 6. Existing API Endpoints

### 6.1 Steps API (ui/routes/steps.py)

- `GET /api/runs/{run_id}/steps` -- list steps (step_name, step_number, execution_time_ms, model, created_at)
- `GET /api/runs/{run_id}/steps/{step_number}` -- full step detail from `PipelineStepState`
  - Returns: result_data, context_snapshot, prompt_system_key/prompt_user_key (keys only), model, execution_time_ms

### 6.2 Events API (ui/routes/events.py)

- `GET /api/runs/{run_id}/events` -- paginated events with optional `event_type` and `step_name` filters
  - Returns: event_type, pipeline_name, run_id, timestamp, event_data (full payload)

### 6.3 Runs API (ui/routes/runs.py)

- `GET /api/runs` -- paginated list with filters
- `GET /api/runs/{run_id}` -- run detail with step summaries
- `POST /api/runs` -- trigger pipeline run (background task)
- `GET /api/runs/{run_id}/context` -- context evolution (snapshots per step)

### 6.4 WebSocket (ui/routes/websocket.py)

- `WS /ws/runs/{run_id}` -- real-time event streaming during execution

## 7. Frontend Current State (StepDetailPanel.tsx)

### 7.1 Tab Structure

7 tabs: Meta, Input, Prompts, Response, Instructions, Context, Extractions

### 7.2 Data Sources per Tab

| Tab | Data Source | Status |
|---|---|---|
| **Meta** | StepDetail API + llm_call_completed events | Works |
| **Input** | Context evolution API (previous step's context_snapshot) | Works |
| **Prompts** | `llm_call_starting` events -> `rendered_system_prompt`, `rendered_user_prompt` | **Works if events exist** |
| **Response** | `llm_call_completed` events -> `raw_response` (always null), `parsed_result` | **raw_response always null** |
| **Instructions** | Introspection API (`/api/pipelines/{name}/steps/{step_name}/prompts`) -- raw templates | Works |
| **Context** | Context evolution API (before/after diff via JsonDiff) | Works |
| **Extractions** | `extraction_completed` / `extraction_error` events | Works |

### 7.3 Frontend Type Definitions (api/types.ts)

```typescript
// Already defined and matching backend events:
interface LLMCallStartingData {
  call_index: number
  rendered_system_prompt: string
  rendered_user_prompt: string
}

interface LLMCallCompletedData {
  call_index: number
  raw_response: string | null      // <-- always null from backend
  parsed_result: Record<string, unknown> | null
  model_name: string | null
  attempt_count: number
  validation_errors: string[]
}
```

## 8. Identified Gaps

### 8.1 Gap: `raw_response` is Always None

**Location**: pipeline.py L857 and L1281 (both normal and consensus paths)
**Root Cause**: pydantic-ai `AgentRunResult.output` returns the parsed Pydantic model. The raw LLM text is not extracted.
**Fix**: After `agent.run_sync()`, call `run_result.all_messages()` to get `List[ModelMessage]`. Find `ModelResponse` messages, extract `TextPart.content` from their `.parts`. This gives the raw LLM output text before Pydantic parsing. Pass this as `raw_response` in `LLMCallCompleted`.

pydantic-ai message structure:
```
run_result.all_messages() -> [ModelRequest, ModelResponse, ...]
ModelResponse.parts -> [TextPart(content="..."), ToolCallPart(...), ...]
```

For structured output agents, the raw response is typically a JSON string in a `TextPart` or the arguments of a `ToolCallPart` (when using tool-based output).

### 8.2 Gap: Rendered Prompts Not in PipelineStepState

Rendered prompts are only available via events (`LLMCallStarting` in `pipeline_events` table). The `PipelineStepState` table only stores prompt keys, not rendered content. This means:
- Real-time display: works (WebSocket events)
- Post-run display: works (events API queries `pipeline_events`)
- If event persistence is disabled: rendered prompts are lost

**No change needed** if SQLiteEventHandler is always in the composite emitter for UI deployments (which it is for `trigger_run`).

### 8.3 Non-Gap: "Empty Tabs" Likely Caused By

The frontend tabs are correctly wired. "Empty" display would occur when:
1. No events exist for the step (event_emitter not configured, or events not persisted)
2. `raw_response` is null (always the case currently)
3. Run not triggered via UI (no UIBridge/SQLiteEventHandler configured)

## 9. Key Files Reference

| File | Purpose |
|---|---|
| `llm_pipeline/pipeline.py` | Core execution loop, LLM calls, event emission |
| `llm_pipeline/step.py` | LLMStep base class, step_definition decorator |
| `llm_pipeline/strategy.py` | StepDefinition, PipelineStrategy, PipelineStrategies |
| `llm_pipeline/agent_builders.py` | build_step_agent(), StepDeps |
| `llm_pipeline/agent_registry.py` | AgentRegistry, AgentSpec |
| `llm_pipeline/state.py` | PipelineStepState, PipelineRunInstance, PipelineRun |
| `llm_pipeline/prompts/service.py` | PromptService (get_system_prompt, get_user_prompt) |
| `llm_pipeline/prompts/variables.py` | VariableResolver protocol |
| `llm_pipeline/prompts/loader.py` | YAML prompt loading and sync |
| `llm_pipeline/db/prompt.py` | Prompt SQLModel |
| `llm_pipeline/events/types.py` | Event dataclasses (LLMCallStarting, LLMCallCompleted, etc) |
| `llm_pipeline/events/handlers.py` | LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler |
| `llm_pipeline/events/emitter.py` | PipelineEventEmitter protocol, CompositeEmitter |
| `llm_pipeline/events/models.py` | PipelineEventRecord (persistence model) |
| `llm_pipeline/ui/bridge.py` | UIBridge (sync adapter for WebSocket streaming) |
| `llm_pipeline/ui/routes/steps.py` | Step list/detail API endpoints |
| `llm_pipeline/ui/routes/events.py` | Events API endpoint |
| `llm_pipeline/ui/routes/runs.py` | Runs API + trigger endpoint |
| `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx` | Frontend step detail with tabs |
| `llm_pipeline/ui/frontend/src/api/types.ts` | TypeScript type definitions |

## 10. Implementation Recommendations

### 10.1 Fix raw_response (Required)

In `pipeline.py`, after `agent.run_sync()`:
```python
run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
instruction = run_result.output

# Extract raw response text from pydantic-ai messages
raw_text = None
for msg in reversed(run_result.new_messages()):
    if hasattr(msg, 'parts'):  # ModelResponse
        text_parts = [p.content for p in msg.parts if hasattr(p, 'content') and hasattr(p, 'part_kind') and p.part_kind == 'text']
        if text_parts:
            raw_text = '\n'.join(text_parts)
            break
        # For tool-call based output, extract args JSON
        tool_parts = [p for p in msg.parts if hasattr(p, 'part_kind') and p.part_kind == 'tool-call']
        if tool_parts:
            import json
            raw_text = json.dumps(tool_parts[0].args, indent=2) if hasattr(tool_parts[0], 'args') else None
            break
```

Apply to both normal path (L830-849) and consensus path (_execute_with_consensus L1256-1271).

### 10.2 No Schema Changes Needed

- PipelineStepState: no new columns (rendered prompts available via events)
- PipelineEventRecord: no changes (already stores full event payload)
- API endpoints: no changes (events API already serves LLMCallStarting/LLMCallCompleted data)
- Frontend types: no changes (LLMCallCompletedData.raw_response already typed as `string | null`)

### 10.3 The Only Backend Change

Replace `raw_response=None` with extracted raw text in both:
1. `pipeline.py L857` (normal path)
2. `pipeline.py L1281` (consensus path)

Frontend will automatically display it in the Response tab (already wired in StepDetailPanel.tsx ResponseTab).
