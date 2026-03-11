# Research: Python Registry, Deprecation & Dataclass Patterns

## 1. __init_subclass__ Registry Patterns in Existing Codebase

### 1.1 Pattern Inventory

The codebase uses six distinct `__init_subclass__` patterns. Three categories:

**Category A: Class-param registries (store config on ClassVar)**
| Class | File | Param | ClassVar | Validation |
|-------|------|-------|----------|------------|
| `PipelineDatabaseRegistry` | registry.py:36 | `models=` | `MODELS` | Concrete subclass must provide models if direct child |
| `PipelineStrategies` | strategy.py:278 | `strategies=` | `STRATEGIES` | Same pattern as above |
| `PipelineConfig` | pipeline.py:111 | `registry=`, `strategies=` | `REGISTRY`, `STRATEGIES` | Naming convention: prefix must match pipeline name |

**Category B: Auto-registration (populate global/class-level dict)**
| Class | File | Registry | Key Derivation |
|-------|------|----------|----------------|
| `PipelineEvent` | events/types.py:83 | `_EVENT_REGISTRY` dict | CamelCase -> snake_case via `_derive_event_type()` |

**Category C: Auto-derivation (compute properties from class name)**
| Class | File | Derived Properties |
|-------|------|-------------------|
| `PipelineStrategy` | strategy.py:155 | `NAME` (snake_case), `DISPLAY_NAME` (title case) |
| `LLMResultMixin` | step.py:198 | Validates `example` dict at definition time |

### 1.2 Skip/Guard Patterns

Three guard patterns exist for intermediate bases:

```python
# Pattern 1: Underscore prefix (PipelineStrategy, PipelineEvent)
if cls.__name__.startswith('_'):
    return

# Pattern 2: Explicit opt-out ClassVar (StepScopedEvent)
if "_skip_registry" in cls.__dict__:
    return

# Pattern 3: Direct-subclass check (PipelineDatabaseRegistry, PipelineStrategies)
if not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineDatabaseRegistry:
    raise ValueError(...)  # enforce param for concrete subclasses only
```

### 1.3 Naming Validation Pattern

`PipelineConfig.__init_subclass__` (pipeline.py:115-135) validates that registry/strategies class names match the pipeline prefix:

```python
# If pipeline is "RateCardParserPipeline", registry must be "RateCardParserRegistry"
pipeline_name_prefix = cls.__name__[:-8]  # Remove "Pipeline"
expected = f"{pipeline_name_prefix}Registry"
if registry.__name__ != expected:
    raise ValueError(...)
```

### 1.4 Recommended AgentRegistry Pattern

Follow **Category A** (class-param registry), consistent with `PipelineDatabaseRegistry`:

```python
class AgentRegistry(ABC):
    AGENTS: ClassVar[dict[str, Agent]] = {}

    def __init_subclass__(cls, agents=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if agents is not None:
            cls.AGENTS = agents
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is AgentRegistry:
            raise ValueError(
                f"{cls.__name__} must specify agents parameter"
            )

    @classmethod
    def get_agent(cls, step_name: str) -> Agent:
        if step_name not in cls.AGENTS:
            raise KeyError(f"No agent registered for step '{step_name}'")
        return cls.AGENTS[step_name]
```

Usage would be:
```python
class RateCardParserAgentRegistry(AgentRegistry, agents={
    "table_type_detection": table_type_agent,
    "constraint_extraction": constraint_agent,
}):
    pass
```

**Naming validation** should be added to `PipelineConfig.__init_subclass__` when an `agent_registry=` param is added, enforcing `{Prefix}AgentRegistry` naming convention.

### 1.5 slots=True Gotcha (events/types.py:10-12)

Important note from events/types.py: `slots=True` on dataclasses creates a new class object that breaks the implicit `__class__` cell used by zero-arg `super()` in `__init_subclass__`. This requires `super(PipelineEvent, cls).__init_subclass__(**kwargs)` explicit form. **Not relevant to AgentRegistry** (not a frozen slotted dataclass), but documented for awareness.


## 2. warnings.warn Deprecation Patterns

### 2.1 Current State

The codebase has **zero** existing `warnings.warn()` calls. This will be the first deprecation warning. Convention should be established cleanly.

### 2.2 Warning Category Selection

| Category | When to Use | Default Filter |
|----------|-------------|----------------|
| `DeprecationWarning` | Feature is deprecated, still works, will be removed | Ignored by default (shown in tests) |
| `PendingDeprecationWarning` | Will be deprecated in future | Ignored by default |
| `FutureWarning` | Behavior will change (not removal) | Always shown |

