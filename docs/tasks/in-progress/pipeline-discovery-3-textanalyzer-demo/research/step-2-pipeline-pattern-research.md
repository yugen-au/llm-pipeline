# Step 2: Pipeline Pattern Research

## Overview

Research into pipeline orchestration patterns for building a 3-step TextAnalyzerPipeline demo (sentiment -> topics -> summary).

---

## 1. PipelineConfig Subclassing Pattern

**File:** `llm_pipeline/pipeline.py`

### Class Definition Syntax

```python
class TextAnalyzerPipeline(PipelineConfig,
                           registry=TextAnalyzerRegistry,
                           strategies=TextAnalyzerStrategies,
                           agent_registry=TextAnalyzerAgentRegistry):
    INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = TextAnalyzerInputData
```

### Naming Enforcement (L112-151)

- Pipeline class MUST end with `"Pipeline"` suffix
- Registry must be `{Prefix}Registry` (e.g. `TextAnalyzerRegistry`)
- Strategies must be `{Prefix}Strategies` (e.g. `TextAnalyzerStrategies`)
- AgentRegistry must be `{Prefix}AgentRegistry` (e.g. `TextAnalyzerAgentRegistry`)
- Prefix = class name minus "Pipeline" suffix

### ClassVars Set by __init_subclass__

- `REGISTRY`: PipelineDatabaseRegistry subclass (required)
- `STRATEGIES`: PipelineStrategies subclass (required)
- `AGENT_REGISTRY`: AgentRegistry subclass (required for execute())
- `INPUT_DATA`: PipelineInputData subclass (optional, enables structured input validation)

### Constructor Signature (L161-243)

```python
def __init__(self, model: str, strategies=None, session=None, engine=None,
             variable_resolver=None, event_emitter=None, run_id=None,
             instrumentation_settings=None)
```

The factory closure in `app.py:_make_pipeline_factory` calls:
```python
cls(model=model, run_id=run_id, engine=engine, event_emitter=event_emitter)
```

### Key Internal State

- `self._context: Dict[str, Any]` -- accumulated context from all steps
- `self._instructions: StepKeyDict` -- raw LLM results per step
- `self.data: StepKeyDict` -- data transformations
- `self.extractions: Dict[Type[SQLModel], List[SQLModel]]` -- DB model instances
- `self._validated_input` -- validated PipelineInputData instance (from execute(input_data=...))

### seed_prompts Pattern

Class-level method called by auto-discovery:
```python
@classmethod
def seed_prompts(cls, engine: Engine) -> None:
    # Create Prompt records idempotently
```

Called in `app.py:_discover_pipelines` L85-93 with isolated try/except. Failure logs warning but does NOT unregister the pipeline.

### pipeline_name Property (L270-277)

Auto-derived: `TextAnalyzerPipeline` -> `"text_analyzer"` via `to_snake_case(name, strip_suffix="Pipeline")`.

---

## 2. PipelineStrategy / PipelineStrategies

**File:** `llm_pipeline/strategy.py`

### PipelineStrategies Declaration

```python
class TextAnalyzerStrategies(PipelineStrategies, strategies=[
    TextAnalyzerStrategy,
]):
    pass
```

- `create_instances()` instantiates all strategy classes
- Single strategy is fine for a linear pipeline

### PipelineStrategy Subclass

```python
class TextAnalyzerStrategy(PipelineStrategy):
    # NAME auto-set to "text_analyzer" (snake_case of prefix)
    # DISPLAY_NAME auto-set to "Text Analyzer"

    def can_handle(self, context: Dict[str, Any]) -> bool:
        return True  # always handles for single-strategy pipeline

    def get_steps(self) -> List[StepDefinition]:
        return [
            SentimentAnalysisStep.create_definition(),
            TopicExtractionStep.create_definition(),
            SummaryStep.create_definition(),
        ]
```

### Execution Flow in PipelineConfig.execute() (L455-962)

1. Iterates `step_index` from 0 to `max_steps`
2. For each index, finds first strategy where `can_handle(context)` is True
3. Gets `StepDefinition` at that index from selected strategy
4. `step_def.create_step(pipeline=self)` creates configured step instance
5. Checks `step.should_skip()`, runs LLM calls via pydantic-ai Agent, processes results
6. Merges context, runs extractions, saves state

### StepDefinition (L24-143)

Connects step class with prompts, extractions, transformation, context:

```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type  # output type (LLMResultMixin subclass)
    extractions: List[Type[PipelineExtraction]] = []
    transformation: Optional[Type[PipelineTransformation]] = None
    context: Optional[Type] = None  # PipelineContext subclass
    agent_name: str | None = None
    consensus_strategy: ConsensusStrategy | None = None
```

`create_step(pipeline)` auto-discovers prompt keys if None, via DB lookup by step_name.

---

## 3. LLMStep and step_definition Decorator

**File:** `llm_pipeline/step.py`

### @step_definition Decorator

```python
@step_definition(
    instructions=SentimentAnalysisInstructions,
    default_system_key=None,  # auto-discovered from DB by step_name
    default_user_key=None,
    default_extractions=[],
    default_transformation=None,
    context=SentimentAnalysisContext,
)
class SentimentAnalysisStep(LLMStep):
    ...
```

Naming enforcement:
- Step class must end with `"Step"`
- Instructions must be `{StepPrefix}Instructions`
- Transformation must be `{StepPrefix}Transformation`
- Context must be `{StepPrefix}Context`

Adds `create_definition()` classmethod to the step class.

### LLMStep Base Class

Key methods to implement:

- **`prepare_calls() -> List[StepCallParams]`** (abstract, required): Returns list of call params. Each entry has `variables` dict used to render user prompt template.
- **`process_instructions(instructions: List[Any]) -> Dict | PipelineContext`**: Extract derived values from LLM results into pipeline context. Default returns `{}`.
- **`should_skip() -> bool`**: Skip logic. Default `False`.
- **`log_instructions(instructions)`**: Custom logging. Default no-op.
- **`extract_data(instructions)`**: Auto-delegates to extraction classes from step_def. Usually not overridden.

### LLMResultMixin

```python
class SentimentAnalysisInstructions(LLMResultMixin):
    sentiment: str
    explanation: str
    # inherits confidence_score: float, notes: str | None

    example = {"sentiment": "positive", "explanation": "...", "confidence_score": 0.9}
```

`create_failure(reason, **safe_defaults)` classmethod for error handling.

---

## 4. PipelineContext -- Runtime Data Flow

**File:** `llm_pipeline/context.py`

### Context Base Class

```python
class PipelineContext(BaseModel):
    pass

class PipelineInputData(BaseModel):
    pass
```

### Context Flow Between Steps

1. Step's `process_instructions()` returns a `PipelineContext` subclass or dict
2. Pipeline calls `_validate_and_merge_context()` (L383-413)
3. If PipelineContext subclass: validated, then `model_dump()`'d to dict
4. Merged into `pipeline._context` via `update()`
5. Next step accesses via `self.pipeline.context["key"]`

### Context Access in prepare_calls()

Steps access context through `self.pipeline.context`:
```python
def prepare_calls(self) -> List[StepCallParams]:
    sentiment = self.pipeline.context["sentiment"]
    return [{"variables": {"text": self.pipeline.validated_input.text, "sentiment": sentiment}}]
```

### INPUT_DATA Validation (L486-499)

If `INPUT_DATA` ClassVar is set:
- `execute(input_data=dict)` validates against the schema
- Stored in `self._validated_input` as Pydantic model instance
- Accessible via `self.pipeline.validated_input`

---

## 5. PipelineExtraction

**File:** `llm_pipeline/extraction.py`

### Pattern

```python
class TopicExtraction(PipelineExtraction, model=Topic):
    def default(self, results: List[TopicExtractionInstructions]) -> List[Topic]:
        topics = []
        for topic_data in results[0].topics:
            topics.append(Topic(name=topic_data.name, relevance=topic_data.relevance))
        return topics
```

- Must end with `"Extraction"` suffix
- `model=` parameter sets `MODEL` ClassVar
- MODEL must be in pipeline's REGISTRY.get_models()
- Smart method detection: `default()` method auto-detected
- `_validate_instances()` checks for NaN, NULL constraint violations
- Pipeline stores returned instances and flushes to DB

---

## 6. PipelineTransformation

**File:** `llm_pipeline/transformation.py`

Not needed for the demo. Transformations handle data structure changes (unpivot, normalize). The TextAnalyzer pipeline doesn't transform data between steps -- it only passes context values.

---

## 7. PipelineDatabaseRegistry

**File:** `llm_pipeline/registry.py`

```python
class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    pass
```

