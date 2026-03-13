# Codebase Architecture Research: TextAnalyzerPipeline Demo

## 1. PipelineConfig Subclassing

### Location
`llm_pipeline/pipeline.py` - `PipelineConfig(ABC)` class

### Pattern
```python
class TextAnalyzerPipeline(
    PipelineConfig,
    registry=TextAnalyzerRegistry,
    strategies=TextAnalyzerStrategies,
    agent_registry=TextAnalyzerAgentRegistry,
):
    INPUT_DATA = TextAnalyzerInputData  # ClassVar, optional
```

### Naming Enforcement (pipeline.py L112-151)
- Class must end with `"Pipeline"` suffix
- `registry` name must be `{Prefix}Registry` (e.g. `TextAnalyzerRegistry`)
- `strategies` name must be `{Prefix}Strategies` (e.g. `TextAnalyzerStrategies`)
- `agent_registry` name must be `{Prefix}AgentRegistry` (e.g. `TextAnalyzerAgentRegistry`)
- `INPUT_DATA` validated as `PipelineInputData` subclass if set

### Constructor Signature (pipeline.py L161-171)
```python
def __init__(self, model: str, strategies=None, session=None, engine=None,
             variable_resolver=None, event_emitter=None, run_id=None,
             instrumentation_settings=None)
```
- `model`: pydantic-ai model string (required)
- `engine`: SQLAlchemy Engine (auto-SQLite if omitted)
- `event_emitter`: PipelineEventEmitter for WebSocket streaming
- `run_id`: UUID string (auto-generated if omitted)

### Factory Pattern (app.py L24-46)
`_make_pipeline_factory(cls, model)` creates a closure matching trigger_run's call signature:
```python
factory(run_id=run_id, engine=engine, event_emitter=bridge, **kwargs)
```

## 2. LLMStep and step_definition

### Location
`llm_pipeline/step.py`

### LLMStep ABC (step.py L186-348)
Abstract base class. Key interface:
- `__init__(system_instruction_key, user_prompt_key, instructions, pipeline)` - receives pipeline ref
- `step_name` property - auto-derived from class name via `to_snake_case(ClassName, strip_suffix="Step")`
- `prepare_calls() -> List[StepCallParams]` - **ABSTRACT**, must return list of dicts with `variables` key
- `process_instructions(instructions) -> dict | PipelineContext` - extracts derived context values
- `should_skip() -> bool` - optional, defaults False
- `log_instructions(instructions) -> None` - optional console logging
- `extract_data(instructions)` - auto-delegates to registered extraction classes
- `build_user_prompt(variables, prompt_service)` - builds user prompt from template + variables

### step_definition Decorator (step.py L34-131)
```python
@step_definition(
    instructions=SentimentAnalysisInstructions,
    default_system_key="sentiment_analysis",  # or None for auto-discovery
    default_user_key="sentiment_analysis",     # or None for auto-discovery
    default_extractions=[],                    # optional extraction classes
    context=SentimentAnalysisContext,           # optional PipelineContext subclass
)
class SentimentAnalysisStep(LLMStep):
    ...
```

### Naming Enforcement (step.py L56-84)
- Step class must end with `"Step"`
- Instructions class must be `{StepPrefix}Instructions`
- Context class must be `{StepPrefix}Context`
- Transformation class must be `{StepPrefix}Transformation` (if used)

### StepCallParams
Defined in `llm_pipeline/types.py` as `TypeAlias = Dict[str, Any]`. Each dict typically contains:
- `variables`: dict of template variables for user prompt
- `array_validation`: optional ArrayValidationConfig
- `validation_context`: optional ValidationContext

## 3. PipelineStrategy and PipelineStrategies

### Location
`llm_pipeline/strategy.py`

### PipelineStrategy ABC (strategy.py L146-255)
```python
class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return True  # always applies

    def get_steps(self) -> List[StepDefinition]:
        return [
            SentimentAnalysisStep.create_definition(),
            TopicExtractionStep.create_definition(),
            SummaryStep.create_definition(),
        ]
```

### Naming Convention
- Must end with `"Strategy"` suffix
- `NAME` auto-generated as snake_case (e.g. `DefaultStrategy` -> `"default"`)
- `DISPLAY_NAME` auto-generated as title case (e.g. `"Default"`)

### PipelineStrategies (strategy.py L258-335)
```python
class TextAnalyzerStrategies(PipelineStrategies, strategies=[DefaultStrategy]):
    pass
```

### Execution Flow (pipeline.py L523-548)
Pipeline iterates step indices. For each index, finds first strategy where `can_handle(context)` returns True and has a step at that index. For a single-strategy demo, this is straightforward linear execution.

## 4. PipelineContext for Inter-Step Data Passing

### Location
`llm_pipeline/context.py`

### Pattern
```python
class SentimentAnalysisContext(PipelineContext):
    sentiment: str
    sentiment_score: float

class TopicExtractionContext(PipelineContext):
    primary_topic: str
    topics: list[str]
```

