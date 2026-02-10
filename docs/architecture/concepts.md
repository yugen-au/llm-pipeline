# Core Concepts

This document explains the fundamental concepts and architectural patterns that make up the llm-pipeline framework.

## Table of Contents

- [Declarative Configuration](#declarative-configuration)
- [Three-Tier Data Model](#three-tier-data-model)
- [Strategy Pattern](#strategy-pattern)
- [Step Lifecycle](#step-lifecycle)
- [Extraction and Transformation](#extraction-and-transformation)
- [Naming Conventions and Validation](#naming-conventions-and-validation)
- [Execution Order Validation](#execution-order-validation)
- [State Tracking and Caching](#state-tracking-and-caching)

---

## Declarative Configuration

llm-pipeline uses a declarative approach to pipeline configuration, leveraging Python's `__init_subclass__` hook to validate and configure components at class definition time rather than runtime.

### Pipeline Configuration

Pipelines declare their registry and strategies at the class level:

```python
class RateCardParserPipeline(PipelineConfig,
                             registry=RateCardParserRegistry,
                             strategies=RateCardParserStrategies):
    pass
```

**Key characteristics:**

- **Validation at class definition time:** Naming conventions and configuration errors are caught when the class is defined, not when it's instantiated
- **No boilerplate constructors:** Configuration is handled by `__init_subclass__`, keeping pipeline classes clean
- **Clear dependencies:** Registry and strategies are explicit class-level declarations

**Naming enforcement:**

- Pipeline class must end with `Pipeline` suffix
- Registry must match pattern: `{PipelinePrefix}Registry`
- Strategies must match pattern: `{PipelinePrefix}Strategies`

```python
# ✓ Valid
class RateCardParserPipeline(PipelineConfig,
                             registry=RateCardParserRegistry,
                             strategies=RateCardParserStrategies):
    pass

# ✗ Invalid - raises ValueError at class definition
class RateCardParser(PipelineConfig,  # Missing 'Pipeline' suffix
                     registry=ParserRegistry,  # Name doesn't match
                     strategies=RateCardParserStrategies):
    pass
```

### Registry Configuration

Registries declare database models in foreign key dependency order:

```python
class RateCardParserRegistry(PipelineDatabaseRegistry, models=[
    Vendor,      # No dependencies
    RateCard,    # FK to Vendor
    Lane,        # FK to RateCard
    Rate,        # FK to Lane
]):
    pass
```

**Purpose:**

- Single source of truth for database models
- Defines insertion order (respects FK dependencies)
- Auto-validated against actual FK relationships in SQLAlchemy metadata

### Strategies Configuration

Strategies classes declare which strategies are available:

```python
class RateCardParserStrategies(PipelineStrategies, strategies=[
    LaneBasedStrategy,
    DestinationBasedStrategy,
    GlobalRatesStrategy,
]):
    pass
```

### Step Definition Decorator

Steps use the `@step_definition` decorator to declare their configuration:

```python
@step_definition(
    instructions=SemanticMappingInstructions,
    default_system_key='semantic_mapping',
    default_user_key='semantic_mapping',
    default_extractions=[LaneExtraction],
    context=SemanticMappingContext
)
class SemanticMappingStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        # Implementation
        pass
```

**Validation rules:**

- Step class must end with `Step` suffix
- Instructions class must match pattern: `{StepPrefix}Instructions`
- Transformation class (if provided) must match: `{StepPrefix}Transformation`
- Context class (if provided) must match: `{StepPrefix}Context`

---

## Three-Tier Data Model

llm-pipeline separates pipeline data into three distinct tiers, each with a specific purpose and access pattern:

### 1. Context (Derived Metadata)

**Purpose:** Store derived values and metadata that influence strategy selection and step behavior.

**Access:** `pipeline.context` (read-write `Dict[str, Any]`)

**Typical contents:**
- Strategy routing values (e.g., `table_type='lane_based'`)
- Metadata extracted from instructions (e.g., `has_zones=True`)
- External references (e.g., `rate_card_id=123`)

**Lifecycle:**
- Steps contribute to context via `process_instructions()` returning a `PipelineContext` subclass
- Context values persist across steps
- Used by strategies' `can_handle()` to determine applicability

**Example:**

```python
class TableTypeDetectionContext(PipelineContext):
    table_type: str
    has_zones: bool

@step_definition(
    instructions=TableTypeDetectionInstructions,
    context=TableTypeDetectionContext
)
class TableTypeDetectionStep(LLMStep):
    def process_instructions(self, instructions) -> TableTypeDetectionContext:
        return TableTypeDetectionContext(
            table_type=instructions[0].table_type.value,
            has_zones=instructions[0].has_zones
        )

# Later, in a strategy:
def can_handle(self, context: Dict[str, Any]) -> bool:
    return context.get('table_type') == 'lane_based'
```

### 2. Data (Transformations)

**Purpose:** Store input data and its transformations through the pipeline.

**Access:** `pipeline.data` (read-write `StepKeyDict`)

**Typical contents:**
- Initial input data (e.g., `pipeline.data['input'] = dataframe`)
- Transformed data at each step (e.g., unpivoted DataFrames)

**Key type:** `StepKeyDict` - custom dict that accepts both string keys and Step class keys (normalized to snake_case)

**Lifecycle:**
- Initial data loaded before execution
- Transformations modify data in-place or create new versions
- Each transformation step can access previous data states

**Example:**

```python
# Initial load
pipeline.data['input'] = pd.read_csv('rate_card.csv')

# Transformation step modifies data
@step_definition(
    instructions=UnpivotInstructions,
    default_transformation=UnpivotTransformation
)
class UnpivotDetectionStep(LLMStep):
    pass

class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def default(self, data: pd.DataFrame, instructions: UnpivotInstructions) -> pd.DataFrame:
        # Transform data based on instructions
        return data.melt(id_vars=instructions.id_columns)

# Access via Step class key (auto-normalized)
unpivoted_df = pipeline.data[UnpivotDetectionStep]
# Equivalent to pipeline.data['unpivot_detection']
```

### 3. Extractions (Database Models)

**Purpose:** Store database model instances extracted from LLM results.

**Access:** `pipeline.extractions` (typed `Dict[Type[SQLModel], List[SQLModel]]`)

**Typical contents:**
- Database models extracted from LLM instructions
- Keyed by model class (e.g., `Lane`, `Rate`)

**Lifecycle:**
- Populated during step execution via extraction classes
- Two-phase write pattern:
  - **Phase 1 (execution):** `_real_session.add()` + `flush()` assigns database IDs
  - **Phase 2 (save):** `commit()` finalizes transaction + `PipelineRunInstance` tracking
- Enables FK references between extractions within same step or across steps

**Example:**

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def extract(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
        result = results[0]
        rate_card_id = self.pipeline.context['rate_card_id']
        lanes = []
        for lane_info in result.lanes:
            lanes.append(Lane(
                rate_card_id=rate_card_id,  # FK reference
                origin=lane_info.origin,
                destination=lane_info.destination
            ))
        return lanes

# Later, access extracted lanes
lanes = pipeline.extractions[Lane]
lane_ids = [lane.id for lane in lanes]  # IDs assigned via flush()
```

### Why Three Tiers?

**Clear separation of concerns:**
- Context: routing and metadata (what strategy to use)
- Data: input and transformations (what to process)
- Extractions: database models (what to persist)

**Type safety:**
- Context: flexible dict for any metadata
- Data: StepKeyDict with class key normalization
- Extractions: strongly typed by model class

**Lifecycle independence:**
- Context: accumulates across steps
- Data: can be replaced or modified
- Extractions: flush during execution, commit at save

---

## Strategy Pattern

Strategies define the execution plan for a pipeline, including which steps to run and when they apply.

### Strategy Selection

Strategies are evaluated for each step position based on their `can_handle()` method:

```python
class LaneBasedStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return context.get('table_type') == 'lane_based'

    def get_steps(self) -> List[StepDefinition]:
        return [
            TableTypeDetectionStep.create_definition(),
            SemanticMappingStep.create_definition(
                extractions=[LaneExtraction, RateExtraction]
            ),
        ]
```

**Selection process:**

1. Pipeline iterates through step positions (0, 1, 2...)
2. For each position, asks each strategy: `can_handle(context)?`
3. First strategy that returns `True` provides the step for that position
4. If no strategy matches, raises error

**Key characteristics:**

- Context-driven selection (based on `pipeline.context`)
- Per-step evaluation (strategy can change between steps)
- Priority order (first matching strategy wins)

### Step Definitions

`StepDefinition` objects connect a step class with its configuration:

```python
@dataclass
class StepDefinition:
    step_class: Type                              # The LLMStep subclass
    system_instruction_key: str                   # System prompt key
    user_prompt_key: str                          # User prompt key
    instructions: Type                            # Result schema (Pydantic model)
    action_after: Optional[str] = None            # Post-action name
    extractions: List[Type[PipelineExtraction]]   # Database extractions
    transformation: Optional[Type[PipelineTransformation]] = None  # Data transformation
    context: Optional[Type] = None                # Context contribution
```

**Factory pattern:**

Steps provide a `create_definition()` class method (added by `@step_definition` decorator):

```python
# Use defaults from decorator
SemanticMappingStep.create_definition()

# Override extractions for specific strategy
SemanticMappingStep.create_definition(
    extractions=[ZoneExtraction, GlobalRateExtraction]
)
```

### Prompt Auto-Discovery

When creating a step instance, prompt keys are auto-discovered if not explicitly provided:

**Priority order:**

1. **Strategy-level:** `{step_name}.{strategy_name}` (e.g., `semantic_mapping.lane_based`)
2. **Step-level:** `{step_name}` (e.g., `semantic_mapping`)
3. **Error:** If neither found, raise `ValueError`

**Example:**

```python
# Database contains:
# - 'semantic_mapping.lane_based' (system + user prompts)
# - 'semantic_mapping' (system + user prompts - fallback)

# Current strategy: LaneBasedStrategy (name='lane_based')

step_def = SemanticMappingStep.create_definition(
    system_instruction_key=None,  # Auto-discover
    user_prompt_key=None          # Auto-discover
)

# Result: Uses 'semantic_mapping.lane_based' prompts
# If 'lane_based' not found, falls back to 'semantic_mapping'
```

### Auto-Generated Properties

Strategy classes auto-generate name and display_name from class name:

```python
class LaneBasedStrategy(PipelineStrategy):
    pass

strategy = LaneBasedStrategy()
strategy.name          # 'lane_based' (auto-generated)
strategy.display_name  # 'Lane Based' (auto-generated)
```

**Naming convention validation:**

- Strategy class must end with `Strategy` suffix
- Intermediate abstract classes can start with `_` to skip validation

---

## Step Lifecycle

Steps follow a structured lifecycle with distinct phases for preparation, execution, and post-processing.

### Lifecycle Phases

```
1. Preparation
   ↓
2. LLM Execution
   ↓
3. Instruction Processing
   ↓
4. Extraction
   ↓
5. Transformation
   ↓
6. Context Contribution
```

### 1. Preparation Phase

**Method:** `prepare_calls() -> List[StepCallParams]`

**Purpose:** Prepare one or more LLM calls based on current pipeline state.

**Access:**
- `self.pipeline.context` - derived metadata
- `self.pipeline.data` - input/transformed data
- `self.pipeline.instructions` - previous step results

**Example:**

```python
class SemanticMappingStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        df = self.pipeline.data['input']
        table_type = self.pipeline.context.get('table_type')

        return [
            self.create_llm_call(
                variables={
                    'column_names': df.columns.tolist(),
                    'sample_rows': df.head(5).to_dict('records'),
                    'table_type': table_type
                }
            )
        ]
```

### 2. LLM Execution Phase

**Framework-managed:** `execute_llm_step()` called for each prepared call.

**Process:**
1. Load prompts from database (system + user)
2. Format prompts with variables
3. Auto-instantiate system variables via `VariableResolver` (if configured)
4. Call LLM provider with formatted prompts
5. Validate response against schema
6. Check for cached results (based on `input_hash + prompt_version`)

**Validation layers:**
1. Schema structure validation (JSON structure matches expected format)
2. Array response validation (if response should be list)
3. Pydantic validation (field types and constraints)
4. Extraction instance validation (NaN/NULL/FK checks)
5. Database constraint validation (deferred to commit)

### 3. Instruction Processing Phase

**Method:** `process_instructions(instructions) -> Optional[PipelineContext]`

**Purpose:** Process LLM results and optionally contribute to pipeline context.

**Example:**

```python
class TableTypeDetectionStep(LLMStep):
    def process_instructions(self, instructions: List[TableTypeDetectionInstructions]) -> TableTypeDetectionContext:
        result = instructions[0]
        return TableTypeDetectionContext(
            table_type=result.table_type.value,
            has_zones=result.has_zones
        )
```

### 4. Extraction Phase

**Framework-managed:** Extraction classes called automatically if configured in `StepDefinition`.

**Smart method detection:**

Extraction classes support flexible method naming with auto-detection:

**Priority order:**

1. **Explicit `default` method** → always used
2. **Strategy-specific method** → matches `strategy.name` (e.g., `lane_based()`)
3. **Single custom method** → auto-detected if only one method exists
4. **Error** → multiple methods but no match

**Example:**

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    # Strategy-specific methods
    def lane_based(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
        # Lane-based extraction logic
        return lanes

    def destination_based(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
        # Destination-based extraction logic
        return lanes

# Auto-routes to matching strategy method:
# - LaneBasedStrategy → calls lane_based()
# - DestinationBasedStrategy → calls destination_based()
```

**Two-phase write pattern:**

During extraction:

```python
def extract_data(self, results: List[BaseModel]) -> None:
    for extraction_class in self._extractions:
        extraction = extraction_class(self.pipeline)
        instances = extraction.extract(results)

        # Phase 1: Add to session and flush to assign IDs
        for instance in instances:
            self.pipeline._real_session.add(instance)

        self.pipeline._real_session.flush()  # Assigns database IDs

        # Store in pipeline.extractions
        self.pipeline.store_extractions(extraction_class.MODEL, instances)
```

Later, during save:

```python
def save(self, session: Session = None, tables: Optional[List[Type[SQLModel]]] = None) -> None:
    # Phase 2: Commit transaction and track instances
    self._real_session.commit()

    # Track instances in PipelineRunInstance
    for model_class, instances in self.extractions.items():
        for instance in instances:
            run_instance = PipelineRunInstance(
                run_id=self.run_id,
                model_name=model_class.__name__,
                instance_id=instance.id
            )
            self._real_session.add(run_instance)

    self._real_session.commit()
```

**Purpose of two-phase write:**

- Phase 1 enables later extractions to reference FK IDs from earlier extractions
- Phase 2 finalizes transaction and establishes traceability links

### 5. Transformation Phase

**Framework-managed:** Transformation class called automatically if configured in `StepDefinition`.

**Smart method detection:**

Transformation classes also support flexible method naming:

**Priority order:**

1. **Explicit `default` method** → always used
2. **Single custom method** → auto-detected if only one method exists
3. **Passthrough** → no methods defined, returns data unchanged
4. **Error** → multiple methods but no `default`

**Important:** Transformations do NOT support strategy-specific routing (unlike extractions).

**Example:**

```python
class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def default(self, data: pd.DataFrame, instructions: UnpivotInstructions) -> pd.DataFrame:
        return data.melt(
            id_vars=instructions.id_columns,
            value_vars=instructions.value_columns
        )
```

**Type validation:**

- Input validated against `INPUT_TYPE` before transformation
- Output validated against `OUTPUT_TYPE` after transformation
- Raises `TypeError` if types don't match

### 6. Context Contribution Phase

**Framework-managed:** Context automatically merged into `pipeline.context` if step returns `PipelineContext`.

**Example:**

```python
# Step returns context
context = step.process_instructions(instructions)  # Returns TableTypeDetectionContext

# Framework merges into pipeline.context
pipeline.context.update(context.model_dump())

# Now available to later steps and strategies
table_type = pipeline.context['table_type']
```

---

## Extraction and Transformation

### Extraction Classes

**Purpose:** Convert LLM instruction objects into database model instances.

**Configuration:**

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def lane_based(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
        result = results[0]
        rate_card_id = self.pipeline.context['rate_card_id']
        lanes = []

        for lane_data in result.lanes:
            lanes.append(Lane(
                rate_card_id=rate_card_id,
                origin=lane_data.origin,
                destination=lane_data.destination
            ))

        return lanes
```

**Access patterns:**

- `self.pipeline.context` - metadata (e.g., parent IDs)
- `self.pipeline.extractions[Model]` - previously extracted models
- `self.pipeline.session` - read-only database session

**Validation:**

Extraction instances are validated before storage:

1. **Required field validation:** Catches NULL in NOT NULL columns
2. **Foreign key validation:** Catches NULL in FK fields (except `id`)
3. **Decimal validation:** Catches NaN and Infinity values

**Example validation error:**

```python
# Missing required field
raise ValueError(
    "Invalid Lane at index 3: "
    "Required field 'origin' cannot be None. "
    "This would violate NOT NULL constraint on database insertion. "
    "Check extraction logic to ensure all required fields are populated."
)
```

**Naming convention:**

- Extraction class must end with `Extraction` suffix
- Model must be specified: `(PipelineExtraction, model=YourModel)`

### Transformation Classes

**Purpose:** Transform data structure (e.g., unpivot, normalize, reformat).

**Configuration:**

```python
class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def default(self, data: pd.DataFrame, instructions: UnpivotInstructions) -> pd.DataFrame:
        if not instructions.should_unpivot:
            return data

        return data.melt(
            id_vars=instructions.id_columns,
            value_vars=instructions.value_columns,
            var_name=instructions.variable_column_name,
            value_name=instructions.value_column_name
        )
```

**Access patterns:**

- `self.pipeline.context` - derived values
- `self.pipeline.instructions` - LLM results from other steps
- `self.pipeline.data` - access to previous data states

**Type safety:**

- Input/output types validated automatically
- Enforces type contracts across transformations

**Passthrough support:**

If no methods defined, transformation returns data unchanged:

```python
class NoOpTransformation(PipelineTransformation,
                         input_type=pd.DataFrame,
                         output_type=pd.DataFrame):
    pass  # No methods - automatically returns data unchanged
```

**Method detection differences:**

| Feature | Extraction | Transformation |
|---------|-----------|----------------|
| Strategy-specific routing | ✓ Yes (priority 2) | ✗ No |
| Default method | ✓ Yes (priority 1) | ✓ Yes (priority 1) |
| Single method auto-detect | ✓ Yes (priority 3) | ✓ Yes (priority 2) |
| Passthrough (no methods) | ✗ Error | ✓ Returns data unchanged (priority 3) |

---

## Naming Conventions and Validation

llm-pipeline enforces strict naming conventions to maintain consistency and enable auto-discovery features.

### Pipeline Components

| Component | Required Suffix | Pattern | Example |
|-----------|----------------|---------|---------|
| Pipeline | `Pipeline` | `{Name}Pipeline` | `RateCardParserPipeline` |
| Registry | `Registry` | `{PipelinePrefix}Registry` | `RateCardParserRegistry` |
| Strategies | `Strategies` | `{PipelinePrefix}Strategies` | `RateCardParserStrategies` |

**Validation:** Enforced at class definition time via `__init_subclass__`.

**Example:**

```python
# ✓ Valid - names match
class RateCardParserPipeline(PipelineConfig,
                             registry=RateCardParserRegistry,
                             strategies=RateCardParserStrategies):
    pass

# ✗ Invalid - raises ValueError at class definition
class RateCardParserPipeline(PipelineConfig,
                             registry=ParserRegistry,  # Name must be 'RateCardParserRegistry'
                             strategies=RateCardParserStrategies):
    pass
```

### Strategy Components

| Component | Required Suffix | Pattern | Example |
|-----------|----------------|---------|---------|
| Strategy | `Strategy` | `{Name}Strategy` | `LaneBasedStrategy` |

**Auto-generated properties:**

- `name`: snake_case version (`LaneBasedStrategy` → `lane_based`)
- `display_name`: Title case version (`LaneBasedStrategy` → `Lane Based`)

**Escape hatch:** Intermediate abstract classes can start with `_` to skip validation.

### Step Components

| Component | Required Suffix | Pattern | Example |
|-----------|----------------|---------|---------|
| Step | `Step` | `{Name}Step` | `SemanticMappingStep` |
| Instructions | `Instructions` | `{StepPrefix}Instructions` | `SemanticMappingInstructions` |
| Transformation | `Transformation` | `{StepPrefix}Transformation` | `SemanticMappingTransformation` |
| Context | `Context` | `{StepPrefix}Context` | `SemanticMappingContext` |

**Validation:** Enforced by `@step_definition` decorator.

**Example:**

```python
# ✓ Valid - all names match
@step_definition(
    instructions=SemanticMappingInstructions,
    default_transformation=SemanticMappingTransformation,
    context=SemanticMappingContext
)
class SemanticMappingStep(LLMStep):
    pass

# ✗ Invalid - raises ValueError at decoration
@step_definition(
    instructions=MappingInstructions,  # Must be 'SemanticMappingInstructions'
    default_transformation=SemanticMappingTransformation,
    context=SemanticMappingContext
)
class SemanticMappingStep(LLMStep):
    pass
```

### Extraction Components

| Component | Required Suffix | Pattern | Example |
|-----------|----------------|---------|---------|
| Extraction | `Extraction` | `{ModelName}Extraction` | `LaneExtraction` |

**Model configuration:** Must be specified via class parameter.

```python
# ✓ Valid
class LaneExtraction(PipelineExtraction, model=Lane):
    pass

# ✗ Invalid - raises ValueError at class definition
class LaneExtractor(PipelineExtraction, model=Lane):  # Must end with 'Extraction'
    pass
```

### Why Strict Naming?

1. **Auto-discovery:** Enables prompt key auto-discovery (`step_name.strategy_name`)
2. **StepKeyDict normalization:** Allows `pipeline.data[StepClass]` access
3. **Consistency:** Makes codebases predictable and navigable
4. **Error prevention:** Catches typos and mismatches at class definition time

### Inheritance Requirements

**Important:** Naming validation assumes **single-level inheritance** (concrete classes directly extend base classes).

**Valid patterns:**

```python
# ✓ Direct inheritance
class LaneExtraction(PipelineExtraction, model=Lane):
    pass

# ✓ Intermediate abstract class with underscore prefix
class _BaseExtraction(PipelineExtraction):
    pass

class LaneExtraction(_BaseExtraction, model=Lane):
    pass
```

**Invalid patterns:**

```python
# ✗ Multi-level inheritance without underscore prefix
class BaseExtraction(PipelineExtraction):  # Triggers validation error
    pass

class LaneExtraction(BaseExtraction, model=Lane):
    pass
```

**Rationale:** Consumer projects use direct subclassing in practice. The underscore prefix exists as an escape hatch for intermediate abstract classes.

---

## Execution Order Validation

llm-pipeline validates execution order at pipeline initialization to catch configuration errors early.

### Foreign Key Dependency Validation

**Validation:** Registry models must be ordered to respect FK dependencies.

**Process:**

1. Extract FK metadata from SQLAlchemy table definitions
2. For each model, find all FK target models
3. Verify FK targets appear BEFORE the model in registry order

**Example:**

```python
# ✓ Valid - FK dependencies respected
class RateCardParserRegistry(PipelineDatabaseRegistry, models=[
    Vendor,      # Position 0 - no dependencies
    RateCard,    # Position 1 - FK to Vendor (position 0) ✓
    Lane,        # Position 2 - FK to RateCard (position 1) ✓
    Rate,        # Position 3 - FK to Lane (position 2) ✓
]):
    pass

# ✗ Invalid - raises ValueError at initialization
class RateCardParserRegistry(PipelineDatabaseRegistry, models=[
    RateCard,    # Position 0 - FK to Vendor
    Vendor,      # Position 1 - should be BEFORE RateCard
    Lane,
    Rate,
]):
    pass

# Error message:
# Foreign key dependency error in RateCardParserRegistry:
#   'RateCard' at position 0, but FK to 'Vendor' at position 1.
# Move 'Vendor' before 'RateCard'.
```

**Implementation:**

```python
def _validate_foreign_key_dependencies(self) -> None:
    registry_models = self.REGISTRY.MODELS
    model_positions = {model: i for i, model in enumerate(registry_models)}

    for model in registry_models:
        dependencies = self._get_foreign_key_dependencies(model)
        model_position = model_positions[model]

        for dependency in dependencies:
            if model_positions[dependency] > model_position:
                raise ValueError(
                    f"Foreign key dependency error in {self.REGISTRY.__name__}:\n"
                    f"  '{model.__name__}' at position {model_position}, "
                    f"but FK to '{dependency.__name__}' at position {model_positions[dependency]}.\n"
                    f"Move '{dependency.__name__}' before '{model.__name__}'."
                )
```

### Extraction Order Validation

**Validation:** Registry order must match extraction step order.

**Process:**

1. Build execution order from all strategies' steps
2. For each model in registry, find which step extracts it
3. Verify models appear in registry in the same order they're extracted

**Example:**

```python
# Strategy defines step order:
class LaneBasedStrategy(PipelineStrategy):
    def get_steps(self) -> List[StepDefinition]:
        return [
            TableTypeDetectionStep.create_definition(),  # Position 0
            SemanticMappingStep.create_definition(       # Position 1
                extractions=[LaneExtraction, RateExtraction]  # Lane, then Rate
            ),
        ]

# ✓ Valid - registry matches extraction order
class Registry(PipelineDatabaseRegistry, models=[
    RateCard,    # Not extracted by steps - OK
    Lane,        # Extracted at position 1
    Rate,        # Extracted at position 1 (after Lane)
]):
    pass

# ✗ Invalid - raises ValueError at initialization
class Registry(PipelineDatabaseRegistry, models=[
    RateCard,
    Rate,        # Extracted at position 1
    Lane,        # Extracted at position 1 (but should be BEFORE Rate)
]):
    pass

# Error message:
# Extraction order mismatch in Registry:
#   'Rate' before 'Lane' in registry, but extracted later.
# Reorder registry to match extraction order.
```

**Why this matters:**

- Ensures database insertion order matches FK dependencies
- Prevents FK constraint violations during `flush()`
- Catches misconfigured registries at initialization, not at runtime

### Step Position Validation

**Validation:** Each step position must have exactly one matching strategy.

**Process:**

1. For step position N, ask each strategy: `can_handle(context)?`
2. If zero strategies match → error
3. If multiple strategies match → first one wins (logged warning)

**Example error:**

```python
# No strategy matches context
raise ValueError(
    f"No strategy can handle step at position 2 with context: {context}\n"
    f"Available strategies: {[s.name for s in self._strategies]}\n"
    f"Ensure at least one strategy's can_handle() returns True for this context."
)
```

---

## State Tracking and Caching

llm-pipeline provides built-in state tracking for audit trails and caching.

### PipelineStepState

**Purpose:** Audit trail of each step's execution.

**Key fields:**

- `pipeline_name`: Pipeline identifier (e.g., `rate_card_parser`)
- `run_id`: UUID for this execution
- `step_name`: Step identifier (e.g., `semantic_mapping`)
- `step_number`: Execution order (1, 2, 3...)
- `input_hash`: Hash of inputs for cache invalidation
- `result_data`: Serialized LLM instructions
- `context_snapshot`: Relevant context at this step
- `prompt_version`: Prompt version for cache invalidation
- `model`: LLM model used
- `execution_time_ms`: Performance tracking

**Caching logic:**

Cache key = `input_hash + prompt_version`

- If cached state found with matching key → reuse result
- Otherwise → execute LLM call and save new state

**Example:**

```python
# First execution
state1 = PipelineStepState(
    pipeline_name='rate_card_parser',
    run_id='550e8400-e29b-41d4-a716-446655440000',
    step_name='semantic_mapping',
    step_number=2,
    input_hash='abc123',
    prompt_version='1.0.0',
    result_data={'lanes': [...], 'confidence_score': 0.95},
    execution_time_ms=1234
)

# Second execution with same inputs
# Cache hit: input_hash='abc123', prompt_version='1.0.0'
# Reuses state1.result_data, skips LLM call

# Third execution after prompt update
# Cache miss: input_hash='abc123', prompt_version='1.1.0' (version changed)
# Executes new LLM call, saves new state
```

### PipelineRunInstance

**Purpose:** Traceability linking between pipeline runs and created database instances.

**Key fields:**

- `run_id`: UUID of the pipeline run
- `model_name`: Model class name (e.g., `Lane`)
- `instance_id`: Primary key of the created instance
- `created_at`: Timestamp

**Use cases:**

- "Which pipeline run created this Lane instance?"
- "What instances were created by this run?"
- "Re-create or validate data from a specific run"

**Example:**

```python
# During save()
for model_class, instances in pipeline.extractions.items():
    for instance in instances:
        run_instance = PipelineRunInstance(
            run_id=pipeline.run_id,
            model_name=model_class.__name__,
            instance_id=instance.id
        )
        session.add(run_instance)

# Later, query instances from a specific run
from sqlmodel import select

instances = session.exec(
    select(PipelineRunInstance)
    .where(PipelineRunInstance.run_id == run_id)
).all()

for ri in instances:
    print(f"{ri.model_name} ID {ri.instance_id} created at {ri.created_at}")
```

### Cache Invalidation

**Triggers:**

1. **Input change:** Different data → different `input_hash`
2. **Prompt update:** Prompt version incremented → cache miss
3. **Manual clear:** Call `pipeline.clear_cache(step_name)` (known bug - see limitations)

**Known limitation:**

`clear_cache()` currently uses `ReadOnlySession` for delete/commit operations, which raises `RuntimeError`. Should use `_real_session` instead. Workaround: delete state records manually or use `use_cache=False` in execute params.

---

## Summary

llm-pipeline's core concepts work together to provide:

1. **Declarative configuration** - validate at class definition time
2. **Three-tier data model** - clear separation of context, data, extractions
3. **Strategy pattern** - context-driven step selection
4. **Structured lifecycle** - prepare → execute → process → extract → transform → contribute
5. **Smart method detection** - flexible extraction/transformation method naming
6. **Strict naming conventions** - enable auto-discovery and consistency
7. **Execution order validation** - catch FK and extraction order errors early
8. **State tracking** - audit trails and caching built-in

These patterns combine to create a robust framework for building LLM-powered data pipelines with strong guarantees and minimal boilerplate.
