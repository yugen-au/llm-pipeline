# Step 1: Creator Package Patterns Research

## 1. Package Structure

```
llm_pipeline/creator/
  __init__.py          # jinja2 ImportError guard, re-exports StepCreatorPipeline
  models.py            # FieldDefinition, ExtractionTarget (Pydantic), GenerationRecord (SQLModel)
  schemas.py           # 4 Instructions + 4 Context classes
  pipeline.py          # InputData, Registry, AgentRegistry, Strategy, Strategies, Pipeline
  steps.py             # 4 @step_definition step classes + GenerationRecordExtraction
  prompts.py           # 8 prompt seed dicts + seed_prompts()
  sandbox.py           # SandboxResult, CodeSecurityValidator, StepSandbox
  sample_data.py       # SampleDataGenerator
  templates/
    __init__.py        # Jinja2 Environment factory, render_template(), custom filters
    step.py.j2         # Renders step class module
    instructions.py.j2 # Renders LLMResultMixin subclass module
    extraction.py.j2   # Renders PipelineExtraction subclass module
    prompts.yaml.j2    # Renders prompt dict Python module (NOT YAML despite name)
```

## 2. Meta-Pipeline Output Shape

The StepCreatorPipeline produces 4 context objects chained sequentially. The final output lives in `CodeValidationContext.all_artifacts`.

### CodeValidationContext (final step output)
```python
class CodeValidationContext(PipelineContext):
    is_valid: bool
    syntax_valid: bool
    llm_review_valid: bool
    issues: list[str]
    all_artifacts: dict[str, str]   # <-- KEY: filename -> rendered code
    sandbox_valid: bool = False
    sandbox_skipped: bool = True
    sandbox_output: str | None = None
```

### all_artifacts dict structure
```python
{
    "{step_name}_step.py": "<rendered step class module>",
    "{step_name}_instructions.py": "<rendered LLMResultMixin subclass>",
    "{step_name}_prompts.py": "<rendered prompt dicts Python module>",
    # optional:
    "{step_name}_extraction.py": "<rendered PipelineExtraction subclass>",
}
```

### RequirementsAnalysisContext (step 1 output)
```python
class RequirementsAnalysisContext(PipelineContext):
    step_name: str              # e.g. "sentiment_analysis"
    step_class_name: str        # e.g. "SentimentAnalysisStep"
    instruction_fields: list[dict]
    context_fields: list[dict]
    extraction_targets: list[dict]
    input_variables: list[str]
    output_context_keys: list[str]
```

### PromptGenerationContext (step 3 output)
```python
class PromptGenerationContext(PipelineContext):
    system_prompt: str
    user_prompt_template: str
    required_variables: list[str]
    prompt_yaml: str             # rendered prompt Python module
```

## 3. Prompt Model and Registration Pattern

### Prompt model (`llm_pipeline/db/prompt.py`)
```python
class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"
    id: Optional[int] = Field(default=None, primary_key=True)
    prompt_key: str              # e.g. "sentiment_analysis"
    prompt_name: str             # e.g. "Sentiment Analysis System"
    prompt_type: str             # "system" or "user"
    category: Optional[str]      # e.g. "text_analyzer", "step_creator"
    step_name: Optional[str]     # e.g. "sentiment_analysis"
    content: str                 # prompt text with {variable} placeholders
    required_variables: Optional[List[str]]  # JSON column
    description: Optional[str]
    version: str = "1.0"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
```

**Uniqueness constraint**: `UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type')` -- each step gets exactly 1 system + 1 user prompt per prompt_key.

### seed_prompts() pattern (used by both demo and creator)
```python
def seed_prompts(cls: type, engine: Engine) -> None:
    # 1. Create pipeline-specific tables
    SQLModel.metadata.create_all(engine, tables=[Model.__table__])
    # 2. Idempotent prompt insertion
    with Session(engine) as session:
        for prompt_data in ALL_PROMPTS:
            existing = session.exec(
                select(Prompt).where(
                    Prompt.prompt_key == prompt_data["prompt_key"],
                    Prompt.prompt_type == prompt_data["prompt_type"],
                )
            ).first()
            if existing is None:
                session.add(Prompt(**prompt_data))
        session.commit()
```