### How Context Flows (pipeline.py L383-413)
1. `step.process_instructions(instructions)` returns a `PipelineContext` subclass instance
2. `_validate_and_merge_context()` validates type, calls `model_dump()`, merges into `pipeline._context`
3. Downstream steps access via `self.pipeline.context['sentiment']`

### PipelineInputData (context.py L36-41)
```python
class TextAnalyzerInputData(PipelineInputData):
    text: str
```
- Set as `INPUT_DATA` ClassVar on PipelineConfig subclass
- Validated in `execute()` (pipeline.py L484-499) via `model_validate(input_data)`
- Accessible via `self.pipeline.validated_input.text`

## 5. Prompt Seeding Pattern

### Contract
`seed_prompts(engine)` classmethod on PipelineConfig subclass. Called by `_discover_pipelines()` (app.py L85-93) after registration. Failure logged as warning, does not unregister pipeline.

### DB Model: Prompt (db/prompt.py)
```python
class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"
    prompt_key: str          # e.g. "sentiment_analysis"
    prompt_name: str         # e.g. "Sentiment Analysis System Prompt"
    prompt_type: str         # "system" or "user"
    category: Optional[str]  # e.g. "text_analyzer"
    step_name: Optional[str] # e.g. "sentiment_analysis"
    content: str             # template with {variable} placeholders
    required_variables: Optional[List[str]]  # auto-extracted from content
    version: str = "1.0"
    is_active: bool = True
```
**Unique constraint**: `(prompt_key, prompt_type)` via `uq_prompts_key_type`

### Idempotent Insertion Pattern
```python
@classmethod
def seed_prompts(cls, engine):
    from sqlmodel import Session, select
    from llm_pipeline.db.prompt import Prompt
    with Session(engine) as session:
        for prompt_data in PROMPTS:
            existing = session.exec(select(Prompt).where(
                Prompt.prompt_key == prompt_data["prompt_key"],
                Prompt.prompt_type == prompt_data["prompt_type"],
            )).first()
            if existing is None:
                session.add(Prompt(**prompt_data))
        session.commit()
```

### Prompt Key Convention
- System: `prompt_key="sentiment_analysis"`, `prompt_type="system"`
- User: `prompt_key="sentiment_analysis"`, `prompt_type="user"`
- Auto-discovery (strategy.py L75-121): Searches for `{step_name}.{strategy_name}` then `{step_name}`

### Template Variables
Content uses `{variable_name}` syntax. Rendered via `str.format(**variables)` in PromptService.

Task spec variables: `{text}`, `{sentiment}`, `{primary_topic}`

## 6. Entry Point Registration

### Current State (from Task 1)
`_discover_pipelines()` in `app.py` scans `llm_pipeline.pipelines` entry point group. For each:
1. `ep.load()` loads the class
2. Validates it's a `PipelineConfig` subclass
3. Registers in `pipeline_registry` (factory) and `introspection_registry` (class)
4. Calls `seed_prompts(engine)` if present

### pyproject.toml Addition
```toml
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
```

### Editable Install Requirement
Entry points are resolved via `importlib.metadata`. For development, the package must be installed in editable mode (`pip install -e .` or `uv pip install -e .`) for entry points to be discoverable.

## 7. DB Model Patterns

### SQLModel Pattern
```python
class Topic(SQLModel, table=True):
    __tablename__ = "demo_topics"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    confidence: float = Field(default=0.0)
    run_id: str = Field(max_length=36)
    # ... additional fields
```

### PipelineDatabaseRegistry (registry.py)
```python
class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    pass
```
- Models listed in FK dependency order
- `init_pipeline_db()` creates framework tables only; pipeline-specific tables need `SQLModel.metadata.create_all(engine, tables=[Topic.__table__])`

### Table Creation
Framework tables are created by `init_pipeline_db()` (db/__init__.py L135-144). Pipeline-specific tables (like `demo_topics`) must be created separately. Options:
- In `seed_prompts(engine)` (already called at discovery time)
- In pipeline `__init__` via `SQLModel.metadata.create_all(engine, tables=[Topic.__table__])`

### PipelineExtraction (extraction.py)
```python
class TopicExtraction(PipelineExtraction, model=Topic):
    def default(self, results):
        instruction = results[0]
        topics = []
        for topic in instruction.topics:
            topics.append(Topic(name=topic, run_id=self.pipeline.run_id, ...))
        return topics
```
- Naming: must end with `"Extraction"`
- Validates MODEL is in pipeline's REGISTRY at init time
- `extract()` auto-dispatches to `default()` or strategy-named method

## 8. Agent/pydantic-ai Integration

### AgentRegistry (agent_registry.py)
```python
class TextAnalyzerAgentRegistry(AgentRegistry, agents={
    "sentiment_analysis": SentimentAnalysisInstructions,
    "topic_extraction": TopicExtractionInstructions,
    "summary": SummaryInstructions,
}):
    pass
```
- Maps step_name (snake_case) to output type (LLMResultMixin subclass)
- Output type is the instructions/result class

