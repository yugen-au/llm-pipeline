# Architecture Overview

## Executive Summary

llm-pipeline is a declarative orchestration framework for building LLM-powered data processing pipelines. It provides a structured approach to chaining multiple LLM calls together with automatic state tracking, caching, database persistence, and flexible strategy-based execution.

**Core Value Proposition**: Transform unstructured or semi-structured data into validated database records through a series of LLM-powered steps, with full audit trail, caching support, and zero boilerplate.

**Key Features**:
- Declarative pipeline configuration via Python class inheritance
- Strategy pattern for context-dependent execution paths
- Automatic database session management and FK dependency validation
- Built-in caching with input hashing and prompt version tracking
- Three-tier data model (context, data, extractions) for clear separation of concerns
- Read-only session pattern to prevent accidental writes during execution
- Consensus polling support for critical LLM decisions

## System Architecture

### High-Level Design

llm-pipeline follows a **Pipeline + Strategy + Step** pattern where:

1. **Pipeline** orchestrates execution, manages state, owns database session
2. **Strategies** define execution paths based on runtime context
3. **Steps** implement individual LLM-powered transformations

```
┌─────────────────────────────────────────────────────────────┐
│                      PipelineConfig                          │
│  - Owns: session, context, data, extractions                │
│  - Manages: step execution, caching, state tracking          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ delegates to
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   PipelineStrategy                           │
│  - Defines: which steps to run, when to apply                │
│  - Returns: List[StepDefinition]                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ creates
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        LLMStep                               │
│  - Implements: prepare_calls(), process_instructions()       │
│  - Calls: LLM via provider, extracts data, transforms data   │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. PipelineConfig (pipeline.py)

The central orchestrator that manages the entire pipeline execution lifecycle.

**Responsibilities**:
- Execute steps in strategy-defined order
- Manage three-tier data storage (context, data, extractions)
- Handle database sessions with read-only wrapper during execution
- Track execution state for caching and audit trail
- Validate foreign key dependencies and extraction order
- Coordinate consensus polling for LLM calls

**Key Properties**:
- `context: Dict[str, Any]` - Derived values from step instructions (strategy selection, metadata)
- `data: StepKeyDict` - Input data and transformation results (DataFrame, sanitized strings)
- `extractions: Dict[Type[SQLModel], List[SQLModel]]` - Database model instances by type
- `session: ReadOnlySession` - Read-only wrapper for database queries
- `_real_session: Session` - Underlying session for controlled writes

**Declarative Configuration**:
```python
class RateCardParserPipeline(PipelineConfig,
                              registry=RateCardParserRegistry,
                              strategies=RateCardParserStrategies):
    pass
```

**Naming Convention**: Class name must end with `Pipeline` suffix. Registry and Strategies must match the prefix (e.g., `RateCardParser` -> `RateCardParserRegistry`, `RateCardParserStrategies`).

#### 2. PipelineStrategy (strategy.py)

Defines conditional execution paths based on runtime context.

**Responsibilities**:
- Determine if strategy applies via `can_handle(context)`
- Define step sequence via `get_steps()`
- Provide step-level configuration (prompts, extractions, transformations)

**Example**:
```python
class LaneBasedStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return context.get('table_type') == 'lane_based'

    def get_steps(self) -> List[StepDefinition]:
        return [
            TableTypeDetectionStep.create_definition(),
            ConstraintExtractionStep.create_definition(
                extractions=[LaneExtraction, RateExtraction]
            ),
        ]
```

**Auto-Generated Properties**:
- `name` - snake_case name derived from class (e.g., `LaneBasedStrategy` -> `"lane_based"`)
- `display_name` - Human-readable name (e.g., `"Lane Based"`)

#### 3. LLMStep (step.py)

Abstract base for implementing LLM-powered pipeline steps.

**IMPORTANT**: `LLMStep` extends `ABC`, NOT `LLMResultMixin`. The mixin is for instruction classes.

**Responsibilities**:
- Prepare LLM call parameters via `prepare_calls()`
- Process LLM results via `process_instructions()`
- Extract database models via `extract_data()`
- Optionally skip execution via `should_skip()`

**Lifecycle**:
1. Pipeline calls `step.prepare_calls()` -> list of call parameter dicts
2. Pipeline executes LLM calls via provider (or loads from cache)
3. Pipeline calls `step.process_instructions(instructions)` -> context updates
4. Pipeline calls `step.extract_data(instructions)` -> database instances added to session

**Example**:
```python
@step_definition(
    instructions=TableTypeDetectionInstructions,
    context=TableTypeDetectionContext,
)
class TableTypeDetectionStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        df = self.pipeline.get_current_data()
        return [self.create_llm_call(
            variables={'table_preview': df.head(5).to_string()}
        )]

    def process_instructions(self, instructions) -> TableTypeDetectionContext:
        return TableTypeDetectionContext(
            table_type=instructions[0].table_type.value
        )
