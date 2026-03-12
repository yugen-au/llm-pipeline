# Step 3: Pydantic-AI Agent System Research

## Scope

How pydantic-ai Agent system is integrated in this codebase. AgentRegistry, agent_builders.py, LLMStep integration, structured outputs, prompt injection, model configuration, streaming/events, ReadOnlySession.

## Source Files Reviewed

| File | Purpose |
|------|---------|
| `llm_pipeline/agent_registry.py` | AgentRegistry base class |
| `llm_pipeline/agent_builders.py` | StepDeps dataclass + build_step_agent factory |
| `llm_pipeline/step.py` | LLMStep, LLMResultMixin, step_definition |
| `llm_pipeline/pipeline.py` | PipelineConfig.execute() -- agent creation + run flow |
| `llm_pipeline/strategy.py` | StepDefinition, PipelineStrategy, PipelineStrategies |
| `llm_pipeline/context.py` | PipelineContext, PipelineInputData |
| `llm_pipeline/prompts/service.py` | PromptService (prompt retrieval + template rendering) |
| `llm_pipeline/prompts/loader.py` | YAML prompt loading + DB sync |
| `llm_pipeline/prompts/variables.py` | VariableResolver protocol |
| `llm_pipeline/db/prompt.py` | Prompt SQLModel (prompt_key, prompt_type, content) |
| `llm_pipeline/validators.py` | not_found_validator, array_length_validator factories |
| `llm_pipeline/types.py` | StepCallParams, ArrayValidationConfig, ValidationContext |
| `llm_pipeline/registry.py` | PipelineDatabaseRegistry base |
| `llm_pipeline/extraction.py` | PipelineExtraction base |
| `llm_pipeline/session/readonly.py` | ReadOnlySession wrapper |
| `llm_pipeline/events/emitter.py` | PipelineEventEmitter protocol, CompositeEmitter |
| `llm_pipeline/events/handlers.py` | LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler |
| `llm_pipeline/events/models.py` | PipelineEventRecord persistence model |
| `llm_pipeline/ui/app.py` | create_app(), _discover_pipelines(), _make_pipeline_factory() |
| `llm_pipeline/ui/routes/runs.py` | trigger_run endpoint (factory invocation + background exec) |
| `llm_pipeline/ui/routes/websocket.py` | ConnectionManager, WebSocket streaming endpoints |
| `llm_pipeline/ui/bridge.py` | UIBridge (sync event -> WebSocket adapter) |
| `llm_pipeline/introspection.py` | PipelineIntrospector (class-level metadata) |
| `tests/test_agent_registry_core.py` | Tests for registry, builders, step methods |

---

## 1. AgentRegistry Pattern

**File:** `llm_pipeline/agent_registry.py`

AgentRegistry is the single source of truth mapping step names to their structured output types. It uses the `__init_subclass__` pattern with a class-call `agents={}` parameter.

### Class Definition

```python
class AgentRegistry(ABC):
    AGENTS: ClassVar[dict[str, Type[BaseModel]]] = {}

    def __init_subclass__(cls, agents=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if agents is not None:
            cls.AGENTS = agents
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is AgentRegistry:
            raise ValueError(...)
```

### Usage Pattern

```python
class TextAnalyzerAgentRegistry(AgentRegistry, agents={
    "sentiment_analysis": SentimentAnalysis,
    "topic_extraction": TopicExtractionResult,
    "summary": SummaryResult,
}):
    pass
```

### Key Methods

- `get_output_type(step_name: str) -> Type[BaseModel]` -- raises KeyError if step not registered

### Naming Convention

- Registry name must be `{PipelinePrefix}AgentRegistry` (e.g., TextAnalyzerAgentRegistry for TextAnalyzerPipeline)
- Validated in PipelineConfig.__init_subclass__ (pipeline.py L138-144)

### Registration on PipelineConfig

```python
class TextAnalyzerPipeline(PipelineConfig,
    registry=TextAnalyzerRegistry,
    strategies=TextAnalyzerStrategies,
    agent_registry=TextAnalyzerAgentRegistry,
):
    pass
```

Stored as `cls.AGENT_REGISTRY` ClassVar. Checked at execute() time -- raises ValueError if None.

---

## 2. build_step_agent Factory

**File:** `llm_pipeline/agent_builders.py`

### Signature

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
) -> Agent[StepDeps, Any]:
```

### Agent Construction

```python
agent_kwargs = dict(
    model=model,
    output_type=output_type,
    deps_type=StepDeps,
    name=step_name,
    retries=retries,
    model_settings=model_settings,
    defer_model_check=True,        # model resolved at run_sync time
    validation_context=lambda ctx: ctx.deps.validation_context,
)
if instrument is not None:
    agent_kwargs["instrument"] = instrument
