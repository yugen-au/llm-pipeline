# LLM Pipeline - Codebase Architecture Analysis

**Date**: 2026-02-10
**Version**: 0.1.0
**Analysis Scope**: Complete codebase architecture review

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architectural Overview](#architectural-overview)
3. [Module Structure](#module-structure)
4. [Core Design Patterns](#core-design-patterns)
5. [Data Flow Architecture](#data-flow-architecture)
6. [Class Hierarchies](#class-hierarchies)
7. [Configuration System](#configuration-system)
8. [Extension Points](#extension-points)
9. [Database Architecture](#database-architecture)
10. [Prompt Management System](#prompt-management-system)
11. [State Tracking & Caching](#state-tracking--caching)
12. [Validation Architecture](#validation-architecture)
13. [Testing Strategy](#testing-strategy)
14. [Key Design Decisions](#key-design-decisions)
15. [Integration Examples](#integration-examples)

---

## Executive Summary

The `llm-pipeline` framework is a declarative orchestration system for building multi-step LLM-powered data processing pipelines. Extracted from the logistics-intelligence project as a standalone reusable library, it provides a highly opinionated architecture that enforces clear separation of concerns between configuration, execution, and data transformation.

### Core Philosophy

**Declarative over Imperative**: Pipelines are defined through class-level configuration rather than procedural code. The framework uses Python's `__init_subclass__` protocol extensively to validate naming conventions and enforce architectural constraints at class definition time.

**Three-tier Separation**:
1. **Context** - Derived metadata and step results
2. **Data** - Input and transformed data
3. **Extractions** - Database instances created from LLM results

**Automatic State Tracking**: Every step execution is recorded for audit trails, caching, and partial regeneration capabilities.

### Key Capabilities

- Strategy-based execution with context-driven step selection
- Database-backed prompt versioning with automatic variable extraction
- Comprehensive validation at extraction time (before database insertion)
- Caching with prompt version awareness
- Read-only session wrappers to prevent accidental writes
- Type-safe transformations with input/output validation
- Consensus polling for critical LLM calls
- Flexible provider abstraction (Gemini implementation included)

---

## Architectural Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Pipeline Configuration                   │
│  (PipelineConfig - owns context, data, extractions)         │
└───────────────┬─────────────────────────────────────────────┘
                │
                ├─► Strategies (PipelineStrategies)
                │   └─► Strategy Selection (can_handle)
                │       └─► Step Definitions (StepDefinition)
                │
                ├─► Steps (LLMStep)
                │   ├─► prepare_calls() → StepCallParams
                │   ├─► create_llm_call() → ExecuteLLMStepParams
                │   └─► process_instructions() → Context
                │
                ├─► Extractions (PipelineExtraction)
                │   └─► extract() → List[SQLModel]
                │
                ├─► Transformations (PipelineTransformation)
                │   └─► transform() → Data
                │
                ├─► Registry (PipelineDatabaseRegistry)
                │   └─► MODELS in FK order
                │
                └─► State Tracking
                    ├─► PipelineStepState (audit/cache)
                    └─► PipelineRunInstance (traceability)
```

### Data Flow Through Pipeline

```
1. Raw Data Input
   ↓
2. Sanitization (pipeline.sanitize())
   ↓
3. Strategy Selection (per-step via can_handle())
   ↓
4. Step Execution Loop
   │
   ├─► Step.prepare_calls()
   │   └─► Variables for prompt templates
   │
   ├─► Prompt Retrieval (PromptService)
   │   ├─► System instruction template
   │   └─► User prompt template
   │
   ├─► LLM Call (via Provider)
   │   ├─► Schema formatting
   │   ├─► Validation (structure + Pydantic)
   │   └─► Retry with rate limiting
   │
   ├─► Instructions Processing
   │   └─► Context extraction (derived values)
   │
   ├─► Data Transformation (optional)
   │   └─► Type-validated data structure changes
   │
   └─► Extraction (optional)
       ├─► LLM results → SQLModel instances
       └─► Instance validation (NaN, NULL, FK checks)
   ↓
5. State Persistence
   ├─► PipelineStepState (for caching)
   └─► PipelineRunInstance (for traceability)
   ↓
6. Pipeline.save()
   └─► Database insertion in FK order
```

---

## Module Structure

### Physical Organization

```
llm_pipeline/
├── __init__.py                 # Public API exports
│
├── pipeline.py                 # PipelineConfig (orchestrator)
├── step.py                     # LLMStep, step_definition decorator
├── strategy.py                 # PipelineStrategy, StepDefinition
├── context.py                  # PipelineContext base class
├── extraction.py               # PipelineExtraction base class
├── transformation.py           # PipelineTransformation base class
├── registry.py                 # PipelineDatabaseRegistry base class
├── state.py                    # State tracking models
├── types.py                    # Shared type definitions
│
├── llm/
│   ├── __init__.py
│   ├── provider.py             # LLMProvider abstract base
│   ├── gemini.py               # GeminiProvider implementation
│   ├── executor.py             # execute_llm_step() function
│   ├── schema.py               # Schema formatting for LLMs
│   ├── validation.py           # Output validation utilities
│   └── rate_limiter.py         # Rate limiting for API calls
│
├── prompts/
│   ├── __init__.py
│   ├── loader.py               # YAML → database sync
│   ├── service.py              # PromptService for retrieval
│   └── variables.py            # VariableResolver protocol
│
├── session/
│   ├── __init__.py
│   └── readonly.py             # ReadOnlySession wrapper
│
└── db/
    ├── __init__.py             # Database initialization
    └── prompt.py               # Prompt model

tests/
└── test_pipeline.py            # Comprehensive test suite
```

### Module Responsibilities

**Core Modules**:
- `pipeline.py` - Orchestration, execution loop, caching, state management
- `step.py` - Step interface, instruction processing, LLM call preparation
- `strategy.py` - Strategy pattern implementation, step selection logic
- `context.py` - Derived context values (lightweight Pydantic models)

**Data Processing**:
- `extraction.py` - LLM results → validated database instances
- `transformation.py` - Type-safe data transformations
- `registry.py` - Database model registration with FK ordering

**LLM Integration**:
- `llm/provider.py` - Provider abstraction
- `llm/executor.py` - Unified execution function
- `llm/gemini.py` - Gemini API implementation
- `llm/schema.py` - Schema flattening for LLM prompts
- `llm/validation.py` - Multi-layered validation
- `llm/rate_limiter.py` - Sliding window rate limiter

**Prompt System**:
- `prompts/loader.py` - YAML file synchronization
- `prompts/service.py` - Database retrieval with template formatting
- `prompts/variables.py` - Variable resolution protocol
- `db/prompt.py` - Versioned prompt storage model

**Infrastructure**:
- `state.py` - Audit trail and caching tables
- `session/readonly.py` - Read-only session enforcement
- `db/__init__.py` - Auto-SQLite initialization

---

## Core Design Patterns

### 1. Declarative Configuration Pattern

Classes use `__init_subclass__` to validate and configure at definition time:

```python
# Pattern: Class-level configuration with validation
class MyPipeline(PipelineConfig,
                registry=MyRegistry,
                strategies=MyStrategies):
    pass  # All configuration happens at class definition time

# Enforces naming conventions
class MyRegistry(PipelineDatabaseRegistry, models=[Model1, Model2]):
    pass  # Must end with 'Registry'

class MyStrategies(PipelineStrategies, strategies=[Strategy1]):
    pass  # Must end with 'Strategies'
```

**Validation occurs at import time**:
- Naming convention enforcement (Pipeline, Registry, Strategies, Step, Extraction, etc.)
- Name matching validation (TestPipeline → TestRegistry, TestStrategies)
- FK dependency ordering verification

### 2. Step Definition Factory Pattern

The `@step_definition` decorator creates a factory method:

```python
@step_definition(
    instructions=MyInstructions,        # Pydantic result class
    default_system_key="my_step",       # Prompt key
    default_user_key="my_step",
    default_extractions=[MyExtraction],  # Data extraction classes
    default_transformation=MyTransform,  # Data transformation
    context=MyContext,                   # Context contribution
)
class MyStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        # Return list of LLM calls to make
        pass

    def process_instructions(self, instructions) -> MyContext:
        # Extract derived values from LLM results
        pass
```

**Auto-generates**:
- `create_definition()` class method
- Validates naming (MyStep → MyInstructions, MyTransformation, MyContext)
- Stores configuration as class attributes

### 3. Strategy Pattern with Auto-naming

```python
class LaneBasedStrategy(PipelineStrategy):  # Suffix required
    # Auto-generates:
    # - NAME = "lane_based" (snake_case)
    # - DISPLAY_NAME = "Lane Based" (title case)

    def can_handle(self, context: Dict[str, Any]) -> bool:
        return context.get("table_type") == "lane_based"

    def get_steps(self) -> List[StepDefinition]:
        return [
            Step1.create_definition(),
            Step2.create_definition(
                system_instruction_key="custom.key"  # Override default
            )
        ]
```

### 4. Smart Method Detection Pattern

Both `PipelineExtraction` and `PipelineTransformation` use smart method detection:

```python
# Priority 1: Explicit 'default' method
class MyExtraction(PipelineExtraction, model=MyModel):
    def default(self, results):
        return instances

# Priority 2: Strategy-specific methods
class MyExtraction(PipelineExtraction, model=MyModel):
    def lane_based(self, results):    # Matches strategy.name
        return instances

    def destination_based(self, results):
        return instances

# Priority 3: Single custom method (any name)
class MyExtraction(PipelineExtraction, model=MyModel):
    def extract_widgets(self, results):  # Auto-detected
        return instances
```

### 5. StepKeyDict Pattern

Special dictionary that accepts both strings and Step classes as keys:

```python
# Access by string
pipeline.data["widget_detection"] = df

# Access by class (auto-converts to snake_case)
pipeline.data[WidgetDetectionStep] = df  # → "widget_detection"

# Enables type-safe access in steps
previous_data = self.pipeline.get_data(PreviousStep)
```

### 6. Read-Only Session Pattern

Prevents accidental database writes during step execution:

```python
# During step execution
self.pipeline.session.exec(select(Model))  # ✓ Allowed
self.pipeline.session.add(instance)        # ✗ Raises RuntimeError

# Internal access to real session
self.pipeline._real_session.add(instance)  # ✓ Used by framework
```

---

## Data Flow Architecture

### Three-Tier Data Model

```
┌──────────────────────────────────────────────────────────┐
│ CONTEXT (pipeline.context)                               │
│ - Derived values from LLM instructions                   │
│ - Read-write dict merged from step contexts              │
│ - Used for strategy selection                            │
│ - Example: {"table_type": "lane_based", "has_zones": T} │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ DATA (pipeline.data - StepKeyDict)                       │
│ - Transformed data at each step                          │
│ - Keys: "raw", "sanitized", step_name                    │
│ - get_data("current") returns latest non-raw            │
│ - Example: DataFrame, dict, list                         │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ EXTRACTIONS (pipeline.extractions)                       │
│ - Dict[Type[SQLModel], List[SQLModel]]                   │
│ - Validated instances ready for DB insertion             │
│ - Ordered by FK dependencies                             │
│ - Example: {Lane: [lane1, lane2], Rate: [rate1, ...]}   │
└──────────────────────────────────────────────────────────┘
```

### Step Execution Flow Detail

```python
# In pipeline.execute()
for step_index in range(max_steps):
    # 1. Strategy Selection
    for strategy in self._strategies:
        if strategy.can_handle(self.context):
            step_def = strategy.get_steps()[step_index]
            break

    # 2. Step Creation
    step = step_def.create_step(pipeline=self)

    # 3. Skip Check
    if step.should_skip():
        continue

    # 4. Cache Check
    input_hash = self._hash_step_inputs(step, step_num)
    if use_cache:
        cached_state = self._find_cached_state(step, input_hash)
        if cached_state:
            # Load from cache
            instructions = self._load_from_cache(cached_state, step)
            self._reconstruct_extractions_from_cache(cached_state, step_def)

    if not cached_state:
        # 5. LLM Call Preparation
        call_params = step.prepare_calls()  # Returns List[StepCallParams]

        # 6. LLM Execution
        instructions = []
        for params in call_params:
            call_kwargs = step.create_llm_call(**params)
            call_kwargs["provider"] = self._provider
            call_kwargs["prompt_service"] = prompt_service

            if use_consensus:
                instruction = self._execute_with_consensus(...)
            else:
                instruction = execute_llm_step(**call_kwargs)

            instructions.append(instruction)

    # 7. Context Update
    new_context = step.process_instructions(instructions)
    self._validate_and_merge_context(step, new_context)

    # 8. Data Transformation (optional)
    if step._transformation:
        transformation = step._transformation(self)
        current_data = self.get_data("current")
        transformed = transformation.transform(current_data, instructions)
        self.set_data(transformed, step_name=step.step_name)

    # 9. Extraction (optional)
    step.extract_data(instructions)

    # 10. State Persistence
    self._save_step_state(step, step_num, instructions, input_hash, ...)

    # 11. Post-Action Hook
    if step_def.action_after:
        action_method = getattr(self, f"_{step_def.action_after}")
        action_method(self.context)
```

### Execution Order Validation

The framework builds execution graphs and validates access:

```python
# Built during __init__
self._step_order = {StepClass: position}
self._model_extraction_step = {ModelClass: StepClass}

# Validated on access
def get_data(self, key):
    if isinstance(key, type) and key in self._step_order:
        self._validate_step_access(key, "data")
    return self.data.get(key)

# Prevents accessing future step data
try:
    data = pipeline.get_data(FutureStep)  # Current step is 1, FutureStep is 3
except ValueError:
    # "Step execution order error: Step 1 attempts to access data from Step 3"
```

---

## Class Hierarchies

### PipelineConfig Hierarchy

```
ABC
 └── PipelineConfig (llm_pipeline/pipeline.py)
      ├── Abstract Methods: None (uses subclass validation)
      ├── Properties:
      │    ├── instructions (read-only MappingProxyType)
      │    ├── context (read-write dict)
      │    └── pipeline_name (auto-derived)
      ├── Core Methods:
      │    ├── execute() - Main execution loop
      │    ├── save() - Persist extractions to DB
      │    ├── get_data() / set_data()
      │    ├── get_extractions()
      │    └── clear_cache()
      └── Subclass Requirements:
           ├── REGISTRY: ClassVar[Type[PipelineDatabaseRegistry]]
           ├── STRATEGIES: ClassVar[Type[PipelineStrategies]]
           └── Naming: Must end with "Pipeline"
```

### LLMStep Hierarchy

```
ABC
 └── LLMStep (llm_pipeline/step.py)
      ├── Abstract Methods:
      │    └── prepare_calls() -> List[StepCallParams]
      ├── Overridable Methods:
      │    ├── process_instructions() -> Dict[str, Any]
      │    ├── should_skip() -> bool
      │    └── log_instructions()
      ├── Framework Methods:
      │    ├── create_llm_call() - Prepare ExecuteLLMStepParams
      │    ├── extract_data() - Delegates to extraction classes
      │    └── store_extractions() - Add to pipeline
      └── Subclass Requirements:
           ├── Decorated with @step_definition
           ├── Naming: Must end with "Step"
           └── Associated classes follow naming conventions
```

### PipelineStrategy Hierarchy

```
ABC
 └── PipelineStrategy (llm_pipeline/strategy.py)
      ├── Abstract Methods:
      │    ├── can_handle(context: Dict) -> bool
      │    └── get_steps() -> List[StepDefinition]
      ├── Auto-Generated:
      │    ├── NAME (snake_case class name)
      │    ├── DISPLAY_NAME (title case)
      │    ├── name property
      │    └── display_name property
      └── Subclass Requirements:
           └── Naming: Must end with "Strategy"
```

### PipelineExtraction Hierarchy

```
ABC
 └── PipelineExtraction (llm_pipeline/extraction.py)
      ├── Class Variables:
      │    └── MODEL: ClassVar[Type[SQLModel]]
      ├── Framework Methods:
      │    ├── extract() - Smart method detection
      │    ├── _validate_instance() - Pre-insert validation
      │    └── _validate_instances() - Batch validation
      ├── Custom Methods (auto-detected):
      │    ├── default(results) -> List[SQLModel]
      │    ├── {strategy_name}(results) -> List[SQLModel]
      │    └── Any single method
      └── Subclass Requirements:
           ├── model parameter in class definition
           ├── Naming: Must end with "Extraction"
           └── MODEL must be in pipeline's REGISTRY
```

### PipelineTransformation Hierarchy

```
ABC
 └── PipelineTransformation (llm_pipeline/transformation.py)
      ├── Class Variables:
      │    ├── INPUT_TYPE: ClassVar[Type]
      │    └── OUTPUT_TYPE: ClassVar[Type]
      ├── Framework Methods:
      │    ├── transform() - Smart method detection + validation
      │    ├── _validate_input()
      │    └── _validate_output()
      ├── Custom Methods (auto-detected):
      │    ├── default(data, instructions) -> Data
      │    ├── {strategy_name}(data, instructions) -> Data
      │    └── Any single method
      │    └── (No methods = passthrough)
      └── Subclass Requirements:
           ├── input_type and output_type in class definition
           └── Naming convention recommended (not enforced)
```

### Registry & Strategies Hierarchies

```
ABC                                ABC
 └── PipelineDatabaseRegistry       └── PipelineStrategies
      ├── MODELS: ClassVar               ├── STRATEGIES: ClassVar
      ├── get_models()                   ├── create_instances()
      └── Requirements:                  └── Requirements:
           ├── models parameter               ├── strategies parameter
           └── FK ordering                    └── Naming: *Strategies
```

---

## Configuration System

### Declarative Configuration Layers

```
Layer 1: Class Definition
┌──────────────────────────────────────────────────────────┐
│ class MyPipeline(PipelineConfig,                         │
│                 registry=MyRegistry,                     │
│                 strategies=MyStrategies):                │
│     pass                                                 │
└──────────────────────────────────────────────────────────┘
         │
         ├─► Validates naming conventions
         ├─► Sets REGISTRY and STRATEGIES class variables
         └─► Validates name matching

Layer 2: Registry Definition
┌──────────────────────────────────────────────────────────┐
│ class MyRegistry(PipelineDatabaseRegistry,               │
│                  models=[Vendor, RateCard, Lane]):      │
│     pass                                                 │
└──────────────────────────────────────────────────────────┘
         │
         ├─► Validates FK dependencies
         └─► Sets insertion order

Layer 3: Strategies Definition
┌──────────────────────────────────────────────────────────┐
│ class MyStrategies(PipelineStrategies,                   │
│                    strategies=[Strategy1, Strategy2]):  │
│     pass                                                 │
└──────────────────────────────────────────────────────────┘
         │
         └─► Creates strategy instances

Layer 4: Step Definition
┌──────────────────────────────────────────────────────────┐
│ @step_definition(                                        │
│     instructions=MyInstructions,                         │
│     default_system_key="my_step",                       │
│     default_user_key="my_step",                         │
│     default_extractions=[MyExtraction],                 │
│     default_transformation=MyTransform,                 │
│     context=MyContext,                                  │
│ )                                                        │
│ class MyStep(LLMStep):                                  │
│     ...                                                  │
└──────────────────────────────────────────────────────────┘
         │
         ├─► Validates naming conventions
         ├─► Stores config as class attributes
         └─► Generates create_definition() method

Layer 5: Strategy Step Configuration
┌──────────────────────────────────────────────────────────┐
│ class MyStrategy(PipelineStrategy):                      │
│     def get_steps(self):                                │
│         return [                                        │
│             Step1.create_definition(),                  │
│             Step2.create_definition(                    │
│                 system_instruction_key="custom.key",   │
│                 extractions=[CustomExtraction],        │
│             )                                          │
│         ]                                               │
└──────────────────────────────────────────────────────────┘
         │
         └─► Overrides defaults per strategy
```

### Runtime Configuration

```python
# Instantiation-time configuration
pipeline = MyPipeline(
    # Database
    session=session,           # Explicit session (highest priority)
    engine=engine,             # Explicit engine (or auto-SQLite)

    # LLM
    provider=GeminiProvider(), # Required for execute()

    # Prompts
    variable_resolver=resolver,  # Optional variable class resolution

    # Execution
    strategies=[Strategy1()],  # Override class-level strategies
)

# Execute-time configuration
pipeline.execute(
    data=raw_data,
    initial_context={"key": "value"},
    use_cache=True,              # Enable step caching
    consensus_polling={          # Consensus mode
        "enable": True,
        "consensus_threshold": 3,
        "maximum_step_calls": 5,
    }
)
```

---

## Extension Points

### 1. Custom LLM Provider

```python
class CustomProvider(LLMProvider):
    def call_structured(
        self,
        prompt: str,
        system_instruction: str,
        result_class: Type[BaseModel],
        max_retries: int = 3,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        # 1. Format request for your LLM API
        # 2. Make API call with retry logic
        # 3. Parse and validate response
        # 4. Return validated dict or None
        pass

# Usage
pipeline = MyPipeline(provider=CustomProvider())
```

### 2. Custom Sanitization

```python
class MyPipeline(PipelineConfig, ...):
    def sanitize(self, data: Any) -> str:
        """Custom sanitization for specific data types."""
        if isinstance(data, pd.DataFrame):
            return data.to_csv(index=False)
        return super().sanitize(data)
```

### 3. Custom Variable Resolver

```python
class MyVariableResolver:
    def resolve(
        self, prompt_key: str, prompt_type: str
    ) -> Optional[Type[BaseModel]]:
        # Look up variable class for this prompt
        # Return PromptVariables.System or PromptVariables.User class
        return my_registry.get(prompt_key, prompt_type)

pipeline = MyPipeline(variable_resolver=MyVariableResolver())
```

### 4. Step Post-Actions

```python
# In strategy
StepDefinition(
    step_class=MyStep,
    ...,
    action_after="validate_rates"  # Method name
)

# In pipeline
class MyPipeline(PipelineConfig, ...):
    def _validate_rates(self, context: Dict[str, Any]):
        """Called after step execution."""
        # Custom validation or side effects
        pass
```

### 5. Custom Extraction Validation

```python
class MyExtraction(PipelineExtraction, model=MyModel):
    def _validate_instance(self, instance: SQLModel, index: int):
        """Override for custom validation."""
        super()._validate_instance(instance, index)

        # Custom business logic validation
        if instance.rate < 0:
            raise ValueError(f"Invalid rate at {index}: negative value")
```

---

## Database Architecture

### Schema Relationships

```
┌───────────────────────────┐
│ prompts                   │
│ - id (PK)                 │
│ - prompt_key              │
│ - prompt_type             │
│ - content                 │
│ - required_variables      │
│ - version                 │
│ - is_active               │
└───────────────────────────┘

┌───────────────────────────┐         ┌──────────────────────────┐
│ pipeline_step_states      │         │ pipeline_run_instances   │
│ - id (PK)                 │         │ - id (PK)                │
│ - pipeline_name           │         │ - run_id                 │
│ - run_id                  │◄────────│ - model_type             │
│ - step_name               │         │ - model_id               │
│ - step_number             │         │ - created_at             │
│ - input_hash              │         └──────────────────────────┘
│ - result_data (JSON)      │                    │
│ - context_snapshot (JSON) │                    │
│ - prompt_version          │                    │
│ - execution_time_ms       │                    ▼
│ - created_at              │         ┌──────────────────────────┐
└───────────────────────────┘         │ Domain Models            │
                                      │ (User-defined)           │
                                      │ - Vendor                 │
                                      │ - RateCard               │
                                      │ - Lane                   │
                                      │ - Rate                   │
                                      └──────────────────────────┘
```

### FK Dependency Validation

The framework validates FK ordering at initialization:

```python
# In __init__
self._validate_foreign_key_dependencies()

# Example error
ValueError:
  Foreign key dependency error in MyRegistry:
    'Rate' at position 1, but FK to 'Lane' at position 2.
  Move 'Lane' before 'Rate'.
```

**Detection mechanism**:
1. Inspects SQLAlchemy table metadata for `column.foreign_keys`
2. Resolves FK to target table via `fk.column.table.name`
3. Validates FK target appears earlier in `MODELS` list
4. Raises error with correction instructions

### Registry Extraction Order Validation

```python
# Also validates extraction order matches registry order
self._validate_registry_order()

# Example error
ValueError:
  Extraction order mismatch in MyRegistry:
    'Vendor' before 'RateCard' in registry, but extracted later.
  Reorder registry to match extraction order.
```

### Auto-SQLite Initialization

```python
# Default: .llm_pipeline/pipeline.db in cwd
db_path = Path.cwd() / ".llm_pipeline" / "pipeline.db"

# Override via environment
export LLM_PIPELINE_DB="/path/to/custom.db"

# Or explicit engine
pipeline = MyPipeline(engine=create_engine("postgresql://..."))
```

---

## Prompt Management System

### YAML → Database Sync

```yaml
# prompts/my_step/system_instruction.yaml
prompt_key: my_step.system_instruction
name: My Step System Instruction
type: system
category: processing
step: my_step
version: "1.2"
description: System instruction for processing widgets
is_active: true
content: |
  You are analyzing widget data.
  Context: {context_var}
  Process carefully.
```

**Sync process**:

```python
from llm_pipeline.prompts.loader import sync_prompts

# Sync from YAML to database
sync_prompts(engine, prompts_dir=Path("./prompts"))

# Behavior:
# - Inserts new prompts (new prompt_key + type combination)
# - Updates if version > current version
# - Skips if version unchanged (idempotent)
# - Auto-extracts required_variables from content
# - Force flag updates all regardless of version
```

### Prompt Retrieval

```python
# In execute_llm_step()
prompt_service = PromptService(session)

# System prompt with variables
system_instruction = prompt_service.get_system_prompt(
    "my_step.system_instruction",
    variables={"context_var": "value"},
    variable_instance=system_vars,  # For error reporting
)

# User prompt with variables
user_prompt = prompt_service.get_user_prompt(
    "my_step.user_prompt",
    variables={"data": sanitized_data},
    variable_instance=user_vars,
)
```

### Prompt Key Auto-Discovery

```python
# StepDefinition.create_step() auto-discovers prompts:

# Priority 1: Strategy-level (step_name.strategy_name)
#   Example: "constraint_extraction.lane_based"

# Priority 2: Step-level (step_name)
#   Example: "constraint_extraction"

# Priority 3: Explicit keys passed to create_definition()
Step.create_definition(
    system_instruction_key="custom.key",
    user_prompt_key="custom.user"
)
```

### Variable Validation

```python
# If template variable missing:
ValueError:
  User prompt template variable 'data' not provided.

  Template requires:  ['data', 'table_type']
  Class defines:      ['data']
  Runtime provided:   ['data']

  Missing from class: ['table_type']
  ACTION: Add missing variables to prompts/my_step/user_prompt.yaml
```

---

## State Tracking & Caching

### PipelineStepState Model

```python
# Records every step execution
PipelineStepState:
    pipeline_name: str           # "rate_card_parser"
    run_id: str                  # UUID for this pipeline run
    step_name: str               # "constraint_extraction"
    step_number: int             # Execution order (1, 2, 3...)
    input_hash: str              # SHA256(step inputs)
    result_data: dict            # Serialized instructions
    context_snapshot: dict       # Context at step completion
    prompt_system_key: str       # Prompt used
    prompt_user_key: str
    prompt_version: str          # For cache invalidation
    model: str                   # LLM model (future use)
    execution_time_ms: int       # Performance tracking
    created_at: datetime

# Indexes
ix_pipeline_step_states_run: (run_id, step_number)
ix_pipeline_step_states_cache: (pipeline_name, step_name, input_hash)
```

### Caching Logic

```python
# Cache key components
input_hash = hashlib.sha256(json.dumps(
    step.prepare_calls(),
    sort_keys=True,
    default=str
)).hexdigest()[:16]

# Cache lookup
cached_state = session.exec(
    select(PipelineStepState).where(
        PipelineStepState.pipeline_name == "rate_card_parser",
        PipelineStepState.step_name == "constraint_extraction",
        PipelineStepState.input_hash == input_hash,
        PipelineStepState.prompt_version == current_version  # Version check
    ).order_by(PipelineStepState.created_at.desc())
).first()

# Cache hit behavior:
if cached_state:
    # 1. Load instructions from cached result_data
    instructions = load_from_cache(cached_state, step)

    # 2. Reconstruct extractions from PipelineRunInstance
    run_instances = session.exec(
        select(PipelineRunInstance).where(
            PipelineRunInstance.run_id == cached_state.run_id,
            PipelineRunInstance.model_type == "Lane"
        )
    ).all()
    for run_instance in run_instances:
        instance = session.get(Lane, run_instance.model_id)
        pipeline.extractions[Lane].append(instance)
```

### PipelineRunInstance Traceability

```python
# Links created database instances to pipeline run
PipelineRunInstance:
    run_id: str          # Links to PipelineStepState.run_id
    model_type: str      # "Lane", "Rate", "ChargeType"
    model_id: int        # FK to actual instance
    created_at: datetime

# Created during save()
for instance in pipeline.get_extractions(Lane):
    run_instance = PipelineRunInstance(
        run_id=pipeline.run_id,
        model_type="Lane",
        model_id=instance.id,  # After flush
    )
    session.add(run_instance)
```

**Enables queries**:
- "Which pipeline run created Lane #123?"
- "What were all the instances created in run abc-def?"
- "Recreate extraction state from previous run"

---

## Validation Architecture

### Multi-Layer Validation

```
Layer 1: Schema Structure Validation (validation.py)
├─► validate_structured_output()
├─► Checks:
│   ├─► Required fields present
│   ├─► No extra fields (configurable)
│   ├─► Type matching (string, number, integer, boolean, array, object)
│   └─► Nested object/array validation
└─► Returns: (is_valid, errors)

Layer 2: Array Response Validation (validation.py)
├─► validate_array_response()
├─► Checks:
│   ├─► Length matches input array
│   ├─► Order matches (with optional reordering)
│   ├─► Match field values align
│   └─► Number prefix stripping
└─► Returns: (is_valid, errors)

Layer 3: Pydantic Model Validation
├─► result_class.model_validate(response_json, context=...)
├─► Checks:
│   ├─► Field validators (custom logic)
│   ├─► Type coercion
│   ├─► Constraints (ge, le, min_length, etc.)
│   └─► Computed fields
└─► Raises: ValidationError or returns instance

Layer 4: Extraction Instance Validation (extraction.py)
├─► _validate_instance()
├─► Checks:
│   ├─► Decimal fields for NaN/Infinity
│   ├─► Required fields for None
│   ├─► FK fields for None
│   └─► Custom extraction validation (override)
└─► Raises: ValueError with clear error message

Layer 5: Database Constraints (SQLAlchemy)
├─► NOT NULL constraints
├─► Foreign key constraints
├─► Unique constraints
└─► Check constraints
```

### Validation Flow in LLM Call

```python
# In GeminiProvider.call_structured()

response = model.generate_content(prompt_with_schema)
response_json = json.loads(extract_json(response.text))

# Layer 1: Structure
is_valid, errors = validate_structured_output(
    response_json,
    expected_schema,
    strict_types=True
)
if not is_valid:
    logger.warning(errors)
    continue  # Retry

# Layer 2: Array (if applicable)
if array_validation:
    array_valid, array_errors = validate_array_response(
        response_json,
        array_validation,
        attempt
    )
    if not array_valid:
        continue  # Retry

# Layer 3: Pydantic
try:
    if validation_context:
        result_class.model_validate(
            response_json,
            context=validation_context.to_dict()
        )
    else:
        result_class(**response_json)
except Exception as e:
    logger.warning(f"Pydantic validation failed: {e}")
    continue  # Retry

return response_json  # All validations passed
```

### Extraction Validation Detail

```python
# In PipelineExtraction._validate_instance()

for field_name, field_info in model.model_fields.items():
    value = getattr(instance, field_name)
    is_required = field_info.is_required()
    is_fk = field_name in foreign_key_fields

    # Check 1: Required field validation
    if is_required and value is None:
        raise ValueError(
            f"Invalid {model_name} at index {index}: "
            f"Required field '{field_name}' cannot be None. "
            "This would violate NOT NULL constraint."
        )

    # Check 2: FK field validation
    if is_fk and value is None and field_name != 'id':
        if is_required:
            raise ValueError(
                f"Invalid {model_name} at index {index}: "
                f"FK field '{field_name}' cannot be None."
            )

    # Check 3: Decimal NaN/Infinity
    if isinstance(value, Decimal):
        if value.is_nan():
            raise ValueError(
                f"Field '{field_name}' cannot be NaN. "
                "Check extraction logic to filter NaN."
            )
        if value.is_infinite():
            raise ValueError(
                f"Field '{field_name}' cannot be Infinity."
            )
```

**Benefits**:
- Errors at extraction time (not database insertion)
- Clear error messages with actionable guidance
- Prevents silent data corruption
- Validates SQLModel constraints that table=True skips

---

## Testing Strategy

### Test Coverage Areas

```python
# tests/test_pipeline.py

# 1. Import Verification
TestImports:
    test_core_imports()
    test_llm_imports()
    test_db_imports()
    test_prompts_imports()

# 2. Component Unit Tests
TestLLMResultMixin:
    test_create_failure()
    test_get_example()
    test_example_not_required()

TestArrayValidationConfig:
    test_defaults()

TestValidationContext:
    test_access()

TestSchemaUtils:
    test_flatten_schema()
    test_format_schema_for_llm()

TestValidation:
    test_validate_structured_output_valid()
    test_validate_structured_output_missing_field()
    test_strip_number_prefix()

TestRateLimiter:
    test_basic_usage()
    test_reset()

# 3. Framework Behavior Tests
TestPipelineNaming:
    test_valid_pipeline_naming()
    test_invalid_pipeline_name()

TestPipelineInit:
    test_auto_sqlite()
    test_explicit_session()
    test_explicit_engine()
    test_requires_provider_for_execute()

# 4. Integration Tests
TestPipelineExecution:
    test_full_execution()  # End-to-end with MockProvider
    test_save_persists_to_db()
    test_step_state_saved()

# 5. Service Tests
TestPromptService:
    test_get_prompt()
    test_prompt_not_found()
    test_prompt_fallback()
    test_format_user_prompt()

TestPromptLoader:
    test_extract_variables()
    test_extract_no_variables()

# 6. Database Tests
TestInitPipelineDb:
    test_creates_tables()
```

### MockProvider Pattern

```python
class MockProvider(LLMProvider):
    """Deterministic responses for testing."""

    def __init__(self, responses: List[Dict[str, Any]] = None):
        self._responses = responses or []
        self._call_count = 0

    def call_structured(self, prompt, system_instruction, result_class, **kwargs):
        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
            self._call_count += 1
            return response
        return None

# Usage
mock_response = {
    "widget_count": 3,
    "category": "gadgets",
    "confidence_score": 0.95,
}
provider = MockProvider(responses=[mock_response])
pipeline = TestPipeline(session=session, provider=provider)
pipeline.execute(data="test", initial_context={})

# Assertions
assert pipeline.context["category"] == "gadgets"
assert len(pipeline.get_extractions(Widget)) == 3
```

### In-Memory SQLite Pattern

```python
@pytest.fixture
def engine():
    """In-memory database for fast testing."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(eng)
    return eng

@pytest.fixture
def session(engine):
    with Session(engine) as sess:
        yield sess
```

---

## Key Design Decisions

### 1. Why Class-Level Configuration?

**Decision**: Use `__init_subclass__` for declarative configuration instead of instance-based setup.

**Rationale**:
- Validates configuration at import time (fail fast)
- Makes architecture explicit and discoverable
- Enforces naming conventions automatically
- Reduces boilerplate in user code

**Trade-off**: Less runtime flexibility, but prevents common misconfiguration errors.

### 2. Why Three-Tier Data Model?

**Decision**: Separate `context`, `data`, and `extractions` instead of single dict.

**Rationale**:
- **Context**: Strategy selection depends on derived values (not raw data)
- **Data**: Transformations need structured access to previous states
- **Extractions**: Database instances have different lifecycle (validation, FK ordering)

**Trade-off**: More complexity, but clearer separation of concerns.

### 3. Why Read-Only Sessions?

**Decision**: Wrap SQLModel sessions to block writes during step execution.

**Rationale**:
- Prevents accidental writes during read operations
- Enforces correct insertion order (via save())
- Catches bugs at development time

**Trade-off**: Requires framework awareness, but eliminates entire class of bugs.

### 4. Why Execution Order Validation?

**Decision**: Build execution graph and validate access patterns.

**Rationale**:
- Prevents accessing future step results
- Catches ordering bugs at pipeline initialization
- Documents dependencies explicitly

**Example Error**:
```
ValueError: Step execution order error:
  ConstraintExtraction (step 2) attempts to access data
  from SemanticMapping (step 3).
  Steps can only access data from previously executed steps.
```

### 5. Why Prompt Versioning?

**Decision**: Store prompt version in state and invalidate cache on version change.

**Rationale**:
- Prompt changes should trigger re-execution
- Version-aware caching prevents stale results
- Audit trail of which prompt version produced results

**Implementation**:
```python
# Cache lookup includes version check
cached_state = session.exec(
    select(PipelineStepState).where(
        ...,
        PipelineStepState.prompt_version == current_version
    )
).first()
```

### 6. Why Smart Method Detection?

**Decision**: Auto-detect extraction/transformation methods instead of requiring specific names.

**Rationale**:
- Single-method classes work without boilerplate
- Strategy-specific methods route automatically
- Explicit `default` method for clarity when needed

**Priority Order**:
1. `default` method (highest priority)
2. Method matching strategy name
3. Single custom method (auto-detected)
4. Error if ambiguous

### 7. Why Separate LLMProvider Abstract Class?

**Decision**: Define abstract interface instead of concrete Gemini implementation.

**Rationale**:
- Enables multiple LLM providers (OpenAI, Anthropic, local models)
- Decouples pipeline logic from specific API
- Makes testing easier (MockProvider)

**Implementation**:
```python
class LLMProvider(ABC):
    @abstractmethod
    def call_structured(...) -> Optional[Dict[str, Any]]:
        pass
```

### 8. Why Consensus Polling?

**Decision**: Optional consensus mode for critical LLM calls.

**Rationale**:
- Some extractions are critical (financial data)
- Multiple identical responses increase confidence
- Configurable threshold balances accuracy vs. cost

**Usage**:
```python
pipeline.execute(
    data=data,
    initial_context={},
    consensus_polling={
        "enable": True,
        "consensus_threshold": 3,  # Need 3 matching responses
        "maximum_step_calls": 5,   # Max 5 attempts
    }
)
```

### 9. Why Auto-SQLite?

**Decision**: Create in-memory SQLite by default if no engine/session provided.

**Rationale**:
- Quick prototyping without database setup
- Testing with in-memory databases
- Production uses explicit engine/session

**Behavior**:
```python
# Auto-SQLite (development)
pipeline = MyPipeline(provider=provider)

# Explicit database (production)
pipeline = MyPipeline(
    engine=create_engine("postgresql://..."),
    provider=provider
)
```

### 10. Why FK Dependency Validation?

**Decision**: Validate FK ordering in registry at initialization time.

**Rationale**:
- FK constraint violations are confusing runtime errors
- Correct ordering is critical for data integrity
- Validation at init provides clear error messages

**Mechanism**:
1. Inspect SQLAlchemy table metadata
2. Extract FK relationships
3. Validate target tables appear earlier in registry
4. Provide correction instructions in error

---

## Integration Examples

### Complete Pipeline Example

```python
# 1. Define Domain Models
class Vendor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

class RateCard(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vendor_id: int = Field(foreign_key="vendor.id")
    effective_date: date

class Lane(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rate_card_id: int = Field(foreign_key="ratecard.id")
    origin: str
    destination: str


# 2. Define Registry (FK order)
class MyRegistry(PipelineDatabaseRegistry, models=[
    Vendor,     # No FKs
    RateCard,   # FK to Vendor
    Lane,       # FK to RateCard
]):
    pass


# 3. Define Instruction Classes
class VendorDetectionInstructions(LLMResultMixin):
    vendor_name: str
    confidence_score: float = 0.95

    example: ClassVar[dict] = {
        "vendor_name": "ACME Logistics",
        "confidence_score": 0.98,
    }

class LaneExtractionInstructions(LLMResultMixin):
    lanes: List[Dict[str, str]]

    example: ClassVar[dict] = {
        "lanes": [
            {"origin": "Sydney", "destination": "Melbourne"},
        ],
        "confidence_score": 0.95,
    }


# 4. Define Context Classes
class VendorDetectionContext(PipelineContext):
    vendor_name: str


# 5. Define Extractions
class VendorExtraction(PipelineExtraction, model=Vendor):
    def default(self, results):
        instruction = results[0]
        return [Vendor(name=instruction.vendor_name)]

class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        instruction = results[0]
        rate_card = self.pipeline.get_extractions(RateCard)[0]

        lanes = []
        for lane_dict in instruction.lanes:
            lanes.append(Lane(
                rate_card_id=rate_card.id,
                origin=lane_dict["origin"],
                destination=lane_dict["destination"],
            ))
        return lanes


# 6. Define Steps
@step_definition(
    instructions=VendorDetectionInstructions,
    default_system_key="vendor_detection",
    default_user_key="vendor_detection",
    default_extractions=[VendorExtraction],
    context=VendorDetectionContext,
)
class VendorDetectionStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [
            self.create_llm_call(
                variables={"data": self.pipeline.get_sanitized_data()}
            )
        ]

    def process_instructions(self, instructions):
        return VendorDetectionContext(
            vendor_name=instructions[0].vendor_name
        )

@step_definition(
    instructions=LaneExtractionInstructions,
    default_system_key="lane_extraction",
    default_user_key="lane_extraction",
    default_extractions=[LaneExtraction],
)
class LaneExtractionStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        vendor_name = self.pipeline.context["vendor_name"]
        return [
            self.create_llm_call(
                variables={
                    "data": self.pipeline.get_sanitized_data(),
                    "vendor": vendor_name,
                }
            )
        ]


# 7. Define Strategy
class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True  # Always handles

    def get_steps(self):
        return [
            VendorDetectionStep.create_definition(),
            LaneExtractionStep.create_definition(),
        ]


# 8. Define Strategies
class MyStrategies(PipelineStrategies, strategies=[DefaultStrategy]):
    pass


# 9. Define Pipeline
class MyPipeline(PipelineConfig,
                 registry=MyRegistry,
                 strategies=MyStrategies):
    pass


# 10. Execute
engine = create_engine("sqlite:///pipeline.db")
provider = GeminiProvider()

pipeline = MyPipeline(engine=engine, provider=provider)
pipeline.execute(
    data="<CSV content>",
    initial_context={},
    use_cache=True,
)

# Save to database
results = pipeline.save()
print(results)  # {"vendors_saved": 1, "ratecards_saved": 1, "lanes_saved": 5}
```

### Multi-Strategy Example

```python
# Context-driven strategy selection
class LaneBasedStrategy(PipelineStrategy):
    def can_handle(self, context):
        return context.get("table_type") == "lane_based"

    def get_steps(self):
        return [
            TableTypeDetection.create_definition(),
            LaneBasedExtraction.create_definition(),
        ]

class ZoneBasedStrategy(PipelineStrategy):
    def can_handle(self, context):
        return context.get("table_type") == "zone_based"

    def get_steps(self):
        return [
            TableTypeDetection.create_definition(),
            ZoneBasedExtraction.create_definition(),
        ]

class MyStrategies(PipelineStrategies, strategies=[
    LaneBasedStrategy,
    ZoneBasedStrategy,
]):
    pass

# Execution
pipeline = MyPipeline(...)
pipeline.execute(data=csv_data, initial_context={})

# Step 1: TableTypeDetection runs
#   → Sets context["table_type"] = "lane_based"
# Step 2: LaneBasedStrategy.can_handle() returns True
#   → LaneBasedExtraction runs
```

---

## Appendices

### A. Naming Conventions Summary

| Component | Pattern | Example |
|-----------|---------|---------|
| Pipeline | `*Pipeline` | `RateCardParserPipeline` |
| Registry | `*Registry` | `RateCardParserRegistry` |
| Strategies | `*Strategies` | `RateCardParserStrategies` |
| Strategy | `*Strategy` | `LaneBasedStrategy` |
| Step | `*Step` | `ConstraintExtractionStep` |
| Instructions | `*Instructions` | `ConstraintExtractionInstructions` |
| Context | `*Context` | `ConstraintExtractionContext` |
| Extraction | `*Extraction` | `LaneExtraction` |
| Transformation | `*Transformation` | `UnpivotDetectionTransformation` |

**Auto-matching requirements**:
- `MyPipeline` requires `MyRegistry` and `MyStrategies`
- `MyStep` requires `MyInstructions`
- Optional `MyContext`, `MyTransformation`

### B. Public API Surface

```python
# Core
from llm_pipeline import (
    PipelineConfig,
    LLMStep,
    LLMResultMixin,
    step_definition,
)

# Strategy
from llm_pipeline import (
    PipelineStrategy,
    PipelineStrategies,
    StepDefinition,
)

# Data Handling
from llm_pipeline import (
    PipelineContext,
    PipelineExtraction,
    PipelineTransformation,
    PipelineDatabaseRegistry,
)

# State
from llm_pipeline import (
    PipelineStepState,
    PipelineRunInstance,
)

# Types
from llm_pipeline import (
    ArrayValidationConfig,
    ValidationContext,
)

# Database
from llm_pipeline import init_pipeline_db

# Session
from llm_pipeline import ReadOnlySession

# LLM
from llm_pipeline.llm import (
    LLMProvider,
    RateLimiter,
)
from llm_pipeline.llm.gemini import GeminiProvider
from llm_pipeline.llm.schema import (
    flatten_schema,
    format_schema_for_llm,
)
from llm_pipeline.llm.validation import (
    validate_structured_output,
    validate_array_response,
)

# Prompts
from llm_pipeline.prompts import (
    PromptService,
    VariableResolver,
)
from llm_pipeline.prompts.loader import (
    sync_prompts,
    load_all_prompts,
)
from llm_pipeline.db import Prompt
```

### C. Error Messages Index

**Configuration Errors**:
```
- "Pipeline class 'X' must end with 'Pipeline' suffix"
- "Registry for XPipeline must be named 'XRegistry', got 'Y'"
- "X must specify registry parameter when defining the class"
- "Instruction class for XStep must be named 'XInstructions'"
```

**Execution Errors**:
```
- "LLMProvider required. Pass provider= to pipeline constructor."
- "Step execution order error: Step X attempts to access data from Step Y"
- "Cannot access data from XStep - not executed yet"
- "Extraction ordering error within XStep: Y attempts to access 'Model' before extracted"
```

**Database Errors**:
```
- "Foreign key dependency error in XRegistry: 'Model1' at position X, but FK to 'Model2' at position Y"
- "Extraction order mismatch in XRegistry: 'Model1' before 'Model2' in registry, but extracted later"
- "XExtraction.MODEL (Model) is not in XRegistry"
```

**Validation Errors**:
```
- "Invalid Model at index X: Required field 'Y' cannot be None"
- "Invalid Model at index X: FK field 'Y' cannot be None"
- "Invalid Model at index X: Field 'Y' cannot be NaN"
- "User prompt template variable 'X' not provided"
```

**Prompt Errors**:
```
- "Prompt not found: X"
- "No prompts found for XStep. Searched for: [keys]"
```

### D. Performance Characteristics

**Initialization**:
- FK validation: O(M²) where M = number of models
- Execution order building: O(S) where S = number of steps
- Registry order validation: O(M×S)

**Execution**:
- Step selection: O(T×S) where T = strategies, S = steps per strategy
- Caching lookup: O(1) with database indexes
- Extraction reconstruction: O(E) where E = extracted instances

**Database Operations**:
- save(): Sequential inserts in FK order (O(I) where I = instances)
- State persistence: 1 insert per step

**Recommended Limits**:
- Steps per pipeline: < 20 (maintainability)
- Strategies per pipeline: < 10
- Models per registry: < 50
- Extractions per step: < 10

### E. File Paths Reference

```
llm_pipeline/
  pipeline.py:73                # PipelineConfig class
  pipeline.py:223               # _build_execution_order
  pipeline.py:257               # _validate_foreign_key_dependencies
  pipeline.py:391               # execute method

  step.py:73                    # step_definition decorator
  step.py:225                   # LLMStep class
  step.py:262                   # create_llm_call

  strategy.py:20                # StepDefinition dataclass
  strategy.py:37                # create_step method
  strategy.py:138               # PipelineStrategy class
  strategy.py:250               # PipelineStrategies class

  extraction.py:33              # PipelineExtraction class
  extraction.py:113             # _validate_instance
  extraction.py:213             # extract (smart detection)

  transformation.py:30          # PipelineTransformation class
  transformation.py:122         # transform (smart detection)

  llm/executor.py:19            # execute_llm_step function
  llm/gemini.py:28              # GeminiProvider class
  llm/schema.py:56              # format_schema_for_llm
  llm/validation.py:110         # validate_structured_output

  prompts/loader.py:84          # sync_prompts function
  prompts/service.py:10         # PromptService class

  state.py:24                   # PipelineStepState model
  state.py:107                  # PipelineRunInstance model

  db/__init__.py:36             # init_pipeline_db function
  session/readonly.py:11        # ReadOnlySession class
```

---

## Conclusion

The llm-pipeline framework provides a robust, opinionated architecture for building LLM-powered data processing pipelines. Its declarative configuration model, comprehensive validation, and automatic state tracking make it suitable for production use in domains requiring high reliability and audit trails.

Key strengths:
- Strong typing and validation at all layers
- Clear separation of concerns
- Extensive error checking with actionable messages
- Flexible strategy system for handling variations
- Database-backed state tracking and caching

The framework's design prioritizes correctness and maintainability over runtime flexibility, making it ideal for teams building long-lived, mission-critical LLM applications.
