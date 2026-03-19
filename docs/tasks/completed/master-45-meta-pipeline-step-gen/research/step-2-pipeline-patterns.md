# Step 2: Pipeline Architecture Patterns Research

## 1. PipelineConfig Subclass Pattern

### How PipelineConfig declares subclasses

From `llm_pipeline/pipeline.py` (L123-196):

```python
class PipelineConfig(ABC):
    REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
    STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None
    AGENT_REGISTRY: ClassVar[Optional[Type["AgentRegistry"]]] = None
    INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None

    def __init_subclass__(cls, registry=None, strategies=None, agent_registry=None, **kwargs):
        # Enforces naming: class must end with "Pipeline"
        # Registry must be named "{Prefix}Registry"
        # Strategies must be named "{Prefix}Strategies"
        # AgentRegistry must be named "{Prefix}AgentRegistry"
```

### Naming enforcement rules

Given `StepCreatorPipeline`, the framework requires:
- `StepCreatorRegistry` (PipelineDatabaseRegistry subclass)
- `StepCreatorStrategies` (PipelineStrategies subclass)
- `StepCreatorAgentRegistry` (AgentRegistry subclass)

### Constructor signature (L197-279)

```python
def __init__(self, model, strategies=None, session=None, engine=None,
             variable_resolver=None, event_emitter=None, run_id=None,
             instrumentation_settings=None):
```

Key: if `session` and `engine` are both None, auto-creates SQLite. If `STRATEGIES` class var set, auto-instantiates from it.

### Reference: TextAnalyzerPipeline (demo/pipeline.py L274-290)

```python
class TextAnalyzerPipeline(
    PipelineConfig,
    registry=TextAnalyzerRegistry,
    strategies=TextAnalyzerStrategies,
    agent_registry=TextAnalyzerAgentRegistry,
):
    INPUT_DATA: ClassVar[type] = TextAnalyzerInputData

    @classmethod
    def seed_prompts(cls, engine: Engine) -> None:
        from llm_pipeline.demo.prompts import seed_prompts
        seed_prompts(cls, engine)
```

---

## 2. Step Definition Pattern

### @step_definition decorator (step.py L34-131)

Decorator configures a step class with:
- `instructions`: Pydantic model class (LLMResultMixin subclass) - required
- `default_system_key`: Prompt key for system prompt - optional
- `default_user_key`: Prompt key for user prompt - optional
- `default_extractions`: List of PipelineExtraction subclasses - optional
- `default_transformation`: PipelineTransformation subclass - optional
- `context`: PipelineContext subclass this step produces - optional

Naming enforcement:
- Step class must end with `Step` (e.g., `RequirementsAnalysisStep`)
- Instructions class must be `{StepPrefix}Instructions` (e.g., `RequirementsAnalysisInstructions`)
- Transformation must be `{StepPrefix}Transformation`
- Context must be `{StepPrefix}Context`

Auto-generates `create_definition()` classmethod that returns a `StepDefinition` dataclass.

### LLMStep base class (step.py L186-349)

Abstract methods:
- `prepare_calls() -> List[StepCallParams]` - REQUIRED. Returns list of dicts with `variables` key.
- `process_instructions(instructions) -> Dict | PipelineContext` - Optional. Derives context from LLM output.
- `should_skip() -> bool` - Optional. Skip step based on context.
- `extract_data(instructions)` - Auto-delegates to extraction classes.

Key properties/methods:
- `self.pipeline` - Reference to PipelineConfig instance
- `self.step_name` - Auto-derived snake_case from class name
- `self.system_instruction_key` / `self.user_prompt_key` - Prompt keys
- `self.instructions` - The instructions Pydantic model class

### LLMResultMixin (step.py L134-183)

All instruction classes inherit from this. Provides:
- `confidence_score: float` (0-1, default 0.95)
- `notes: str | None`
- `example: ClassVar[dict]` - Optional example for validation
- `create_failure(reason, **safe_defaults)` - Factory for failure results

---

## 3. Strategy Pattern

### PipelineStrategy (strategy.py L146-255)

Abstract base class. Subclasses must implement:
- `can_handle(context: Dict) -> bool` - Whether strategy applies to current context
- `get_steps() -> List[StepDefinition]` - Ordered list of step definitions

Naming: must end with `Strategy`. Auto-generates `NAME` (snake_case) and `DISPLAY_NAME`.

### PipelineStrategies (strategy.py L258-335)

Container that declares which strategies a pipeline uses:
```python
class MyStrategies(PipelineStrategies, strategies=[Strategy1, Strategy2]):
    pass
```