```

#### 4. PipelineExtraction (extraction.py)

Converts LLM instruction results into validated database model instances.

**Smart Method Detection** (priority order):
1. `default()` method -> always used if present
2. Strategy-name method (e.g., `lane_based()`) -> matched to current strategy
3. Single custom method -> auto-detected
4. Error if multiple methods without default or strategy match

**Two-Phase Write Pattern** (CRITICAL):

Phase 1 (during step execution):
```python
# extract_data() in step.py line 329-330
self.pipeline._real_session.add(instance)
self.pipeline._real_session.flush()  # Assigns database IDs
```

Phase 2 (during save):
```python
# save() in pipeline.py line 749
session.commit()  # Finalizes transaction
```

**Purpose**: The flush during execution assigns database IDs to extracted instances, enabling later extractions to reference those IDs via foreign keys. The commit in `save()` finalizes the transaction and tracks instances via `PipelineRunInstance`.

**Validation**:
- NaN/Infinity detection for Decimal fields
- NOT NULL constraint validation for required fields
- Foreign key constraint validation

**Example**:
```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def lane_based(self, results: List[ConstraintInstructions]) -> List[Lane]:
        rate_card = self.pipeline.get_extractions(RateCard)[0]
        lanes = []
        for constraint in results[0].constraints:
            lane = Lane(
                rate_card_id=rate_card.id,  # FK available via flush
                origin=constraint.origin,
                destination=constraint.destination,
            )
            lanes.append(lane)
        return lanes
```

#### 5. PipelineTransformation (transformation.py)

Handles data structure changes (unpivoting, normalizing, etc.) with type validation.

**Smart Method Detection** (priority order):
1. `default()` method -> always used if present
2. Single custom method -> auto-detected
3. No methods -> passthrough (returns data unchanged)
4. Error if multiple methods without default

**IMPORTANT**: Transformation does NOT support strategy-specific routing. Only extractions have strategy-name method matching.

**Example**:
```python
class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def default(self, data: pd.DataFrame, instructions: UnpivotInstructions) -> pd.DataFrame:
        return data.melt(
            id_vars=instructions.id_columns,
            value_vars=instructions.value_columns,
            var_name=instructions.variable_name,
            value_name=instructions.value_name,
        )
```

#### 6. PipelineDatabaseRegistry (registry.py)

Declarative specification of managed database models in insertion order.

**Responsibilities**:
- Define which models the pipeline manages
- Enforce FK dependency order
- Provide single source of truth for `save()` operation

**Foreign Key Validation**: Pipeline automatically validates that models are listed in dependency order (dependencies before dependents).

**Example**:
```python
class RateCardParserRegistry(PipelineDatabaseRegistry, models=[
    Vendor,           # No dependencies
    RateCard,         # FK to Vendor
    Lane,             # FK to RateCard
    ChargeType,       # FK to RateCard
    Rate,             # FK to Lane, ChargeType
])
```

#### 7. State Tracking (state.py)

Two models provide audit trail and caching:

**PipelineStepState**: Records execution details for each step
- Input hash for cache key
- Result data (serialized instructions)
- Prompt keys and version for cache invalidation
- Execution time metrics

**PipelineRunInstance**: Links created database instances to pipeline runs
- Enables "Which run created this record?" queries
- Supports cache reconstruction from previous runs

**Cache Key**: `(pipeline_name, step_name, input_hash, prompt_version)`

#### 8. ReadOnlySession (session/readonly.py)

Wrapper that blocks write operations during step execution.

**Allowed Operations**:
- `exec()`, `query()`, `get()` - Read queries
- `execute()`, `scalar()`, `scalars()` - Query execution

**Blocked Operations**:
- `add()`, `delete()`, `flush()`, `commit()` - Write operations
- Raises `RuntimeError` with clear error message

**Purpose**: Prevent accidental database modifications during step execution. All writes go through controlled extraction flow with validation.

**Known Bug**: `clear_cache()` calls `self.session.delete()` instead of `self._real_session.delete()`, triggering RuntimeError. Rarely encountered because `use_cache` defaults to False.

### Data Flow Architecture

llm-pipeline maintains three separate data stores with distinct purposes:

```
┌──────────────────────────────────────────────────────────────┐
│                     Pipeline Execution                        │
└──────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│   Context    │    │     Data     │    │   Extractions    │
│              │    │              │    │                  │
│ Strategy     │    │ Raw          │    │ Lane: [...]      │
│ selection,   │    │ Current      │    │ Rate: [...]      │
│ metadata     │    │ Sanitized    │    │ RateCard: [...]  │
│              │    │ Transformed  │    │                  │
│ Dict[str,    │    │              │    │ Dict[Type[Model],│
│      Any]    │    │ StepKeyDict  │    │      List[Model]]│
└──────────────┘    └──────────────┘    └──────────────────┘
```

#### Context (pipeline.context)

**Purpose**: Derived values from LLM instructions used for strategy selection and metadata.

**Typical Contents**:
- `table_type: str` - Strategy selection key
- `rate_card_id: int` - Foreign key references
- `unpivot_required: bool` - Conditional execution flags

**Usage**:
```python
# Write: via process_instructions()
def process_instructions(self, instructions) -> TableTypeDetectionContext:
    return TableTypeDetectionContext(table_type=instructions[0].table_type.value)