- Models listed in FK dependency order (insertion order)
- `get_models()` returns the list
- `save()` iterates registry models, creates tables if needed, commits

---

## 8. AgentRegistry

**File:** `llm_pipeline/agent_registry.py`

```python
class TextAnalyzerAgentRegistry(AgentRegistry, agents={
    "sentiment_analysis": SentimentAnalysisInstructions,
    "topic_extraction": TopicExtractionInstructions,
    "summary": SummaryInstructions,
}):
    pass
```

- Maps step_name (snake_case) to output Pydantic model
- Used by `step.get_agent(registry)` to get output_type for pydantic-ai Agent
- Step name derived from class: `SentimentAnalysisStep` -> `"sentiment_analysis"`

---

## 9. Prompt Seeding (seed_prompts)

**File:** `llm_pipeline/db/prompt.py` (Prompt model)

### Prompt Model

```python
class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"
    prompt_key: str       # e.g. "sentiment_analysis"
    prompt_type: str      # "system" or "user"
    content: str          # template with {variable} placeholders
    # UniqueConstraint('prompt_key', 'prompt_type')
```

### seed_prompts Implementation Pattern

```python
@classmethod
def seed_prompts(cls, engine: Engine) -> None:
    from sqlmodel import Session, select
    from llm_pipeline.db.prompt import Prompt

    prompts = [
        Prompt(prompt_key="sentiment_analysis", prompt_type="system",
               prompt_name="Sentiment Analysis System", content="..."),
        Prompt(prompt_key="sentiment_analysis", prompt_type="user",
               prompt_name="Sentiment Analysis User", content="Analyze: {text}"),
        # ... more prompts
    ]

    with Session(engine) as session:
        for prompt in prompts:
            existing = session.exec(select(Prompt).where(
                Prompt.prompt_key == prompt.prompt_key,
                Prompt.prompt_type == prompt.prompt_type
            )).first()
            if not existing:
                session.add(prompt)
        session.commit()
```

Idempotent: checks unique constraint (prompt_key, prompt_type) before insert.

### Template Variables

- User prompts use `{variable}` syntax: `{text}`, `{sentiment}`, `{primary_topic}`
- Rendered by `PromptService.get_user_prompt()` via `template.format(**variables)`
- Variables come from step's `prepare_calls()` -> `{"variables": {...}}`

---

## 10. Entry Point Discovery

**File:** `llm_pipeline/ui/app.py`

### Registration

In `pyproject.toml`:
```toml
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
```

### Discovery Flow (app.py L49-102)

1. `_discover_pipelines(engine, default_model)` scans `llm_pipeline.pipelines` group
2. For each entry point: load class, validate PipelineConfig subclass
3. Create factory closure via `_make_pipeline_factory(cls, model)`
4. Call `seed_prompts(engine)` if present
5. Returns (pipeline_registry, introspection_registry) dicts

### Factory Signature

```python
def factory(run_id, engine, event_emitter=None, **kwargs) -> PipelineConfig:
    return cls(model=model, run_id=run_id, engine=engine, event_emitter=event_emitter)
```

Note: `**kwargs` absorbs `input_data=` passed by `trigger_run` (L231) since PipelineConfig.__init__ doesn't accept input_data. Input data flows through `execute(input_data=body.input_data)` instead.

---

## 11. WebSocket / Streaming Event Patterns

**Files:** `llm_pipeline/ui/bridge.py`, `llm_pipeline/ui/routes/websocket.py`

### Event Flow

1. `trigger_run` creates `UIBridge(run_id)` as event_emitter
2. Pipeline constructor receives it via `event_emitter=` param
3. During execute(), pipeline calls `self._emit(EventType(...))` at each lifecycle point
4. UIBridge.emit() -> ConnectionManager.broadcast_to_run() -> thread_queue.Queue per client
5. WebSocket endpoint reads queue -> sends JSON to client

### Auto-Emitted Events (no custom code needed)

Pipeline lifecycle: PipelineStarted, PipelineCompleted, PipelineError
Step lifecycle: StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
LLM calls: LLMCallPrepared, LLMCallStarting, LLMCallCompleted
Context: InstructionsStored, InstructionsLogged, ContextUpdated
Extraction: ExtractionStarting, ExtractionCompleted
State: StateSaved

### Terminal Event Handling

UIBridge auto-detects PipelineCompleted/PipelineError and sends None sentinel to signal stream end.

---

## 12. State Tracking

**File:** `llm_pipeline/state.py`