Provides `create_instances()` classmethod to instantiate all strategies.

### StepDefinition dataclass (strategy.py L24-143)

Connects step class with its configuration:
```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type
    action_after: Optional[str] = None
    extractions: List[Type[PipelineExtraction]] = field(default_factory=list)
    transformation: Optional[Type[PipelineTransformation]] = None
    context: Optional[Type] = None
    agent_name: str | None = None
    not_found_indicators: list[str] | None = None
    consensus_strategy: ConsensusStrategy | None = None
```

`create_step(pipeline)` method instantiates the step with prompt auto-discovery (tries strategy-level key first, then step-level key).

---

## 4. Registry Patterns

### PipelineDatabaseRegistry (registry.py)

Declares SQLModel classes managed by a pipeline:
```python
class MyRegistry(PipelineDatabaseRegistry, models=[Model1, Model2]):
    pass
```

Key constraint: `models=` must be non-empty list. `get_models()` raises ValueError on empty list.

### AgentRegistry (agent_registry.py)

Maps step names to pydantic-ai output types:
```python
class MyAgentRegistry(AgentRegistry, agents={
    "step_name": InstructionsClass,          # bare type
    "other_step": AgentSpec(Output, tools=[fn]),  # with tools
}):
    pass
```

Methods: `get_output_type(step_name)`, `get_tools(step_name)`.

---

## 5. PipelineContext Data Flow

### Context model (context.py)

```python
class PipelineContext(BaseModel):
    """Base class for step context contributions."""
    pass

class PipelineInputData(BaseModel):
    """Base class for pipeline input data."""
    pass
```

### How steps chain data (pipeline.py execute() flow)

1. Pipeline initializes: `self._context = {}`, `self.data = {"raw": data, "sanitized": ...}`
2. For each step position, selects strategy via `can_handle(context)`
3. Step created via `step_def.create_step(pipeline=self)`
4. Step accesses previous context: `self.pipeline.context["key"]`
5. Step's `prepare_calls()` returns variables for LLM call
6. LLM called via pydantic-ai Agent, result validated against Instructions class
7. `step.process_instructions(instructions)` returns PipelineContext subclass
8. Pipeline merges context: flattened dict merge of all PipelineContext fields
9. Next step can access via `self.pipeline.context["field_name"]`

### Context merge mechanism (pipeline.py _validate_and_merge_context)

When `process_instructions()` returns a PipelineContext subclass, its fields are model_dump()'d and merged into `pipeline._context` dict. Fields from later steps overwrite earlier ones if same key.

### Input data flow

When `INPUT_DATA` ClassVar is set on pipeline, execute() validates `input_data` dict against the schema. Steps access via `self.pipeline.validated_input.field_name`.

---

## 6. Agent Builder Pattern

### build_step_agent() (agent_builders.py L59-169)

Factory function that creates pydantic-ai Agent instances:
```python
def build_step_agent(step_name, output_type, model=None, system_instruction_key=None,
                     retries=3, model_settings=None, validators=None,
                     instrument=None, tools=None) -> Agent[StepDeps, Any]:
```

- Creates Agent with `deps_type=StepDeps`
- Registers `@agent.instructions` that resolves system prompt from DB at runtime
- Registers output validators
- Wraps tools in EventEmittingToolset

### StepDeps (agent_builders.py L23-56)

Dependency injection container for agents:
```python
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
    array_validation: Any | None = None
    validation_context: Any | None = None
    extra: dict[str, Any] = field(default_factory=dict)
```

---

## 7. Prompt System

### DB-stored prompts (db/prompt.py)

Prompts stored in `prompts` table with unique constraint on (prompt_key, prompt_type). Fields:
- `prompt_key`: Step-level key (e.g., "sentiment_analysis")
- `prompt_type`: "system" or "user"
- `content`: Template string with `{variable}` placeholders
- `required_variables`: JSON list of variable names
- `category`, `step_name`: Organization fields

### Prompt seeding pattern (demo/prompts.py)

Each pipeline defines a `seed_prompts()` classmethod that idempotently inserts prompts:
```python
ALL_PROMPTS = [
    {"prompt_key": "step_name", "prompt_type": "system", "content": "...", ...},
    {"prompt_key": "step_name", "prompt_type": "user", "content": "...", ...},
]
```

Template variables use Python str.format() syntax: `{text}`, `{sentiment}`.

---

## 8. Extraction and Transformation Patterns

### PipelineExtraction (extraction.py)

