# Research Step 3: LLM-Driven Code Generation Patterns

## 1. Pydantic-AI Agent Architecture in llm-pipeline

### AgentRegistry (agent_registry.py)

Maps step names to output types at class definition time via `__init_subclass__`:

```python
class MyAgentRegistry(AgentRegistry, agents={
    "step_name": InstructionsClass,               # bare Type[BaseModel]
    "tool_step": AgentSpec(OutputType, tools=[fn]) # with tools
}):
    pass
```

Key methods:
- `get_output_type(step_name)` - returns BaseModel subclass (unwraps AgentSpec)
- `get_tools(step_name)` - returns tool callables list (empty for bare types)

### build_step_agent (agent_builders.py)

Factory that creates `Agent[StepDeps, Any]` instances:

```python
agent = build_step_agent(
    step_name="constraint_extraction",
    output_type=ConstraintExtractionInstructions,  # Pydantic model
    model="google-gla:gemini-2.0-flash-lite",
    system_instruction_key="constraint_extraction",
    retries=3,
    validators=[not_found_validator(), array_length_validator()],
    tools=[my_tool_fn],
)
```

Critical internals:
- `defer_model_check=True` always set (model resolved at run-time)
- `deps_type=StepDeps` for dependency injection
- `validation_context` lambda wires StepDeps.validation_context into Pydantic validators
- System prompt injected via `@agent.instructions` decorator, resolved from DB at runtime
- Output validators registered via `agent.output_validator(v)` loop
- Tools wrapped in `FunctionToolset` -> `EventEmittingToolset` chain

### StepDeps (agent_builders.py)

Dependency injection dataclass for pydantic-ai agents:

```python
@dataclass
class StepDeps:
    session: Any              # SQLModel Session
    pipeline_context: dict    # current pipeline context
    prompt_service: Any       # PromptService
    run_id: str
    pipeline_name: str
    step_name: str
    event_emitter: Any | None
    variable_resolver: Any | None
    array_validation: Any | None
    validation_context: Any | None
    extra: dict[str, Any]     # extensible bag
```

### Agent Execution Flow (pipeline.py execute())

1. Pipeline selects strategy via `strategy.can_handle(context)`
2. Strategy provides `StepDefinition` list via `get_steps()`
3. `StepDefinition.create_step(pipeline)` instantiates the step
4. Step's `prepare_calls()` returns list of `StepCallParams` dicts
5. For each call: `build_step_agent()` creates agent, `agent.run_sync()` executes
6. Output validators run automatically on structured output
7. `process_instructions()` extracts context for downstream steps

## 2. LLMResultMixin and Instruction Schema Patterns

### LLMResultMixin (step.py)

All instruction schemas inherit from this:

```python
class LLMResultMixin(BaseModel):
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0)
    notes: str | None = Field(default=None)

    # Self-validation at class definition time
    def __init_subclass__(cls, **kwargs):
        if hasattr(cls, 'example'):
            cls(**cls.example)  # validates example dict

    @classmethod
    def create_failure(cls, reason: str, **safe_defaults):
        return cls(confidence_score=0.0, notes=f"Failed: {reason}", **safe_defaults)
```

### Instruction Schema Pattern (from demo)

```python
class TopicExtractionInstructions(LLMResultMixin):
    topics: list[TopicItem] = []
    primary_topic: str = ""

    example: ClassVar[dict] = {
        "topics": [{"name": "ml", "relevance": 0.95}],
        "primary_topic": "ml",
        "confidence_score": 0.9,
    }
```

Key conventions:
- Class name: `{StepPrefix}Instructions` (enforced by @step_definition)
- All fields have defaults (LLM might omit)
- `example` ClassVar validates at class definition time
- Nested models (like TopicItem) are plain BaseModel, not LLMResultMixin
- `instructions_match()` in consensus treats LLMResultMixin fields (confidence_score, notes) as always matching

## 3. Step Definition Pattern

### @step_definition Decorator (step.py)

```python
@step_definition(
    instructions=SentimentAnalysisInstructions,
    default_system_key="sentiment_analysis",
    default_user_key="sentiment_analysis",
    default_extractions=[TopicExtraction],
    context=SentimentAnalysisContext,
)
class SentimentAnalysisStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {"text": self.pipeline.validated_input.text}}]

    def process_instructions(self, instructions):
        return SentimentAnalysisContext(sentiment=instructions[0].sentiment)
```

Enforced naming conventions:
- Step class: `{Prefix}Step`
- Instructions: `{Prefix}Instructions`
- Context: `{Prefix}Context`
- Transformation: `{Prefix}Transformation`

`create_definition()` classmethod generates `StepDefinition` for strategy registration.

### LLMStep Abstract Base (step.py)

Required implementation:
- `prepare_calls() -> List[StepCallParams]` - returns list of {variables: dict} for LLM calls

