# Research: OTel + pydantic-ai Instrumentation for llm-pipeline

## 1. pydantic-ai OTel API

### InstrumentationSettings

Import: `from pydantic_ai import InstrumentationSettings` (or `from pydantic_ai.models.instrumented import InstrumentationSettings`)

Parameters:
| Param | Type | Default | Purpose |
|---|---|---|---|
| `tracer_provider` | `TracerProvider` | global OTel provider | Custom trace provider |
| `logger_provider` | `LoggerProvider` | global OTel provider | Custom log provider |
| `include_content` | `bool` | `True` | Include prompts/completions in spans (privacy-sensitive) |
| `use_aggregated_usage_attribute_names` | `bool` | `False` | Use `gen_ai.aggregated_usage.*` attrs on agent run spans to prevent double-counting |
| `event_mode` | `str` | varies | Controls how events are emitted in spans |

### Activation patterns

**Global (process-wide):**
```python
from pydantic_ai import Agent, InstrumentationSettings
Agent.instrument_all(InstrumentationSettings(...))
```

**Per-agent:**
```python
agent = Agent('model', instrument=InstrumentationSettings(...))
# or
agent = Agent('model', instrument=True)  # uses defaults
```

### OTel spans emitted by pydantic-ai

pydantic-ai automatically creates spans for:
- Agent run (parent span) -- includes aggregated token usage
- Each model request (child span) -- includes per-request token usage
- Tool calls (child spans)
- Retries (visible as multiple model request spans under the agent run span)

Span attributes follow OpenTelemetry Semantic Conventions for GenAI:
- `gen_ai.usage.input_tokens`
- `gen_ai.usage.output_tokens`
- `gen_ai.client.operation.name`
- `gen_ai.request.model`
- `gen_ai.response.model`

### Standard OTel env vars

pydantic-ai respects standard OpenTelemetry configuration:
- `OTEL_EXPORTER_OTLP_ENDPOINT` -- OTLP collector endpoint (e.g. `http://localhost:4318`)
- `OTEL_EXPORTER_OTLP_HEADERS` -- auth headers
- `OTEL_SERVICE_NAME` -- service name in traces
- `OTEL_RESOURCE_ATTRIBUTES` -- resource attributes

### Example: OTLP exporter setup

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider
from pydantic_ai import Agent

exporter = OTLPSpanExporter()
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
set_tracer_provider(tracer_provider)

Agent.instrument_all()
```

## 2. result.usage() API

After `agent.run_sync()`, `RunResult.usage()` returns a `RunUsage` dataclass:

```python
result = agent.run_sync('prompt', deps=deps, model=model)
usage = result.usage()
# RunUsage(input_tokens=57, output_tokens=8, requests=1)
usage.input_tokens   # int -- prompt/input tokens
usage.output_tokens  # int -- completion/output tokens
usage.requests       # int -- number of model requests (includes retries)
```

Additional fields for Anthropic caching:
- `usage.cache_write_tokens`
- `usage.cache_read_tokens`

## 3. Current Codebase State

### agent_builders.py

`build_step_agent()` creates `Agent[StepDeps, Any]` at L98-107:
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

No `instrument` parameter is passed.

### pipeline.py -- execute() (L809)

```python
run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
instruction = run_result.output
```

`run_result.usage()` is never called. The `run_result` variable goes out of scope unused.

### pipeline.py -- _execute_with_consensus() (L1227)

```python
run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
instruction = run_result.output
```

Same: `.usage()` never captured. Multiple calls per step (up to `maximum_step_calls`).

### PipelineStepState (state.py)

Current fields: `pipeline_name`, `run_id`, `step_name`, `step_number`, `input_hash`, `result_data`, `context_snapshot`, `prompt_system_key`, `prompt_user_key`, `prompt_version`, `model`, `created_at`, `execution_time_ms`.

**No token usage fields exist.**

### Existing event system

Already comprehensive with 25+ event types in `events/types.py`:
- `StepStarted`, `StepCompleted` -- step lifecycle (already exist, task description's "StepStarting/StepCompleted" are covered)
- `LLMCallPrepared`, `LLMCallStarting`, `LLMCallCompleted` -- per-call lifecycle (task description's "StepPrepared" is covered)
- `LLMCallRetry`, `LLMCallFailed`, `LLMCallRateLimited` -- defined but never emitted (orphaned after Task 2 deleted GeminiProvider)

`LLMCallCompleted` fields: `call_index`, `raw_response`, `parsed_result`, `model_name`, `attempt_count`, `validation_errors`. **No token usage fields.**

### pyproject.toml dependencies

No OTel dependencies exist. `pydantic-ai>=1.0.5` is in optional `[pydantic-ai]` and `[dev]` groups.

## 4. Implementation Plan (Recommended)

### 4a. New optional dependency group

```toml
otel = [
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-exporter-otlp-proto-http>=1.20.0",
]
```

Add to `[dev]` as well.

### 4b. Public instrumentation helper

New file: `llm_pipeline/instrumentation.py`

```python
def enable_instrumentation(
    include_content: bool = False,
    use_aggregated_usage: bool = True,
    tracer_provider=None,
    logger_provider=None,
):
    """Enable OTel instrumentation for all pydantic-ai agents.

    Call once at application startup. Requires opentelemetry-sdk.
    """
    from pydantic_ai import Agent, InstrumentationSettings

    settings = InstrumentationSettings(
        include_content=include_content,
        use_aggregated_usage_attribute_names=use_aggregated_usage,
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
    )
    Agent.instrument_all(settings)