# Read: in strategy can_handle()
def can_handle(self, context: Dict[str, Any]) -> bool:
    return context.get('table_type') == 'lane_based'
```

#### Data (pipeline.data)

**Purpose**: Input data and transformation results, typically DataFrames or text.

**Special Keys**:
- `raw` - Original input data
- `sanitized` - Output of `pipeline.sanitize()` (default: `str(data)`)
- `current` - Most recent transformation result
- Step names - Results from transformation steps

**StepKeyDict**: Custom dict that accepts both string keys and Step class keys, automatically converting class names to snake_case.

**Usage**:
```python
# Write: pipeline.set_data()
transformed_df = transformation.transform(current_data, instructions)
self.set_data(transformed_df, step_name=step.step_name)

# Read: pipeline.get_data()
current_data = self.pipeline.get_current_data()
sanitized_data = self.pipeline.get_sanitized_data()
```

#### Extractions (pipeline.extractions)

**Purpose**: Database model instances ready for persistence.

**Storage**: Dict mapping model class to list of instances.

**Usage**:
```python
# Write: during extract_data()
lanes = extraction.extract(instructions)
self.store_extractions(Lane, lanes)

# Read: in later extractions
rate_card = self.pipeline.get_extractions(RateCard)[0]
lane_id = rate_card.lanes[0].id  # ID available via flush
```

**Validation**: Pipeline validates extraction order matches registry order and enforces step execution sequence.

### Execution Flow

#### Standard Pipeline Execution

1. **Initialization**
   ```python
   pipeline = RateCardParserPipeline(
       provider=GeminiProvider(api_key="..."),
       engine=engine,  # Optional, auto-SQLite if omitted
   )
   ```

2. **Execution**
   ```python
   pipeline.execute(
       data=df,
       initial_context={'vendor_id': 123},
       use_cache=True,
   )
   ```

3. **Step Loop** (for each step in strategy)
   - Select strategy via `can_handle(context)`
   - Create step instance via `StepDefinition.create_step(pipeline)`
   - Check cache via input hash + prompt version
   - If cached: Reconstruct extractions from `PipelineRunInstance`
   - If fresh:
     - Call `step.prepare_calls()` -> call parameters
     - Execute LLM via provider (with optional consensus polling)
     - Call `step.process_instructions()` -> update context
     - Apply transformation if configured
     - Call `step.extract_data()` -> add instances to session + flush
     - Save state via `PipelineStepState`

4. **Save to Database**
   ```python
   results = pipeline.save()  # Commits transaction
   # results: {'lanes_saved': 5, 'rates_saved': 20, ...}
   ```

#### Two-Phase Write Pattern

**Phase 1: Flush During Execution**

Location: `step.py` lines 329-330

```python
for instance in instances:
    self.pipeline._real_session.add(instance)
self.pipeline._real_session.flush()  # Assigns database IDs
```

**Purpose**: Assign database IDs to extracted instances during step execution, enabling later extractions to reference those IDs via foreign keys.

**Phase 2: Commit During Save**

Location: `pipeline.py` line 749

```python
session.commit()  # Finalizes transaction
```

**Purpose**: Finalize the transaction after all extractions complete and track created instances via `PipelineRunInstance` for traceability.

**Design Rationale**: This pattern enables forward references within a single pipeline run. For example, a `Lane` extraction can reference a `RateCard.id` that was just extracted in a previous step, because the flush assigned the ID before committing the transaction.

### Design Patterns

#### 1. Declarative Configuration via __init_subclass__

Classes use Python's `__init_subclass__` hook to validate naming conventions and configure class-level attributes at definition time.

**Example: PipelineConfig**
```python
class MyPipeline(PipelineConfig,
                 registry=MyRegistry,
                 strategies=MyStrategies):
    pass

# Validates:
# - Class name ends with 'Pipeline'
# - Registry name is 'MyRegistry' (prefix + 'Registry')
# - Strategies name is 'MyStrategies' (prefix + 'Strategies')
```

**Benefits**:
- Errors at import time, not runtime
- Clear, self-documenting configuration
- Enforces consistency across codebase

#### 2. Step Factory via @step_definition

The `@step_definition` decorator auto-generates a `create_definition()` class method.

**Example**:
```python
@step_definition(
    instructions=TableTypeDetectionInstructions,
    default_system_key='table_type_detection',
    default_user_key='table_type_detection',
    context=TableTypeDetectionContext,
)
class TableTypeDetectionStep(LLMStep):
    pass

