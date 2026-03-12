# Step 3: Current Codebase Analysis - OTel & Token Usage Integration Points

## File Structure (Actual vs Task Description)

Task description references `core/schemas/pipeline/` paths. Actual structure is flat:
- `llm_pipeline/pipeline.py` (was `config.py`)
- `llm_pipeline/state.py`
- `llm_pipeline/agent_builders.py`
- `llm_pipeline/strategy.py`
- `llm_pipeline/__init__.py`
- `llm_pipeline/events/types.py`, `emitter.py`, `handlers.py`, `models.py`

---

## 1. Existing Event System (ALREADY COMPREHENSIVE)

The codebase has a fully built event system with 22+ event dataclasses. Key events relevant to Task 4 scope:

| Event | File | Category | Already Exists |
|---|---|---|---|
| StepStarted | events/types.py:238 | step_lifecycle | YES |
| StepCompleted | events/types.py:249 | step_lifecycle | YES |
| LLMCallPrepared | events/types.py:307 | llm_call | YES |
| LLMCallStarting | events/types.py:318 | llm_call | YES |
| LLMCallCompleted | events/types.py:329 | llm_call | YES |
| LLMCallRetry | events/types.py:347 | llm_call | YES |
| LLMCallFailed | events/types.py:359 | llm_call | YES |
| ConsensusStarted | events/types.py:383 | consensus | YES |

**The task description mentions "Define pipeline event types (StepPrepared, StepStarting, StepCompleted)". These already exist as StepStarted, StepCompleted, LLMCallPrepared. The pipeline.py execute() loop already emits all of these.**

Infrastructure:
- `PipelineEventEmitter` - Protocol with `emit()` method (emitter.py:21)
- `CompositeEmitter` - Multi-handler dispatch with error isolation (emitter.py:44)
- `LoggingEventHandler`, `InMemoryEventHandler`, `SQLiteEventHandler` (handlers.py)
- `PipelineEventRecord` - SQLModel table for persistence (models.py:16)
- Auto-registration via `__init_subclass__` with derived `event_type` strings

---

## 2. OTel Instrumentation (NOT YET DONE)

### Current State
`agent_builders.py:98-107` - Agent construction has NO `instrument=` parameter:

```python
agent: Agent[StepDeps, Any] = Agent(
    model=model,
    output_type=output_type,
    deps_type=StepDeps,
    name=step_name,
    retries=retries,
    model_settings=model_settings,
    defer_model_check=True,
    validation_context=lambda ctx: ctx.deps.validation_context,
)
```

### pydantic-ai OTel API (v1.0.5, from Context7)

Two approaches:
1. **Per-agent**: `Agent(instrument=InstrumentationSettings(include_content=True))`
2. **Global**: `Agent.instrument_all(InstrumentationSettings(include_content=True))`

`InstrumentationSettings` accepts:
- `include_content: bool` - include prompt/response content in spans
- `include_binary_content: bool` - include binary content
- `tracer_provider: TracerProvider` - custom OTel tracer provider
- `event_logger_provider: EventLoggerProvider` - custom OTel event logger

### Insertion Point
`build_step_agent()` in `agent_builders.py:55-143`. Add optional `instrument` parameter.

---

## 3. Token Usage (NOT YET CAPTURED)

### Current State - Token Data is Discarded

**Normal path** (pipeline.py:808-814):
```python
run_result = agent.run_sync(
    user_prompt,
    deps=step_deps,
    model=self._model,
)
instruction = run_result.output  # <-- usage() is NEVER called
```

**Consensus path** (pipeline.py:1227-1228):
```python
run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
instruction = run_result.output  # <-- usage() is NEVER called
```

### pydantic-ai Usage API (v1.0.5, from Context7)

`run_result.usage()` returns `RunUsage`:
- `input_tokens: int`
- `output_tokens: int`
- `requests: int`

Note: pydantic-ai uses `input_tokens`/`output_tokens`, not `request_tokens`/`response_tokens` as mentioned in the task description. Field naming should match pydantic-ai's convention.

### PipelineStepState - Missing Token Fields

Current fields in `state.py:24-103`:
- `id`, `pipeline_name`, `run_id`, `step_name`, `step_number`
- `input_hash`, `result_data` (JSON), `context_snapshot` (JSON)
- `prompt_system_key`, `prompt_user_key`, `prompt_version`
- `model` (str)
- `created_at`, `execution_time_ms`

**Missing**: No token usage fields at all.

### Needed New Fields on PipelineStepState

```python
# Token usage (from pydantic-ai RunUsage)
request_tokens: Optional[int] = Field(default=None, description="Input tokens used")
response_tokens: Optional[int] = Field(default=None, description="Output tokens used")
total_tokens: Optional[int] = Field(default=None, description="Total tokens (request + response)")
total_requests: Optional[int] = Field(default=None, description="Number of LLM requests (including retries)")
```

