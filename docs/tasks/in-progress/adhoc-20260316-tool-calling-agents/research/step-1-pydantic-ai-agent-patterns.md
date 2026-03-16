# Step 1: pydantic-ai Agent Tool-Calling Patterns

## Environment

- **pydantic-ai installed**: 1.67.0 (pyproject.toml requires `>=1.0.5`)
- **Agent location**: `llm_pipeline/agent_builders.py` -> `build_step_agent()`
- **Current deps type**: `StepDeps` dataclass

---

## 1. Agent Constructor `tools` Parameter

```python
# From Agent.__init__ signature (v1.67.0):
tools: Sequence[Tool[AgentDepsT] | ToolFuncEither[AgentDepsT, ...]] = ()
```

Accepts:
- **Raw callables** -- pydantic-ai auto-detects `takes_ctx` by inspecting first param for `RunContext`
- **`Tool()` wrapper objects** -- explicit control: `Tool(fn, takes_ctx=True, name=..., description=...)`

```python
# Pattern A: raw functions (auto-detect)
agent = Agent(..., tools=[my_ctx_tool, my_plain_tool])

# Pattern B: explicit Tool wrappers
agent = Agent(..., tools=[
    Tool(my_ctx_tool, takes_ctx=True),
    Tool(my_plain_tool, takes_ctx=False),
])
```

Both patterns verified working in v1.67.0.

## 2. Tool Registration Patterns

### Constructor (build-time)
```python
agent = Agent(model, deps_type=StepDeps, tools=[fn1, fn2])
```

### Decorator (post-construction)
```python
agent = Agent(model, deps_type=StepDeps)

@agent.tool
def ctx_tool(ctx: RunContext[StepDeps], query: str) -> str: ...

@agent.tool_plain
def plain_tool(query: str) -> str: ...
```

### Direct call (post-construction, non-decorator)
```python
agent.tool(my_function)
agent.tool_plain(my_function)
```

### Mixed (constructor + decorator)
```python
agent = Agent(model, deps_type=StepDeps, tools=[fn1])
@agent.tool
def fn2(ctx: RunContext[StepDeps]) -> str: ...
# Both fn1 and fn2 available -- verified working
```

**Recommendation for build_step_agent()**: Use **constructor `tools=` param**. We build agent once per step in the factory; passing tools at construction is cleanest. No need for post-construction decorator loops.

## 3. RunContext[DepsType] Injection

Tools decorated with `@agent.tool` (or passed with `takes_ctx=True`) receive `RunContext[DepsType]` as first param:

```python
@agent.tool
async def navigate_sheet(ctx: RunContext[StepDeps], sheet_name: str) -> str:
    workbook = ctx.deps.extra["workbook_context"]  # domain dep via extra dict
    session = ctx.deps.session                      # DB session
    pipeline_ctx = ctx.deps.pipeline_context        # pipeline context dict
    return workbook.get_sheet(sheet_name).to_string()
```

RunContext provides:
- `ctx.deps` -- the StepDeps instance passed to `run_sync(deps=...)`
- `ctx.tool_call_id` -- unique ID for this tool call
- `ctx.retry` -- current retry count for this tool call

**Key**: Our existing StepDeps flows through automatically. Tools access all pipeline deps (session, pipeline_context, prompt_service, event_emitter, etc.) via `ctx.deps.*`. Domain-specific deps go in `ctx.deps.extra["key"]`.

## 4. Tool-Call Loop in `run_sync()`

### Internal Loop Behavior

`agent.run_sync()` (and `agent.run()`) internally runs a loop:

1. Send user prompt + system prompt + tool definitions to model
2. Model responds with either:
   - **Tool calls** -> execute tools, send results back, goto step 1
   - **Structured output** -> validate, return RunResult
3. Loop continues until model produces final output (no more tool calls)

### EndStrategy

```python
# Agent constructor param:
end_strategy: EndStrategy = 'early'  # Literal['early', 'exhaustive']
```

- `'early'` (default): Stop as soon as model produces a valid output, even if tool calls are pending
- `'exhaustive'`: Process ALL tool calls before accepting output

For our use case, `'early'` default is correct -- agent should stop when it has enough info to produce structured output.

### Safety Limits

