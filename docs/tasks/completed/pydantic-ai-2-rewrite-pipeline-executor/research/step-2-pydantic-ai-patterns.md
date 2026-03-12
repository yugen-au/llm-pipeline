# Research Step 2: pydantic-ai Library Patterns

## Installed Version

pydantic-ai **1.62.0** (Python 3.13, installed in project venv)

---

## 1. Agent.run_sync() API

### Signature (v1.62.0)

```python
def run_sync(
    self,
    user_prompt: str | Sequence[UserContent] | None = None,
    *,
    output_type: OutputSpec[RunOutputDataT] | None = None,
    message_history: Sequence[ModelMessage] | None = None,
    model: Model | KnownModelName | str | None = None,
    instructions: Instructions[AgentDepsT] = None,
    deps: AgentDepsT = None,
    model_settings: ModelSettings | None = None,
    usage_limits: UsageLimits | None = None,
    usage: RunUsage | None = None,
    metadata: AgentMetadata[AgentDepsT] | None = None,
    infer_name: bool = True,
    toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
    builtin_tools: Sequence[AbstractBuiltinTool | BuiltinToolFunc[AgentDepsT]] | None = None,
    event_stream_handler: EventStreamHandler[AgentDepsT] | None = None,
) -> AgentRunResult[Any]
```

### Key Parameters for Pipeline Integration

| Parameter | Usage in Pipeline |
|-----------|------------------|
| `user_prompt` | Output of `step.build_user_prompt(variables, prompt_service)` |
| `deps` | `StepDeps(session=..., pipeline_context=..., prompt_service=..., ...)` |
| `model` | Runtime model override (e.g. `"google-gla:gemini-2.0-flash-lite"`) - can override agent's default |
| `model_settings` | Temperature, max_tokens, etc. |
| `usage` | Pass `RunUsage()` accumulator for cross-call token tracking |
| `usage_limits` | `UsageLimits(request_limit=N, request_tokens_limit=N)` for safety |

### Important Behaviors

- `run_sync()` is a convenience wrapper around `loop.run_until_complete(self.run(...))` -- cannot be called inside async code or with an active event loop.
- System prompt / instructions are resolved at call time from registered `@agent.instructions` decorators (already set up by `build_step_agent()` in Task 1).
- `output_type` kwarg can override agent's default output type per-call (useful if one agent handles multiple schemas, but NOT our pattern).
- `model=` kwarg overrides the agent's configured model for this single call.

---

## 2. AgentRunResult

### Import Path

```python
from pydantic_ai import AgentRunResult  # re-exported at top level
# Actual location: pydantic_ai.run.AgentRunResult
```

### Access Patterns

```python
result = agent.run_sync(user_prompt, deps=step_deps)

# Validated output (the Pydantic model instance)
instruction = result.output  # dataclass field, direct access, NOT a method

# Token usage
usage = result.usage()  # method call, returns RunUsage
```

### RunUsage Fields

```python
@dataclass
class RunUsage:
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    input_audio_tokens: int = 0
    cache_audio_read_tokens: int = 0
    output_audio_tokens: int = 0
    details: dict[str, int] = field(default_factory=dict)
    requests: int = 0
    tool_calls: int = 0
```

### Other AgentRunResult Attributes

| Attribute | Type | Notes |
|-----------|------|-------|
| `.output` | `OutputDataT` | Validated Pydantic model (dataclass field) |
| `.usage()` | `RunUsage` | Method returning token counts |
| `.all_messages()` | `list[ModelMessage]` | Full conversation history |
| `.new_messages()` | `list[ModelMessage]` | Messages from this run only |
| `.response` | `ModelResponse` | Raw model response |
| `.run_id` | `str` | pydantic-ai's internal run ID |
| `.timestamp` | `datetime` | Completion timestamp |
| `.metadata` | `dict` | Attached metadata |

---

## 3. StepDeps / RunContext Dependency Injection

### Pattern (Already Implemented in Task 1)

```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

@dataclass
class StepDeps:
    session: Any
    pipeline_context: dict[str, Any]
    prompt_service: Any
    run_id: str
    pipeline_name: str
    step_name: str
    event_emitter: Any | None = None
    variable_resolver: Any | None = None

agent = Agent(
    model=model,
    output_type=output_type,
    deps_type=StepDeps,
    name=step_name,
    retries=retries,
    defer_model_check=True,
)

# At runtime:
result = agent.run_sync(user_prompt, deps=step_deps_instance)
```