### PipelineStepState

Per-step audit record: pipeline_name, run_id, step_name, step_number, input_hash, result_data (JSON), context_snapshot (JSON), prompt keys, model, timing, token usage.

### PipelineRunInstance

Links created DB instances to pipeline runs: run_id, model_type, model_id. Enables traceability.

### PipelineRun

Run lifecycle: run_id, pipeline_name, status (running/completed/failed), timing, step_count.

All three are auto-managed by PipelineConfig.execute() and save(). No custom code needed.

---

## 13. Concrete File/Class Map for TextAnalyzerPipeline

### Required Files

| File | Contents |
|------|----------|
| `llm_pipeline/demo/__init__.py` | Export TextAnalyzerPipeline |
| `llm_pipeline/demo/pipeline.py` | Pipeline class, strategy, registry, agent_registry, steps, instructions, context, extraction, input data model, Topic SQLModel |
| `llm_pipeline/demo/prompts.py` | seed_prompts() implementation with prompt constants |

### Required Classes

| Class | Base | Purpose |
|-------|------|---------|
| `TextAnalyzerInputData` | `PipelineInputData` | Input schema: `text: str` |
| `Topic` | `SQLModel, table=True` | DB model, `__tablename__="demo_topics"` |
| `TextAnalyzerRegistry` | `PipelineDatabaseRegistry` | `models=[Topic]` |
| `TextAnalyzerStrategy` | `PipelineStrategy` | Single strategy, always handles, returns 3 steps |
| `TextAnalyzerStrategies` | `PipelineStrategies` | `strategies=[TextAnalyzerStrategy]` |
| `SentimentAnalysisInstructions` | `LLMResultMixin` | Output: sentiment, explanation |
| `SentimentAnalysisContext` | `PipelineContext` | Context: sentiment |
| `SentimentAnalysisStep` | `LLMStep` | prepare_calls with {text}, process_instructions extracts sentiment |
| `TopicExtractionInstructions` | `LLMResultMixin` | Output: topics list, primary_topic |
| `TopicExtractionContext` | `PipelineContext` | Context: primary_topic, topics |
| `TopicExtractionStep` | `LLMStep` | prepare_calls with {text, sentiment}, extracts topics |
| `TopicExtraction` | `PipelineExtraction` | `model=Topic`, converts LLM topics to Topic instances |
| `SummaryInstructions` | `LLMResultMixin` | Output: summary text |
| `SummaryContext` | `PipelineContext` | Context: summary |
| `SummaryStep` | `LLMStep` | prepare_calls with {text, sentiment, primary_topic} |
| `TextAnalyzerAgentRegistry` | `AgentRegistry` | Maps 3 step names to instruction types |
| `TextAnalyzerPipeline` | `PipelineConfig` | Wires registry, strategies, agent_registry, INPUT_DATA |

### Step Execution Order

1. `SentimentAnalysisStep` -> reads `validated_input.text` -> produces `context["sentiment"]`
2. `TopicExtractionStep` -> reads `context["sentiment"]` + `validated_input.text` -> produces `context["primary_topic"]`, `context["topics"]` + persists Topic instances
3. `SummaryStep` -> reads `context["sentiment"]` + `context["primary_topic"]` + `validated_input.text` -> produces `context["summary"]`

### Prompt Template Variables

| Step | System Key | User Key | User Template Variables |
|------|-----------|----------|------------------------|
| sentiment_analysis | `sentiment_analysis` | `sentiment_analysis` | `{text}` |
| topic_extraction | `topic_extraction` | `topic_extraction` | `{text}`, `{sentiment}` |
| summary | `summary` | `summary` | `{text}`, `{sentiment}`, `{primary_topic}` |

---

## 14. Entry Point Registration

```toml
# pyproject.toml addition
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
```

After `pip install -e .` (or equivalent), the entry point is discoverable by `importlib.metadata.entry_points(group="llm_pipeline.pipelines")`.

---

## 15. Default Model

Task specifies `google-gla:gemini-2.0-flash-lite`. This is passed via:
- CLI `--model` flag -> `create_app(default_model=...)` -> factory closure captures it
- Env `LLM_PIPELINE_MODEL` -> fallback in `create_app()` L167
- No pipeline-level override needed; model flows through factory -> constructor -> `agent.run_sync(model=self._model)`

---

## Questions

None. All patterns are clearly defined by the existing codebase and task spec aligns with them.
