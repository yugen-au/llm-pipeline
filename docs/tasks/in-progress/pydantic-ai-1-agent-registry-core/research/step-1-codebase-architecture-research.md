# Step 1: Codebase Architecture Research

## 1. PipelineDatabaseRegistry and __init_subclass__ Pattern

**File**: `llm_pipeline/registry.py`

The pattern to replicate for AgentRegistry:

```python
class PipelineDatabaseRegistry(ABC):
    MODELS: ClassVar[List[Type[SQLModel]]] = []

    def __init_subclass__(cls, models=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if models is not None:
            cls.MODELS = models
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineDatabaseRegistry:
            raise ValueError(...)

    @classmethod
    def get_models(cls) -> List[Type[SQLModel]]:
        if not cls.MODELS:
            raise ValueError(...)
        return cls.MODELS
```

**Usage pattern** (declarative class syntax):
```python
class MyRegistry(PipelineDatabaseRegistry, models=[Vendor, RateCard, Lane]):
    pass
```

**Key conventions**:
- ClassVar stores config set at class definition time
- `__init_subclass__` validates at definition time (fail-fast)
- Skip validation for intermediate bases (check `cls.__bases__[0]`)
- Skip validation for names starting with `_`
- Provide classmethod accessors (get_models)

**Same pattern used by**: PipelineStrategies (strategies=[...]), PipelineExtraction (model=...), PipelineTransformation (input_type=..., output_type=...)

---

## 2. StepDefinition in strategy.py

**File**: `llm_pipeline/strategy.py`

```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type            # Pydantic BaseModel subclass (the LLM output schema)
    action_after: Optional[str] = None
    extractions: List[Type['PipelineExtraction']] = field(default_factory=list)
    transformation: Optional[Type['PipelineTransformation']] = None
    context: Optional[Type] = None
```

**create_step(pipeline)** method:
1. Derives snake_case step_name from step_class name (remove 'Step' suffix)
2. Auto-discovers prompt keys from DB via strategy-level then step-level fallback
3. Instantiates step_class with system_instruction_key, user_prompt_key, instructions, pipeline
4. Attaches _extractions, _transformation, _context to step instance

**step_definition decorator** (step.py): Stores defaults on the class (INSTRUCTIONS, DEFAULT_SYSTEM_KEY, etc.) and adds create_definition() classmethod that returns a StepDefinition.

**For Task 1**: Need to add `agent_name: Optional[str] = None` field. Default should be derived from step_class name (snake_case without 'Step' suffix). This matches existing auto-derivation pattern.

---

## 3. LLMStep in step.py

**File**: `llm_pipeline/step.py`

```python
class LLMStep(ABC):
    def __init__(self, system_instruction_key, user_prompt_key, instructions, pipeline):
        self.system_instruction_key = system_instruction_key
        self.user_prompt_key = user_prompt_key
        self.instructions = instructions       # Type[BaseModel] - the output schema class
        self.pipeline = pipeline               # PipelineConfig reference

    @property
    def step_name(self) -> str:  # auto-derived snake_case from class name

    def create_llm_call(self, variables, system_instruction_key=None,
                        user_prompt_key=None, instructions=None, **extra_params) -> ExecuteLLMStepParams:
        # Builds dict with system_instruction_key, user_prompt_key, variables,
        # result_class, system_variables
        # Auto-resolves system variables via pipeline._variable_resolver

    @abstractmethod
    def prepare_calls(self) -> List[StepCallParams]:
        # Steps return list of {variables: ..., array_validation: ..., validation_context: ...}

    def process_instructions(self, instructions: List[Any]) -> Dict[str, Any]:
        # Optional: extract context from results

    def should_skip(self) -> bool:
        # Optional: skip step based on context

    def extract_data(self, instructions: List[Any]) -> None:
        # Delegates to _extractions classes, emits events

    def store_extractions(self, model_class, instances) -> None:
        # Delegates to pipeline.store_extractions()
```

**create_llm_call() return type**: `ExecuteLLMStepParams` TypedDict containing system_instruction_key, user_prompt_key, variables, result_class, system_variables, plus optional array_validation, validation_context.