---

## 4. Exact Insertion Points

### A. agent_builders.py - Add OTel instrumentation

**Where**: `build_step_agent()` function signature and Agent() constructor call (lines 55-107)
**What**: Add optional `instrument` parameter, pass to Agent()

### B. pipeline.py - Capture token usage (normal path)

**Where**: Lines 808-814 (after `run_result = agent.run_sync(...)`)
**What**: Call `run_result.usage()`, accumulate per-step totals

### C. pipeline.py - Capture token usage (consensus path)

**Where**: Lines 1227-1228 in `_execute_with_consensus()`
**What**: Call `run_result.usage()`, sum across all consensus attempts

### D. pipeline.py - Pass tokens to _save_step_state()

**Where**: Line 878 call to `self._save_step_state()`
**What**: Add token parameters to signature and call site

### E. pipeline.py - _save_step_state() signature

**Where**: Lines 1063-1114
**What**: Accept and store token fields in PipelineStepState

### F. state.py - PipelineStepState model

**Where**: After `execution_time_ms` field (line 97)
**What**: Add request_tokens, response_tokens, total_tokens, total_requests fields

### G. events/types.py - LLMCallCompleted enrichment

**Where**: Lines 329-345
**What**: Add token usage fields to existing LLMCallCompleted event

### H. pyproject.toml - OTel dependencies

**Where**: `[project.optional-dependencies]` section
**What**: Add `[otel]` group with opentelemetry-api, opentelemetry-sdk

---

## 5. Dependencies Analysis

### Current pyproject.toml

```toml
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
pydantic-ai = ["pydantic-ai>=1.0.5"]
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
```

### Needed for OTel

Minimum packages for OTel instrumentation:
- `opentelemetry-api` - core OTel API
- `opentelemetry-sdk` - trace/span SDK

Optional exporters (user-configured, not our dependency):
- `opentelemetry-exporter-otlp-proto-http` - for OTLP/HTTP
- `opentelemetry-exporter-jaeger` - for Jaeger

pydantic-ai's `InstrumentationSettings` uses `opentelemetry.sdk.trace.TracerProvider` and `opentelemetry.sdk._events.EventLoggerProvider`, so the SDK is required.

---

## 6. Upstream Task Deviations

### Task 2 (Rewrite Pipeline Executor) - DONE

Reviewed `docs/tasks/completed/pydantic-ai-2-rewrite-pipeline-executor/`. Key outcomes relevant to Task 4:
- `agent.run_sync(user_prompt, deps=step_deps, model=self._model)` is the current call pattern
- `run_result.output` extracts the instruction
- `UnexpectedModelBehavior` mapped to `create_failure()`
- Events system left intact during rewrite
- Token usage retrieval explicitly deferred to Task 4 (per task 2 description: "run_result.usage() for token logging is detailed in Task 4")

### No Deviations from Plan
The executor rewrite followed the expected pattern. Token usage capture was deliberately left for Task 4.

---

## 7. Downstream Task Scope (Task 6 - OUT OF SCOPE)

Task 6 is "Final Integration, Comprehensive Testing, and Cleanup". It depends on tasks 1-5. Not relevant to current research except noting that OTel + token fields added here will need integration testing there.

---

## 8. Open Questions for CEO

### Q1: Event System Scope
Task 4 description says "Define pipeline event types (StepPrepared, StepStarting, StepCompleted) as dataclasses in events.py". These already exist in `events/types.py`. Is the actual scope now:
- (a) OTel instrumentation on agents
- (b) Token usage capture + storage in PipelineStepState
- (c) Token field enrichment on existing LLMCallCompleted event
- (d) docs/observability.md
- Or are additional/different events needed?

### Q2: OTel Dependency Strategy
Should OTel packages be:
- (a) New `[otel]` optional dep group in pyproject.toml (recommended - keeps base light)
- (b) Required deps
- (c) Bundled with existing `[pydantic-ai]` optional group

### Q3: Instrumentation Scope
Should OTel be:
- (a) Per-agent via `instrument=` in `build_step_agent()` (granular control)
- (b) Global via `Agent.instrument_all()` in pipeline init
- (c) Configurable - user passes `InstrumentationSettings` to `PipelineConfig` constructor

### Q4: Consensus Token Accumulation
In `_execute_with_consensus()`, multiple `run_sync()` calls happen. Should `PipelineStepState` token counts be:
- (a) Sum of all consensus attempts (shows true cost)
- (b) Only the winning attempt's tokens

### Q5: LLMCallCompleted Enrichment
Should we add `request_tokens`/`response_tokens`/`total_tokens` to the existing `LLMCallCompleted` event for per-call granularity?

### Q6: Token Field Naming
pydantic-ai uses `input_tokens`/`output_tokens`. Task description uses `request_tokens`/`response_tokens`. Which naming convention for PipelineStepState?