### Prompt dict structure (matches Prompt model fields exactly)
```python
{
    "prompt_key": "sentiment_analysis",
    "prompt_name": "Sentiment Analysis System",
    "prompt_type": "system",
    "category": "text_analyzer",
    "step_name": "sentiment_analysis",
    "content": "You are a sentiment analysis expert...",
    "required_variables": [],
    "description": "System prompt for sentiment analysis step",
}
```

### Generated prompt file structure (from prompts.yaml.j2)
The template renders a Python module (NOT YAML) with:
- `{STEP_UPPER}_SYSTEM: dict` -- system prompt dict
- `{STEP_UPPER}_USER: dict` -- user prompt dict
- `ALL_PROMPTS: list[dict]` -- both prompts for iteration

Integrator can either:
- **(a)** Parse the rendered Python prompt file to extract dicts
- **(b)** Use PromptGenerationContext data directly to construct Prompt objects (cleaner, structured data already available)

## 4. Registry Pattern (`PipelineDatabaseRegistry`)

**File**: `llm_pipeline/registry.py`

```python
class PipelineDatabaseRegistry(ABC):
    MODELS: ClassVar[List[Type[SQLModel]]] = []

    def __init_subclass__(cls, models=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if models is not None:
            cls.MODELS = models
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineDatabaseRegistry:
            raise ValueError(...)
```

**Usage**:
```python
class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    pass
```

**Key facts**:
- MODELS is set at **class definition time** via `__init_subclass__`
- `get_models()` returns `cls.MODELS`
- Models are in FK dependency order (insertion order)
- Naming: must be `{PipelinePrefix}Registry`
- To add a model at runtime: `SomeRegistry.MODELS.append(NewModel)` (direct list mutation)

## 5. Strategy Pattern

### PipelineStrategy (`llm_pipeline/strategy.py`)
```python
class PipelineStrategy(ABC):
    def __init_subclass__(cls, **kwargs):
        # Auto-generates cls.NAME (snake_case) and cls.DISPLAY_NAME
        # Validates class name ends with 'Strategy'

    @abstractmethod
    def can_handle(self, context: Dict[str, Any]) -> bool: ...

    @abstractmethod
    def get_steps(self) -> List[StepDefinition]: ...
```

### PipelineStrategies
```python
class PipelineStrategies(ABC):
    STRATEGIES: ClassVar[List[Type[PipelineStrategy]]] = []

    def __init_subclass__(cls, strategies=None, **kwargs):
        if strategies is not None:
            cls.STRATEGIES = strategies
```

### StepDefinition (dataclass)
```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type
    action_after: Optional[str] = None
    extractions: List[Type['PipelineExtraction']] = field(default_factory=list)
    transformation: Optional[Type['PipelineTransformation']] = None
    context: Optional[Type] = None
    agent_name: str | None = None
    not_found_indicators: list[str] | None = None
    consensus_strategy: 'ConsensusStrategy | None' = None
```

**How steps are added to a strategy** (demo pattern):
```python
class DefaultStrategy(PipelineStrategy):
    def get_steps(self):
        return [
            SentimentAnalysisStep.create_definition(),
            TopicExtractionStep.create_definition(),
            SummaryStep.create_definition(),
        ]
```

**`create_definition()` classmethod** (auto-generated by `@step_definition` decorator):
- Returns a `StepDefinition` with all defaults from the decorator
- Can override system_instruction_key, user_prompt_key, extractions, transformation

## 6. AgentRegistry Pattern

**File**: `llm_pipeline/agent_registry.py`

```python
class AgentRegistry(ABC):
    AGENTS: ClassVar[dict[str, Type[BaseModel] | AgentSpec]] = {}

    def __init_subclass__(cls, agents=None, **kwargs):
        if agents is not None:
            cls.AGENTS = agents
```