# Usage in strategy:
TableTypeDetectionStep.create_definition()
TableTypeDetectionStep.create_definition(extractions=[CustomExtraction])
```

**Benefits**:
- Default configuration at class level
- Override-able per-strategy
- Type-safe with IDE autocomplete

#### 3. Smart Method Detection

Both `PipelineExtraction` and `PipelineTransformation` auto-detect which method to call.

**Extraction Priority**:
1. `default()` method
2. Strategy-name method (e.g., `lane_based()`)
3. Single custom method
4. Error

**Transformation Priority** (NO strategy routing):
1. `default()` method
2. Single custom method
3. Passthrough (return data unchanged)
4. Error

**Benefits**:
- Single-method extractions "just work"
- Multi-strategy extractions use descriptive method names
- Explicit `default()` for clarity

#### 4. StepKeyDict Pattern

Custom dict subclass that normalizes Step class keys to snake_case.

**Example**:
```python
# Both work:
pipeline.data['constraint_extraction'] = result
pipeline.data[ConstraintExtractionStep] = result  # Auto-converts to 'constraint_extraction'

# Retrieval:
data = pipeline.get_data(ConstraintExtractionStep)  # Type-safe
```

**Benefits**:
- Type-safe access with IDE autocomplete
- String-based storage for serialization
- Consistent naming across framework

#### 5. Read-Only Session Pattern

Pipeline provides `self.session` as `ReadOnlySession` wrapper during execution.

**Pattern**:
```python
# During execution: read-only
results = pipeline.session.exec(select(Prompt).where(...)).all()

# During save: controlled writes
pipeline._real_session.add(instance)
pipeline._real_session.flush()
```

**Benefits**:
- Prevents accidental writes in step logic
- Clear separation between queries and persistence
- Explicit write boundaries

### Dependency Management

#### Foreign Key Validation

Pipeline automatically validates FK dependencies at initialization:

```python
def _validate_foreign_key_dependencies(self) -> None:
    # For each model in registry:
    # 1. Inspect table metadata for FK columns
    # 2. Find target table names
    # 3. Verify target models appear BEFORE current model in registry
    # 4. Raise ValueError if dependency ordering violated
```

**Error Example**:
```
ValueError: Foreign key dependency error in RateCardParserRegistry:
  'Rate' at position 4, but FK to 'ChargeType' at position 5.
Move 'ChargeType' before 'Rate'.
```

#### Extraction Order Validation

Pipeline validates that models are extracted in registry order:

```python
def _validate_registry_order(self) -> None:
    # For each extracted model in registry:
    # 1. Get step that extracts it
    # 2. Get execution position of that step
    # 3. Verify all previous models extracted in earlier/same steps
    # 4. Raise ValueError if extraction order violated
```

**Error Example**:
```
ValueError: Extraction order mismatch in RateCardParserRegistry:
  'Lane' before 'RateCard' in registry, but extracted later.
Reorder registry to match extraction order.
```

#### Step Access Validation

Pipeline validates that steps only access results from previously executed steps:

```python
def _validate_step_access(self, step_class, resource_type, model_class) -> None:
    # Prevents:
    # - Accessing instructions from future steps
    # - Accessing data from future steps
    # - Accessing extractions from future steps
    # - Accessing extractions within same step before they're extracted
```

**Error Example**:
```
ValueError: Step execution order error:
  LaneExtraction (in step 1) attempts to access model 'RateCard' from step 2.
Steps can only access data from previously executed steps.
```

### Caching Strategy

#### Cache Key Components

1. **Input Hash**: SHA-256 of `prepare_calls()` result or context dict
2. **Prompt Version**: Database version field from `Prompt` model
3. **Pipeline Name**: Auto-derived from class name
4. **Step Name**: Auto-derived from step class name

**Lookup Query**:
```sql
SELECT * FROM pipeline_step_states
WHERE pipeline_name = ?
  AND step_name = ?
  AND input_hash = ?
  AND prompt_version = ?  -- Optional, if system prompt exists
ORDER BY created_at DESC
LIMIT 1
```

#### Cache Hit Behavior

1. Load serialized instructions from `PipelineStepState.result_data`
2. Deserialize to instruction class via Pydantic
3. Call `step.process_instructions()` to update context
4. Apply transformation if configured
5. Reconstruct extractions from `PipelineRunInstance` links
6. If extractions missing, re-run `step.extract_data()`

**Partial Cache**: If `PipelineRunInstance` records not found, cache is considered partial and extraction re-runs with fresh instructions from cache.

#### Cache Invalidation

Cache automatically invalidates when:
- Input data changes (different `input_hash`)
- Prompt content changes (different `prompt_version`)
- Prompt becomes inactive (`is_active = False`)

Manual invalidation:
```python
pipeline.clear_cache()  # Deletes all PipelineStepState for current run_id
```

**Known Bug**: `clear_cache()` uses `self.session.delete()` instead of `self._real_session.delete()`, causing RuntimeError. Rarely triggered because `use_cache` defaults to False.

### Consensus Polling

Optional feature for critical LLM decisions requiring high confidence.

**Configuration**:
```python
pipeline.execute(
    data=df,
    initial_context={...},
    consensus_polling={
        'enable': True,
        'consensus_threshold': 3,  # Min matching results
        'maximum_step_calls': 5,   # Max LLM calls
    }
)
```

**Algorithm**:
1. Make LLM call, get instruction result
2. Compare to existing result groups via `_instructions_match()`
3. If match found, add to that group
4. If group size >= threshold, return result (consensus reached)
5. If no match, create new group
6. Repeat until consensus or max calls reached
7. If no consensus, return most common result

**Comparison Logic** (`_smart_compare`):
- Strings: Always match (ignored in comparison)
- None values: Always match (ignored in comparison)
- Numbers/Booleans: Exact match required
- Lists: Length must match, recursive element comparison
- Dicts: Keys must match, recursive value comparison
- LLMResultMixin fields: Ignored (confidence_score, notes)

**Use Cases**:
- Critical classification decisions
- Ambiguous table structure detection
- High-stakes data extraction

### Extension Points

#### 1. Custom LLM Provider

Implement `LLMProvider` abstract class:

```python
from llm_pipeline.llm.provider import LLMProvider