agent = Agent(**agent_kwargs)
```

Key: `defer_model_check=True` means the Agent is constructed without requiring a model string. The actual model is passed at `agent.run_sync(model=self._model)` call time.

### Dynamic System Prompt Injection

```python
@agent.instructions
def _inject_system_prompt(ctx: RunContext[StepDeps]) -> str:
    if ctx.deps.variable_resolver:
        var_class = ctx.deps.variable_resolver.resolve(sys_key, 'system')
        if var_class:
            system_variables = var_class()
            variables_dict = system_variables.model_dump() if hasattr(system_variables, 'model_dump') else system_variables
            return ctx.deps.prompt_service.get_system_prompt(
                prompt_key=sys_key, variables=variables_dict, variable_instance=system_variables,
            )
    return ctx.deps.prompt_service.get_prompt(prompt_key=sys_key, prompt_type='system')
```

System prompt is fetched from DB at runtime via `PromptService`. For the demo pipeline with no VariableResolver, the simple path is taken: `get_prompt(prompt_key, prompt_type='system')`.

### Output Validators

Registered via `agent.output_validator(v)` for each validator in the list. In pipeline.execute(), two validators are always registered:
- `not_found_validator(step_def.not_found_indicators)` -- checks for LLM evasion phrases
- `array_length_validator()` -- validates array lengths (no-op when config is None)

For the demo pipeline, these validators will pass through harmlessly (not_found checks strings, array_length requires explicit config).

---

## 3. StepDeps Dependency Injection

**File:** `llm_pipeline/agent_builders.py`

```python
@dataclass
class StepDeps:
    session: Any                          # ReadOnlySession
    pipeline_context: dict[str, Any]      # pipeline._context
    prompt_service: Any                   # PromptService
    run_id: str
    pipeline_name: str
    step_name: str
    event_emitter: Any | None = None      # PipelineEventEmitter
    variable_resolver: Any | None = None  # VariableResolver
    array_validation: Any | None = None   # ArrayValidationConfig
    validation_context: Any | None = None # ValidationContext
```

Created per-call in pipeline.execute() (one StepDeps per LLM call, not per step):

```python
step_deps = StepDeps(
    session=self.session,                   # ReadOnlySession
    pipeline_context=self._context,
    prompt_service=prompt_service,
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    event_emitter=self._event_emitter,
    variable_resolver=self._variable_resolver,
    array_validation=params.get("array_validation"),
    validation_context=params.get("validation_context"),
)
```

For TextAnalyzer: no variable_resolver, no array_validation, no validation_context needed (simple structured outputs).

---

## 4. LLMStep Integration with Agents

**File:** `llm_pipeline/step.py`

### Abstract Base

```python
class LLMStep(ABC):
    def __init__(self, system_instruction_key, user_prompt_key, instructions, pipeline):
        # stores all four; pipeline gives access to context, data, session
```

### Key Methods

| Method | Purpose | TextAnalyzer Relevance |
|--------|---------|----------------------|
| `step_name` (property) | Auto-derived snake_case from class name | SentimentAnalysisStep -> "sentiment_analysis" |
| `get_agent(registry)` | Looks up output_type from AgentRegistry | Returns output BaseModel type |
| `build_user_prompt(variables, prompt_service)` | Renders user prompt template | Fills {text}, {sentiment}, {primary_topic} |
| `prepare_calls()` | Returns List[StepCallParams] with template variables | Must return variables dict for each LLM call |
| `process_instructions(instructions)` | Extract context values from results | Returns dict merged into pipeline.context |
| `should_skip()` | Optional skip logic | Default False, not needed for demo |
| `extract_data(instructions)` | Runs PipelineExtraction classes | TopicExtractionStep needs this for Topics |
| `log_instructions(instructions)` | Optional logging | Default no-op |

### get_agent() Implementation

```python
def get_agent(self, registry: 'AgentRegistry') -> type:
    agent_name = getattr(self, '_agent_name', None) or self.step_name
    return registry.get_output_type(agent_name)
```

Returns the BaseModel **type** (not an Agent instance). The Agent is built in pipeline.execute() via build_step_agent.

### prepare_calls() Contract

Must return `List[StepCallParams]`:
```python
class StepCallParams(TypedDict, total=False):
    variables: Any                              # dict or Pydantic model for template vars
    array_validation: Optional[Any]             # ArrayValidationConfig
    validation_context: Optional[Any]           # ValidationContext