**Usage**:
```python
class TextAnalyzerAgentRegistry(AgentRegistry, agents={
    "sentiment_analysis": SentimentAnalysisInstructions,
    "topic_extraction": TopicExtractionInstructions,
    "summary": SummaryInstructions,
}):
    pass
```

**Key**: Maps step_name (snake_case) to Instructions class (or AgentSpec for tools).

## 7. PipelineConfig `__init_subclass__` Naming Enforcement

```python
class PipelineConfig(ABC):
    def __init_subclass__(cls, registry=None, strategies=None, agent_registry=None, **kwargs):
        # Enforces: class name ends with "Pipeline"
        # Enforces: registry name == "{PipelinePrefix}Registry"
        # Enforces: strategies name == "{PipelinePrefix}Strategies"
        # Enforces: agent_registry name == "{PipelinePrefix}AgentRegistry"
        if registry is not None:
            cls.REGISTRY = registry
        if strategies is not None:
            cls.STRATEGIES = strategies
        if agent_registry is not None:
            cls.AGENT_REGISTRY = agent_registry
```

## 8. `@step_definition` Decorator Naming Enforcement

```python
def step_definition(instructions, default_system_key, default_user_key, ...):
    def decorator(step_class):
        # Enforces: step_class name ends with "Step"
        # Enforces: instructions name == "{StepPrefix}Instructions"
        # Enforces: context name == "{StepPrefix}Context" (if provided)
        # Enforces: transformation name == "{StepPrefix}Transformation" (if provided)

        step_class.INSTRUCTIONS = instructions
        step_class.DEFAULT_SYSTEM_KEY = default_system_key
        # ... stores all config as class attributes
        # Adds step_class.create_definition() classmethod
```

## 9. PipelineExtraction Pattern

**File**: `llm_pipeline/extraction.py`

```python
class PipelineExtraction(ABC):
    MODEL: ClassVar[Type[SQLModel]] = None

    def __init_subclass__(cls, model=None, **kwargs):
        # Enforces: model parameter required for concrete subclasses
        # Enforces: class name ends with "Extraction"

    def __init__(self, pipeline: PipelineConfig):
        # Validates: self.MODEL in pipeline.REGISTRY.get_models()
```

**Usage**:
```python
class TopicExtraction(PipelineExtraction, model=Topic):
    def default(self, results: list[TopicExtractionInstructions]) -> list[Topic]:
        return [Topic(...) for t in results[0].topics]
```

## 10. DraftStep Model (task 50)

**File**: `llm_pipeline/state.py`

```python
class DraftStep(SQLModel, table=True):
    __tablename__ = "draft_steps"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str                    # unique step name
    description: Optional[str]
    generated_code: dict         # JSON -- artifact dict from meta-pipeline
    test_results: Optional[dict]
    validation_errors: Optional[dict]
    status: str = "draft"        # draft, tested, accepted, error
    run_id: Optional[str]        # link to creator_generation_records
    created_at: datetime
    updated_at: datetime
```

**UniqueConstraint on `name`** -- re-generation updates existing row.

## 11. Entry Points and Pipeline Discovery

**File**: `pyproject.toml`

```toml
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
step_creator = "llm_pipeline.creator:StepCreatorPipeline"
```

Pipelines are discoverable via `importlib.metadata.entry_points(group="llm_pipeline.pipelines")`.

## 12. init_pipeline_db() Pattern

**File**: `llm_pipeline/db/__init__.py`

```python
def init_pipeline_db(engine=None) -> Engine:
    # Creates framework tables: PipelineStepState, PipelineRunInstance,
    # PipelineRun, Prompt, PipelineEventRecord, DraftStep, DraftPipeline
    SQLModel.metadata.create_all(engine, tables=[...])
    # Runs migrations for new columns
    # Adds performance indexes
```

Pipeline-specific tables (e.g., Topic, GenerationRecord) are created by `Pipeline.seed_prompts(engine)`, NOT by `init_pipeline_db()`.

## 13. Jinja2 Template Environment

**File**: `llm_pipeline/creator/templates/__init__.py`