class CustomProvider(LLMProvider):
    def call_structured(self, prompt, system_instruction, result_class, **kwargs):
        # Your LLM integration here
        return result_dict
```

**Current Implementation**: `GeminiProvider` (Google Gemini)

#### 2. Custom Sanitization

Override `PipelineConfig.sanitize()`:

```python
class MyPipeline(PipelineConfig, ...):
    def sanitize(self, data: Any) -> str:
        if isinstance(data, pd.DataFrame):
            return data.to_csv()  # Custom DataFrame sanitization
        return str(data)
```

**Purpose**: Sanitized data is passed to LLM for steps that need text context.

#### 3. Custom Variable Resolver

Implement `VariableResolver` for automatic system prompt variable instantiation:

```python
from llm_pipeline.prompts.variables import VariableResolver

class MyResolver(VariableResolver):
    def resolve(self, prompt_key: str, prompt_type: str) -> Type[BaseModel]:
        # Return variable class for prompt_key
        return MySystemVariables
```

**Usage**:
```python
pipeline = MyPipeline(
    provider=provider,
    variable_resolver=MyResolver(),
)
```

#### 4. Post-Step Actions

Configure actions to run after specific steps:

```python
StepDefinition(
    step_class=ConstraintExtractionStep,
    system_instruction_key='...',
    user_prompt_key='...',
    instructions=ConstraintInstructions,
    action_after='validate_constraints',  # Method name on pipeline
)

class MyPipeline(PipelineConfig, ...):
    def _validate_constraints(self, context: Dict[str, Any]) -> None:
        # Custom validation logic
        if context.get('error_count', 0) > 10:
            raise ValueError("Too many constraint errors")
```

#### 5. Custom Extraction Validation

Override `PipelineExtraction._validate_instance()`:

```python
class CustomExtraction(PipelineExtraction, model=MyModel):
    def _validate_instance(self, instance: MyModel, index: int) -> None:
        super()._validate_instance(instance, index)
        # Additional validation
        if instance.price < 0:
            raise ValueError(f"Invalid price at index {index}")
```

## Design Philosophy

### 1. Declarative Over Imperative

**Principle**: Configuration should be visible at the class level, not buried in runtime logic.

**Examples**:
- Registry models declared via class parameter
- Strategies declared via class parameter
- Step definitions created via decorator and factory
- Naming conventions enforced at class definition time

**Benefits**:
- Code organization matches mental model
- Easy to audit entire pipeline configuration
- Errors caught at import time

### 2. Three-Tier Data Model

**Principle**: Separate context (routing), data (transformations), and extractions (persistence).

**Rationale**:
- Context: Strategy selection and metadata (small, serializable)
- Data: Transformation pipeline (DataFrames, text, large)
- Extractions: Database persistence (validated, typed)

**Benefits**:
- Clear ownership of each data tier
- No confusion about where to store values
- Optimized for different access patterns

### 3. Explicit State Tracking

**Principle**: All execution state should be queryable and auditable.

**Implementation**:
- `PipelineStepState` for execution history
- `PipelineRunInstance` for data traceability
- `run_id` for linking related records
- Immutable state (no updates, only inserts)

**Benefits**:
- "How was this data created?" is always answerable
- Caching works across runs
- Debugging is data-driven, not log-driven

### 4. Fail-Fast Validation

**Principle**: Catch errors as early as possible in the execution flow.

**Implementation**:
- Naming validation at class definition time
- FK dependency validation at pipeline initialization
- Extraction order validation at pipeline initialization
- Step access validation during execution
- Model instance validation before database insertion

**Benefits**:
- Errors point to configuration mistakes, not runtime bugs
- Clear error messages with actionable fixes
- Less defensive coding in business logic

### 5. Smart Defaults, Explicit Overrides

**Principle**: Common cases should require minimal configuration, but all behavior should be overridable.

**Examples**:
- Auto-SQLite database if no engine provided
- Auto-derived step names from class names
- Smart method detection in extractions/transformations
- Default prompt key discovery via strategy + step name
- Passthrough transformations if no methods defined

**Benefits**:
- Low barrier to entry for simple pipelines
- Full control for complex use cases
- No "magic" that can't be overridden

## Technology Stack

### Core Dependencies

- **Python 3.11+**: Required for modern type hints and pattern matching
- **Pydantic v2**: Data validation, serialization, LLM result schemas
- **SQLModel**: Database models with SQLAlchemy 2.0 + Pydantic integration
- **SQLAlchemy 2.0**: Database ORM and session management
- **PyYAML**: Prompt template storage

### Optional Dependencies

- **google-generativeai**: Gemini provider implementation (`[gemini]` extra)
- **pytest**: Test runner (`[dev]` extra)
- **pytest-cov**: Coverage reporting (`[dev]` extra)

### Database Support

- **SQLite**: Auto-initialized for development (no configuration required)
- **PostgreSQL, MySQL, etc.**: Via SQLAlchemy engine parameter

### LLM Providers

- **Gemini**: Built-in via `GeminiProvider`
- **Custom**: Implement `LLMProvider` abstract class

## Deployment Considerations

### Database Initialization

**Development** (auto-SQLite):
```python
pipeline = MyPipeline(provider=provider)
# SQLite database auto-created in memory or current directory
```

**Production** (explicit engine):
```python
from sqlalchemy import create_engine
from llm_pipeline.db import init_pipeline_db

