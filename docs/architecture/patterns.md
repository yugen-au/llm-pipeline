# Design Patterns

## Overview

The llm-pipeline framework employs several sophisticated design patterns to achieve its declarative, type-safe, and extensible architecture. These patterns work together to enable automatic configuration validation, smart method detection, safe database operations, and flexible extension points.

This document details the core design patterns used throughout the framework, with practical examples showing how they work together.

---

## Table of Contents

- [Class-Level Configuration via __init_subclass__](#class-level-configuration-via-__init_subclass__)
- [Step Factory Pattern via @step_definition](#step-factory-pattern-via-step_definition)
- [Smart Method Detection Pattern](#smart-method-detection-pattern)
- [StepKeyDict Pattern](#stepkeydict-pattern)
- [Read-Only Session Pattern](#read-only-session-pattern)
- [Two-Phase Write Pattern](#two-phase-write-pattern)
- [Extension Points](#extension-points)

---

## Class-Level Configuration via __init_subclass__

### Purpose

Validate naming conventions and relationships at class definition time, catching configuration errors before runtime. This pattern enables declarative configuration while maintaining strict enforcement of framework conventions.

### How It Works

Python's `__init_subclass__` hook is called automatically whenever a class is subclassed. The framework uses this to:

1. Validate naming conventions (e.g., classes ending with `Pipeline`, `Step`, `Extraction`)
2. Enforce relationships between related classes (e.g., `RateCardPipeline` requires `RateCardRegistry` and `RateCardStrategies`)
3. Set class-level configuration attributes
4. Prevent mismatched or incorrectly named components

### Implementation Examples

#### Pipeline Configuration

```python
# llm_pipeline/pipeline.py
class PipelineConfig(ABC):
    REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
    STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None

    def __init_subclass__(cls, registry=None, strategies=None, **kwargs):
        super().__init_subclass__(**kwargs)

        if registry is not None or strategies is not None:
            # Enforce naming convention: Pipeline suffix
            if not cls.__name__.endswith("Pipeline"):
                raise ValueError(
                    f"Pipeline class '{cls.__name__}' must end with 'Pipeline' suffix."
                )

            # Extract base name
            pipeline_name_prefix = cls.__name__[:-8]  # Remove "Pipeline"

            # Validate registry name matches pipeline
            if registry is not None:
                expected = f"{pipeline_name_prefix}Registry"
                if registry.__name__ != expected:
                    raise ValueError(
                        f"Registry for {cls.__name__} must be named '{expected}', "
                        f"got '{registry.__name__}'"
                    )

            # Validate strategies name matches pipeline
            if strategies is not None:
                expected = f"{pipeline_name_prefix}Strategies"
                if strategies.__name__ != expected:
                    raise ValueError(
                        f"Strategies for {cls.__name__} must be named '{expected}', "
                        f"got '{strategies.__name__}'"
                    )

        if registry is not None:
            cls.REGISTRY = registry
        if strategies is not None:
            cls.STRATEGIES = strategies
```

**Usage:**

```python
# Correct usage - validated at class definition time
class RateCardPipeline(PipelineConfig,
                       registry=RateCardRegistry,
                       strategies=RateCardStrategies):
    pass  # ✓ Valid: names match convention

# This would raise ValueError at class definition time:
class RateCardPipeline(PipelineConfig,
                       registry=WrongNameRegistry,  # ✗ Error: must be RateCardRegistry
                       strategies=RateCardStrategies):
    pass
```

#### Extraction Configuration

```python
# llm_pipeline/extraction.py
class PipelineExtraction(ABC):
    MODEL: ClassVar[Type[SQLModel]] = None

    def __init_subclass__(cls, model=None, **kwargs):
        super().__init_subclass__(**kwargs)

        # Set MODEL from class parameter
        if model is not None:
            cls.MODEL = model
        # Validate concrete extractions have a model
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineExtraction:
            raise ValueError(
                f"{cls.__name__} must specify model parameter when defining the class:\n"
                f"class {cls.__name__}(PipelineExtraction, model=YourModel)"
            )

        # Enforce naming convention: Extraction suffix
        if not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineExtraction:
            if not cls.__name__.endswith('Extraction'):
                raise ValueError(
                    f"{cls.__name__} must follow naming convention: {{ModelName}}Extraction"
                )
```

**Usage:**

```python
from sqlmodel import SQLModel, Field

class Lane(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str

# Correct usage
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        # extraction logic
        return [Lane(...)]

# These would raise ValueError at class definition time:
class WrongName(PipelineExtraction, model=Lane):  # ✗ Must end with 'Extraction'
    pass

class LaneExtraction(PipelineExtraction):  # ✗ Must specify model parameter
    pass
```

#### LLMResultMixin Validation

```python
# llm_pipeline/step.py
class LLMResultMixin(BaseModel):
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0)
    notes: str | None = Field(default=None)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Validate example if provided
        if not hasattr(cls, 'example'):
            return
        if not isinstance(cls.example, dict):
            raise ValueError(
                f"{cls.__name__}.example must be a dict, got {type(cls.example).__name__}"
            )

        # Validate example by instantiating the class
        try:
            cls(**cls.example)
        except Exception as e:
            raise ValueError(
                f"{cls.__name__}.example is invalid: {e}"
            )
```

**Usage:**

```python
class SemanticMappingInstructions(LLMResultMixin):
    column_mappings: List[ColumnMapping]

    example = {  # Validated at class definition time
        "column_mappings": [{"source": "Origin", "target": "origin_city"}],
        "confidence_score": 0.95,
        "notes": "High confidence mapping"
    }
```

### Benefits

- **Early error detection**: Configuration errors caught at import time, not runtime
- **Type safety**: Relationships between components validated automatically
- **Declarative syntax**: Clean, readable class definitions
- **Self-documenting**: Naming conventions encode relationships

---

## Step Factory Pattern via @step_definition

### Purpose

Provide a declarative decorator for LLM steps that:
1. Validates naming conventions at class definition time
2. Stores configuration on the class
3. Auto-generates factory methods for creating step definitions
4. Reduces boilerplate code

### How It Works

The `@step_definition` decorator:
1. Validates step name matches instruction class name
2. Validates transformation/context class names if provided
3. Stores configuration as class attributes
4. Injects a `create_definition()` classmethod that returns `StepDefinition` instances

### Implementation

```python
# llm_pipeline/step.py
def step_definition(
    instructions: Type[BaseModel],
    default_system_key: Optional[str] = None,
    default_user_key: Optional[str] = None,
    default_extractions: Optional[List] = None,
    default_transformation=None,
    context: Optional[Type] = None,
):
    """
    Decorator that auto-generates a factory function for creating step definitions.

    Validates naming conventions and stores configuration on the class.
    """
    def decorator(step_class):
        # Validate step name ends with 'Step'
        if not step_class.__name__.endswith('Step'):
            raise ValueError(
                f"{step_class.__name__} must follow naming convention: {{StepName}}Step"
            )

        step_name_prefix = step_class.__name__[:-4]  # Remove 'Step'

        # Validate instruction class name
        expected_instruction_name = f"{step_name_prefix}Instructions"
        if instructions.__name__ != expected_instruction_name:
            raise ValueError(
                f"Instruction class for {step_class.__name__} must be named "
                f"'{expected_instruction_name}', got '{instructions.__name__}'"
            )

        # Validate transformation name if provided
        if default_transformation:
            expected_transformation_name = f"{step_name_prefix}Transformation"
            if default_transformation.__name__ != expected_transformation_name:
                raise ValueError(
                    f"Transformation class for {step_class.__name__} must be named "
                    f"'{expected_transformation_name}', got '{default_transformation.__name__}'"
                )

        # Validate context name if provided
        if context:
            expected_context_name = f"{step_name_prefix}Context"
            if context.__name__ != expected_context_name:
                raise ValueError(
                    f"Context class for {step_class.__name__} must be named "
                    f"'{expected_context_name}', got '{context.__name__}'"
                )

        # Store configuration on class
        step_class.INSTRUCTIONS = instructions
        step_class.DEFAULT_SYSTEM_KEY = default_system_key
        step_class.DEFAULT_USER_KEY = default_user_key
        step_class.DEFAULT_EXTRACTIONS = default_extractions or []
        step_class.DEFAULT_TRANSFORMATION = default_transformation
        step_class.CONTEXT = context

        # Inject factory method
        @classmethod
        def create_definition(
            cls,
            system_instruction_key: Optional[str] = None,
            user_prompt_key: Optional[str] = None,
            extractions: Optional[List] = None,
            transformation=None,
            **kwargs
        ):
            from llm_pipeline.strategy import StepDefinition

            if extractions is None:
                extractions = cls.DEFAULT_EXTRACTIONS
            if transformation is None:
                transformation = cls.DEFAULT_TRANSFORMATION

            return StepDefinition(
                step_class=cls,
                system_instruction_key=system_instruction_key or cls.DEFAULT_SYSTEM_KEY,
                user_prompt_key=user_prompt_key or cls.DEFAULT_USER_KEY,
                instructions=cls.INSTRUCTIONS,
                extractions=extractions,
                transformation=transformation,
                context=cls.CONTEXT,
                **kwargs
            )

        step_class.create_definition = create_definition
        return step_class

    return decorator
```

### Usage Example

```python
# Define instruction schema
class SemanticMappingInstructions(LLMResultMixin):
    column_mappings: List[ColumnMapping]

# Define extraction
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        return [Lane(...)]

# Apply decorator - validation happens at definition time
@step_definition(
    instructions=SemanticMappingInstructions,
    default_system_key="semantic_mapping",
    default_user_key="semantic_mapping_user",
    default_extractions=[LaneExtraction]
)
class SemanticMappingStep(LLMStep):
    def process_instructions(self, instructions):
        return {"mappings": instructions[0].column_mappings}

# Use factory method in strategy
class LaneBasedStrategy(PipelineStrategy):
    def get_steps(self):
        return [
            SemanticMappingStep.create_definition(),
            # Can override defaults:
            SemanticMappingStep.create_definition(
                system_instruction_key="semantic_mapping.custom"
            )
        ]
```

### Benefits

- **Automatic validation**: Names validated at class definition time
- **Reduced boilerplate**: Factory method auto-generated
- **Flexible overrides**: Defaults can be overridden per strategy
- **Type-safe**: Configuration stored as typed class attributes

---

## Smart Method Detection Pattern

### Purpose

Enable flexible extraction and transformation implementations without requiring explicit method configuration. The framework automatically detects and routes to the appropriate method based on context.

### Detection Priority Order

#### Extraction Method Detection

```python
# llm_pipeline/extraction.py
def extract(self, results: List[any]) -> List[SQLModel]:
    """
    Auto-detect and call the appropriate extraction method.

    Priority order:
    1. Explicit 'default' method → always used
    2. Strategy-specific method (e.g., 'lane_based') → matches strategy name
    3. Single custom method → auto-detected if only one method exists
    4. Error → multiple methods exist but none match
    """
    # Get custom methods (excluding inherited and private)
    all_methods = set(dir(self))
    base_methods = set(dir(PipelineExtraction))
    custom_methods = [
        m for m in (all_methods - base_methods)
        if callable(getattr(self, m))
        and not m.startswith('_')
        and m != 'extract'
    ]

    # Priority 1: explicit 'default' method
    if 'default' in custom_methods:
        instances = self.default(results)
        return self._validate_instances(instances)

    # Priority 2: strategy-specific method
    if hasattr(self.pipeline, '_current_strategy') and self.pipeline._current_strategy:
        strategy_name = self.pipeline._current_strategy.name
        if strategy_name in custom_methods:
            method = getattr(self, strategy_name)
            instances = method(results)
            return self._validate_instances(instances)

    # Priority 3: single custom method
    if len(custom_methods) == 1:
        method = getattr(self, custom_methods[0])
        instances = method(results)
        return self._validate_instances(instances)

    # Priority 4: error (no methods or ambiguous)
    if len(custom_methods) == 0:
        raise NotImplementedError(
            f"{self.__class__.__name__} has no extraction methods defined."
        )

    raise NotImplementedError(
        f"{self.__class__.__name__} has multiple extraction methods {custom_methods} "
        f"but no matching method for current strategy and no 'default' method."
    )
```

#### Transformation Method Detection

**Important**: Transformation does NOT support strategy-specific routing. Only `default()`, single method, or passthrough patterns are supported.

```python
# llm_pipeline/transformation.py
def transform(self, data: Any, instructions: Any) -> Any:
    """
    Auto-detect and call the appropriate transformation method.

    Priority order:
    1. Explicit 'default' method → always used
    2. Single custom method → auto-detected if only one method exists
    3. Passthrough → returns data unchanged if no methods defined
    4. Error → multiple methods exist but none named 'default'
    """
    self._validate_input(data)

    # Get custom methods
    all_methods = set(dir(self))
    base_methods = set(dir(PipelineTransformation))
    custom_methods = [
        m for m in (all_methods - base_methods)
        if callable(getattr(self, m))
        and not m.startswith('_')
        and m != 'transform'
    ]

    # Priority 1: explicit 'default' method
    if 'default' in custom_methods:
        result = self.default(data, instructions)
    # Priority 2: single custom method
    elif len(custom_methods) == 1:
        method = getattr(self, custom_methods[0])
        result = method(data, instructions)
    # Priority 3: passthrough (no methods)
    elif len(custom_methods) == 0:
        result = data
    # Priority 4: error (ambiguous)
    else:
        raise NotImplementedError(
            f"{self.__class__.__name__} has multiple transformation methods {custom_methods} "
            f"but no 'default' method."
        )

    self._validate_output(result)
    return result
```

### Usage Examples

#### Single Method (Auto-detected)

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def extract_lanes(self, results):  # Any name works
        # Framework auto-detects this as the only method
        return [Lane(...)]
```

#### Explicit Default Method

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):  # Always used
        return [Lane(...)]

    def alternative(self, results):  # Never called (default takes priority)
        return [Lane(...)]
```

#### Strategy-Specific Methods (Extraction Only)

```python
class RateExtraction(PipelineExtraction, model=Rate):
    def lane_based(self, results):
        # Called when strategy.name == "lane_based"
        return [Rate(...)]

    def zone_based(self, results):
        # Called when strategy.name == "zone_based"
        return [Rate(...)]
```

#### Passthrough Transformation

```python
class NoOpTransformation(PipelineTransformation,
                          input_type=pd.DataFrame,
                          output_type=pd.DataFrame):
    # No methods defined → data passes through unchanged
    pass
```

### Benefits

- **Convention over configuration**: Simple cases "just work" without configuration
- **Flexibility**: Complex cases can use explicit routing
- **Strategy polymorphism**: Extractions can adapt to different strategies
- **Clear error messages**: Ambiguous cases caught with helpful guidance

---

## StepKeyDict Pattern

### Purpose

Allow accessing step data/instructions using both string keys (snake_case) and Step class references, providing a clean API that works naturally with both runtime strings and compile-time class references.

### Implementation

```python
# llm_pipeline/pipeline.py
class StepKeyDict(dict):
    """Dictionary that accepts both string keys and Step class keys."""

    @staticmethod
    def _normalize_key(key):
        if isinstance(key, type) and key.__name__.endswith("Step"):
            # Convert Step class to snake_case string
            class_name = key.__name__[:-4]  # Remove "Step"
            # CamelCase → snake_case
            step_name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", class_name)
            step_name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", step_name)
            return step_name.lower()
        return key

    def __getitem__(self, key):
        return super().__getitem__(self._normalize_key(key))

    def __setitem__(self, key, value):
        return super().__setitem__(self._normalize_key(key), value)

    def __contains__(self, key):
        return super().__contains__(self._normalize_key(key))

    def get(self, key, default=None):
        return super().get(self._normalize_key(key), default)

    def pop(self, key, *args):
        return super().pop(self._normalize_key(key), *args)
```

### Usage Examples

```python
# In PipelineConfig.__init__
self.data = StepKeyDict()
self._instructions = StepKeyDict()

# During execution - both access methods work identically:

# String-based access (snake_case)
pipeline.data["semantic_mapping"] = df
instructions = pipeline.get_instructions("semantic_mapping")

# Class-based access
pipeline.data[SemanticMappingStep] = df
instructions = pipeline.get_instructions(SemanticMappingStep)

# Both access the same underlying key: "semantic_mapping"
```

### Normalization Rules

```python
# Class name → snake_case
SemanticMappingStep → "semantic_mapping"
UnpivotDetectionStep → "unpivot_detection"
RateExtractionStep → "rate_extraction"
```

### Benefits

- **Type safety**: IDE autocomplete works with class references
- **Flexibility**: Runtime string keys also work
- **Consistency**: Same data accessible via both methods
- **Refactoring-friendly**: Rename class → automatic key updates

---

## Read-Only Session Pattern

### Purpose

Prevent accidental database writes during step execution while allowing read operations. Database modifications should only occur during controlled phases (extraction with flush, save with commit).

### Implementation

```python
# llm_pipeline/session/readonly.py
class ReadOnlySession:
    """
    Read-only wrapper for SQLModel Session.

    Allows all read operations but blocks write operations to prevent
    accidental database modifications during step execution.
    """

    def __init__(self, session: Session):
        self._session = session

    # Allow read operations
    def query(self, *args, **kwargs):
        return self._session.query(*args, **kwargs)

    def exec(self, *args, **kwargs):
        return self._session.exec(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._session.get(*args, **kwargs)

    # Block write operations
    def add(self, *args, **kwargs):
        raise RuntimeError(
            "Cannot write to database during step execution. "
            "Database writes are only allowed in pipeline.save(). "
            "If you need to create database records during extraction, "
            "create the model instances and return them - the pipeline "
            "will handle insertion in the correct order."
        )

    def commit(self, *args, **kwargs):
        raise RuntimeError(
            "Cannot commit to database during step execution. "
            "Database writes are only allowed in pipeline.save()."
        )

    def delete(self, *args, **kwargs):
        raise RuntimeError(
            "Cannot delete from database during step execution. "
            "Database writes are only allowed in pipeline.save()."
        )

    def flush(self, *args, **kwargs):
        raise RuntimeError(
            "Cannot flush to database during step execution. "
            "Database writes are only allowed in pipeline.save()."
        )
```

### Usage in Pipeline

```python
# llm_pipeline/pipeline.py
def __init__(self, ...):
    # Create real session
    if session is not None:
        self._owns_session = False
        self._real_session = session
    else:
        if engine is None:
            engine = init_pipeline_db()
        self._owns_session = True
        self._real_session = Session(engine)

    # Wrap in read-only session for public API
    self.session = ReadOnlySession(self._real_session)
```

### When Read-Only Session Is Active

During normal step execution, steps receive the read-only wrapper:

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        # Can query database
        existing = self.pipeline.session.exec(
            select(RateCard).where(RateCard.id == rate_card_id)
        ).first()  # ✓ Works

        # Cannot write
        lane = Lane(...)
        self.pipeline.session.add(lane)  # ✗ RuntimeError

        # Correct approach: return instances
        return [lane]  # ✓ Pipeline handles insertion
```

### When Real Session Is Active

During controlled write phases, the framework uses `_real_session`:

```python
# Phase 1: Extraction with flush (llm_pipeline/step.py)
def extract_data(self, instructions):
    for extraction_class in self._extractions:
        extraction = extraction_class(self.pipeline)
        instances = extraction.extract(instructions)

        for instance in instances:
            self.pipeline._real_session.add(instance)  # Direct write access

        self.pipeline._real_session.flush()  # Assign IDs
        self.pipeline.store_extractions(extraction_class.MODEL, instances)

# Phase 2: Save with commit (llm_pipeline/pipeline.py)
def save(self, session: Session = None, tables: Optional[List[Type[SQLModel]]] = None):
    session = session or self._real_session  # Real session

    # ... track instances ...

    session.commit()  # Finalize transaction
```

### Benefits

- **Safety**: Prevents accidental writes during read-heavy phases
- **Clear intent**: Read vs write phases are explicit
- **Error messages**: Helpful guidance when write attempted incorrectly
- **Controlled state**: Database modifications only happen during defined phases

---

## Two-Phase Write Pattern

### Purpose

Enable foreign key references between extractions within the same step or across steps while maintaining transaction safety. This is the most critical pattern for understanding how database writes work in the framework.

### The Two Phases

**Phase 1: Execution Phase** (Flush for IDs)
- Occurs during `step.extract_data()`
- Uses `_real_session.add()` + `_real_session.flush()`
- Purpose: Assign database IDs without committing transaction
- Enables FK references between extractions

**Phase 2: Save Phase** (Commit Transaction)
- Occurs during `pipeline.save()`
- Calls `session.commit()` to finalize transaction
- Creates `PipelineRunInstance` records for traceability
- Returns summary of saved records

### Why This Pattern?

Without Phase 1 flush, extractions cannot reference each other within the same pipeline run:

```python
# Without flush:
rate_card = RateCard(name="Standard")
session.add(rate_card)
# rate_card.id is None (not assigned until commit)

lane = Lane(rate_card_id=rate_card.id)  # ✗ FK reference fails (None)

# With flush:
rate_card = RateCard(name="Standard")
session.add(rate_card)
session.flush()  # Assign ID without committing
# rate_card.id is 123 (assigned by database)

lane = Lane(rate_card_id=rate_card.id)  # ✓ FK reference works
session.add(lane)
session.flush()

# Later: commit finalizes everything
session.commit()
```

### Implementation

#### Phase 1: Extraction with Flush

```python
# llm_pipeline/step.py (called during pipeline.execute())
def extract_data(self, instructions: List[Any]) -> None:
    """
    Extract database instances from LLM instructions.

    This method uses a two-phase write pattern:
    1. Add instances to session and flush to assign IDs
    2. This allows later extractions to reference these IDs
    3. Transaction is not committed until save() is called
    """
    if not self._extractions:
        return

    for extraction_class in self._extractions:
        self.pipeline._current_extraction = extraction_class

        extraction = extraction_class(self.pipeline)
        instances = extraction.extract(instructions)

        # Phase 1: Add to session and flush to get IDs
        for instance in instances:
            self.pipeline._real_session.add(instance)  # Add to session

        self.pipeline._real_session.flush()  # Assign IDs (no commit)

        # Store in pipeline for later access
        self.pipeline.store_extractions(extraction_class.MODEL, instances)

    self.pipeline._current_extraction = None
```

#### Phase 2: Save with Commit

```python
# llm_pipeline/pipeline.py (called after pipeline.execute())
def save(
    self,
    session: Session = None,
    tables: Optional[List[Type[SQLModel]]] = None,
) -> Dict[str, int]:
    """
    Save extracted database instances to database.

    This is Phase 2 of the two-phase write pattern:
    1. Phase 1 (during execution): instances added + flushed for IDs
    2. Phase 2 (this method): commit transaction + track instances
    """
    session = session or self._real_session

    if not hasattr(self, "REGISTRY"):
        raise AttributeError(
            f"{self.__class__.__name__} must define REGISTRY class attribute."
        )

    models_to_save = tables if tables else self.REGISTRY.get_models()

    # Validate tables parameter
    if tables:
        registry_models = self.REGISTRY.get_models()
        for model_class in tables:
            if model_class not in registry_models:
                raise ValueError(
                    f"{model_class.__name__} is not in {self.REGISTRY.__name__}."
                )

    # Ensure tables exist
    for model_class in models_to_save:
        self.ensure_table(model_class, session)

    # Track instances for traceability
    results = {}
    for model_class in models_to_save:
        instances = self.get_extractions(model_class)
        self._track_created_instances(model_class, instances, session)
        model_name = model_class.__name__
        results[f"{model_name.lower()}s_saved"] = len(instances)

    # Phase 2: Commit transaction
    session.commit()

    return results

def _track_created_instances(self, model_class, instances, session):
    """Create PipelineRunInstance records for traceability."""
    from llm_pipeline.state import PipelineRunInstance

    for instance in instances:
        if hasattr(instance, "id") and instance.id:
            run_instance = PipelineRunInstance(
                run_id=self.run_id,
                model_type=model_class.__name__,
                model_id=instance.id,
            )
            session.add(run_instance)
```

### Complete Example

```python
# Define models with FK relationships
class RateCard(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str

class Lane(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    rate_card_id: int = Field(foreign_key="ratecard.id")
    origin: str
    destination: str

# Extractions
class RateCardExtraction(PipelineExtraction, model=RateCard):
    def default(self, results):
        rate_card = RateCard(name=self.pipeline.context['rate_card_name'])
        return [rate_card]

class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        # Access rate_card extracted in previous step
        rate_cards = self.pipeline.get_extractions(RateCard)
        rate_card = rate_cards[0]

        # rate_card.id is available because Phase 1 flush happened
        lanes = []
        for mapping in results[0].column_mappings:
            lane = Lane(
                rate_card_id=rate_card.id,  # ✓ FK reference works
                origin=mapping.origin,
                destination=mapping.destination
            )
            lanes.append(lane)
        return lanes

# Execution
pipeline = RateCardPipeline(provider=gemini_provider)
pipeline.execute(
    data=df,
    initial_context={"rate_card_name": "Standard Rates"}
)

# Phase 1 already happened during execute():
# - RateCard instance added + flushed → ID assigned
# - Lane instances added + flushed → FKs valid

# Phase 2: Commit transaction
results = pipeline.save()
# {'ratecards_saved': 1, 'lanes_saved': 5}
```

### Consumer Project Confirmation

From `logistics-intelligence/llm/step.py` (lines 632-639):

```python
# Add instances to session and flush to assign IDs
# This allows later extractions to reference these IDs
# Transaction is not committed until save() is called
for instance in instances:
    self.pipeline._real_session.add(instance)

self.pipeline._real_session.flush()
```

The consumer project explicitly documents this pattern with comments confirming the intent.

### Common Pitfalls

**❌ Trying to access IDs without flush:**
```python
def default(self, results):
    rate_card = RateCard(name="Standard")
    # Don't add to session yourself - return instances
    lane = Lane(rate_card_id=rate_card.id)  # None!
    return [rate_card, lane]
```

**✓ Correct approach - rely on extraction order:**
```python
# Step 1 extraction
class RateCardExtraction(PipelineExtraction, model=RateCard):
    def default(self, results):
        return [RateCard(name="Standard")]  # Framework adds + flushes

# Step 2 extraction
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        rate_card = self.pipeline.get_extractions(RateCard)[0]
        return [Lane(rate_card_id=rate_card.id)]  # ID available!
```

### Benefits

- **FK integrity**: Later extractions can reference earlier ones
- **Transaction safety**: All-or-nothing semantics preserved
- **Traceability**: PipelineRunInstance tracks what was created
- **Cache reconstruction**: Cached runs can reconstruct extractions from PipelineRunInstance records

---

## Extension Points

The framework provides several extension points for customizing behavior without modifying core code.

### LLM Model Selection

llm-pipeline uses pydantic-ai model strings to configure the LLM provider. Any model supported by pydantic-ai can be used:

```python
# Google Gemini
pipeline = RateCardPipeline(model='google-gla:gemini-2.0-flash-lite')

# OpenAI
pipeline = RateCardPipeline(model='openai:gpt-4o')

# Anthropic
pipeline = RateCardPipeline(model='anthropic:claude-3-5-sonnet-latest')

pipeline.execute(data=df, initial_context={})
```

See [pydantic-ai model configuration](https://ai.pydantic.dev/models/) for the full list of supported model strings.

### Custom Sanitization

Override `sanitize()` method on your pipeline to customize data sanitization:

```python
class RateCardPipeline(PipelineConfig,
                       registry=RateCardRegistry,
                       strategies=RateCardStrategies):

    def sanitize(self, data: Any) -> str:
        """
        Custom sanitization for rate card data.

        Override to implement domain-specific cleaning:
        - Remove PII
        - Truncate long values
        - Format for LLM consumption
        """
        if isinstance(data, str):
            return data

        if isinstance(data, pd.DataFrame):
            # Remove columns with sensitive data
            safe_df = data.drop(columns=['email', 'phone'], errors='ignore')

            # Truncate to first 100 rows for LLM context
            if len(safe_df) > 100:
                safe_df = safe_df.head(100)

            # Convert to string with formatting
            return safe_df.to_string(max_rows=100, max_cols=20)

        return str(data)
```

### Custom Variable Resolver

Implement `VariableResolver` protocol to customize prompt variable extraction:

```python
from llm_pipeline.prompts.variables import VariableResolver
from typing import Dict, Any

class CustomVariableResolver(VariableResolver):
    """
    Custom logic for extracting prompt variables from context.

    The default resolver extracts variables from BaseModel instances.
    Override to support custom data structures.
    """

    def resolve_variables(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract prompt variables from pipeline context.

        Args:
            context: Pipeline context dict

        Returns:
            Dict of variables for prompt template formatting
        """
        variables = {}

        # Extract from custom data structure
        if 'rate_card_config' in context:
            config = context['rate_card_config']
            variables['origin_column'] = config.origin_field
            variables['dest_column'] = config.destination_field
            variables['rate_column'] = config.rate_field

        # Add computed variables
        if 'df' in context:
            df = context['df']
            variables['row_count'] = len(df)
            variables['column_list'] = ', '.join(df.columns)

        return variables

# Usage
resolver = CustomVariableResolver()
pipeline = RateCardPipeline(
    provider=gemini_provider,
    variable_resolver=resolver
)
```

### Post-Action Hooks

Define post-action methods on your pipeline to execute logic after specific steps:

```python
class RateCardPipeline(PipelineConfig,
                       registry=RateCardRegistry,
                       strategies=RateCardStrategies):

    def _after_semantic_mapping(self, context: Dict[str, Any]):
        """
        Called after semantic mapping step completes.

        Use for:
        - Logging intermediate results
        - Triggering external systems
        - Validating step outputs
        - Modifying context for next steps
        """
        mappings = context.get('mappings', [])

        # Log mapping summary
        print(f"Mapped {len(mappings)} columns")

        # Validate mapping quality
        if len(mappings) < 3:
            raise ValueError("Insufficient column mappings detected")

        # Modify context for next step
        context['mapping_count'] = len(mappings)

# Configure in step definition
@step_definition(
    instructions=SemanticMappingInstructions,
    default_extractions=[LaneExtraction]
)
class SemanticMappingStep(LLMStep):
    pass

class LaneBasedStrategy(PipelineStrategy):
    def get_steps(self):
        return [
            SemanticMappingStep.create_definition(
                action_after="after_semantic_mapping"  # Hook name
            )
        ]
```

### Extraction Validation

Override `_validate_instance()` in extraction classes for custom validation:

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def _validate_instance(self, instance: Lane, index: int) -> None:
        """
        Custom validation before database insertion.

        Called automatically by framework for each extracted instance.
        """
        # Call parent validation first (NaN, NULL, FK checks)
        super()._validate_instance(instance, index)

        # Domain-specific validation
        if instance.origin == instance.destination:
            raise ValueError(
                f"Invalid Lane at index {index}: "
                f"origin and destination cannot be the same ({instance.origin})"
            )

        # Business rule validation
        if instance.transit_days is not None and instance.transit_days < 0:
            raise ValueError(
                f"Invalid Lane at index {index}: "
                f"transit_days cannot be negative ({instance.transit_days})"
            )

        # Ensure required FK references
        rate_cards = self.pipeline.get_extractions(RateCard)
        if not rate_cards:
            raise ValueError(
                f"Invalid Lane at index {index}: "
                f"No RateCard extracted yet. Ensure RateCardExtraction runs first."
            )

    def default(self, results):
        # Validation called automatically on return
        return [Lane(...)]
```

---

## Pattern Interactions

These patterns work together to create a cohesive framework:

```python
# 1. Class-level configuration validates structure at definition time
class RateCardPipeline(PipelineConfig,
                       registry=RateCardRegistry,  # Validated: must be "RateCardRegistry"
                       strategies=RateCardStrategies):  # Validated: must be "RateCardStrategies"
    pass

# 2. Step factory pattern creates step definitions
@step_definition(
    instructions=SemanticMappingInstructions,  # Validated: must be "SemanticMappingInstructions"
    default_extractions=[LaneExtraction]
)
class SemanticMappingStep(LLMStep):
    pass

# 3. Smart method detection routes to appropriate extraction method
class LaneExtraction(PipelineExtraction, model=Lane):
    def lane_based(self, results):  # Auto-detected when strategy.name == "lane_based"
        # 4. Read-only session prevents accidental writes
        rate_card = self.pipeline.session.get(RateCard, rate_card_id)  # ✓ Read OK

        # 5. StepKeyDict allows both access patterns
        instructions = self.pipeline.get_instructions(SemanticMappingStep)
        instructions = self.pipeline.get_instructions("semantic_mapping")

        # 6. Two-phase write: return instances, framework handles IDs
        return [Lane(rate_card_id=rate_card.id, ...)]

# 7. Extension points allow customization
class CustomPipeline(RateCardPipeline):
    def sanitize(self, data):  # Custom sanitization
        return super().sanitize(data).upper()

    def _after_semantic_mapping(self, context):  # Post-action hook
        print(f"Mapping complete: {len(context['mappings'])} columns")

# Execution ties it all together
pipeline = CustomPipeline(provider=custom_provider)
pipeline.execute(data=df, initial_context={})
results = pipeline.save()  # Two-phase write completes here
```

---

## Summary

The llm-pipeline framework's design patterns enable:

- **Early validation** via `__init_subclass__` hooks
- **Reduced boilerplate** via `@step_definition` decorator
- **Flexible implementations** via smart method detection
- **Type-safe access** via StepKeyDict
- **Safe database operations** via read-only session wrapper
- **FK integrity** via two-phase write pattern
- **Extensibility** via well-defined extension points

These patterns work together to create a framework that is both easy to use for simple cases and flexible enough for complex enterprise applications.