Optional overrides:
- `process_instructions(instructions) -> dict | PipelineContext` - extract context from results
- `should_skip() -> bool` - conditional execution
- `log_instructions(instructions)` - custom logging
- `extract_data(instructions)` - delegates to extraction classes

## 4. Prompt System

### Prompt Model (db/prompt.py)

```python
class Prompt(SQLModel, table=True):
    prompt_key: str          # e.g. "sentiment_analysis"
    prompt_name: str
    prompt_type: str         # "system" or "user"
    category: str | None
    step_name: str | None
    content: str             # template with {variable} placeholders
    required_variables: list[str] | None  # JSON column
    version: str = "1.0"
    is_active: bool = True
```

Unique constraint on (prompt_key, prompt_type).

### Prompt Resolution

1. **System prompts**: Resolved at agent creation via `@agent.instructions` decorator
   - Looks up by `prompt_key` + `prompt_type='system'` from DB
   - Optionally formatted with variable resolver variables
2. **User prompts**: Built per-call via `step.build_user_prompt(variables, prompt_service)`
   - Looks up by `prompt_key` + `prompt_type='user'` from DB
   - Formatted with `template.format(**variables)`
3. **Auto-discovery**: StepDefinition.create_step() tries `step_name.strategy_name` first, falls back to `step_name`

### YAML Prompt Loader (prompts/loader.py)

Required YAML fields: `prompt_key, name, type, category, step, version, content`

```yaml
prompt_key: sentiment_analysis
name: Sentiment Analysis System
type: system
category: text_analyzer
step: sentiment_analysis
version: "1.0"
content: |
  You are a sentiment analysis expert...
```

Variables auto-extracted from `{variable_name}` patterns in content.

### Demo Prompt Seeding (demo/prompts.py)

Uses Python dicts (not YAML files) with programmatic seeding:

```python
SENTIMENT_ANALYSIS_SYSTEM = {
    "prompt_key": "sentiment_analysis",
    "prompt_name": "Sentiment Analysis System",
    "prompt_type": "system",
    "content": "You are a sentiment analysis expert...",
    "required_variables": [],
}
```

## 5. Meta-Step Instruction Schema Designs

### RequirementsAnalysisInstructions

```python
class FieldDefinition(BaseModel):
    name: str
    python_type: str      # "str", "float", "list[str]", etc.
    description: str
    required: bool = True
    default: str | None = None

class ValidationRule(BaseModel):
    field_name: str
    rule_type: str        # "range", "regex", "enum", "custom"
    parameters: dict[str, Any] = {}

class ExtractionTarget(BaseModel):
    model_name: str       # SQLModel class name
    fields: list[str]
    source_step: str

class RequirementsAnalysisInstructions(LLMResultMixin):
    step_name: str = ""
    step_description: str = ""
    fields: list[FieldDefinition] = []
    validation_rules: list[ValidationRule] = []
    extraction_targets: list[ExtractionTarget] = []
    context_keys: list[str] = []         # keys this step adds to pipeline context
    input_dependencies: list[str] = []    # context keys this step reads
    needs_extraction: bool = False
    needs_transformation: bool = False
```

### CodeGenerationInstructions

```python
class CodeGenerationInstructions(LLMResultMixin):
    instructions_code: str = ""    # Python source for XxxInstructions class
    step_code: str = ""            # Python source for XxxStep class
    context_code: str = ""         # Python source for XxxContext class (if needed)
    extraction_code: str = ""      # Python source for XxxExtraction class (if needed)
    imports: list[str] = []        # required import statements
```

### PromptGenerationInstructions

```python
class PromptGenerationInstructions(LLMResultMixin):
    system_prompt_content: str = ""
    user_prompt_content: str = ""      # with {variable} placeholders
    prompt_key: str = ""
    required_variables: list[str] = []
```

### ValidationInstructions

```python
class ValidationInstructions(LLMResultMixin):
    is_valid: bool = False
    syntax_errors: list[str] = []
    naming_errors: list[str] = []
    consistency_errors: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
```

## 6. Output Validator Patterns for Code Generation

### Existing Validator Pattern (validators.py)

Factories return async callables compatible with `RunContext[StepDeps]`:

```python
def not_found_validator(indicators=None):
    async def _not_found_validator(ctx: RunContext[StepDeps], output: Any) -> Any:
        # validate, raise ModelRetry on failure
        return output
    return _not_found_validator
```

### Proposed Code Validation Validators