**For Task 1**: Add get_agent(registry) -> Agent and build_user_prompt(variables) -> str methods. Deprecate create_llm_call() with warnings.warn(). These are additive -- existing flow continues to work.

---

## 4. Pipeline Execution Flow (pipeline.py)

**File**: `llm_pipeline/pipeline.py` (1187 lines)

**PipelineConfig.__init_subclass__**: Accepts registry= and strategies= class params, validates naming (Pipeline suffix, matching registry/strategies names).

**PipelineConfig.__init__**: Accepts engine, session, provider, variable_resolver, event_emitter, run_id. Creates PromptService internally during execute(). Validates REGISTRY and STRATEGIES exist. Builds execution order from strategy step definitions.

**execute() flow** (lines 443-856):
```
1. Validate provider exists
2. Create PromptService(self._real_session)
3. Parse consensus config
4. Validate input_data against INPUT_DATA schema
5. For each step_index:
   a. Select strategy via can_handle(context)
   b. step_def.create_step(pipeline=self) -> step instance
   c. Check should_skip()
   d. Hash step inputs for caching
   e. Check cache (if use_cache)
   f. If cached: load, process_instructions, extract (reconstruct), transform
   g. If fresh:
      - step.prepare_calls() -> call_params
      - For each call_params:
        - step.create_llm_call(**params) -> call_kwargs
        - call_kwargs["provider"] = self._provider
        - call_kwargs["prompt_service"] = prompt_service
        - execute_llm_step(**call_kwargs) -> instruction
      - Store instructions, process_instructions, transform, extract
      - Save step state
   h. Emit events throughout
```

**Key injection pattern**: Pipeline injects provider and prompt_service into call_kwargs dict before passing to execute_llm_step(). This is the seam where Task 2 replaces with agent.run_sync().

---

## 5. LLMProvider and GeminiProvider

**File**: `llm_pipeline/llm/provider.py`

```python
class LLMProvider(ABC):
    @abstractmethod
    def call_structured(
        self, prompt, system_instruction, result_class,
        max_retries=3, not_found_indicators=None, strict_types=True,
        array_validation=None, validation_context=None,
        event_emitter=None, step_name=None, run_id=None, pipeline_name=None,
        **kwargs
    ) -> LLMCallResult:
```

**File**: `llm_pipeline/llm/gemini.py`

GeminiProvider implements:
- Custom RateLimiter (sliding window)
- Manual JSON extraction from response text
- Manual schema validation via validate_structured_output()
- Manual array validation via validate_array_response()
- Manual Pydantic validation with context
- Custom retry loop with exponential backoff for rate limits
- Event emission for retries, rate limits, failures

**For pydantic-ai migration**: All of this validation/retry logic gets replaced by pydantic-ai's built-in structured output handling, ModelRetry, and retry mechanisms. GeminiProvider becomes unnecessary -- pydantic-ai handles model communication directly.

---

## 6. execute_llm_step() Function

**File**: `llm_pipeline/llm/executor.py`

```python
def execute_llm_step(
    system_instruction_key, user_prompt_key, variables, result_class,
    provider=None, prompt_service=None, context=None,
    array_validation=None, system_variables=None, validation_context=None,
    event_emitter=None, run_id=None, pipeline_name=None, step_name=None,
    call_index=0
) -> T:
```

Flow:
1. Convert PromptVariables to dicts
2. Get system instruction via prompt_service.get_system_prompt()
3. Get user prompt via prompt_service.get_user_prompt()
4. Emit LLMCallStarting event
5. Call provider.call_structured() -> LLMCallResult
6. Emit LLMCallCompleted event
7. If parsed is None -> result_class.create_failure()
8. Validate with Pydantic -> return result or create_failure()

**For Task 2**: This entire function gets replaced by agent.run_sync(). The prompt retrieval moves to @agent.instructions decorator (dynamic system prompts). User prompt is passed as the user_prompt arg to run_sync().

---

## 7. Supporting Types (types.py)

**File**: `llm_pipeline/types.py`