```

### 4c. Token usage capture in pipeline.py

After each `agent.run_sync()` call, capture `run_result.usage()`:

**Normal path (L809):**
```python
run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
instruction = run_result.output
usage = run_result.usage()
step_input_tokens += usage.input_tokens
step_output_tokens += usage.output_tokens
step_requests += usage.requests
```

**Consensus path:** Sum across all attempts.

### 4d. PipelineStepState schema addition

Add 3 nullable int fields:
```python
input_tokens: Optional[int] = Field(default=None, description="Total input/prompt tokens for this step")
output_tokens: Optional[int] = Field(default=None, description="Total output/completion tokens for this step")
request_count: Optional[int] = Field(default=None, description="Number of model requests (includes retries)")
```

Migration: ALTER TABLE pattern (same as `SQLiteEventHandler.__init__` handles `step_name`).

### 4e. LLMCallCompleted event enrichment

Add `input_tokens`, `output_tokens`, `request_count` fields to `LLMCallCompleted` event:
```python
input_tokens: int | None = None
output_tokens: int | None = None
request_count: int | None = None
```

### 4f. StepCompleted event enrichment

Add token aggregates to `StepCompleted`:
```python
input_tokens: int | None = None
output_tokens: int | None = None
```

### 4g. _save_step_state() update

Pass token counts to `_save_step_state()` and store in `PipelineStepState`.

### 4h. Exports and docs

- Export `enable_instrumentation` from `llm_pipeline/__init__.py`
- Create `docs/observability.md` documenting OTel setup

## 5. What is NOT needed (already exists)

- Pipeline event types: `StepStarted`, `StepCompleted`, `LLMCallPrepared` already exist
- Event emitter infrastructure: `CompositeEmitter`, `PipelineEventEmitter` protocol already exist
- Event persistence: `SQLiteEventHandler`, `PipelineEventRecord` already exist
- No new event *types* needed for the "pipeline event system" -- the task description was written before the event system was built

## 6. Open Questions for CEO

### Q1: OTel activation pattern
`Agent.instrument_all()` is process-wide -- instruments ALL pydantic-ai agents, not just pipeline agents. If the consumer uses pydantic-ai agents outside llm-pipeline, those get instrumented too.
- **Option A**: `Agent.instrument_all()` via public helper (simpler, recommended)
- **Option B**: `instrument=settings` per-agent in `build_step_agent()` (scoped to pipeline agents only)

### Q2: include_content default
Task description says `include_content=True`. This sends all prompts and model completions to the OTel backend. For a library consumed by external apps, this is a privacy risk (PII in prompts).
- **Option A**: Default `True` (as task says) -- convenient for development
- **Option B**: Default `False` (security-first) -- consumer opts in
- Recommendation: `False`

### Q3: Consensus token aggregation
In consensus mode, multiple `agent.run_sync()` calls per step. How to store token usage?
- **Option A**: Sum all attempts' tokens (accurate cost tracking, recommended)
- **Option B**: Only store winning result's tokens (misleading cost data)

### Q4: Existing event types sufficient?
Task says "Define pipeline event types (StepPrepared, StepStarting, StepCompleted)". These already exist (`LLMCallPrepared`, `StepStarted`, `StepCompleted`). Should we:
- **Option A**: Use existing events, enrich with token fields (recommended)
- **Option B**: Create additional/duplicate event types
