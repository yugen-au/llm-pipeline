# Registry API Reference

## Overview

The registry module provides the base class for declaring which database models a pipeline manages and their insertion order. Each pipeline defines its own registry to ensure foreign key dependencies are satisfied during writes.

## Module: `llm_pipeline.registry`

### Classes

- [`PipelineDatabaseRegistry`](#pipelinedatabaseregistry) - Base class for pipeline database registries

---

## PipelineDatabaseRegistry

Abstract base class for pipeline database registries. Each pipeline defines a registry subclass that declares managed models in FK-safe insertion order.

**Purpose:** Single source of truth for:
1. What database tables the pipeline creates
2. What order to insert them (FK dependencies)
3. Which models the `save()` method operates on

### Class Definition Syntax

Registries use **class call syntax** to configure models at definition time:

```python
class MyPipelineRegistry(PipelineDatabaseRegistry, models=[
    Vendor,      # No dependencies
    RateCard,    # Depends on Vendor (vendor_id FK)
    Lane,        # Depends on RateCard (rate_card_id FK)
]):
    pass
```

**Parameters:**
- `models` (List[Type[SQLModel]]) - Model classes in insertion order (required for concrete registries)

**Validation:** Raises `ValueError` if:
- `models` not provided for concrete registry
- Class doesn't follow naming conventions (see below)

### Naming Conventions

Registry classes must follow strict naming to match their pipeline:

**Pattern:** `{PipelineName}Registry`

**Examples:**
```python
# Pipeline: RateCardParserPipeline
# Registry must be: RateCardParserRegistry

class RateCardParserPipeline(PipelineConfig,
                             registry=RateCardParserRegistry,
                             strategies=RateCardParserStrategies):
    pass
```

**Validation:** Enforced at pipeline class definition via `PipelineConfig.__init_subclass__`:
- Pipeline name must end with `Pipeline`
- Registry name must be `{prefix}Registry` where prefix matches pipeline
- Raises `ValueError` on mismatch

### Class Attributes

**`MODELS`** (ClassVar[List[Type[SQLModel]]])
- List of managed model classes
- Set via `models` parameter during class definition
- Used by `save()` to determine insertion order
- Accessed via `get_models()` classmethod

### Methods

#### `get_models()`

Returns all managed models in insertion order.

```python
@classmethod
def get_models(cls) -> List[Type[SQLModel]]
```

**Returns:** List of model classes ordered by FK dependencies

**Raises:** `ValueError` if `MODELS` not defined

**Example:**

```python
models = RateCardParserRegistry.get_models()
# Returns: [Vendor, RateCard, Lane, Rate, ChargeType, ...]
# Order ensures Vendor inserted before RateCard (vendor_id FK)
```

### Foreign Key Ordering

The order of models in the registry **MUST** respect foreign key dependencies:

**Rule:** Parent tables BEFORE child tables

**Example:**

```python
# CORRECT: Parent before child
class MyRegistry(PipelineDatabaseRegistry, models=[
    Vendor,      # Has no FKs
    RateCard,    # Has vendor_id FK -> Vendor
    Lane,        # Has rate_card_id FK -> RateCard
]):
    pass

# INCORRECT: Child before parent
class BrokenRegistry(PipelineDatabaseRegistry, models=[
    Lane,        # Depends on RateCard
    RateCard,    # Depends on Vendor
    Vendor,      # Inserted last - violates FKs!
]):
    pass
```

**Validation:** `PipelineConfig._validate_registry_order()` checks FK dependencies at pipeline initialization:

```python
# Extracts FK references from SQLAlchemy table metadata
for model_class in registry.get_models():
    for fk in model_class.__table__.foreign_keys:
        referenced_table = fk.column.table
        # Ensures referenced model appears earlier in registry
```

**Error:** Raises `ValueError` if FK dependency ordering violated:

```
ValueError: Foreign key dependency violation in MyRegistry:
Lane depends on RateCard, but RateCard appears later in registry.
Move RateCard before Lane in models list.
```

### Integration with Pipeline

#### Registration

Registries are bound to pipelines via class parameters:

```python
class RateCardParserPipeline(PipelineConfig,
                             registry=RateCardParserRegistry,
                             strategies=RateCardParserStrategies):
    pass
```

**Validation at definition time:**
- Registry name must match pipeline name pattern
- Registry must have `MODELS` configured
- All FK dependencies must be ordered correctly

#### Usage During Save

The `pipeline.save()` method uses registry to determine write order:

```python
# In PipelineConfig.save()
models_to_save = tables if tables else self.REGISTRY.get_models()

for model_class in models_to_save:
    instances = self.get_extractions(model_class)
    # Insert in registry order - FKs satisfied
```

**Two-Phase Write Pattern:**

1. **During execution:** Extractions call `session.add()` + `session.flush()` to assign IDs
2. **During save:** Registry order determines final insertion, then `session.commit()`

**Why flush during execution?** Enables later extractions to reference FKs of earlier extractions within the same step.

### Example: Complete Registry

```python
from llm_pipeline import PipelineDatabaseRegistry
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List

# Define domain models
class Vendor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    rate_cards: List["RateCard"] = Relationship(back_populates="vendor")

class RateCard(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vendor_id: int = Field(foreign_key="vendor.id")  # FK to Vendor
    name: str
    vendor: Vendor = Relationship(back_populates="rate_cards")
    lanes: List["Lane"] = Relationship(back_populates="rate_card")

class Lane(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rate_card_id: int = Field(foreign_key="ratecard.id")  # FK to RateCard
    origin: str
    destination: str
    rate_card: RateCard = Relationship(back_populates="lanes")

# Define registry with FK-safe order
class RateCardParserRegistry(PipelineDatabaseRegistry, models=[
    Vendor,      # First - no dependencies
    RateCard,    # Second - depends on Vendor
    Lane,        # Third - depends on RateCard
]):
    """
    Registry for rate card parser pipeline.

    Insertion order ensures foreign key integrity:
    1. Vendor (no FKs)
    2. RateCard (vendor_id -> Vendor.id)
    3. Lane (rate_card_id -> RateCard.id)
    """
    pass
```

### Example: Using Registry

```python
from llm_pipeline import PipelineConfig

class RateCardParserPipeline(PipelineConfig,
                             registry=RateCardParserRegistry,
                             strategies=RateCardParserStrategies):
    pass

# Initialize and execute
pipeline = RateCardParserPipeline(
    session=session,
    provider=gemini_provider
)

pipeline.execute(
    data=rate_card_pdf,
    initial_context={"table_type": "lane_based"}
)

# Save uses registry order
results = pipeline.save()
# Inserts: Vendor -> RateCard -> Lane (FK-safe order)

# Query what was created
print(results)
# {"vendors_saved": 1, "ratecards_saved": 1, "lanes_saved": 12}
```

### Example: Partial Save

The `tables` parameter allows saving only specific models:

```python
# Save only Vendor and RateCard (skip Lane)
results = pipeline.save(tables=[Vendor, RateCard])

# Validation: tables must be in registry
try:
    pipeline.save(tables=[SomeOtherModel])
except ValueError as e:
    print(e)
    # "SomeOtherModel is not in RateCardParserRegistry."
```

**Use case:** Incremental persistence during long-running pipelines.

### Advanced: Intermediate Base Classes

For complex pipelines with shared model hierarchies, use underscore-prefix convention:

```python
# Intermediate abstract registry (not validated)
class _BaseParserRegistry(PipelineDatabaseRegistry):
    """Abstract base - no models enforcement."""
    pass

# Concrete registry (models required)
class RateCardParserRegistry(_BaseParserRegistry, models=[
    Vendor,
    RateCard,
    Lane,
]):
    pass
```

**Validation logic:** Only validates concrete registries that:
1. Don't start with underscore
2. Directly subclass `PipelineDatabaseRegistry`

**Pattern used when:** Multiple pipelines share common model subsets.

---

## ReadOnlySession

While not part of the registry module, `ReadOnlySession` enforces the registry-based write pattern.

**Module:** `llm_pipeline.session.readonly`

**Purpose:** Prevents accidental database writes during step execution by wrapping the session and blocking write operations.

### Architecture

During pipeline execution:
- `pipeline.session` → `ReadOnlySession` wrapper (blocks writes)
- `pipeline._real_session` → Actual SQLModel Session (used internally)

During `save()`:
- `pipeline.save()` uses `_real_session` for writes
- Registry order determines insertion sequence

### Blocked Operations

The following operations raise `RuntimeError` during step execution:

```python
# Write operations (blocked)
session.add(instance)           # RuntimeError
session.add_all(instances)      # RuntimeError
session.delete(instance)        # RuntimeError
session.flush()                 # RuntimeError
session.commit()                # RuntimeError
session.merge(instance)         # RuntimeError

# State management (blocked)
session.refresh(instance)       # RuntimeError
session.expire(instance)        # RuntimeError
session.expire_all()           # RuntimeError
session.expunge(instance)       # RuntimeError
session.expunge_all()          # RuntimeError
```

### Allowed Operations

Read operations work normally:

```python
# Query operations (allowed)
session.query(Model).filter(...)   # OK
session.exec(select(Model))        # OK
session.get(Model, id)             # OK
session.execute(statement)         # OK
session.scalar(statement)          # OK
session.scalars(statement)         # OK

# Metadata (allowed)
session.bind                       # OK
session.info                       # OK
session.is_active()               # OK
```

### Error Messages

All blocked operations provide clear guidance:

```python
try:
    pipeline.session.add(instance)
except RuntimeError as e:
    print(e)
    # "Cannot write to database during step execution.
    #  Database writes are only allowed in pipeline.save().
    #  If you need to create database records during extraction,
    #  create the model instances and return them - the pipeline
    #  will handle insertion in the correct order."
```

### Design Rationale

**Why block writes during execution?**

1. **Registry enforcement:** Ensures all writes go through registry-ordered `save()`
2. **FK safety:** Prevents out-of-order insertions that violate dependencies
3. **Clarity:** Separates computation (steps) from persistence (save)
4. **Testing:** Steps can be tested without database writes

**When are writes actually performed?**

During extraction, the framework internally uses `_real_session`:

```python
# In PipelineExtraction.extract_data()
for instance in instances:
    self.pipeline._real_session.add(instance)
self.pipeline._real_session.flush()  # Assigns IDs
# No commit yet - transaction stays open
```

Then during save:

```python
# In PipelineConfig.save()
for model_class in self.REGISTRY.get_models():
    instances = self.get_extractions(model_class)
    self._track_created_instances(model_class, instances, session)
session.commit()  # Finalizes transaction
```

### Example: Attempting Write

```python
class MyStep(LLMStep):
    def extract_data(self, instructions):
        # WRONG: Trying to write directly
        try:
            vendor = Vendor(name="Acme Corp")
            self.pipeline.session.add(vendor)  # RuntimeError!
        except RuntimeError:
            pass

        # CORRECT: Return instance, let extraction handle it
        return [Vendor(name="Acme Corp")]

# Configure extraction
@step_definition(
    system_instruction_key="vendor_extraction",
    user_prompt_key="vendor_user",
    instructions=VendorInstructions,
    extractions=[VendorExtraction]  # Handles add/flush/commit
)
class MyStep(LLMStep):
    pass
```

---

## See Also

- [State API Reference](state.md) - Pipeline state tracking and caching
- [Pipeline API Reference](pipeline.md) - Pipeline execution and save logic
- [Extraction API Reference](extraction.md) - Extraction classes and FK handling
- [Architecture: Patterns](../architecture/patterns.md) - Two-phase write pattern and registry design
- [Architecture: Concepts](../architecture/concepts.md) - FK dependency validation