### RunContext Access in Decorators

```python
@agent.instructions
def inject_prompt(ctx: RunContext[StepDeps]) -> str:
    return ctx.deps.prompt_service.get_prompt(...)

@agent.tool
def some_tool(ctx: RunContext[StepDeps], query: str) -> str:
    return ctx.deps.session.exec(...)

@agent.output_validator
def validate(ctx: RunContext[StepDeps], output: MyModel) -> MyModel:
    # Can raise ModelRetry("fix this") to trigger LLM retry
    return output
```

### RunContext Properties

- `ctx.deps` - The StepDeps instance
- `ctx.usage` - Current RunUsage accumulator
- `ctx.run_id` - pydantic-ai run identifier
- `ctx.model` - Current model being used
- `ctx.retry` - Current retry count

---

## 4. UnexpectedModelBehavior Exception

### Class Hierarchy

```
UnexpectedModelBehavior -> AgentRunError -> RuntimeError -> Exception
```

### Constructor

```python
def __init__(self, message: str, body: str | None = None):
    self.message = message
    # body is pretty-printed JSON if parseable, raw string otherwise
    if body is not None:
        try:
            self.body = json.dumps(json.loads(body), indent=2)
        except ValueError:
            self.body = body
    else:
        self.body = None
    super().__init__(message)
```

### When Raised

- Max tool retries exceeded (e.g. `ModelRetry` raised more than `retries` times)
- Unexpected HTTP response codes (after transport-level retries exhausted)
- Model returns unparseable output after all retries

### Mapping to create_failure()

```python
try:
    result = agent.run_sync(user_prompt, deps=step_deps)
    instruction = result.output
except UnexpectedModelBehavior as e:
    instruction = result_class.create_failure(e.message)
    # e.body available for detailed logging if needed
    # e.__cause__ contains original ModelRetry if from validator
```

---

## 5. Retry / Rate Limiting

### Two Layers of Retry in pydantic-ai

#### Layer 1: HTTP Transport (429 / Rate Limits)

pydantic-ai uses `httpx` with `AsyncTenacityTransport` for HTTP-level retries:

```python
from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig, wait_retry_after

transport = AsyncTenacityTransport(
    config=RetryConfig(
        retry=retry_if_exception_type(HTTPStatusError),
        wait=wait_retry_after(
            fallback_strategy=wait_exponential(multiplier=1, max=60),
            max_wait=300
        ),
        stop=stop_after_attempt(5),
        reraise=True
    ),
    validate_response=lambda r: r.raise_for_status()
)
client = AsyncClient(transport=transport)
```

- Respects `Retry-After` headers from 429 responses
- Falls back to exponential backoff
- Handles 429, 502, 503, 504 status codes
- **For google-gla (Gemini) provider**: uses Google's genai SDK which has its own retry logic

**This fully replaces our custom `RateLimiter` class** (sliding window + `time.sleep`).

#### Layer 2: Agent Output Validation Retries

Controlled by `retries=` parameter on `Agent()` constructor (default: 1):

```python
agent = Agent(model=..., output_type=MyModel, retries=3)
```

- When `@agent.output_validator` raises `ModelRetry("fix message")`, pydantic-ai sends the error back to the LLM and retries
- When Pydantic validation fails on output, pydantic-ai sends validation errors back to LLM
- After `retries` attempts, raises `UnexpectedModelBehavior`
- **Task 1 already sets `retries=3` in `build_step_agent()`**

### What Our RateLimiter Did vs pydantic-ai

| Feature | Our RateLimiter | pydantic-ai |
|---------|----------------|-------------|
| Sliding window rate limit | Yes (max_requests per time_window) | No (uses per-request retry) |
| 429 Retry-After respect | No (manual regex parsing) | Yes (built into transport) |
| Exponential backoff | No | Yes (tenacity) |
| Pre-request throttling | Yes (wait_if_needed before call) | No (reactive, retry after failure) |
| Scope | Global singleton | Per HTTP client / per model |

**Key difference**: Our RateLimiter was proactive (throttle before hitting limits), pydantic-ai is reactive (retry after 429). For Gemini's rate limits, pydantic-ai's approach is sufficient because:
1. Google's genai SDK already handles retry internally
2. The Retry-After header tells exactly how long to wait
3. Exponential backoff prevents thundering herd

---

## 6. Dynamic Instructions via @agent.instructions