engine = create_engine("postgresql://user:pass@host/db")
init_pipeline_db(engine)

pipeline = MyPipeline(provider=provider, engine=engine)
```

### Session Management

**Shared Session** (multi-pipeline runs):
```python
from sqlmodel import Session

with Session(engine) as session:
    pipeline1 = MyPipeline(provider=provider, session=session)
    pipeline1.execute(data1, context1)
    pipeline1.save(session)

    pipeline2 = MyPipeline(provider=provider, session=session)
    pipeline2.execute(data2, context2)
    pipeline2.save(session)

    session.commit()  # Single transaction for both
```

**Owned Session** (single pipeline run):
```python
pipeline = MyPipeline(provider=provider, engine=engine)
pipeline.execute(data, context)
pipeline.save()  # Commits transaction
pipeline.close()  # Cleanup
```

### Caching Strategy

**Development** (caching enabled):
```python
pipeline.execute(data, context, use_cache=True)
# Subsequent runs with same inputs reuse cached results
```

**Production** (caching disabled):
```python
pipeline.execute(data, context, use_cache=False)
# Always fresh LLM calls, no cache lookup overhead
```

**Cache Cleanup**:
```python
# Manual cleanup
pipeline.clear_cache()  # Clear current run only

# Database cleanup (all pipelines)
from llm_pipeline.state import PipelineStepState
from sqlmodel import select, delete
session.exec(delete(PipelineStepState).where(
    PipelineStepState.created_at < cutoff_date
))
```

### Error Handling

**LLM Failures**:
```python
# Instructions include create_failure() for graceful degradation
result = instruction_class.create_failure("API timeout")
# result.confidence_score == 0.0
# result.notes == "Failed: API timeout"
```

**Validation Failures**:
```python
# Extraction validation raises ValueError with context
# ValueError: Invalid Lane at index 3: Required field 'origin' cannot be None.
```

**Configuration Errors**:
```python
# Naming validation raises ValueError at class definition time
# ValueError: Pipeline class 'MyConfig' must end with 'Pipeline' suffix.
```

### Monitoring and Observability

**Event System**:

The primary real-time observability mechanism is the event system. The pipeline emits events at every significant execution point; handlers receive them synchronously as the pipeline runs.

`InMemoryEventHandler` captures all events as dicts for inspection after a run. Events are stored via `PipelineEvent.to_dict()` so all fields are accessed with bracket notation, not attribute access:

```python
from llm_pipeline.events.handlers import InMemoryEventHandler
from llm_pipeline.events.emitter import CompositeEmitter

handler = InMemoryEventHandler()
emitter = CompositeEmitter(handlers=[handler])

# Pass emitter into your pipeline config / strategy, then run...

# Retrieve all events for a specific run
events = handler.get_events(run_id="abc-123")
for event in events:
    print(event['event_type'], event['timestamp'])

# Filter by type
llm_events = handler.get_events_by_type('llm_call_completed', run_id="abc-123")
for event in llm_events:
    print(event['step_name'], event['raw_response'])

# Retrieve all events regardless of run
all_events = handler.get_events()
```

The event system covers 31 event types across 9 categories:

| Category | Events |
|---|---|
| `pipeline_lifecycle` | `PipelineStarted`, `PipelineCompleted`, `PipelineError` |
| `step_lifecycle` | `StepSelecting`, `StepSelected`, `StepSkipped`, `StepStarted`, `StepCompleted` |
| `llm_call` | `LLMCallPrepared`, `LLMCallStarting`, `LLMCallCompleted`, `LLMCallRetry`, `LLMCallFailed`, `LLMCallRateLimited` |
| `cache` | `CacheLookup`, `CacheHit`, `CacheMiss`, `CacheReconstruction` |
| `consensus` | `ConsensusStarted`, `ConsensusAttempt`, `ConsensusReached`, `ConsensusFailed` |
| `instructions_context` | `InstructionsStored`, `InstructionsLogged`, `ContextUpdated` |
| `transformation` | `TransformationStarting`, `TransformationCompleted` |
| `extraction` | `ExtractionStarting`, `ExtractionCompleted`, `ExtractionError` |
| `state` | `StateSaved` |

Use `CompositeEmitter` to attach multiple handlers simultaneously. A common pattern is pairing `InMemoryEventHandler` for programmatic access with `LoggingEventHandler` for structured logs:

```python
from llm_pipeline.events.handlers import InMemoryEventHandler, LoggingEventHandler
from llm_pipeline.events.emitter import CompositeEmitter

