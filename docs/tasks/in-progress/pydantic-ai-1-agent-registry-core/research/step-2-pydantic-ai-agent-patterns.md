# Step 2: Pydantic AI Agent Patterns Research

## 1. Agent Class Overview (v1.0.5)

### Constructor Signature

```python
Agent(
    model: Model | KnownModelName | str | None = None,
    *,
    output_type: OutputSpec[OutputDataT] = str,           # Pydantic model for validated output
    instructions: Instructions[AgentDepsT] = None,        # Static or callable instructions
    system_prompt: str | Sequence[str] = (),              # Static system prompts
    deps_type: type[AgentDepsT] = NoneType,               # DI type for RunContext
    name: str | None = None,                              # Agent name (logging)
    model_settings: ModelSettings | None = None,          # temperature, max_tokens, etc.
    retries: int = 1,                                     # Default retries for tools/output
    validation_context: Any | Callable[[RunContext], Any] = None,  # Pydantic validation ctx
    output_retries: int | None = None,                    # Override retries for output only
    tools: Sequence[Tool | ToolFunc] = (),
    defer_model_check: bool = False,                      # Skip model env check until run
    end_strategy: EndStrategy = "early",
    instrument: InstrumentationSettings | bool | None = None,
)
```

### Key Parameters for llm-pipeline

| Parameter | Maps to Current | Notes |
|-----------|----------------|-------|
| `model` | `LLMProvider.model_name` | e.g., `'google-gla:gemini-2.0-flash-lite'` |
| `output_type` | `instructions` class (LLMResultMixin subclass) | Automatic Pydantic validation |
| `deps_type` | No equivalent (pipeline ref on step) | New `StepDeps` dataclass |
| `instructions` | `system_instruction_key` -> DB prompt | Use `@agent.instructions` decorator |
| `system_prompt` | Static system prompts | Can combine with dynamic instructions |
| `retries` | `max_retries` on provider | pydantic-ai handles retry loop |
| `model_settings` | Not exposed | temperature, max_tokens, top_p |
| `defer_model_check` | N/A | Set `True` for tests without API keys |
| `validation_context` | `ValidationContext` | Can be callable receiving `RunContext` |

### Execution Methods

```python
# Synchronous (matches current pipeline pattern)
result: RunResult[T] = agent.run_sync(
    user_prompt: str,
    *,
    deps: AgentDepsT = None,
    model: Model | str | None = None,         # Override model at runtime
    model_settings: ModelSettings | None = None,  # Override settings at runtime
    message_history: list[ModelMessage] | None = None,
)

# Async
result = await agent.run(user_prompt, deps=deps)

# Streaming
async with agent.run_stream(user_prompt, deps=deps) as response:
    async for text in response.stream_text():
        ...
```

**RunResult properties:**
- `result.output` - Validated Pydantic model instance (was `parsed` dict)
- `result.usage()` - `RunUsage(input_tokens=N, output_tokens=N, requests=N)`
- `result.all_messages()` - Full message history
- `result.new_messages()` - Messages from this run only

### Model Selection Precedence

```
run-time model_settings > agent-level model_settings > model-level defaults
```

Model can be overridden at `run_sync(model='...')`, allowing per-step model selection at runtime.


## 2. RunContext and Dependency Injection

### Pattern

```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

@dataclass
class StepDeps:
    session: Any                    # SQLModel Session
    pipeline_context: dict          # Current pipeline context
    prompt_service: Any             # PromptService instance
    event_emitter: Any | None       # PipelineEventEmitter
    run_id: str                     # Pipeline run identifier
    pipeline_name: str              # Pipeline name
    step_name: str                  # Current step name
    variable_resolver: Any | None   # VariableResolver instance

agent = Agent(
    'google-gla:gemini-2.0-flash-lite',
    deps_type=StepDeps,
    output_type=MyInstructions,
)

# RunContext[StepDeps] available in:
# - @agent.instructions
# - @agent.tool / @agent.tool_plain
# - @agent.output_validator

@agent.instructions
def system_prompt(ctx: RunContext[StepDeps]) -> str:
    return ctx.deps.prompt_service.get_system_prompt(
        prompt_key=ctx.deps.step_name,
        variables={...},
    )
```