Converts LLM results into SQLModel instances for DB persistence:
```python
class MyExtraction(PipelineExtraction, model=MySQLModel):
    def default(self, results: list[InstructionsClass]) -> list[MySQLModel]:
        return [MySQLModel(...) for item in results[0].items]
```

Auto-routing: tries `default()` -> strategy-named method -> single custom method.

### PipelineTransformation (transformation.py)

Data structure changes between steps:
```python
class MyTransformation(PipelineTransformation, input_type=TypeA, output_type=TypeB):
    def default(self, data: TypeA, instructions: Any) -> TypeB:
        return transformed_data
```

---

## 9. StepCreatorPipeline Architecture Design

### Package structure

```
llm_pipeline/creator/
    __init__.py
    pipeline.py          # StepCreatorPipeline, registry, strategies, agent registry
    steps.py             # 4 step classes with @step_definition
    schemas.py           # Instructions classes (LLMResultMixin subclasses)
    models.py            # GenerationRecord SQLModel + intermediate Pydantic models
    prompts.py           # Prompt seed definitions for 4 meta-steps
    templates/
        __init__.py      # Jinja2 Environment setup, render helpers
        step.py.j2       # Step class template
        instructions.py.j2  # Instructions class template
        extraction.py.j2    # Extraction class template
        prompts.yaml.j2     # Prompt definitions template
```

### Naming map (enforced by framework)

| Component | Name |
|-----------|------|
| Pipeline | `StepCreatorPipeline` |
| DB Registry | `StepCreatorRegistry` |
| Strategies container | `StepCreatorStrategies` |
| Agent Registry | `StepCreatorAgentRegistry` |
| Strategy | `DefaultCreatorStrategy` |
| Step 1 | `RequirementsAnalysisStep` |
| Step 1 Instructions | `RequirementsAnalysisInstructions` |
| Step 1 Context | `RequirementsAnalysisContext` |
| Step 2 | `CodeGenerationStep` |
| Step 2 Instructions | `CodeGenerationInstructions` |
| Step 2 Context | `CodeGenerationContext` |
| Step 3 | `PromptGenerationStep` |
| Step 3 Instructions | `PromptGenerationInstructions` |
| Step 3 Context | `PromptGenerationContext` |
| Step 4 | `ValidationStep` |
| Step 4 Instructions | `ValidationInstructions` |
| Step 4 Context | `ValidationContext` |

NOTE: `ValidationContext` name conflicts with `llm_pipeline.types.ValidationContext`. The step must use a different name. Options: `StepValidationContext`, `CodeValidationContext`, or keep `ValidationContext` in a separate namespace (the `creator` package). Since contexts are merged by field name into pipeline._context dict (not by class name globally), namespace isolation via the creator package is sufficient. However, imports in consuming code could collide. Recommend: `CodeValidationStep` / `CodeValidationInstructions` / `CodeValidationContext` to avoid ambiguity.

Updated step 4 naming:
| Step 4 | `CodeValidationStep` |
| Step 4 Instructions | `CodeValidationInstructions` |
| Step 4 Context | `CodeValidationContext` |

### Registry design

Since the meta-pipeline generates code rather than extracting DB models, use a minimal tracking model:

```python
class GenerationRecord(SQLModel, table=True):
    __tablename__ = "creator_generation_records"
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str
    step_name_generated: str          # name of the step that was generated
    files_generated: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    is_valid: bool = False
    created_at: datetime

class StepCreatorRegistry(PipelineDatabaseRegistry, models=[GenerationRecord]):
    pass
```

### Strategy design

Single strategy (always applies):

```python
class DefaultCreatorStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [
            RequirementsAnalysisStep.create_definition(),
            CodeGenerationStep.create_definition(),
            PromptGenerationStep.create_definition(),
            CodeValidationStep.create_definition(),
        ]

class StepCreatorStrategies(PipelineStrategies, strategies=[DefaultCreatorStrategy]):
    pass
```

### Input data

```python
class StepCreatorInputData(PipelineInputData):
    description: str                    # NL description of desired step
    target_pipeline: str | None = None  # optional target pipeline name
    include_extraction: bool = True     # whether to generate extraction class
    include_transformation: bool = False
```

### Agent registry

```python
class StepCreatorAgentRegistry(AgentRegistry, agents={
    "requirements_analysis": RequirementsAnalysisInstructions,
    "code_generation": CodeGenerationInstructions,
    "prompt_generation": PromptGenerationInstructions,
    "code_validation": CodeValidationInstructions,
}):
    pass
```

---

## 10. Four-Step Data Flow Design

### Step 1: RequirementsAnalysisStep

**Purpose**: Parse NL description into structured requirements the LLM can use for code generation.