```python
import ast
import yaml

def python_syntax_validator(fields: list[str] | None = None):
    """Validate that string fields contain syntactically valid Python."""
    async def _validator(ctx: RunContext[StepDeps], output: Any) -> Any:
        target_fields = fields or ["step_code", "instructions_code", "extraction_code", "context_code"]
        for field_name in target_fields:
            code = getattr(output, field_name, None)
            if code:
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    raise ModelRetry(
                        f"Python syntax error in {field_name} at line {e.lineno}: {e.msg}\n"
                        f"Fix the code and try again."
                    )
        return output
    return _validator

def yaml_syntax_validator(fields: list[str] | None = None):
    """Validate that string fields contain valid YAML."""
    async def _validator(ctx: RunContext[StepDeps], output: Any) -> Any:
        target_fields = fields or ["yaml_content"]
        for field_name in target_fields:
            content = getattr(output, field_name, None)
            if content:
                try:
                    yaml.safe_load(content)
                except yaml.YAMLError as e:
                    raise ModelRetry(f"YAML syntax error in {field_name}: {e}")
        return output
    return _validator

def naming_convention_validator():
    """Validate generated code follows llm-pipeline naming conventions."""
    async def _validator(ctx: RunContext[StepDeps], output: Any) -> Any:
        code = getattr(output, "step_code", "")
        if code:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if "Step" in node.name and not node.name.endswith("Step"):
                        raise ModelRetry(f"Step class must end with 'Step': {node.name}")
        return output
    return _validator
```

Key: `ModelRetry` triggers pydantic-ai retry mechanism (up to `retries` times).

## 7. Prompt Engineering for Code Generation

### System Prompt Strategy

For CodeGenerationStep, the system prompt should include:
1. Role definition ("expert Python developer generating llm-pipeline step code")
2. Framework conventions (naming, base classes, imports)
3. Complete example of an existing step (TextAnalyzer demo as reference)
4. Output format instructions (each field is a separate Python source string)

### Example System Prompt Structure

```
You are a Python code generator for the llm-pipeline framework.

FRAMEWORK CONVENTIONS:
- Step classes inherit from LLMStep and end with "Step" suffix
- Instruction classes inherit from LLMResultMixin and end with "Instructions"
- Context classes inherit from PipelineContext and end with "Context"
- Extraction classes inherit from PipelineExtraction and end with "Extraction"
- Steps are decorated with @step_definition(instructions=..., context=...)
- prepare_calls() returns list of dicts with "variables" key
- process_instructions() returns a Context instance

REQUIRED IMPORTS:
from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition
from llm_pipeline.context import PipelineContext
from llm_pipeline.extraction import PipelineExtraction
from pydantic import BaseModel, Field
from typing import ClassVar, list, Optional

EXAMPLE - Complete step definition:
[TextAnalyzer demo code inserted here]

Generate code following these exact patterns. Each code field must be valid Python.
```

### User Prompt Strategy

```
Generate pipeline step code for the following requirements:

Step Name: {step_name}
Description: {step_description}
Fields: {fields_json}
Validation Rules: {validation_rules_json}
Context Keys: {context_keys_json}
Needs Extraction: {needs_extraction}
Input Dependencies: {input_dependencies_json}
```

### Key Prompt Engineering Principles

1. **Structured output over free-form**: Use Pydantic schemas to force LLM into generating separate code blocks per field, not one large blob
2. **Concrete examples**: Include full working examples from the demo pipeline in system prompt
3. **Naming constraint reinforcement**: Repeat naming rules multiple times (system prompt + validation)
4. **Retry-driven correction**: Use output validators with ModelRetry for syntax errors - pydantic-ai will retry with error message
5. **Separation of concerns**: Each code artifact in its own field enables targeted validation
6. **Template variables**: Keep {variable} placeholders simple - match prepare_calls() output exactly

## 8. Jinja2 Templates (creator/templates/)

Templates serve as scaffolding that the LLM fills in. Alternative to pure LLM generation:

### Hybrid Approach

1. LLM generates field definitions and logic snippets
2. Jinja2 templates provide structural boilerplate
3. Template rendering produces final Python/YAML files

```jinja2
{# step.py.j2 #}
from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition
from llm_pipeline.context import PipelineContext
from pydantic import BaseModel, Field
from typing import ClassVar


class {{ step_name }}Instructions(LLMResultMixin):
    """Structured output for {{ step_description }}."""
{% for field in fields %}
    {{ field.name }}: {{ field.python_type }} = {{ field.default }}
{% endfor %}

    example: ClassVar[dict] = {{ example_dict }}


{% if context_keys %}
class {{ step_name }}Context(PipelineContext):
    """Context produced by {{ step_name }}."""
{% for key in context_keys %}
    {{ key.name }}: {{ key.python_type }}
{% endfor %}
{% endif %}


@step_definition(
    instructions={{ step_name }}Instructions,
    default_system_key="{{ prompt_key }}",
    default_user_key="{{ prompt_key }}",
{% if context_keys %}
    context={{ step_name }}Context,
{% endif %}
)
class {{ step_name }}Step(LLMStep):
    """{{ step_description }}"""

    def prepare_calls(self):
        return [{"variables": {{ variables_dict }}}]

{% if context_keys %}
    def process_instructions(self, instructions):
        return {{ step_name }}Context(
{% for key in context_keys %}
            {{ key.name }}=instructions[0].{{ key.name }},
{% endfor %}
        )
{% endif %}
```