```python
@dataclass
class ArrayValidationConfig:
    input_array, match_field, filter_empty_inputs, allow_reordering, strip_number_prefix

@dataclass
class ValidationContext:
    data: Dict[str, Any]
    # dict-like access (get, __getitem__, __contains__, to_dict)

class StepCallParams(TypedDict, total=False):
    variables, array_validation, validation_context

class ExecuteLLMStepParams(StepCallParams):
    system_instruction_key, user_prompt_key, result_class, context, system_variables
```

---

## 8. PromptService

**File**: `llm_pipeline/prompts/service.py`

Key methods:
- `get_prompt(prompt_key, prompt_type, context, fallback)` - DB lookup
- `get_system_prompt(prompt_key, variables, variable_instance, context)` - template.format(**variables)
- `get_user_prompt(prompt_key, variables, variable_instance, context)` - template.format(**variables)
- `prompt_exists(prompt_key)` - bool check

PromptService takes a Session. Created fresh in pipeline.execute() from self._real_session.

**For pydantic-ai**: System prompt retrieval moves into @agent.instructions decorator (accessing PromptService via RunContext[StepDeps].deps.prompt_service). User prompt formatting may move into build_user_prompt() on LLMStep.

---

## 9. Current Exports (__init__.py)

**File**: `llm_pipeline/__init__.py`

Currently exports 24 symbols across categories:
- Core: PipelineConfig, LLMStep, LLMResultMixin, step_definition
- Strategy: PipelineStrategy, PipelineStrategies, StepDefinition
- Data: PipelineContext, PipelineInputData, PipelineExtraction, PipelineTransformation, PipelineDatabaseRegistry
- State: PipelineStepState, PipelineRunInstance, PipelineRun, PipelineEventRecord
- Events: PipelineEvent, PipelineEventEmitter, CompositeEmitter, LLMCallResult
- Handlers: LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, DEFAULT_LEVEL_MAP
- Types: ArrayValidationConfig, ValidationContext
- DB: init_pipeline_db
- Session: ReadOnlySession
- Introspection: PipelineIntrospector

**For Task 1**: Add AgentRegistry, StepDeps, build_step_agent (from new modules).

---

## 10. Naming Conventions

Strict enforcement throughout codebase:
| Type | Suffix | Validation Location |
|------|--------|-------------------|
| Pipeline | `Pipeline` | PipelineConfig.__init_subclass__ |
| Registry | `{Prefix}Registry` | PipelineConfig.__init_subclass__ |
| Strategies | `{Prefix}Strategies` | PipelineConfig.__init_subclass__ |
| Strategy | `Strategy` | PipelineStrategy.__init_subclass__ |
| Step | `Step` | step_definition decorator, LLMStep.step_name |
| Instructions | `{StepPrefix}Instructions` | step_definition decorator |
| Context | `{StepPrefix}Context` | step_definition decorator |
| Extraction | `Extraction` | PipelineExtraction.__init_subclass__ |
| Transformation | `{StepPrefix}Transformation` | step_definition decorator |

snake_case derivation uses double regex:
```python
re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
re.sub(r'([a-z\d])([A-Z])', r'\1_\2', name).lower()
```

---

## 11. Path Mapping (Task Description vs Codebase)

Task 1 references paths from the original logistics-intelligence project. Correct mappings for llm-pipeline:

| Task Reference | Correct llm-pipeline Path |
|---|---|
| logistics_intelligence/core/schemas/pipeline/agent_registry.py | llm_pipeline/agent_registry.py |
| logistics_intelligence/core/schemas/pipeline/agent_builders.py | llm_pipeline/agent_builders.py |
| schemas/pipeline/__init__.py | llm_pipeline/__init__.py |
| schemas/pydantic_models.py | llm_pipeline/types.py (no pydantic_models.py exists) |
| schemas/validation.py | llm_pipeline/llm/validation.py |

New files follow existing convention: top-level under llm_pipeline/ (like registry.py, strategy.py, step.py).

---

## 12. Integration Points for Agent Abstractions

Where new Agent abstractions connect to existing pipeline flow:

### AgentRegistry
- **Analogous to**: PipelineDatabaseRegistry (class-syntax registration)
- **Used by**: PipelineConfig (similar to REGISTRY ClassVar)
- **Purpose**: Map step names to Agent instances or Agent factories
- **Declaration**: `class MyAgentRegistry(AgentRegistry, agents={...})` or similar

### StepDeps (pydantic-ai dependency injection)
- **Contains**: session, pipeline_context, prompt_service, validation_context
- **Used via**: RunContext[StepDeps] in @agent.instructions and @agent.output_validator
- **Created in**: pipeline.execute() (where PromptService is currently created)

### get_agent() on LLMStep
- **Replaces**: create_llm_call() (for agent-based execution path)
- **Resolves**: step_name -> Agent from AgentRegistry
- **Used by**: pipeline.execute() in Task 2

### build_user_prompt() on LLMStep
- **Extracts**: user prompt construction from create_llm_call() and execute_llm_step()
- **Currently**: prompt_service.get_user_prompt(key, variables) happens in execute_llm_step()
- **After**: step.build_user_prompt(variables) returns formatted string for agent.run_sync()

---

## 13. Downstream Tasks (OUT OF SCOPE)

### Task 2: Rewrite Pipeline Executor (depends on Task 1)
- Replace execute_llm_step() calls with agent.run_sync() in pipeline.execute()
- Build StepDeps, handle RunResult.output
- Delete execute_llm_step(), call_gemini_with_structured_output(), format_schema_for_llm(), validate_structured_output(), validate_array_response()
- Delete RateLimiter
- Deprecate ExecuteLLMStepParams

### Task 3: Port Custom Validation (depends on Task 1 + 2)
- Migrate not_found_indicators and ArrayValidationConfig to @agent.output_validator
- Create validator factories
- Delete schemas/validation.py

### Task 6: Final Integration Testing (depends on all)
- End-to-end testing, cleanup, documentation

---

## 14. LLMCallResult Structure

**File**: `llm_pipeline/llm/result.py`

```python
@dataclass(frozen=True, slots=True)
class LLMCallResult:
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)
```

Has factory methods: `success()`, `failure()`. Properties: `is_success`, `is_failure`.

**For pydantic-ai**: Agent.run_sync() returns RunResult[T] with .output (typed), .usage() (token info). LLMCallResult may still be useful for event emission but the parsed dict pattern goes away -- pydantic-ai returns typed Pydantic models directly.

---

## 15. LLMResultMixin (Step Output Schema Base)

**File**: `llm_pipeline/step.py`

```python
class LLMResultMixin(BaseModel):
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0)
    notes: str | None = Field(default=None)

    @classmethod
    def create_failure(cls, reason: str, **safe_defaults):
        return cls(confidence_score=0.0, notes=f"Failed: {reason}", **safe_defaults)

    @classmethod
    def get_example(cls):
        # Returns instance from cls.example dict if defined
```

All LLM step instruction/result schemas inherit from this. The `example` class attribute provides schema examples for LLM prompting (used by format_schema_for_llm). In pydantic-ai, output_type= on Agent replaces the manual schema formatting.

---

## 16. VariableResolver Protocol

**File**: `llm_pipeline/prompts/variables.py`

```python
@runtime_checkable
class VariableResolver(Protocol):
    def resolve(self, prompt_key: str, prompt_type: str) -> Optional[Type[BaseModel]]:
```

Used by LLMStep.create_llm_call() to auto-instantiate system variable classes. Pipeline stores it as self._variable_resolver. This pattern may or may not continue in the agent-based flow depending on how @agent.instructions handles system prompt variable injection.

---

## 17. Event System Integration

The pipeline emits events at every stage (StepStarted, LLMCallStarting, LLMCallCompleted, etc.). Current flow:
1. Pipeline passes event_emitter into call_kwargs
2. execute_llm_step() emits LLMCallStarting/LLMCallCompleted
3. GeminiProvider emits LLMCallRetry/LLMCallRateLimited/LLMCallFailed

For pydantic-ai migration: Event emission needs to be preserved. pydantic-ai has its own instrumentation via `agent.instrument()` or manual hooks. The event emission in execute_llm_step() and GeminiProvider will need to be ported to pydantic-ai's lifecycle hooks or maintained separately.