```

For TextAnalyzer, each step returns one call (single text analysis), so `[{"variables": {...}}]`.

### build_user_prompt()

```python
def build_user_prompt(self, variables, prompt_service, context=None):
    variable_instance = variables
    if hasattr(variables, 'model_dump'):
        variables = variables.model_dump()
    return prompt_service.get_user_prompt(self.user_prompt_key, variables=variables, ...)
```

Fetches user prompt template from DB, applies `template.format(**variables)`.

---

## 5. Structured Output Schemas

### LLMResultMixin

```python
class LLMResultMixin(BaseModel):
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0)
    notes: str | None = Field(default=None)

    @classmethod
    def create_failure(cls, reason: str, **safe_defaults):
        return cls(confidence_score=0.0, notes=f"Failed: {reason}", **safe_defaults)
```

Used by `pipeline.execute()` on `UnexpectedModelBehavior`: `instruction = output_type.create_failure(str(exc))`.

### For TextAnalyzer

Each step output type should inherit LLMResultMixin to support create_failure():

```python
class SentimentAnalysis(LLMResultMixin):
    sentiment: str       # e.g., "positive", "negative", "neutral"
    explanation: str

class TopicExtractionResult(LLMResultMixin):
    topics: list[TopicItem]   # list of extracted topics

class SummaryResult(LLMResultMixin):
    summary: str
```

The `confidence_score` and `notes` fields are inherited from LLMResultMixin. The `create_failure()` classmethod requires that all non-default fields have safe defaults or be passed via `**safe_defaults`.

### Output Type Registration

Output types are plain Pydantic BaseModel subclasses (or LLMResultMixin subclasses). They are registered in AgentRegistry and pydantic-ai validates the LLM response against them automatically.

---

## 6. Pipeline.execute() Agent Flow (Complete)

**File:** `llm_pipeline/pipeline.py` L455-955

Step-by-step for each pipeline step (non-cached path):

```
1. step_def.create_step(pipeline)           -> LLMStep instance with prompts resolved
2. step.prepare_calls()                     -> List[StepCallParams]
3. output_type = step.get_agent(AGENT_REGISTRY) -> BaseModel type
4. build validators (not_found + array_length)
5. agent = build_step_agent(step_name, output_type, validators, instrument)
6. For each call_params:
   a. step_deps = StepDeps(session, context, prompt_service, ...)
   b. user_prompt = step.build_user_prompt(params["variables"], prompt_service)
   c. run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
   d. instruction = run_result.output    <- structured Pydantic model
7. self._instructions[step.step_name] = [instruction, ...]
8. new_context = step.process_instructions(instructions)
9. Merge context into self._context
10. Run transformations (if any)
11. step.extract_data(instructions)          <- PipelineExtraction persistence
12. Save step state to DB
```

Key: model is passed at `agent.run_sync(model=self._model)`, not at Agent construction. This allows `defer_model_check=True`.

---

## 7. Prompt System

### Prompt Model (DB)

```python
class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"
    prompt_key: str           # e.g., "sentiment_analysis"
    prompt_name: str          # display name
    prompt_type: str          # "system" or "user"
    content: str              # template with {variable} placeholders
    required_variables: Optional[List[str]]  # auto-extracted from content
    # unique constraint: (prompt_key, prompt_type)
```

### PromptService

```python
prompt_service.get_prompt(prompt_key, prompt_type='system')      # raw template
prompt_service.get_system_prompt(prompt_key, variables, ...)     # formatted
prompt_service.get_user_prompt(prompt_key, variables, ...)       # formatted
```

Template rendering: `template.format(**variables)` -- standard Python string formatting.

### seed_prompts Pattern

For TextAnalyzerPipeline, seed_prompts(engine) classmethod should:
1. Create Session(engine)
2. For each prompt (system + user for each step):
   - Check if prompt already exists (by prompt_key + prompt_type)
   - Insert if not exists (idempotent)
3. Commit and close session

Prompt keys follow step_name convention:
- `sentiment_analysis` (system) + `sentiment_analysis` (user)
- `topic_extraction` (system) + `topic_extraction` (user)
- `summary` (system) + `summary` (user)

### Template Variables

User prompts contain `{variable}` placeholders filled by prepare_calls():
- Sentiment: `{text}` -- the input text
- Topic: `{text}` -- the input text (may also use `{sentiment}` from context)
- Summary: `{text}`, `{sentiment}`, `{primary_topic}` -- from input + previous step context

System prompts are fetched via @agent.instructions decorator. For simple cases (no VariableResolver), they are returned as-is from DB.

---

## 8. Model Configuration and Override

### Resolution Chain

1. `PipelineConfig.__init__(model=...)` -- stored as `self._model`
2. In app.py: `_make_pipeline_factory(cls, model)` captures model from `create_app(default_model=...)` or `LLM_PIPELINE_MODEL` env var
3. In `trigger_run`: factory is called with model already captured in closure
4. At call time: `agent.run_sync(user_prompt, deps=step_deps, model=self._model)`

### Model String Format

pydantic-ai model strings: `"google-gla:gemini-2.0-flash-lite"`, `"openai:gpt-4o"`, etc. The `model` param flows through to pydantic-ai's model resolution.

### Default for Demo

Task spec: `google-gla:gemini-2.0-flash-lite`. Overridden by CLI `--model` flag or `LLM_PIPELINE_MODEL` env var.

---

## 9. WebSocket Event Streaming

### Architecture

```
POST /api/runs -> trigger_run()
  |
  v