```python
@lru_cache(maxsize=None)
def get_template_env() -> Environment:
    env = Environment(
        loader=PackageLoader("llm_pipeline.creator", "templates"),
        trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    env.filters["snake_case"] = to_snake_case
    env.filters["camel_case"] = _camel_case
    env.filters["indent_code"] = _indent_code
    env.filters["format_dict"] = _format_dict
    return env

def render_template(template_name: str, **context) -> str:
    return get_template_env().get_template(template_name).render(**context)
```

## 14. Complete Naming Convention Summary

| Component | Pattern | Enforced By | Example |
|-----------|---------|-------------|---------|
| Pipeline | `{Prefix}Pipeline` | `PipelineConfig.__init_subclass__` | `TextAnalyzerPipeline` |
| Registry | `{Prefix}Registry` | `PipelineConfig.__init_subclass__` | `TextAnalyzerRegistry` |
| Strategies | `{Prefix}Strategies` | `PipelineConfig.__init_subclass__` | `TextAnalyzerStrategies` |
| AgentRegistry | `{Prefix}AgentRegistry` | `PipelineConfig.__init_subclass__` | `TextAnalyzerAgentRegistry` |
| Strategy | `{Name}Strategy` | `PipelineStrategy.__init_subclass__` | `DefaultStrategy` |
| Step | `{Name}Step` | `@step_definition` | `SentimentAnalysisStep` |
| Instructions | `{StepPrefix}Instructions` | `@step_definition` | `SentimentAnalysisInstructions` |
| Context | `{StepPrefix}Context` | `@step_definition` | `SentimentAnalysisContext` |
| Extraction | `{Name}Extraction` | `PipelineExtraction.__init_subclass__` | `TopicExtraction` |
| Transformation | `{StepPrefix}Transformation` | `@step_definition` | (pattern exists, none in demo) |

## 15. Data Flow: Meta-Pipeline to Integration

```
StepCreatorPipeline.execute()
  -> RequirementsAnalysisStep -> RequirementsAnalysisContext
     (step_name, step_class_name, fields, extraction_targets)
  -> CodeGenerationStep -> CodeGenerationContext
     (step_code, instructions_code, extraction_code)
  -> PromptGenerationStep -> PromptGenerationContext
     (system_prompt, user_prompt_template, required_variables, prompt_yaml)
  -> CodeValidationStep -> CodeValidationContext
     (is_valid, all_artifacts, sandbox_valid)

pipeline.context accumulates all fields flatly.
pipeline.extractions contains GenerationRecord instances.

StepIntegrator.integrate() consumes:
  1. all_artifacts (dict[str, str]) -> write to target_dir
  2. prompt data (from context or parsed from prompt file) -> Prompt DB rows
  3. step_name, extraction_targets -> update strategy/registry (if target specified)
```

## 16. Open Items for Planning Phase

### Q1: GeneratedStep type definition
Task spec references `GeneratedStep` as integrate() input. Type doesn't exist yet. Options:
- New Pydantic model in `creator/models.py` with structured fields
- Wrap/accept `DraftStep` directly (has `generated_code: dict` = all_artifacts)
- Accept raw `CodeValidationContext` (has all needed data)

### Q2: Strategy/Registry update mechanism
Registry MODELS, Strategies STRATEGIES, AgentRegistry AGENTS are all set at class definition time. Updating requires:
- **(a)** Runtime mutation: `cls.MODELS.append(Model)` -- immediate but non-persistent
- **(b)** AST source file modification -- persistent but complex
- **(c)** Hybrid: runtime + source update
Note: target_pipeline and target_strategy are optional params, so this may be deferred.

### Q3: Prompt registration source
Two data sources for prompt insertion:
- **(a)** Parse `{step_name}_prompts.py` artifact (has ALL_PROMPTS list as Python source)
- **(b)** Use structured data from PromptGenerationContext (system_prompt, user_prompt_template, etc.)
Option (b) avoids Python source parsing; option (a) stays consistent with what gets written to disk.