### RunContext Fields

- `ctx.deps` - The StepDeps instance passed at `run_sync(deps=...)`
- `ctx.model` - Current model being used
- `ctx.usage` - Current usage stats
- `ctx.retry` - Current retry count (useful in validators)

### StepDeps Design for llm-pipeline

Based on downstream task requirements (Task 2: "Build StepDeps from session, pipeline_context, prompt_service"; Task 3: "accessing ArrayValidationConfig data via StepDeps"):

```python
@dataclass
class StepDeps:
    """Dependencies injected into pydantic-ai agents for pipeline steps.

    Compatible with RunContext[StepDeps] for use in @agent.instructions,
    @agent.tool, and @agent.output_validator decorators.
    """
    # Core pipeline deps
    session: Session                          # DB session for prompt queries
    pipeline_context: dict[str, Any]          # Current pipeline context dict
    prompt_service: PromptService             # Prompt retrieval service

    # Execution metadata
    run_id: str
    pipeline_name: str
    step_name: str

    # Optional deps
    event_emitter: PipelineEventEmitter | None = None
    variable_resolver: VariableResolver | None = None

    # Step-specific config (for validators, Task 3)
    array_validation: ArrayValidationConfig | None = None
    validation_context: ValidationContext | None = None
    not_found_indicators: list[str] | None = None
```


## 3. Dynamic Instruction Injection

### @agent.instructions Decorator

Three patterns supported:

```python
# 1. Static string (passed at constructor)
agent = Agent('model', instructions="You are a helpful assistant.")

# 2. Plain function (no deps)
@agent.instructions
def add_date() -> str:
    return f'The date is {date.today()}.'

# 3. Function with RunContext (dynamic, deps-aware)
@agent.instructions
def add_system_prompt(ctx: RunContext[StepDeps]) -> str:
    return ctx.deps.prompt_service.get_system_prompt(
        prompt_key=ctx.deps.step_name,
        variables=ctx.deps.system_variables,
    )
```

Multiple `@agent.instructions` decorators can be stacked. All are concatenated into the system prompt.

### Mapping to llm-pipeline's Prompt System

Current flow:
1. `step.system_instruction_key` -> `prompt_service.get_system_prompt(key, variables)` -> system instruction string
2. `step.user_prompt_key` -> `prompt_service.get_user_prompt(key, variables)` -> user prompt string

With pydantic-ai:
1. System prompt: `@agent.instructions` fetches from DB via `RunContext[StepDeps].deps.prompt_service`
2. User prompt: Rendered string passed directly to `agent.run_sync(user_prompt, deps=step_deps)`

```python
def build_step_agent(
    step_name: str,
    output_type: type[BaseModel],
    model: str | None = None,
    system_instruction_key: str | None = None,
    user_prompt_key: str | None = None,
    retries: int = 3,
    model_settings: ModelSettings | None = None,
) -> Agent[StepDeps, Any]:
    """Factory function to build a pydantic-ai Agent for a pipeline step."""

    agent = Agent(
        model=model,
        output_type=output_type,
        deps_type=StepDeps,
        name=step_name,
        retries=retries,
        model_settings=model_settings,
        defer_model_check=True,  # Allows testing without API keys
    )

    sys_key = system_instruction_key or step_name

    @agent.instructions
    def inject_system_prompt(ctx: RunContext[StepDeps]) -> str:
        """Fetch system prompt from DB and format with variables."""
        # Resolve system variables if variable_resolver available
        system_variables = None
        if ctx.deps.variable_resolver:
            var_class = ctx.deps.variable_resolver.resolve(sys_key, 'system')
            if var_class:
                system_variables = var_class()

        if system_variables:
            variables_dict = system_variables.model_dump() if hasattr(system_variables, 'model_dump') else system_variables
            return ctx.deps.prompt_service.get_system_prompt(
                prompt_key=sys_key,
                variables=variables_dict,
                variable_instance=system_variables,
            )
        else:
            return ctx.deps.prompt_service.get_prompt(
                prompt_key=sys_key,
                prompt_type='system',
            )

    return agent
```