BackgroundTasks.add_task(run_pipeline)
  |
  v
factory(run_id, engine, event_emitter=UIBridge) -> pipeline
pipeline.execute() -> emits PipelineEvent subclasses via self._emit()
  |
  v
UIBridge.emit(event) -> ConnectionManager.broadcast_to_run(run_id, event.to_dict())
  |
  v
Queue.put_nowait(event_data) -> per-client queues
  |
  v
WebSocket endpoint: /ws/runs/{run_id} -> _stream_events() reads from queue
```

### Event Types Emitted by execute()

Pipeline-level: PipelineStarted, PipelineCompleted, PipelineError
Step-level: StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
LLM-level: LLMCallPrepared, LLMCallStarting, LLMCallCompleted
Extraction: ExtractionStarting, ExtractionCompleted, ExtractionError
Context: InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved
Transformation: TransformationStarting, TransformationCompleted
Cache: CacheLookup, CacheHit, CacheMiss, CacheReconstruction

All events are auto-emitted by pipeline.execute() -- no custom event code needed in TextAnalyzer steps.

### UIBridge

```python
class UIBridge:
    def emit(self, event: PipelineEvent) -> None:
        self._manager.broadcast_to_run(self.run_id, event.to_dict())
        if isinstance(event, (PipelineCompleted, PipelineError)):
            self.complete()

    def complete(self) -> None:
        if not self._completed:
            self._completed = True
            self._manager.signal_run_complete(self.run_id)
```

Terminal events auto-signal completion. Also called in trigger_run's `finally` block as safety net.

---

## 10. ReadOnlySession

**File:** `llm_pipeline/session/readonly.py`

Wraps SQLModel Session. Allows: query, exec, get, execute, scalar, scalars. Blocks: add, add_all, delete, flush, commit, merge, refresh, expire, expunge.

Steps receive `pipeline.session` (ReadOnlySession) for safe DB reads. The real session (`pipeline._real_session`) is used internally by extract_data() and save().

For TextAnalyzer: steps can read prompts/context from DB but cannot write. Topic extraction writes happen through PipelineExtraction.extract() -> pipeline._real_session.add().

---

## 11. Context Passing Between Steps

### Mechanism

1. Step.process_instructions(instructions) returns a dict (or PipelineContext subclass instance via model_dump)
2. Pipeline._validate_and_merge_context(step, new_context) merges into pipeline._context
3. Subsequent steps access pipeline._context in prepare_calls() via self.pipeline.context

### For TextAnalyzer

```
SentimentAnalysisStep.process_instructions():
  -> {"sentiment": "positive", "sentiment_confidence": 0.95}

TopicExtractionStep.process_instructions():
  -> {"primary_topic": "technology", "topics": [...]}

SummaryStep.prepare_calls():
  -> [{"variables": {
      "text": self.pipeline.validated_input.text,
      "sentiment": self.pipeline.context["sentiment"],
      "primary_topic": self.pipeline.context["primary_topic"],
  }}]
```

### PipelineContext Subclasses (Optional)

```python
class SentimentAnalysisContext(PipelineContext):
    sentiment: str
    sentiment_confidence: float
```

The naming convention `{StepPrefix}Context` is enforced by step_definition decorator. process_instructions() can return either a dict or a PipelineContext instance.

---

## 12. PipelineExtraction for Topic Persistence

**File:** `llm_pipeline/extraction.py`

### Pattern

```python
class TopicExtraction(PipelineExtraction, model=Topic):
    def extract(self, instructions: List[TopicExtractionResult]) -> List[Topic]:
        # Convert LLM result topics into Topic SQLModel instances
        topics = []
        for topic_item in instructions[0].topics:
            topics.append(Topic(name=topic_item.name, ...))
        return topics
