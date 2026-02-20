# Research: Pipeline Introspection Patterns

## Overview

This document covers Python runtime introspection techniques, Pydantic v2 schema extraction, caching patterns, and service class design for building a `PipelineIntrospector` that extracts metadata from declarative pipeline classes without instantiation.

## 1. Codebase Architecture for Introspection

### 1.1 ClassVar-Based Declarative Pattern

The pipeline framework uses Python's `__init_subclass__` extensively to set ClassVar attributes at class definition time. This is the foundation for safe introspection.

| Class | ClassVar Attributes | Set Via |
|---|---|---|
| `PipelineConfig` | `REGISTRY`, `STRATEGIES` | `__init_subclass__(cls, registry=, strategies=)` |
| `PipelineStrategies` | `STRATEGIES` (list of strategy classes) | `__init_subclass__(cls, strategies=[...])` |
| `PipelineStrategy` | `NAME`, `DISPLAY_NAME` | Auto-generated in `__init_subclass__` from class name |
| `PipelineExtraction` | `MODEL` (SQLModel class) | `__init_subclass__(cls, model=)` |
| `PipelineTransformation` | `INPUT_TYPE`, `OUTPUT_TYPE` | `__init_subclass__(cls, input_type=, output_type=)` |
| `PipelineDatabaseRegistry` | `MODELS` (list of SQLModel classes) | `__init_subclass__(cls, models=[...])` |
| `LLMStep` (via `@step_definition`) | `INSTRUCTIONS`, `DEFAULT_SYSTEM_KEY`, `DEFAULT_USER_KEY`, `DEFAULT_EXTRACTIONS`, `DEFAULT_TRANSFORMATION`, `CONTEXT` | Set by decorator |

All of these are accessible on the **class type** without instantiation.

### 1.2 Side Effect Map

| Operation | Side Effects | Safe for Introspection? |
|---|---|---|
| `pipeline_class.STRATEGIES` | None (class attr read) | YES |
| `pipeline_class.REGISTRY` | None (class attr read) | YES |
| `PipelineStrategies.STRATEGIES` | None (class attr read) | YES |
| `PipelineStrategy()` constructor | None (no `__init__` override) | YES |
| `strategy_instance.get_steps()` | None (returns StepDefinition dataclasses) | YES |
| `PipelineConfig()` constructor | DB init, session creation, validation | NO - AVOID |
| `StepDefinition.create_step()` | DB queries for prompt auto-discovery | NO - AVOID |
| `PipelineExtraction()` constructor | Validates MODEL against registry, requires pipeline | NO - AVOID |
| `PipelineTransformation()` constructor | Requires pipeline instance | NO - AVOID |
| `model.model_json_schema()` | Pure computation | YES |
| `model.model_fields` | Property read | YES |

### 1.3 Naming Convention Derivation

Pipeline names are derived from class names using a consistent pattern:

```python
# PipelineConfig.pipeline_name property (pipeline.py L238-246)
# Remove "Pipeline" suffix, then CamelCase -> snake_case
# e.g., RateCardParserPipeline -> rate_card_parser

import re
class_name = pipeline_class.__name__
name = class_name[:-8]  # Remove 'Pipeline'
snake_case = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()
```

Strategy names: Remove 'Strategy' suffix, CamelCase -> snake_case (strategy.py L187-191).
Step names: Remove 'Step' suffix, CamelCase -> snake_case (step.py L254-262).

## 2. Python Introspection Techniques

### 2.1 Class Attribute Access

Direct attribute access on class types (not instances):

```python
# Access ClassVar attributes directly on the type
strategies_class = pipeline_class.STRATEGIES  # Type[PipelineStrategies]
registry_class = pipeline_class.REGISTRY      # Type[PipelineDatabaseRegistry]
strategy_classes = strategies_class.STRATEGIES # List[Type[PipelineStrategy]]
registry_models = registry_class.MODELS       # List[Type[SQLModel]]
```

### 2.2 Safe Strategy Instantiation

`PipelineStrategy` subclasses have no `__init__` override (they inherit from ABC). Instantiation is safe:

```python
for strategy_class in strategies_class.STRATEGIES:
    strategy = strategy_class()  # Safe - no side effects
    step_defs = strategy.get_steps()  # Returns List[StepDefinition]
    # StepDefinition is a dataclass - all fields are plain data
```