## 4. Agent Result Types and Validation

### output_type with Pydantic Models

pydantic-ai validates output against `output_type` automatically:

```python
class MyInstructions(LLMResultMixin):
    table_type: str
    confidence_score: float
    notes: str | None = None

agent = Agent(
    'google-gla:gemini-2.0-flash-lite',
    output_type=MyInstructions,  # Automatic Pydantic validation
    retries=3,                    # Retries on validation failure
)

result = agent.run_sync("Analyze this table")
instruction: MyInstructions = result.output  # Type-safe, validated
```

**Key difference from current system:** pydantic-ai handles JSON extraction, parsing, and Pydantic validation internally. No need for:
- `format_schema_for_llm()` - pydantic-ai sends schema to model natively
- `validate_structured_output()` - pydantic-ai validates against output_type
- Manual JSON extraction from markdown code blocks
- Custom retry loops in GeminiProvider

### @agent.output_validator (Task 3 scope, documented here for context)

```python
from pydantic_ai import ModelRetry

@agent.output_validator
def validate_output(ctx: RunContext[StepDeps], output: MyInstructions) -> MyInstructions:
    if output.confidence_score < 0.1:
        raise ModelRetry("Confidence too low, please try again with more detail")
    return output
```

`ModelRetry` triggers automatic retry with the error message fed back to the model. This replaces custom validation + retry logic in GeminiProvider.


## 5. Agent Factory Function Pattern

### build_step_agent Design

```python
def build_step_agent(
    step_name: str,
    output_type: type[BaseModel],
    model: str | None = None,
    system_instruction_key: str | None = None,
    user_prompt_key: str | None = None,
    retries: int = 3,
    model_settings: ModelSettings | None = None,
    validators: list[Callable] | None = None,
) -> Agent[StepDeps, Any]:
    """
    Factory function to create a pydantic-ai Agent for a pipeline step.

    Args:
        step_name: Unique step identifier (e.g., 'table_type_detection')
        output_type: Pydantic model for validated output (LLMResultMixin subclass)
        model: Model string (e.g., 'google-gla:gemini-2.0-flash-lite').
               None means must be provided at run-time or via AgentRegistry default.
        system_instruction_key: DB prompt key for system instruction.
                                 Defaults to step_name.
        user_prompt_key: DB prompt key for user prompt template.
                          Used by caller to render user prompt before run_sync().
        retries: Max retries for output validation failures.
        model_settings: ModelSettings for temperature, max_tokens, etc.
        validators: Optional output validator functions (Task 3).

    Returns:
        Configured Agent[StepDeps, output_type] with dynamic instructions.
    """
```

### Integration with StepDefinition

```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type                                    # output_type for Agent
    action_after: str | None = None
    extractions: list[Type[PipelineExtraction]] = field(default_factory=list)
    transformation: Type[PipelineTransformation] | None = None
    context: Type | None = None

    # NEW: pydantic-ai agent (lazy-built)
    _agent: Agent | None = field(default=None, init=False, repr=False)

    @property
    def agent(self) -> Agent:
        """Get or build the pydantic-ai Agent for this step."""
        if self._agent is None:
            self._agent = build_step_agent(
                step_name=self.step_name,
                output_type=self.instructions,
                system_instruction_key=self.system_instruction_key,
                user_prompt_key=self.user_prompt_key,
            )
        return self._agent
```


## 6. AgentRegistry Pattern

### Design Options

**Option A: Dict-based registry (simple, recommended)**