### LLMResultMixin (step.py L134-183)
All instruction classes must inherit from this:
```python
class SentimentAnalysisInstructions(LLMResultMixin):
    sentiment: str
    sentiment_score: float
    example: ClassVar[dict] = {"sentiment": "positive", "sentiment_score": 0.85}
```
- Provides `confidence_score`, `notes` fields
- `create_failure(reason)` classmethod for error fallback
- `example` ClassVar validated at class definition time

### build_step_agent (agent_builders.py)
Called in pipeline.execute() (L736-741). Constructs `pydantic_ai.Agent` with:
- Dynamic system prompt via `@agent.instructions` decorator (resolves from PromptService at runtime)
- Output validators (not_found_validator, array_length_validator)
- `deps_type=StepDeps` for dependency injection
- `defer_model_check=True` (model resolved at run_sync time)

### StepDeps (agent_builders.py L22-52)
Dependency container passed to agent at `run_sync()`:
- `session`, `pipeline_context`, `prompt_service`
- `run_id`, `pipeline_name`, `step_name`
- `event_emitter`, `variable_resolver`

## 9. WebSocket Streaming

### Already Handled by Framework
- `trigger_run()` (runs.py L228-253) creates `UIBridge` and passes as `event_emitter`
- `UIBridge.emit()` calls `ConnectionManager.broadcast_to_run()` which enqueues to per-client `queue.Queue`
- `websocket_endpoint()` (websocket.py L164-207) streams from queue to WebSocket
- Terminal events (`PipelineCompleted`, `PipelineError`) auto-signal completion
- **No demo-specific work needed** - pipeline events are emitted by framework during `execute()`

## 10. File Structure for Demo

```
llm_pipeline/demo/
    __init__.py          # exports TextAnalyzerPipeline
    pipeline.py          # pipeline class, steps, models, strategies, registries
    prompts.py           # seed_prompts implementation with prompt constants
```

## 11. Upstream Task 1 Deviations

From SUMMARY.md:
- Factory closure accepts `**kwargs` (absorbs `input_data` from trigger_run)
- HTTP 422 (not 400) for missing model
- `PipelineIntrospector._pipeline_name` has naming bug with consecutive caps (workaround: uses `ep.name` as registry key)

## 12. Test Pattern Reference

From `tests/test_pipeline.py`:
```python
# Domain model
class Widget(SQLModel, table=True):
    __tablename__ = "widgets"

# Instructions (LLMResultMixin subclass)
class WidgetDetectionInstructions(LLMResultMixin):
    widget_count: int
    category: str
    example: ClassVar[dict] = {...}

# Context
class WidgetDetectionContext(PipelineContext):
    category: str

# Extraction
class WidgetExtraction(PipelineExtraction, model=Widget):
    def default(self, results): ...

# Step with decorator
@step_definition(instructions=..., default_system_key=..., default_user_key=...,
                 default_extractions=[...], context=...)
class WidgetDetectionStep(LLMStep):
    def prepare_calls(self): return [{"variables": {"data": ...}}]
    def process_instructions(self, instructions): return WidgetDetectionContext(...)

# Strategy
class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context): return True
    def get_steps(self): return [WidgetDetectionStep.create_definition()]

# Registry, AgentRegistry, Strategies, Pipeline
class TestRegistry(PipelineDatabaseRegistry, models=[Widget]): pass
class TestAgentRegistry(AgentRegistry, agents={"widget_detection": WidgetDetectionInstructions}): pass
class TestStrategies(PipelineStrategies, strategies=[DefaultStrategy]): pass
class TestPipeline(PipelineConfig, registry=TestRegistry, strategies=TestStrategies, agent_registry=TestAgentRegistry): pass
```

## 13. Demo-Specific Design Decisions

### Three Steps in Order
1. **SentimentAnalysisStep**: Input = `{text}`. Output context = `{sentiment, sentiment_score}`
2. **TopicExtractionStep**: Input = `{text}`. Output context = `{primary_topic, topics}`. Extraction = Topic records
3. **SummaryStep**: Input = `{text}, {sentiment}, {primary_topic}`. Output context = `{summary}`

### Default Model
`google-gla:gemini-2.0-flash-lite` per task spec. Overridable via `LLM_PIPELINE_MODEL` env var or `--model` CLI flag.

### Context Passing Flow
```
Step 1: SentimentAnalysis
  Input: pipeline.validated_input.text
  Context output: {sentiment: "positive", sentiment_score: 0.85}

Step 2: TopicExtraction
  Input: pipeline.validated_input.text, pipeline.context["sentiment"]
  Context output: {primary_topic: "technology", topics: ["AI", "ML"]}
  Extraction: Topic records to demo_topics table

Step 3: Summary
  Input: pipeline.validated_input.text, pipeline.context["sentiment"], pipeline.context["primary_topic"]
  Context output: {summary: "..."}
```