memory_handler = InMemoryEventHandler()
log_handler = LoggingEventHandler()  # uses DEFAULT_LEVEL_MAP: lifecycle=INFO, cache/state=DEBUG
emitter = CompositeEmitter(handlers=[memory_handler, log_handler])

# CompositeEmitter isolates per-handler failures -- a failing handler
# never prevents delivery to subsequent handlers.
```

**Execution Metrics**:
```python
from llm_pipeline.state import PipelineStepState
from sqlmodel import select

# Query execution times
states = session.exec(
    select(PipelineStepState)
    .where(PipelineStepState.pipeline_name == 'rate_card_parser')
    .order_by(PipelineStepState.created_at.desc())
).all()

for state in states:
    print(f"{state.step_name}: {state.execution_time_ms}ms")
```

**Data Traceability**:
```python
from llm_pipeline.state import PipelineRunInstance

# Find pipeline run that created a record
run_instances = session.exec(
    select(PipelineRunInstance)
    .where(PipelineRunInstance.model_type == 'Lane')
    .where(PipelineRunInstance.model_id == lane.id)
).all()

for instance in run_instances:
    print(f"Created by run: {instance.run_id}")
```

**Logging**:
```python
import logging

# Framework uses standard logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('llm_pipeline')
```

## Performance Characteristics

### Bottlenecks

1. **LLM API Calls**: 1-10 seconds per call (network + model latency)
   - Mitigation: Caching, consensus polling limits

2. **Database Flushes**: 10-100ms per flush (depends on model count)
   - Mitigation: Batch extractions in single step

3. **Pydantic Validation**: <1ms per instance (negligible)
   - No mitigation needed

### Scaling Considerations

**Horizontal Scaling**:
- Pipeline instances are stateless (session-scoped state only)
- Multiple workers can process different inputs in parallel
- Database session is per-pipeline, no shared state

**Vertical Scaling**:
- Memory usage: O(n) with input data size (DataFrame, extractions)
- CPU usage: Minimal (LLM calls are I/O bound)

**Database Scaling**:
- State tables grow linearly with execution count
- Periodic cleanup of old `PipelineStepState` records recommended
- Indexes on `run_id`, `pipeline_name`, `step_name`, `input_hash` for cache performance

## Security Considerations

### Prompt Injection

Framework does not sanitize user-provided variables before template substitution. **User input must be sanitized by the application** before passing to pipeline.

**Example**:
```python
# BAD: Unsanitized user input
pipeline.execute(data=df, initial_context={'user_query': request.POST['query']})

# GOOD: Sanitized input
query = sanitize_user_input(request.POST['query'])
pipeline.execute(data=df, initial_context={'user_query': query})
```

### Database Access

Pipeline requires read/write access to:
- Prompt storage tables (`prompts`)
- State tracking tables (`pipeline_step_states`, `pipeline_run_instances`)
- Domain model tables (defined in registry)

**Principle of Least Privilege**: Grant only necessary database permissions to pipeline service account.

### API Key Management

LLM provider API keys should be passed via environment variables, not hardcoded:

```python
import os
from llm_pipeline.llm.gemini import GeminiProvider

provider = GeminiProvider(api_key=os.getenv('GEMINI_API_KEY'))
```

### Data Privacy

- LLM providers receive prompts and data passed via `variables`
- Sensitive data should be anonymized before passing to pipeline
- Cached results stored in database (`PipelineStepState.result_data`) may contain sensitive information
- Consider encryption at rest for production databases

## Known Limitations

### 1. clear_cache() Bug

**Issue**: `clear_cache()` calls `self.session.delete()` instead of `self._real_session.delete()`, triggering `ReadOnlySession` RuntimeError.

**Location**: `pipeline.py` lines 570-573

**Workaround**: None currently. Bug rarely triggered because `use_cache` defaults to False.

**Fix Required**: Change to `self._real_session.delete()` and `self._real_session.commit()`.

### 2. Prompt.context Vestigial Code

**Issue**: `PromptService.get_prompt()` accepts `context` parameter but `Prompt` model has no `context` field. Code path would fail at runtime if triggered.

**Location**: `service.py` and `db/prompt.py`

**Workaround**: Do not pass `context` parameter to `get_prompt()`. Use `get_system_prompt()` or `get_user_prompt()` instead.

**History**: Field existed in earlier version (evidence in `_legacy/` folder) but was removed. Service code not updated.

### 3. Single-Level Inheritance Requirement

**Issue**: Naming validation in `__init_subclass__` only works for direct subclasses. Multi-level inheritance breaks validation.

**Example**:
```python
class _BaseExtraction(PipelineExtraction, model=BaseModel):
    pass