**LLM Input**: Natural language step description from `pipeline.validated_input.description`

**LLM Output** (RequirementsAnalysisInstructions):
```python
class FieldDefinition(BaseModel):
    name: str
    type_annotation: str      # e.g., "str", "float", "list[str]"
    description: str
    default: str | None = None
    is_required: bool = True

class ExtractionTarget(BaseModel):
    model_name: str
    fields: list[FieldDefinition]
    source_field_mapping: dict[str, str]  # instruction field -> model field

class RequirementsAnalysisInstructions(LLMResultMixin):
    step_name: str                        # e.g., "sentiment_analysis"
    step_class_name: str                  # e.g., "SentimentAnalysisStep"
    description: str                      # cleaned step description
    instruction_fields: list[FieldDefinition]
    context_fields: list[FieldDefinition]
    extraction_targets: list[ExtractionTarget]
    input_variables: list[str]            # variables step needs from pipeline context
    output_context_keys: list[str]        # keys step adds to pipeline context
```

**Context output** (RequirementsAnalysisContext):
```python
class RequirementsAnalysisContext(PipelineContext):
    step_name: str
    step_class_name: str
    instruction_fields: list[dict]
    context_fields: list[dict]
    extraction_targets: list[dict]
    input_variables: list[str]
    output_context_keys: list[str]
```

### Step 2: CodeGenerationStep

**Purpose**: Generate Python source code using Jinja2 templates populated with structured requirements.

**LLM Input**: Structured requirements from Step 1 context + template rendering parameters

**LLM Output** (CodeGenerationInstructions):
```python
class CodeGenerationInstructions(LLMResultMixin):
    imports: list[str]                    # additional imports needed
    prepare_calls_body: str               # Python code for prepare_calls() method body
    process_instructions_body: str        # Python code for process_instructions() method body
    extraction_method_body: str | None    # Python code for extraction default() method
    should_skip_condition: str | None     # Optional skip condition
```

**Template rendering**: `process_instructions()` takes these parameters + Step 1 context, renders Jinja2 templates to produce actual Python source strings.

**Context output** (CodeGenerationContext):
```python
class CodeGenerationContext(PipelineContext):
    step_code: str           # rendered step.py.j2 output
    instructions_code: str   # rendered instructions.py.j2 output
    extraction_code: str | None  # rendered extraction.py.j2 output (if applicable)
```

### Step 3: PromptGenerationStep

**Purpose**: Generate system and user prompts tailored to the step's requirements.

**LLM Input**: Requirements (Step 1) + generated code context (Step 2)

**LLM Output** (PromptGenerationInstructions):
```python
class PromptGenerationInstructions(LLMResultMixin):
    system_prompt_content: str
    user_prompt_template: str             # with {variable} placeholders
    required_variables: list[str]
    prompt_category: str
```

**Context output** (PromptGenerationContext):
```python
class PromptGenerationContext(PipelineContext):
    system_prompt: str
    user_prompt_template: str
    required_variables: list[str]
    prompt_yaml: str          # rendered prompts.yaml.j2 output
```

### Step 4: CodeValidationStep

**Purpose**: Validate all generated artifacts for syntax correctness and consistency.

**LLM Input**: All generated code + prompts from Steps 2-3

**Processing**: Combines LLM review with programmatic validation (ast.parse for Python syntax, template variable cross-check).

**LLM Output** (CodeValidationInstructions):
```python
class CodeValidationInstructions(LLMResultMixin):
    is_valid: bool
    issues: list[str]
    suggestions: list[str]
    naming_valid: bool
    imports_valid: bool
    type_annotations_valid: bool
```

**Context output** (CodeValidationContext):
```python
class CodeValidationContext(PipelineContext):
    is_valid: bool
    syntax_valid: bool        # from ast.parse (programmatic)
    llm_review_valid: bool    # from LLM review
    issues: list[str]
    all_artifacts: dict[str, str]  # filename -> content map
```

**Extraction**: GenerationRecordExtraction stores a GenerationRecord to DB.

---

## 11. Jinja2 Template Integration

### Dependency

Jinja2 is NOT currently in pyproject.toml. Add as optional dependency:
```toml
creator = ["jinja2>=3.0"]
```

### Environment setup (creator/templates/__init__.py)

```python
from jinja2 import Environment, PackageLoader

def get_template_env() -> Environment:
    return Environment(
        loader=PackageLoader("llm_pipeline.creator", "templates"),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
```