### Template vs Pure LLM Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| Pure LLM | Flexible, handles edge cases | Syntax errors, inconsistent formatting |
| Pure Jinja2 | Guaranteed syntax, consistent | Rigid, can't handle complex logic |
| Hybrid (recommended) | Best of both - structure from templates, logic from LLM | More complex pipeline, two-phase generation |

**Recommendation**: Use Jinja2 templates for structural scaffolding (imports, class declarations, decorators) and LLM for content generation (field definitions, prepare_calls logic, extraction logic). The RequirementsAnalysisStep output feeds directly into Jinja2 template variables.

## 9. Pipeline Wiring for creator/

### StepCreatorPipeline Structure

```python
# creator/meta_pipeline.py

class StepCreatorRegistry(PipelineDatabaseRegistry, models=[]):
    pass  # no DB models to extract in meta-pipeline

class StepCreatorAgentRegistry(AgentRegistry, agents={
    "requirements_analysis": RequirementsAnalysisInstructions,
    "code_generation": CodeGenerationInstructions,
    "prompt_generation": PromptGenerationInstructions,
    "validation": ValidationInstructions,
}):
    pass

class StepCreatorStrategy(PipelineStrategy):
    def can_handle(self, context): return True
    def get_steps(self):
        return [
            RequirementsAnalysisStep.create_definition(),
            CodeGenerationStep.create_definition(),
            PromptGenerationStep.create_definition(),
            ValidationStep.create_definition(),
        ]

class StepCreatorStrategies(PipelineStrategies, strategies=[StepCreatorStrategy]):
    pass

class StepCreatorPipeline(PipelineConfig,
                          registry=StepCreatorRegistry,
                          strategies=StepCreatorStrategies,
                          agent_registry=StepCreatorAgentRegistry):
    INPUT_DATA = StepCreatorInputData  # NL description input
```

### Data Flow Between Steps

```
NL Description
    |
    v
[RequirementsAnalysisStep]
    | -> RequirementsAnalysisContext (fields, rules, targets)
    v
[CodeGenerationStep]
    | -> CodeGenerationContext (step_code, instructions_code, ...)
    v
[PromptGenerationStep]
    | -> PromptGenerationContext (system_prompt, user_prompt)
    v
[ValidationStep]
    | -> ValidationContext (is_valid, errors, warnings)
    v
Generated Artifacts (ready for integration by Task 47)
```

## 10. Validation Strategy for Generated Code

### Multi-Layer Validation

1. **Output Validator Layer** (pydantic-ai retries):
   - `python_syntax_validator()` - ast.parse() on code fields
   - `naming_convention_validator()` - check Step/Instructions/Context suffixes
   - Runs automatically during agent execution, triggers retry on failure

2. **ValidationStep Layer** (LLM-based review):
   - LLM reviews all artifacts for logical consistency
   - Checks field references match between Instructions and prepare_calls
   - Checks context key usage across steps

3. **Post-Pipeline Layer** (Task 46 - Docker sandbox):
   - Import-test generated code in isolated container
   - Run with sample data
   - Out of scope for Task 45 (handled by Task 46)

### ast.parse Validation Details

```python
import ast

def validate_python_code(code: str) -> tuple[bool, str | None]:
    try:
        tree = ast.parse(code)
        # Additional checks
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"
```

## 11. Existing Patterns Summary Table

| Component | Location | Pattern | Relevance to Meta-Pipeline |
|-----------|----------|---------|---------------------------|
| AgentRegistry | agent_registry.py | `__init_subclass__` with agents={} | StepCreatorAgentRegistry follows same pattern |
| build_step_agent | agent_builders.py | Factory with @agent.instructions | Each meta-step uses same agent builder |
| LLMResultMixin | step.py | BaseModel with confidence_score, notes | All 4 instruction schemas inherit from it |
| @step_definition | step.py | Decorator enforcing naming conventions | All 4 meta-steps use same decorator |
| PipelineContext | context.py | BaseModel for inter-step data | Each meta-step produces context for next |
| Prompt (DB) | db/prompt.py | SQLModel with prompt_key/type/content | Meta-pipeline prompts stored same way |
| PromptService | prompts/service.py | Runtime prompt resolution from DB | Unchanged - meta-steps use same service |
| Validators | validators.py | Factory -> async callable pattern | New validators follow same pattern |
| Demo Pipeline | demo/pipeline.py | Complete working example | Reference implementation for code gen prompts |
