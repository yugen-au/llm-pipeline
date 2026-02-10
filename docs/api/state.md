# State API Reference

## Overview

The state module provides generic state tracking for pipeline executions, enabling audit trails, caching, and traceability. These models work for ANY pipeline type and are not tied to specific domains.

## Module: `llm_pipeline.state`

### Models

- [`PipelineStepState`](#pipelinestepstate) - Audit trail and caching for individual step executions
- [`PipelineRunInstance`](#pipelineruninstance) - Links created database instances to pipeline runs

---

## PipelineStepState

Records execution details for each step in a pipeline run, enabling audit trails, caching, and partial regeneration.

**Table:** `pipeline_step_states`

**Purpose:** Provides generic state tracking for any pipeline step. Records what happened at each execution, enabling questions like "What inputs produced this output?" and "Can we reuse previous results?"

### Fields

#### Identification

**`id`** (int, primary key)
- Auto-generated primary key

**`pipeline_name`** (str, max_length=100)
- Pipeline name in snake_case (e.g., `"rate_card_parser"`, `"table_config_generator"`)
- Derived from pipeline class name by removing `Pipeline` suffix and converting to snake_case

**`run_id`** (str, max_length=36, indexed)
- UUID identifying this specific pipeline execution
- Links multiple steps within the same run
- Used for traceability via `PipelineRunInstance`

**`step_name`** (str, max_length=100)
- Name of the step (e.g., `"table_type_detection"`, `"constraint_extraction"`)
- Derived from step class name by removing `Step` suffix and converting to snake_case

**`step_number`** (int)
- Execution order within the pipeline (1, 2, 3...)
- Used for sequential replay and partial regeneration

#### Cache Key Components

**`input_hash`** (str, max_length=64)
- SHA-256 hash of step inputs
- Computed from `pipeline.context` dictionary (all keys sorted for consistency)
- Invalidates cache when inputs change

**`prompt_version`** (str, max_length=20, nullable)
- Version of the prompt used during execution
- Loaded from `Prompt.version` for `prompt_system_key`
- Invalidates cache when prompts are updated
- **Cache Key Logic:** Cache hits require matching `input_hash` AND `prompt_version`

#### State Data

**`result_data`** (JSON dict)
- Serialized step results (LLM instructions)
- List of instruction dictionaries via `model_dump(mode="json")`
- Used for cache reconstruction

**`context_snapshot`** (JSON dict)
- Relevant pipeline context at this execution point
- Format: `{step_name: [serialized_instructions]}`
- Provides audit trail of what data was available

#### Prompt Metadata

**`prompt_system_key`** (str, max_length=200, nullable)
- Database key for system prompt (if applicable)
- Example: `"constraint_extraction"`
- Used to query `Prompt` table for version during caching

**`prompt_user_key`** (str, max_length=200, nullable)
- Database key for user prompt template (if applicable)
- Example: `"rate_card_extraction"`

**`model`** (str, max_length=50, nullable)
- LLM model identifier used (if applicable)
- Example: `"gemini-1.5-pro"`

#### Timing

**`created_at`** (datetime)
- UTC timestamp of step execution
- Defaults to `datetime.now(timezone.utc)`

**`execution_time_ms`** (int, nullable)
- Execution time in milliseconds
- Tracks step performance

### Indexes

**`ix_pipeline_step_states_run`**
- Composite index on `(run_id, step_number)`
- Enables efficient sequential replay

**`ix_pipeline_step_states_cache`**
- Composite index on `(pipeline_name, step_name, input_hash)`
- Enables fast cache lookups

### Caching Workflow

#### Cache Lookup

During `pipeline.execute(use_cache=True)`, the framework queries for cached results:

```python
# In PipelineConfig._find_cached_state()
cached_state = session.exec(
    select(PipelineStepState)
    .where(
        PipelineStepState.pipeline_name == pipeline_name,
        PipelineStepState.step_name == step_name,
        PipelineStepState.input_hash == input_hash,
        PipelineStepState.prompt_version == current_prompt_version  # If prompt exists
    )
    .order_by(PipelineStepState.created_at.desc())
).first()
```

**Cache Hit Criteria:**
1. Matching `pipeline_name` and `step_name`
2. Matching `input_hash` (inputs unchanged)
3. Matching `prompt_version` (prompt unchanged) OR no prompt for this step
4. Most recent match returned if multiple exist

#### Cache Storage

After step execution, state is automatically saved:

```python
# In PipelineConfig._save_step_state()
state = PipelineStepState(
    pipeline_name=self.pipeline_name,
    run_id=self.run_id,
    step_name=step.step_name,
    step_number=step_number,
    input_hash=input_hash,
    result_data=serialized_instructions,
    context_snapshot={step.step_name: serialized_instructions},
    prompt_system_key=step.system_instruction_key,
    prompt_user_key=step.user_prompt_key,
    prompt_version=prompt_version,
    execution_time_ms=execution_time_ms,
)
session.add(state)
session.flush()  # Assigns ID immediately
```

#### Cache Reconstruction

When cache hit occurs:

1. **Instructions:** Deserialized from `result_data` and loaded into `pipeline._instructions[step_name]`
2. **Context:** Step's `process_instructions()` called to update `pipeline.context`
3. **Data:** Step's transformation applied if configured
4. **Extractions:** Reconstructed via `PipelineRunInstance` links (see below)

### Extraction Reconstruction

For steps with configured extractions, cache hits trigger reconstruction:

```python
# In PipelineConfig._reconstruct_extractions_from_cache()
# 1. Query PipelineRunInstance for cached run_id
run_instances = session.exec(
    select(PipelineRunInstance).where(
        PipelineRunInstance.run_id == cached_state.run_id,
        PipelineRunInstance.model_type == model_class.__name__,
    )
).all()

# 2. Load actual model instances by ID
for run_instance in run_instances:
    instance = session.get(model_class, run_instance.model_id)
    pipeline.extractions[model_class].append(instance)
```

**Partial Cache:** If extraction reconstruction fails (instances deleted), step's `extract_data()` re-runs while preserving cached LLM results.

### Example Usage

```python
# Automatic state tracking during execution
pipeline = RateCardParserPipeline(
    session=session,
    provider=gemini_provider
)

# Execute with caching enabled
pipeline.execute(
    data=rate_card_data,
    initial_context={"table_type": "lane_based"},
    use_cache=True  # Enables state-based caching
)

# Query state for audit trail
from llm_pipeline.state import PipelineStepState
from sqlmodel import select

states = session.exec(
    select(PipelineStepState)
    .where(PipelineStepState.run_id == pipeline.run_id)
    .order_by(PipelineStepState.step_number)
).all()

for state in states:
    print(f"Step {state.step_number}: {state.step_name}")
    print(f"  Executed: {state.created_at}")
    print(f"  Duration: {state.execution_time_ms}ms")
    print(f"  Input hash: {state.input_hash}")
    print(f"  Prompt version: {state.prompt_version}")
```

---

## PipelineRunInstance

Tracks which database instances were created by which pipeline run, enabling traceability from created data back to the pipeline execution.

**Table:** `pipeline_run_instances`

**Purpose:** Generic linking table that works for ANY pipeline + ANY model. Answers questions like "Which pipeline run created this Rate record?" and "What data was created during run X?"

### Fields

**`id`** (int, primary key)
- Auto-generated primary key

**`run_id`** (str, max_length=36, indexed)
- UUID of the pipeline run that created this instance
- Links to `PipelineStepState.run_id` for full traceability

**`model_type`** (str, max_length=100)
- Model class name (e.g., `"Rate"`, `"Lane"`, `"ChargeType"`)
- Used for polymorphic queries across multiple model types

**`model_id`** (int)
- Primary key ID of the created instance in its table
- Used with `model_type` to retrieve actual instance

**`created_at`** (datetime)
- UTC timestamp when tracking record was created
- Defaults to `datetime.now(timezone.utc)`

### Indexes

**`ix_pipeline_run_instances_run`**
- Index on `run_id`
- Enables "show all data created by run X" queries

**`ix_pipeline_run_instances_model`**
- Composite index on `(model_type, model_id)`
- Enables "which run created this specific instance" queries

### Traceability Workflow

#### Instance Tracking

During `pipeline.save()`, created instances are automatically tracked:

```python
# In PipelineConfig._track_created_instances()
for instance in instances:
    if hasattr(instance, "id") and instance.id:
        run_instance = PipelineRunInstance(
            run_id=self.run_id,
            model_type=model_class.__name__,
            model_id=instance.id,
        )
        session.add(run_instance)
```

**Note:** Instances must have IDs assigned before tracking. The two-phase write pattern (flush during execution, commit at save) ensures IDs exist.

#### Querying Created Data

**Find all instances created by a run:**

```python
from llm_pipeline.state import PipelineRunInstance
from sqlmodel import select

# Get all tracking records for run
run_instances = session.exec(
    select(PipelineRunInstance)
    .where(PipelineRunInstance.run_id == run_id)
).all()

# Group by model type
by_type = {}
for ri in run_instances:
    if ri.model_type not in by_type:
        by_type[ri.model_type] = []
    by_type[ri.model_type].append(ri.model_id)

# Load actual instances
for model_type, ids in by_type.items():
    print(f"{model_type}: {len(ids)} instances created")
```

**Find which run created a specific instance:**

```python
# Query by model type and ID
tracking = session.exec(
    select(PipelineRunInstance)
    .where(
        PipelineRunInstance.model_type == "Rate",
        PipelineRunInstance.model_id == 456
    )
).first()

if tracking:
    # Load full pipeline execution details
    states = session.exec(
        select(PipelineStepState)
        .where(PipelineStepState.run_id == tracking.run_id)
        .order_by(PipelineStepState.step_number)
    ).all()

    print(f"Rate #456 created by run {tracking.run_id}")
    print(f"Pipeline: {states[0].pipeline_name}")
    print(f"Steps executed: {len(states)}")
```

### Example Usage

```python
# Execute pipeline with automatic tracking
pipeline = RateCardParserPipeline(
    session=session,
    provider=gemini_provider
)

pipeline.execute(
    data=rate_card_data,
    initial_context={"table_type": "lane_based"}
)

# Save extractions (triggers tracking)
results = pipeline.save()
# results = {"rates_saved": 42, "lanes_saved": 8, ...}

# Query what was created
from llm_pipeline.state import PipelineRunInstance
from sqlmodel import select

tracking_records = session.exec(
    select(PipelineRunInstance)
    .where(PipelineRunInstance.run_id == pipeline.run_id)
).all()

print(f"Created {len(tracking_records)} instances")
for record in tracking_records:
    print(f"  {record.model_type} #{record.model_id}")

# Reconstruct created data from tracking
rates = session.exec(
    select(Rate)
    .join(PipelineRunInstance,
          (PipelineRunInstance.model_type == "Rate") &
          (PipelineRunInstance.model_id == Rate.id))
    .where(PipelineRunInstance.run_id == pipeline.run_id)
).all()
```

---

## Cache Invalidation

Cache invalidation is automatic based on state fields:

### Input Changes

**Trigger:** Pipeline context changes
**Mechanism:** `input_hash` computed from sorted `pipeline.context` dict
**Result:** Cache miss, fresh execution

```python
# Run 1: context = {"table_type": "lane_based"}
# input_hash = "a1b2c3d4..."

# Run 2: context = {"table_type": "zone_based"}
# input_hash = "e5f6g7h8..." (different!)
# Cache miss - fresh execution required
```

### Prompt Updates

**Trigger:** Prompt version changed in database
**Mechanism:** `prompt_version` compared during cache lookup
**Result:** Cache miss, fresh execution with new prompt

```python
# Initial prompt version: "1.0.0"
# Cached with prompt_version = "1.0.0"

# Update prompt in database to "1.1.0"
# Cache lookup checks current version = "1.1.0"
# Mismatch with cached "1.0.0" - cache miss
```

### Manual Cache Clearing

**Warning:** `clear_cache()` has a known bug and is not recommended.

```python
# BROKEN - Uses ReadOnlySession for delete/commit
count = pipeline.clear_cache()  # Raises RuntimeError!

# Bug: calls self.session.delete() where self.session is ReadOnlySession
# Should use self._real_session instead
# See architecture/limitations.md for details
```

**Workaround:** Manually delete states using direct session access:

```python
from llm_pipeline.state import PipelineStepState
from sqlmodel import select

states = session.exec(
    select(PipelineStepState)
    .where(PipelineStepState.pipeline_name == "rate_card_parser")
).all()

for state in states:
    session.delete(state)
session.commit()
```

---

## See Also

- [Registry API Reference](registry.md) - Database model registration and FK ordering
- [Pipeline API Reference](pipeline.md) - Pipeline execution and context management
- [Architecture: Patterns](../architecture/patterns.md) - Two-phase write pattern and state tracking design
- [Architecture: Limitations](../architecture/limitations.md) - Known issues with `clear_cache()`