**Recommendation: `DeprecationWarning`** for `create_llm_call()`. It's deprecated now, still functional, will be removed in a future version.

### 2.3 stacklevel Parameter

`stacklevel=2` is the standard. Makes the warning point at the **caller** of the deprecated function, not the deprecated function itself. Without it, the warning message shows the `warnings.warn()` line inside the deprecated function -- useless for finding the call site.

### 2.4 Message Format Convention

Pattern: `"{function}() is deprecated and will be removed in {version}. Use {replacement} instead."`

```python
import warnings

def create_llm_call(self, variables, ...):
    warnings.warn(
        "create_llm_call() is deprecated, use get_agent() + build_user_prompt() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    # ... existing implementation unchanged ...
```

### 2.5 Upcoming Deprecations

Task 1 deprecates `create_llm_call()`. Task 2 deprecates `ExecuteLLMStepParams`. If multiple deprecations are expected, consider a helper:

```python
def _deprecation_warn(old: str, new: str, stacklevel: int = 3) -> None:
    warnings.warn(
        f"{old} is deprecated, use {new} instead",
        DeprecationWarning,
        stacklevel=stacklevel,
    )
```

However, with only 2 deprecations, inline `warnings.warn()` calls are simpler and more explicit. **Recommend: inline calls, no helper.**


## 3. dataclass vs Pydantic BaseModel for StepDeps

### 3.1 Decision: @dataclass

**Use `@dataclass`**, not Pydantic BaseModel.

### 3.2 Rationale

| Factor | @dataclass | Pydantic BaseModel |
|--------|-----------|-------------------|
| pydantic-ai compatibility | All official examples use @dataclass | Works but unconventional |
| Validation need | None (constructed internally by executor) | Unnecessary overhead |
| Serialization need | None (runtime DI container) | Unnecessary |
| Arbitrary types | Native support | Requires `model_config = ConfigDict(arbitrary_types_allowed=True)` |
| Existing codebase precedent | `ArrayValidationConfig`, `ValidationContext` use @dataclass | Pipeline models use Pydantic |
| Semantic fit | DI container = dataclass | Data model = Pydantic |

### 3.3 Codebase Precedent

```python
# types.py:11 - ArrayValidationConfig uses @dataclass
@dataclass
class ArrayValidationConfig:
    input_array: List[Any]
    match_field: str = "original"
    ...

# types.py:27 - ValidationContext uses hand-rolled dataclass pattern
@dataclass
class ValidationContext:
    data: Dict[str, Any]
    ...
```

### 3.4 StepDeps Design

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class StepDeps:
    session: ReadOnlySession
    pipeline_context: dict[str, Any]
    prompt_service: PromptService
    validation_context: ValidationContext | None = None
```

### 3.5 pydantic-ai RunContext Compatibility

pydantic-ai uses `RunContext[StepDeps]` generic for type safety in tools/validators/system_prompt decorators:

```python
@agent.system_prompt
async def get_system_prompt(ctx: RunContext[StepDeps]) -> str:
    prompt = ctx.deps.prompt_service.get_prompt(...)
    return prompt

@agent.output_validator
def validate_output(ctx: RunContext[StepDeps], data: T) -> T:
    if ctx.deps.validation_context:
        # access validation context via deps
        ...
    return data
```

The `deps_type=StepDeps` param on Agent constructor enables type checking. At runtime, `ctx.deps` is the StepDeps instance passed to `agent.run_sync(user_prompt, deps=step_deps)`.


## 4. Abstract Method Patterns for get_agent() and build_user_prompt()

### 4.1 Current LLMStep Method Classification

| Method | Type | Override Expected |
|--------|------|------------------|
| `prepare_calls()` | `@abstractmethod` | Always (each step defines its own calls) |
| `create_llm_call()` | Concrete | Rarely (standard param assembly) |
| `process_instructions()` | Concrete (default: `return {}`) | Often (extract context values) |
| `should_skip()` | Concrete (default: `return False`) | Sometimes |
| `log_instructions()` | Concrete (default: `pass`) | Sometimes |
| `extract_data()` | Concrete | Rarely |

### 4.2 get_agent() -- Concrete Method (Not Abstract)

`get_agent()` is a lookup operation, not step-specific logic:

```python
def get_agent(self, registry: AgentRegistry) -> Agent:
    """Resolve agent from registry by step name or agent_name override."""
    agent_name = getattr(self, '_agent_name', None) or self.step_name
    return registry.get_agent(agent_name)