```python
class AgentRegistry:
    """Registry mapping step names to pydantic-ai Agent instances."""

    def __init__(self):
        self._agents: dict[str, Agent[StepDeps, Any]] = {}
        self._default_model: str | None = None

    def register(self, step_name: str, agent: Agent) -> None:
        self._agents[step_name] = agent

    def get(self, step_name: str) -> Agent[StepDeps, Any]:
        if step_name not in self._agents:
            raise KeyError(f"No agent registered for step '{step_name}'")
        return self._agents[step_name]

    def build_and_register(
        self, step_name: str, output_type: type, **kwargs
    ) -> Agent:
        agent = build_step_agent(step_name, output_type, **kwargs)
        self.register(step_name, agent)
        return agent

    @classmethod
    def from_strategies(cls, strategies: list[PipelineStrategy], model: str | None = None) -> 'AgentRegistry':
        """Auto-build registry from pipeline strategies."""
        registry = cls()
        registry._default_model = model
        for strategy in strategies:
            for step_def in strategy.get_steps():
                step_name = step_def.step_name  # derived from step_class
                if step_name not in registry._agents:
                    registry.build_and_register(
                        step_name=step_name,
                        output_type=step_def.instructions,
                        model=model,
                        system_instruction_key=step_def.system_instruction_key,
                        user_prompt_key=step_def.user_prompt_key,
                    )
        return registry
```

**Option B: Integrated into PipelineConfig (lifecycle-managed)**

Agents are built during `PipelineConfig.__init__()` or lazily during `execute()`. The registry lives as `self._agent_registry` on the pipeline.

**Recommendation:** Option A with integration into PipelineConfig lifecycle. AgentRegistry is a standalone class but instantiated by PipelineConfig. This keeps the registry testable independently while pipeline manages lifecycle.


## 7. Model Selection and Provider Routing

### pydantic-ai Built-in Models

pydantic-ai supports these model strings natively:

| Provider | Format | Example |
|----------|--------|---------|
| Google Gemini | `google-gla:model-name` | `google-gla:gemini-2.0-flash-lite` |
| OpenAI | `openai:model-name` | `openai:gpt-4o` |
| Anthropic | `anthropic:model-name` | `anthropic:claude-sonnet-4-20250514` |
| Ollama (via OpenAI compat) | Custom `OpenAIChatModel` | See below |

### Replacing GeminiProvider

Current `GeminiProvider(model_name="gemini-2.0-flash-lite")` maps to:

```python
agent = Agent(
    'google-gla:gemini-2.0-flash-lite',
    output_type=MyInstructions,
    deps_type=StepDeps,
)
```

pydantic-ai internally handles:
- API key from `GEMINI_API_KEY` env var
- JSON structured output via native API
- Pydantic model validation
- Retry logic (including 429 rate limit backoff)
- Schema formatting

### ModelSettings Precedence

```python
# 1. Model-level defaults
from pydantic_ai.models.openai import OpenAIChatModel
model = OpenAIChatModel('gpt-4o', settings=ModelSettings(temperature=0.8))

# 2. Agent-level defaults (merges with model defaults)
agent = Agent(model, model_settings=ModelSettings(temperature=0.5))

# 3. Run-time override (highest priority)
result = agent.run_sync(prompt, model_settings=ModelSettings(temperature=0.0))
```

### Per-Step Model Override

```python
# Agent created with default model
agent = Agent('google-gla:gemini-2.0-flash-lite', ...)

# Override at runtime for specific step
result = agent.run_sync(
    user_prompt,
    deps=step_deps,
    model='google-gla:gemini-2.5-pro',  # Use different model for this step
)
```


## 8. Agent Lifecycle Management

### Creation Timing

Agents are lightweight and stateless between runs. Safe to create at init time:

```python
class PipelineConfig:
    def __init__(self, ...):
        # Build agents from strategies
        self._agent_registry = AgentRegistry.from_strategies(
            self._strategies,
            model=self._model_string,
        )
```