```

### Flow in pipeline.execute()

```python
step.extract_data(instructions)
  -> for extraction_class in step._extractions:
      extraction = extraction_class(self.pipeline)
      instances = extraction.extract(instructions)
      self.store_extractions(extraction.MODEL, instances)
      for instance in instances:
          self.pipeline._real_session.add(instance)
      self.pipeline._real_session.flush()
```

Instances are added via _real_session (bypassing ReadOnlySession). save() later commits them.

### Topic SQLModel

```python
class Topic(SQLModel, table=True):
    __tablename__ = "demo_topics"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    # ... additional fields
```

Must be registered in PipelineDatabaseRegistry:
```python
class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    pass
```

---

## 13. step_definition Decorator

**File:** `llm_pipeline/step.py`

```python
@step_definition(
    instructions=SentimentAnalysisInstructions,
    default_system_key="sentiment_analysis",
    default_user_key="sentiment_analysis",
    context=SentimentAnalysisContext,
)
class SentimentAnalysisStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {"text": self.pipeline.validated_input.text}}]

    def process_instructions(self, instructions):
        result = instructions[0]
        return {"sentiment": result.sentiment, "sentiment_confidence": result.confidence_score}
```

### Naming Conventions Enforced

- Step class must end with 'Step': `SentimentAnalysisStep`
- Instructions class must be `{StepPrefix}Instructions`: `SentimentAnalysisInstructions`
- Transformation class (if any) must be `{StepPrefix}Transformation`
- Context class (if any) must be `{StepPrefix}Context`

### create_definition() Auto-generated

The decorator attaches `create_definition()` classmethod that returns a StepDefinition for use in strategy.get_steps().

---

## 14. Complete TextAnalyzer Pipeline Skeleton

Based on all patterns discovered:

### Required Components

| Component | Naming | Purpose |
|-----------|--------|---------|
| TextAnalyzerPipeline | PipelineConfig subclass | Pipeline orchestrator |
| TextAnalyzerRegistry | PipelineDatabaseRegistry | Registers Topic model |
| TextAnalyzerStrategies | PipelineStrategies | Declares strategies |
| TextAnalyzerAgentRegistry | AgentRegistry | Maps step -> output type |
| DefaultStrategy | PipelineStrategy | Single strategy (always handles) |
| SentimentAnalysisStep | LLMStep | Step 1 |
| TopicExtractionStep | LLMStep | Step 2 |
| SummaryStep | LLMStep | Step 3 |
| SentimentAnalysis | LLMResultMixin | Output for step 1 |
| TopicExtractionResult | LLMResultMixin | Output for step 2 (wraps Topic list) |
| SummaryResult | LLMResultMixin | Output for step 3 |
| Topic | SQLModel | Persisted topic model |
| TopicExtraction | PipelineExtraction | Converts LLM topics to Topic SQLModel |
| TextAnalyzerInputData | PipelineInputData | Input schema ({text: str}) |
| seed_prompts(engine) | classmethod | Seeds 6 prompts (3 system + 3 user) |

### Entry Point

```toml
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
```

### Context Flow

```
Input: {"text": "Some text to analyze"}
  |
  v
SentimentAnalysisStep:
  prepare_calls() -> [{"variables": {"text": input.text}}]
  agent output -> SentimentAnalysis(sentiment="positive", confidence_score=0.92, explanation="...")
  process_instructions() -> {"sentiment": "positive", "sentiment_confidence": 0.92, "explanation": "..."}
  |
  v
TopicExtractionStep:
  prepare_calls() -> [{"variables": {"text": input.text}}]
  agent output -> TopicExtractionResult(topics=[TopicItem(name="...", relevance=0.9), ...])
  process_instructions() -> {"primary_topic": topics[0].name, "topics": [...]}
  extract_data() -> TopicExtraction persists Topic instances to demo_topics table
  |
  v
SummaryStep:
  prepare_calls() -> [{"variables": {"text": input.text, "sentiment": ctx["sentiment"], "primary_topic": ctx["primary_topic"]}}]
  agent output -> SummaryResult(summary="...")
  process_instructions() -> {"summary": "..."}
```

---

## 15. Upstream Task 1 Deviations

From task 1 SUMMARY.md:

1. Factory closure accepts `**kwargs` -- `trigger_run` passes `input_data=body.input_data` as kwarg. The `**kwargs` absorbs it. TextAnalyzer factory will receive this same pattern.
2. HTTP 422 (not 400) for missing model -- resolved by CEO decision.
3. No entry points declared yet -- task 3 will add the first.
4. PipelineIntrospector naming bug (single vs double regex) -- not blocking; entry point name is used as registry key.

No deviations affect TextAnalyzer implementation.