```

Rationale: The agent is determined by the registry mapping (set at class definition time via `AgentRegistry` subclass), not by per-step logic. If a step needs a non-default agent, `StepDefinition.agent_name` field handles it (stored as `self._agent_name` by `create_step()`).

### 4.3 build_user_prompt() -- Concrete with Default

```python
def build_user_prompt(
    self,
    variables: dict[str, Any],
    prompt_service: PromptService,
    context: dict[str, Any] | None = None,
) -> str:
    """Format user prompt from DB template + variables."""
    if hasattr(variables, "model_dump"):
        variables = variables.model_dump()
    return prompt_service.get_user_prompt(
        self.user_prompt_key,
        variables=variables,
        variable_instance=variables,
        context=context,
    )
```

Rationale: This replicates the prompt resolution currently done inside `execute_llm_step()`. The default implementation handles the common case. Steps that need custom prompt building can override.


## 5. Python 3.11+ Features Relevant to This Work

### 5.1 Already Used in Codebase

| Feature | Python Version | Usage |
|---------|---------------|-------|
| `str \| None` union syntax | 3.10+ | Throughout (events/types.py, pipeline.py) |
| `kw_only=True` on dataclass | 3.10+ | events/types.py (multiple event classes) |
| `slots=True` on dataclass | 3.10+ | events/types.py (all event classes) |
| `ClassVar` type hints | 3.5+ | Throughout |
| `TYPE_CHECKING` guard | 3.5+ | Throughout |

### 5.2 Available but Not Currently Used

| Feature | Python Version | Relevance |
|---------|---------------|-----------|
| `typing.Self` | 3.11+ | Could type classmethod returns on AgentRegistry, but not needed |
| `@typing.override` | 3.12+ | Could annotate overridden methods, project targets 3.11+ so not safe |
| `typing.dataclass_transform` | 3.11+ | Could improve type checker support for __init_subclass__ patterns |
| `ExceptionGroup` | 3.11+ | Not relevant to registry/deprecation patterns |

### 5.3 Recommendation

Continue using existing patterns. No new 3.11+ features provide meaningful benefit for the AgentRegistry/StepDeps work. The `str | None` union syntax and `kw_only=True` dataclass features are already established and should continue to be used.


## 6. Module __init__.py Export Patterns

### 6.1 Current Pattern (llm_pipeline/__init__.py)

```python
# Explicit top-level imports
from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.step import LLMStep, LLMResultMixin, step_definition
# ...

# Categorized __all__ with comments
__all__ = [
    # Core
    "PipelineConfig",
    "LLMStep",
    # Strategy
    "PipelineStrategy",
    # ...
]
```

### 6.2 New Exports for Task 1

Add to `llm_pipeline/__init__.py`:

```python
# New imports
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.agent_builders import StepDeps, build_step_agent

# Add to __all__
__all__ = [
    # Core
    ...
    # Agent (new)
    "AgentRegistry",
    "StepDeps",
    "build_step_agent",
    ...
]
```

### 6.3 File Location Decisions

| New Module | Location | Rationale |
|-----------|----------|-----------|
| `agent_registry.py` | `llm_pipeline/agent_registry.py` | Top-level, mirrors `registry.py` |
| `agent_builders.py` | `llm_pipeline/agent_builders.py` | Top-level, utility module |

These go in the library root (`llm_pipeline/`), not in a subdirectory. Consistent with how `registry.py`, `strategy.py`, `step.py` are organized.


## 7. Key Findings Summary

1. **AgentRegistry**: Follow `PipelineDatabaseRegistry` pattern with `agents=` class param, `AGENTS` ClassVar, direct-subclass enforcement. Add naming validation to `PipelineConfig.__init_subclass__`.

2. **Deprecation**: Use `warnings.warn("...", DeprecationWarning, stacklevel=2)` inline. No helper function needed. Include migration path in message.

3. **StepDeps**: `@dataclass`, not Pydantic. Holds Session, PipelineContext dict, PromptService, optional ValidationContext. Compatible with `RunContext[StepDeps]` typing.

4. **get_agent()**: Concrete method on LLMStep, not abstract. Registry lookup by step_name with agent_name override.

5. **build_user_prompt()**: Concrete method with default implementation. Replicates prompt resolution from execute_llm_step().

6. **Exports**: Add AgentRegistry, StepDeps, build_step_agent to `llm_pipeline/__init__.py` with "Agent" category section.

7. **Python 3.11+**: No new features needed. Continue existing patterns (union syntax, kw_only dataclass).