### Testing with defer_model_check

```python
agent = Agent(
    'google-gla:gemini-2.0-flash-lite',
    output_type=MyInstructions,
    defer_model_check=True,  # Won't check GEMINI_API_KEY until first run
)
```

For tests, use `PYDANTIC_AI_DEFER_MODEL_CHECK=True` env var (noted in Task 6).

### Agent Reuse

Agents are designed to be reused across runs. Same agent, different deps:

```python
agent = registry.get('table_type_detection')

# Run 1
result1 = agent.run_sync(prompt1, deps=deps_for_run1)

# Run 2 (different pipeline run)
result2 = agent.run_sync(prompt2, deps=deps_for_run2)
```


## 9. Deprecation Strategy for create_llm_call()

### Current Usage

`LLMStep.create_llm_call()` returns an `ExecuteLLMStepParams` dict consumed by `execute_llm_step()`.

### Deprecation Plan (Task 1 scope)

```python
import warnings

class LLMStep(ABC):
    def create_llm_call(self, variables, ...) -> 'ExecuteLLMStepParams':
        """DEPRECATED: Use agent.run_sync() via AgentRegistry instead."""
        warnings.warn(
            "create_llm_call() is deprecated. Use pydantic-ai Agent via "
            "AgentRegistry. Will be removed in v0.3.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        # ... existing implementation unchanged ...
```

Task 2 replaces `execute_llm_step(**call_kwargs)` with `agent.run_sync()`.
Task 6 removes the deprecated method entirely.


## 10. Key Mapping: Current -> pydantic-ai

| Current Component | pydantic-ai Replacement | Notes |
|---|---|---|
| `LLMProvider` (abstract) | Built-in model routing | Model string selects provider |
| `GeminiProvider` | `'google-gla:model'` | Native support |
| `execute_llm_step()` | `agent.run_sync()` | Task 2 scope |
| `LLMCallResult` | `RunResult` | `.output` instead of `.parsed` |
| `RateLimiter` | Built-in 429 retry | Automatic exponential backoff |
| `validate_structured_output()` | `output_type` validation | Automatic |
| `validate_array_response()` | `@agent.output_validator` | Task 3 scope |
| `check_not_found_response()` | `@agent.output_validator` | Task 3 scope |
| `format_schema_for_llm()` | Native structured output | Model-specific schema handling |
| `ValidationContext` | `validation_context` param or StepDeps | Passed via deps |
| `ArrayValidationConfig` | StepDeps field | Accessed in output_validator |
| `PromptService.get_system_prompt()` | `@agent.instructions` | Dynamic via RunContext |
| `PromptService.get_user_prompt()` | Caller renders, passes to `run_sync()` | User prompt is the run argument |


## 11. File Organization (Proposed)

```
llm_pipeline/
    agents/
        __init__.py          # exports AgentRegistry, StepDeps, build_step_agent
        registry.py          # AgentRegistry class
        deps.py              # StepDeps dataclass
        builder.py           # build_step_agent factory
    step.py                  # LLMStep (deprecation warnings on create_llm_call)
    strategy.py              # StepDefinition (agent property added)
```

Or simpler flat structure:

```
llm_pipeline/
    agents.py                # AgentRegistry, StepDeps, build_step_agent (all in one)
```


## 12. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| pydantic-ai model string format changes | Use `defer_model_check=True`, centralize model strings in config |
| Prompt rendering mismatch (current vs pydantic-ai) | @agent.instructions uses same PromptService, identical output |
| Breaking existing pipelines during migration | Deprecation warnings in Task 1, actual replacement in Task 2 |
| Test suite relies on LLMProvider mock | `defer_model_check=True` + pydantic-ai TestModel for unit tests |
| Rate limiting behavior difference | pydantic-ai handles 429 automatically; may need custom backoff config via ModelSettings |
| Multiple instructions decorators ordering | pydantic-ai concatenates all; document expected order |