class LaneExtraction(_BaseExtraction):  # Validation skipped
    pass
```

**Workaround**: Use underscore prefix for intermediate base classes (e.g., `_BaseExtraction`). Validation skips classes starting with `_`.

**By Design**: All consumer project concrete classes directly subclass their base. No multi-level inheritance in practice.

### 4. Gemini-Only Provider

**Issue**: Framework ships with only `GeminiProvider` implementation. No built-in support for OpenAI, Anthropic, etc.

**Workaround**: Implement custom provider via `LLMProvider` abstract class.

**Extension Point**: Designed for pluggability, just no other implementations included.

### 5. save() Signature Inconsistency

**Documented Signature**: `save(session, tables)` where `tables` is `List[Type[SQLModel]]`

**Common Misunderstanding**: Documentation previously stated `save(session, engine)`, which is incorrect.

**Correct Usage**:
```python
# Save all registry models
pipeline.save()

# Save specific models
pipeline.save(session, tables=[Lane, Rate])
```

## Migration Guide

### From Manual LLM Orchestration

**Before** (manual approach):
```python
# Manual prompt loading
system_prompt = load_prompt('constraint_extraction.system')
user_prompt = load_prompt('constraint_extraction.user').format(table=df.to_string())

# Manual LLM call
response = llm.call(system=system_prompt, user=user_prompt)

# Manual parsing
constraints = parse_constraints(response)

# Manual database insertion
for constraint in constraints:
    lane = Lane(origin=constraint['origin'], destination=constraint['destination'])
    session.add(lane)
session.commit()
```

**After** (llm-pipeline):
```python
@step_definition(instructions=ConstraintInstructions)
class ConstraintExtractionStep(LLMStep):
    def prepare_calls(self):
        return [self.create_llm_call(variables={'table': self.pipeline.get_current_data()})]

class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        return [Lane(origin=c.origin, destination=c.destination)
                for c in results[0].constraints]

pipeline = MyPipeline(provider=GeminiProvider())
pipeline.execute(data=df, initial_context={})
pipeline.save()  # All extractions committed
```

**Benefits**:
- Automatic prompt management
- Pydantic validation
- Caching support
- Audit trail
- Type safety

### From Langchain

**Key Differences**:
- llm-pipeline is pipeline-oriented, Langchain is chain-oriented
- llm-pipeline manages database persistence, Langchain does not
- llm-pipeline enforces declarative configuration, Langchain is imperative
- llm-pipeline has built-in state tracking, Langchain requires external tools

**Migration Strategy**:
1. Map Langchain chains to llm-pipeline steps
2. Convert Langchain prompts to YAML templates
3. Implement extractions for database persistence
4. Add registry for model management
5. Create strategies for conditional execution

## Glossary

- **Pipeline**: Orchestrator managing step execution, state, and persistence
- **Strategy**: Conditional execution path based on runtime context
- **Step**: Individual LLM-powered transformation in the pipeline
- **Extraction**: Logic for converting LLM results to database models
- **Transformation**: Logic for modifying data structure (unpivot, normalize)
- **Registry**: Declarative list of database models in insertion order
- **Context**: Derived values from LLM instructions used for routing
- **Data**: Input and transformation results (DataFrames, text)
- **Extractions**: Database model instances ready for persistence
- **Instruction**: Pydantic model representing LLM result schema
- **StepDefinition**: Configuration linking step class to prompts, extractions, transformations
- **Two-Phase Write**: Flush during execution for IDs, commit during save for transaction
- **Cache Key**: Hash of inputs + prompt version for result reuse
- **Consensus Polling**: Multiple LLM calls with majority voting for high-confidence results

## References

### Source Files

- `llm_pipeline/pipeline.py` - PipelineConfig orchestrator
- `llm_pipeline/strategy.py` - PipelineStrategy and PipelineStrategies
- `llm_pipeline/step.py` - LLMStep and step_definition decorator
- `llm_pipeline/extraction.py` - PipelineExtraction base class
- `llm_pipeline/transformation.py` - PipelineTransformation base class
- `llm_pipeline/registry.py` - PipelineDatabaseRegistry base class
- `llm_pipeline/state.py` - PipelineStepState and PipelineRunInstance models
- `llm_pipeline/session/readonly.py` - ReadOnlySession wrapper
- `llm_pipeline/llm/executor.py` - execute_llm_step function
- `llm_pipeline/llm/gemini.py` - GeminiProvider implementation
- `llm_pipeline/prompts/service.py` - PromptService for template management

### Consumer Project

The logistics-intelligence `rate_card_parser` pipeline demonstrates real-world usage:
- Multi-strategy execution (lane-based, destination-based, global rates)
- Complex extraction hierarchies (RateCard -> Lane -> Rate)
- DataFrame transformations (unpivot, normalize)
- FK dependency management
- Consensus polling for critical decisions

### External Documentation

- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [SQLModel Documentation](https://sqlmodel.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