### Already Implemented (Task 1)

`build_step_agent()` registers `@agent.instructions` that resolves system prompt from DB via PromptService:

```python
@agent.instructions
def _inject_system_prompt(ctx: RunContext[StepDeps]) -> str:
    if ctx.deps.variable_resolver:
        var_class = ctx.deps.variable_resolver.resolve(sys_key, 'system')
        if var_class:
            system_variables = var_class()
            variables_dict = (
                system_variables.model_dump()
                if hasattr(system_variables, 'model_dump')
                else system_variables
            )
            return ctx.deps.prompt_service.get_system_prompt(
                prompt_key=sys_key,
                variables=variables_dict,
                variable_instance=system_variables,
            )
    return ctx.deps.prompt_service.get_prompt(
        prompt_key=sys_key,
        prompt_type='system',
    )
```

### Additional Notes

- Multiple `@agent.instructions` decorators are **additive** (all called, results concatenated as separate system prompt parts)
- `instructions=` kwarg on `run_sync()` can add **per-call** instructions without modifying agent
- `@agent.system_prompt` is an older alias for `@agent.instructions` (both work in v1.62.0)
- Instructions can be sync or async functions

---

## 7. AgentRegistry + build_step_agent() Integration

### Current State (from Task 1)

```python
# AgentRegistry stores output_type refs only (NOT Agent instances)
class MyAgentRegistry(AgentRegistry, agents={
    "constraint_extraction": ConstraintExtractionInstructions,
    "lane_extraction": LaneExtractionInstructions,
}):
    pass

# LLMStep.get_agent() returns output_type, not an Agent
output_type = step.get_agent(registry)  # returns Type[BaseModel]

# build_step_agent() constructs the Agent at call time
agent = build_step_agent(
    step_name="constraint_extraction",
    output_type=output_type,
    model="google-gla:gemini-2.0-flash-lite",
    retries=3,
)
```

### Proposed Integration for execute()

```python
# In PipelineConfig.execute(), for each step:
output_type = step.get_agent(self.AGENT_REGISTRY)
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
    model=model_string,  # pydantic-ai format
    system_instruction_key=step.system_instruction_key,
    retries=3,
)
step_deps = StepDeps(
    session=self._real_session,
    pipeline_context=dict(self._context),
    prompt_service=prompt_service,
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    event_emitter=self._event_emitter,
    variable_resolver=self._variable_resolver,
)
user_prompt = step.build_user_prompt(params["variables"], prompt_service)
try:
    run_result = agent.run_sync(user_prompt, deps=step_deps)
    instruction = run_result.output
except UnexpectedModelBehavior as e:
    instruction = output_type.create_failure(e.message)
```

---

## 8. Gemini Model String Mapping

| Context | Format | Example |
|---------|--------|---------|
| Current GeminiProvider | Google SDK format | `"gemini-2.0-flash-lite"` |
| pydantic-ai (google-gla) | Prefixed format | `"google-gla:gemini-2.0-flash-lite"` |
| pydantic-ai (vertex) | Prefixed format | `"google-vertex:gemini-2.0-flash-lite"` |

The pipeline currently stores model name as `self._provider.model_name` (e.g. `"gemini-2.0-flash-lite"`). For pydantic-ai, this must be prefixed with `"google-gla:"` (or configurable provider prefix).

### Available Gemini Models in pydantic-ai 1.62.0

- `google-gla:gemini-2.0-flash-lite`
- `google-gla:gemini-2.0-flash`
- `google-gla:gemini-2.5-flash`
- `google-gla:gemini-2.5-flash-lite`
- `google-gla:gemini-2.5-pro`

---

## 9. Functions to Delete (Scope Confirmation)

Per Task 2 description, these become obsolete:

| Function/Class | File | Reason |
|---------------|------|--------|
| `execute_llm_step()` | `llm/executor.py` | Replaced by `agent.run_sync()` |
| `validate_structured_output()` | `llm/validation.py` | pydantic-ai handles Pydantic validation natively |
| `validate_array_response()` | `llm/validation.py` | Deferred to Task 3 (output validators) |
| `check_not_found_response()` | `llm/validation.py` | Deferred to Task 3 (output validators) |
| `format_schema_for_llm()` | `llm/schema.py` | pydantic-ai sends schema automatically via tool/output schema |
| `RateLimiter` | `llm/rate_limiter.py` | Replaced by pydantic-ai transport-level retry |
| `ExecuteLLMStepParams` | `types.py` | Deprecated (no longer needed without execute_llm_step) |