Custom filters needed:
- `snake_case`: CamelCase to snake_case conversion (reuse `llm_pipeline.naming.to_snake_case`)
- `camel_case`: snake_case to CamelCase
- `indent_code`: Proper Python indentation for code blocks

### Template rendering location

Template rendering happens inside `CodeGenerationStep.process_instructions()` and `PromptGenerationStep.process_instructions()`. These are pure computation (no I/O, no DB access) - they take LLM structured output, feed parameters to Jinja2 templates, and return PipelineContext with rendered strings.

This is appropriate because:
- PipelineTransformation is designed for data structure changes (DataFrame ops), not code generation
- process_instructions() is the canonical place for deriving context from LLM output
- Template rendering is deterministic computation, not a side effect

### Template files

**step.py.j2** - Generates step class with @step_definition decorator:
```
{# Variables: step_class_name, instructions_class_name, context_class_name,
   system_key, user_key, extractions, prepare_calls_body, process_instructions_body,
   imports #}
```

**instructions.py.j2** - Generates LLMResultMixin subclass:
```
{# Variables: class_name, fields (list of FieldDefinition), example_dict #}
```

**extraction.py.j2** - Generates PipelineExtraction subclass:
```
{# Variables: class_name, model_name, extraction_method_body #}
```

**prompts.yaml.j2** - Generates prompt seed dict definitions:
```
{# Variables: step_name, system_content, user_content, required_variables, category #}
```

---

## 12. Prompt Architecture for Meta-Steps

Following the demo pattern (db/prompt.py + demo/prompts.py), each meta-step needs system + user prompts seeded to DB.

### Prompt keys

| Step | System Key | User Key |
|------|-----------|----------|
| RequirementsAnalysisStep | `requirements_analysis` | `requirements_analysis` |
| CodeGenerationStep | `code_generation` | `code_generation` |
| PromptGenerationStep | `prompt_generation` | `prompt_generation` |
| CodeValidationStep | `code_validation` | `code_validation` |

### Seed function

```python
# creator/prompts.py
def seed_prompts(cls, engine):
    """Idempotently seed meta-pipeline prompts."""
    # Same pattern as demo/prompts.py
```

StepCreatorPipeline defines `seed_prompts()` classmethod calling this.

---

## 13. Scope Boundaries

### In scope (Task 45)
- StepCreatorPipeline class with all components (registry, strategies, agent registry)
- 4 step classes with @step_definition
- Instruction schemas (LLMResultMixin subclasses) for each step
- Context classes for each step
- Jinja2 templates in creator/templates/
- Prompt definitions in creator/prompts.py
- GenerationRecord SQLModel for tracking
- GenerationRecordExtraction for persisting results

### Out of scope
- Task 46: Docker sandbox (StepSandbox) - downstream, depends on 45
- Task 47: StepIntegrator (file writing, strategy updating, registry updating) - downstream, depends on 45+46
- The pipeline produces generated artifacts IN MEMORY (pipeline.context). Writing to disk is task 47.

---

## 14. Key Architecture Decisions

### Decision 1: Template-driven vs raw LLM code generation
**Choice**: Template-driven. LLM produces structured parameters, Jinja2 templates produce code.
**Rationale**: Much more reliable - LLM only decides WHAT to generate (field names, types, method bodies), templates handle boilerplate, imports, decorators, naming conventions.

### Decision 2: Registry approach
**Choice**: Minimal tracking model (GenerationRecord).
**Rationale**: PipelineDatabaseRegistry requires non-empty models list. GenerationRecord provides useful tracking and follows existing patterns. Enables task 47 to query what was generated.

### Decision 3: Single strategy
**Choice**: DefaultCreatorStrategy (always applies).
**Rationale**: No context-dependent branching needed for code generation. All 4 steps always run sequentially.

### Decision 4: Jinja2 as optional dependency
**Choice**: `creator = ["jinja2>=3.0"]` in pyproject.toml optional-dependencies.
**Rationale**: Not all users of llm-pipeline need code generation. Keeps core package lean.

### Decision 5: Step 4 naming (avoid ValidationContext collision)
**Choice**: `CodeValidationStep` / `CodeValidationInstructions` / `CodeValidationContext`.
**Rationale**: `ValidationContext` already exists in `llm_pipeline.types`. While namespace isolation via the creator package prevents runtime collision, explicit naming avoids import confusion.

### Decision 6: Template rendering in process_instructions()
**Choice**: Render Jinja2 templates inside process_instructions(), not in a PipelineTransformation.
**Rationale**: Transformations are designed for data structure changes (DataFrame operations). Template rendering is pure computation that derives context values from LLM output - exactly what process_instructions() is for.