### 2.3 StepDefinition Field Access

`StepDefinition` is a `@dataclass` (strategy.py L21-35). All fields are directly accessible:

```python
step_def.step_class              # Type[LLMStep] - the step class
step_def.system_instruction_key  # str or None
step_def.user_prompt_key         # str or None
step_def.instructions            # Type[BaseModel] - the instructions/result schema
step_def.extractions             # List[Type[PipelineExtraction]]
step_def.transformation          # Type[PipelineTransformation] or None
step_def.context                 # Type[PipelineContext] or None
step_def.action_after            # str or None
```

### 2.4 Decorator-Applied Attributes

The `@step_definition` decorator (step.py L79-176) sets class attributes on step classes:

```python
step_class = step_def.step_class
step_class.INSTRUCTIONS            # Type[BaseModel] - same as step_def.instructions
step_class.DEFAULT_SYSTEM_KEY      # str or None
step_class.DEFAULT_USER_KEY        # str or None
step_class.DEFAULT_EXTRACTIONS     # List[Type[PipelineExtraction]]
step_class.DEFAULT_TRANSFORMATION  # Type[PipelineTransformation] or None
step_class.CONTEXT                 # Type[PipelineContext] or None
```

These provide fallback information when StepDefinition fields are None (overrides at strategy level).

### 2.5 Extraction Method Discovery

PipelineExtraction uses smart method detection (extraction.py L237-280). Introspection can discover available methods:

```python
all_methods = set(dir(extraction_class))
base_methods = set(dir(PipelineExtraction))
custom_methods = [
    m for m in (all_methods - base_methods)
    if callable(getattr(extraction_class, m))
    and not m.startswith('_')
    and m != 'extract'
]
# Returns method names like ['default'], ['lane_based', 'destination_based'], etc.
```

Note: This works on the **class** (not instance) since methods are defined on the class.

## 3. Pydantic v2 Schema Extraction

### 3.1 model_json_schema()

Primary method for extracting full JSON Schema from any Pydantic model:

```python
# Instructions/Result schema
schema = instructions_class.model_json_schema()
# Returns dict with: type, properties, required, title, description, $defs

# Extraction model schema (SQLModel is Pydantic BaseModel subclass)
model_schema = extraction_class.MODEL.model_json_schema()

# Context schema
context_schema = context_class.model_json_schema()
```

The schema includes: field names, types, descriptions, constraints (min/max, pattern), defaults, required fields, and nested model definitions via `$defs`.

### 3.2 model_fields Introspection

For field-level detail without full JSON schema overhead:

```python
for field_name, field_info in model_class.model_fields.items():
    field_info.annotation    # The type annotation
    field_info.default       # Default value (PydanticUndefined if required)
    field_info.description   # Field description string
    field_info.is_required() # bool
    field_info.metadata      # List of metadata (constraints, etc.)
    field_info.alias         # Alias if set
```

### 3.3 Prompt Key Extraction

Prompt keys from StepDefinition may be:
1. **Explicit**: Set directly in StepDefinition constructor (non-None string)
2. **Decorator default**: From `@step_definition(default_system_key=..., default_user_key=...)`
3. **Auto-discovered at runtime**: Resolved via DB lookup in `create_step()` - NOT available without DB

For introspection, report in priority order:
```python
system_key = step_def.system_instruction_key or getattr(step_class, 'DEFAULT_SYSTEM_KEY', None)
user_key = step_def.user_prompt_key or getattr(step_class, 'DEFAULT_USER_KEY', None)

# If still None, provide inferred naming convention
if system_key is None:
    # Convention: step_name or step_name.strategy_name
    inferred_keys = [step_name]
    if strategy_name:
        inferred_keys.insert(0, f"{step_name}.{strategy_name}")
```

### 3.4 Prompt Template Variable Extraction

The `extract_variables_from_content()` function in `prompts/loader.py` extracts `{variable_name}` patterns from prompt content. For introspection without DB access, this information is not directly available. However, the `VariableResolver` protocol (prompts/variables.py) shows that variable classes are Pydantic BaseModel subclasses, so if a resolver is provided, their schemas can be extracted.