### Functions to KEEP

| Function/Class | File | Reason |
|---------------|------|--------|
| `save_step_yaml()` | `llm/executor.py` | Still used for YAML export, not LLM-related |
| `flatten_schema()` | `llm/schema.py` | May still be useful for other purposes |
| `LLMProvider` | `llm/provider.py` | TBD - see open question below |
| `GeminiProvider` | `llm/gemini.py` | TBD - see open question below |
| `LLMCallResult` | `llm/result.py` | TBD - may be needed for backward compat |
| `strip_number_prefix()` | `llm/validation.py` | Used by array validation (Task 3) |
| `extract_retry_delay_from_error()` | `llm/validation.py` | May still be useful |
| `validate_field_value()` | `llm/validation.py` | May still be useful |

---

## 10. Consensus Polling with run_sync()

Current `_execute_with_consensus()` calls `execute_llm_step()` in a loop. Direct replacement:

```python
def _execute_with_consensus(self, agent, step_deps, user_prompt, output_type,
                             consensus_threshold, maximum_step_calls, step_name):
    results = []
    result_groups = []
    for attempt in range(maximum_step_calls):
        try:
            run_result = agent.run_sync(user_prompt, deps=step_deps)
            instruction = run_result.output
        except UnexpectedModelBehavior as e:
            instruction = output_type.create_failure(e.message)
        results.append(instruction)
        # ... same grouping/consensus logic ...
```

The `usage=` parameter on `run_sync()` can accumulate tokens across consensus calls by passing the same `RunUsage` instance.

---

## 11. Key Differences: Old vs New Pattern

| Aspect | Old (execute_llm_step) | New (agent.run_sync) |
|--------|----------------------|---------------------|
| System prompt | Resolved in executor, passed as string | Resolved via @agent.instructions decorator |
| User prompt | Resolved in executor, passed as string | Resolved via step.build_user_prompt(), passed to run_sync() |
| Output validation | Manual: JSON parse -> validate_structured_output -> Pydantic model | Automatic: pydantic-ai validates against output_type schema |
| Retry on validation | Manual: loop with max_retries in GeminiProvider | Automatic: pydantic-ai retries with error feedback to LLM |
| Rate limiting | Manual: RateLimiter.wait_if_needed() pre-call | Automatic: httpx transport retry on 429 |
| Error handling | try/except -> create_failure() | UnexpectedModelBehavior -> create_failure() |
| Token tracking | Not tracked | run_result.usage() -> RunUsage dataclass |
| Provider abstraction | LLMProvider ABC + GeminiProvider | pydantic-ai model string (e.g. "google-gla:gemini-2.0-flash-lite") |

---

## 12. Open Questions for Implementation Phase

### Q1: Agent Caching Strategy

Should agents be built once per step and cached, or built fresh each call? `build_step_agent()` registers `@agent.instructions` which creates a closure over `sys_key`. If `system_instruction_key` doesn't change between calls, the agent can be cached. Recommendation: build once per step in execute loop (not per-call-param), since the agent config doesn't change within a step.

### Q2: LLMProvider / GeminiProvider Fate

Task 2 description says delete specific utils but doesn't mention LLMProvider/GeminiProvider. Options:
- **Keep as deprecated**: Mark with deprecation warnings, remove in Task 6
- **Delete now**: Task 2 replaces all call sites, no remaining usage
- **Thin wrapper**: Keep LLMProvider as config holder for model name only

Recommendation: Keep but deprecate. GeminiProvider still has value for non-pydantic-ai use cases during migration. Full removal in Task 6 (final cleanup).

### Q3: Model String Source

Where does the pydantic-ai model string come from at runtime?
- Option A: New `model: str` field on PipelineConfig (pydantic-ai format)
- Option B: Derive from `self._provider.model_name` with prefix mapping
- Option C: Field on StepDefinition for per-step model override

Recommendation: Option A or B. Pipeline-level model string is simplest; per-step override can come later.

### Q4: `create_llm_call()` Removal Timing

Task 1 deprecated it. Task 2 should stop calling it in execute(). But should we delete it now or in Task 6?
- Task 2 description says to replace its usage, not explicitly delete the method
- Recommendation: Stop calling it, keep deprecated method on LLMStep for backward compat, delete in Task 6.