```python
# UsageLimits (passed to run_sync via usage_limits=)
request_limit: int | None = 50        # max model round-trips (default 50)
tool_calls_limit: int | None = None   # max total tool invocations (unlimited)
input_tokens_limit: int | None = None
output_tokens_limit: int | None = None
total_tokens_limit: int | None = None
```

Default `request_limit=50` prevents infinite tool-call loops. Can override per-call:
```python
from pydantic_ai.usage import UsageLimits
agent.run_sync(prompt, deps=deps, usage_limits=UsageLimits(request_limit=20))
```

### No Executor Changes Needed

The existing `pipeline.py` code:
```python
run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
instruction = run_result.output
```
Works unchanged for tool-calling agents. `run_sync` handles the full tool-call loop internally and returns only when it has a final structured output.

## 5. Token Usage Tracking Across Tool-Call Iterations

### RunUsage (returned by RunResult.usage())

```python
# dataclass fields:
input_tokens: int = 0
output_tokens: int = 0
cache_write_tokens: int = 0
cache_read_tokens: int = 0
requests: int = 0          # total model round-trips (includes tool-call iterations)
tool_calls: int = 0        # total tool invocations across all iterations
details: dict[str, int]    # provider-specific details
```

**Critical**: `RunResult.usage()` **aggregates across ALL tool-call iterations**. If an agent makes 3 tool calls across 2 model round-trips, `usage.requests == 2` and `usage.tool_calls == 3`.

### Existing Code Compatibility

Our pipeline.py already does:
```python
_usage = run_result.usage()
if _usage:
    _call_input_tokens = _usage.input_tokens
    _call_output_tokens = _usage.output_tokens
```

This works correctly for tool-calling agents -- tokens from all iterations are summed. No changes needed.

### New Tracking Opportunity

We could additionally log `_usage.requests` and `_usage.tool_calls` for observability on tool-calling steps, but this is optional enhancement.

## 6. Additional Agent Constructor Params (Tool-Related)

| Param | Type | Default | Relevance |
|-------|------|---------|-----------|
| `tools` | `Sequence[Tool \| Callable]` | `()` | Primary -- pass tools here |
| `builtin_tools` | `Sequence[AbstractBuiltinTool]` | `()` | For pydantic-ai builtins (web search, etc) |
| `toolsets` | `Sequence[AbstractToolset]` | `None` | Advanced: composable tool groupings |
| `prepare_tools` | `ToolsPrepareFunc` | `None` | Dynamic tool filtering per-call |
| `end_strategy` | `'early' \| 'exhaustive'` | `'early'` | When to stop tool-call loop |
| `tool_timeout` | `float \| None` | `None` | Per-tool execution timeout |
| `max_concurrency` | `AnyConcurrencyLimit` | `None` | Parallel tool execution limit |

For initial implementation, only `tools` is needed. `end_strategy`, `tool_timeout`, and `usage_limits` are useful follow-up params.

## 7. Recommended Implementation for build_step_agent()

```python
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
    instrument: Any | None = None,
    tools: Sequence[Tool | Callable] | None = None,  # NEW
) -> Agent[StepDeps, Any]:

    agent_kwargs = dict(
        model=model,
        output_type=output_type,
        deps_type=StepDeps,
        name=step_name,
        retries=retries,
        model_settings=model_settings,
        defer_model_check=True,
        validation_context=lambda ctx: ctx.deps.validation_context,
    )
    if instrument is not None:
        agent_kwargs["instrument"] = instrument
    if tools:
        agent_kwargs["tools"] = list(tools)

    agent = Agent(**agent_kwargs)
    # ... rest unchanged (instructions, validators)
```

This is ~3 lines of change in the factory function.

## 8. Verified Assumptions from GAP Doc

| GAP Doc Claim | Verified? | Notes |
|---------------|-----------|-------|
| "Register via agent.tool(fn) or pass to constructor as tools=[...]" | Yes | Both work, constructor preferred for factory |
| "Tools receive RunContext[StepDeps]" | Yes | Auto-detected or explicit via Tool(fn, takes_ctx=True) |
| "agent.run_sync() handles tool-call loops internally" | Yes | Internal loop, transparent to caller |
| "Token usage from tool-call loops included in RunResult.usage()" | Yes | Aggregated: requests + tool_calls fields |
| "No executor changes needed" | Yes | run_sync return contract unchanged |
| "~30 lines in agent_builders.py" | Mostly | ~3-5 lines for tools param, more if adding end_strategy/timeout |