## 4. Caching Patterns

### 4.1 Recommended: Class-Level Cache Dict

Pipeline metadata is immutable once classes are defined. A class-level cache keyed by pipeline class type is most appropriate:

```python
class PipelineIntrospector:
    _cache: ClassVar[Dict[Type, Dict[str, Any]]] = {}

    def __init__(self, pipeline_class: Type[PipelineConfig]):
        self.pipeline_class = pipeline_class

    def get_metadata(self) -> Dict[str, Any]:
        if self.pipeline_class in self._cache:
            return self._cache[self.pipeline_class]
        metadata = self._build_metadata()
        self._cache[self.pipeline_class] = metadata
        return metadata

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached introspection results."""
        cls._cache.clear()

    @classmethod
    def invalidate(cls, pipeline_class: Type) -> None:
        """Invalidate cache for a specific pipeline class."""
        cls._cache.pop(pipeline_class, None)
```

### 4.2 Why Not functools.lru_cache

- `lru_cache` on methods requires the instance to be hashable or uses `__func__` pattern
- `lru_cache` doesn't provide selective invalidation
- Class-level dict is simpler and more controllable
- Class types are hashable (they're `type` objects), so dict keying works perfectly

### 4.3 Why Not functools.cached_property

- `cached_property` caches per instance; new `PipelineIntrospector(cls)` creates new cache
- Would need to additionally cache introspector instances to avoid redundant work
- Adds unnecessary indirection; class-level dict is more direct

### 4.4 Cache Key Safety

Python class types (`type` objects) are hashable and use identity-based hashing (`id()`). Two references to the same class always hash to the same value. This is perfect for caching since pipeline classes are singletons in the module system.

## 5. Service Class Design

### 5.1 Proposed Structure

```python
class PipelineIntrospector:
    """Extract pipeline metadata via class-level introspection.

    Operates entirely on class types - never instantiates PipelineConfig.
    Safe to call without DB connections or LLM providers.
    Results are cached per pipeline class (immutable after class definition).
    """

    _cache: ClassVar[Dict[Type, Dict[str, Any]]] = {}

    def __init__(self, pipeline_class: Type[PipelineConfig]):
        self.pipeline_class = pipeline_class

    def get_metadata(self) -> Dict[str, Any]:
        """Full pipeline metadata (cached)."""
        ...

    # --- Private extraction methods ---

    def _derive_pipeline_name(self) -> str:
        """CamelCase class name -> snake_case pipeline name."""
        ...

    def _extract_strategies(self) -> List[Dict[str, Any]]:
        """Extract strategy metadata with step details."""
        ...

    def _extract_strategy_steps(self, strategy) -> List[Dict[str, Any]]:
        """Extract step metadata from a strategy instance."""
        ...

    def _extract_step_metadata(self, step_def, strategy_name) -> Dict[str, Any]:
        """Extract metadata from a single StepDefinition."""
        ...

    def _extract_schema(self, model_class) -> Dict[str, Any]:
        """Extract Pydantic/SQLModel schema via model_json_schema()."""
        ...

    def _extract_extraction_metadata(self, extraction_class) -> Dict[str, Any]:
        """Extract PipelineExtraction metadata (MODEL, methods)."""
        ...

    def _extract_transformation_metadata(self, transformation_class) -> Dict[str, Any]:
        """Extract PipelineTransformation metadata (input/output types)."""
        ...

    def _extract_registry_models(self) -> List[Dict[str, Any]]:
        """Extract registry model schemas."""
        ...

    def _build_global_step_order(self) -> List[Dict[str, Any]]:
        """Build deduplicated step order across all strategies."""
        ...

    # --- Cache management ---

    @classmethod
    def clear_cache(cls) -> None: ...

    @classmethod
    def invalidate(cls, pipeline_class: Type) -> None: ...
```

### 5.2 Metadata Output Shape

Based on downstream task 24 (Pipelines API) requirements:

```python
{
    "name": "rate_card_parser",              # snake_case from class name
    "class_name": "RateCardParserPipeline",  # original class name
    "strategies": [
        {
            "name": "lane_based",            # from NAME ClassVar
            "display_name": "Lane Based",    # from DISPLAY_NAME ClassVar
            "class_name": "LaneBasedStrategy",
            "steps": [
                {
                    "name": "semantic_mapping",
                    "class_name": "SemanticMappingStep",
                    "position": 0,
                    "system_instruction_key": "semantic_mapping.lane_based",  # or None
                    "user_prompt_key": "semantic_mapping.lane_based",         # or None
                    "inferred_prompt_keys": ["semantic_mapping.lane_based", "semantic_mapping"],
                    "instructions_schema": { ... },  # model_json_schema()
                    "context_schema": { ... } | None,
                    "extractions": [
                        {
                            "class_name": "LaneExtraction",
                            "model_name": "Lane",
                            "model_schema": { ... },
                            "methods": ["default"]
                        }
                    ],
                    "transformation": {
                        "class_name": "UnpivotTransformation",
                        "input_type": "DataFrame",
                        "output_type": "DataFrame"
                    } | None,
                    "action_after": null
                }
            ]
        }
    ],
    "registry_models": [
        {
            "name": "Vendor",
            "schema": { ... },
            "position": 0
        }
    ],
    "step_order": [  # Deduplicated global order
        {"name": "semantic_mapping", "position": 0},
        {"name": "constraint_extraction", "position": 1},
    ]
}
```

### 5.3 Global Step Order Algorithm

Mirrors `PipelineConfig._build_execution_order()` (pipeline.py L248-263) but without instantiation:

```python
def _build_global_step_order(self) -> List[Dict]:
    """Build deduplicated step order across all strategies.

    Replicates _build_execution_order() logic:
    - Iterate strategies in order
    - For each strategy, iterate steps
    - First occurrence of a step_class wins its position
    """
    seen_classes = set()
    ordered = []
    strategies_class = self.pipeline_class.STRATEGIES

    for strategy_class in strategies_class.STRATEGIES:
        strategy = strategy_class()  # Safe instantiation
        for step_def in strategy.get_steps():
            if step_def.step_class not in seen_classes:
                seen_classes.add(step_def.step_class)
                ordered.append({
                    'name': self._step_name_from_class(step_def.step_class),
                    'class_name': step_def.step_class.__name__,
                    'position': len(ordered),
                })
    return ordered
```

## 6. Safety Guarantees

### 6.1 No Instantiation of PipelineConfig

The introspector NEVER calls `PipelineConfig()` or any subclass constructor. All data comes from:
- ClassVar attributes (set by `__init_subclass__`)
- Class-level attributes (set by `@step_definition` decorator)
- Safe `PipelineStrategy()` instantiation (no `__init__` override, no DB)
- `StepDefinition` dataclass field access

### 6.2 No Database Access

No SQLAlchemy engines, sessions, or queries. Prompt keys that require DB auto-discovery are reported as None with inferred naming conventions provided separately.

### 6.3 No LLM Calls

No LLM provider interaction. All metadata is structural.

### 6.4 Class Hierarchy Safety

Using `__init_subclass__` means attributes are set at class definition time (import time). By the time the introspector runs, all ClassVars are already populated. No metaclass magic or descriptors that could trigger side effects.

## 7. Edge Cases

### 7.1 Pipeline Without Strategies

If `STRATEGIES` is None on the pipeline class (shouldn't happen for valid pipelines due to `__init_subclass__` validation), return empty strategy list.

### 7.2 Steps With None Prompt Keys

When `system_instruction_key` or `user_prompt_key` is None on StepDefinition and DEFAULT_*_KEY is also None, the key is resolved at runtime via DB. Report as None with inferred keys.

### 7.3 Extraction MODEL as SQLModel with table=True

SQLModel models with `table=True` have both Pydantic fields and SQLAlchemy columns. `model_json_schema()` works but may include internal fields (`id`, etc.). The schema correctly reflects the full model shape.

### 7.4 Abstract/Intermediate Base Classes

Strategy `__init_subclass__` skips classes starting with `_` and non-direct subclasses. The introspector only encounters concrete strategy classes via `STRATEGIES` list, so this is not an issue.

## 8. File Placement

Per task 23 specification: `llm_pipeline/ui/introspection.py`

Imports needed:
```python
from typing import Type, Dict, Any, List, ClassVar
import re
from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.transformation import PipelineTransformation
```

No database imports, no LLM imports, no session imports.
