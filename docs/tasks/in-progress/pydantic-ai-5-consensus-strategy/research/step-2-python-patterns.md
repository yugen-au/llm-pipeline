# Research Step 2: Python Patterns for Consensus Strategy

## 1. Strategy Pattern with ABC in Python 3.11+

### Current Codebase Pattern (PipelineStrategy)

The codebase already implements Strategy Pattern via `PipelineStrategy(ABC)` in `strategy.py`. Key traits:
- Pure ABC with `@abstractmethod` for `can_handle()` and `get_steps()`
- `__init_subclass__` for auto-naming (NAME, DISPLAY_NAME from class name)
- No Pydantic BaseModel inheritance -- behavioral contract only
- Concrete strategies instantiated via `PipelineStrategies.create_instances()`

### Recommended Pattern for ConsensusStrategy

Follow the same `ABC`-only pattern. ConsensusStrategy is a behavioral interface, not a data validation model.

```python
from abc import ABC, abstractmethod
from typing import Any, List
from pydantic import BaseModel

class ConsensusStrategy(ABC):
    """ABC for consensus voting algorithms."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier (e.g., 'majority_vote')."""
        ...

    @abstractmethod
    def should_continue(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
        attempt: int,
        max_attempts: int,
    ) -> bool:
        """Whether to continue polling. Called after each LLM call."""
        ...

    @abstractmethod
    def select(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
    ) -> "ConsensusResult":
        """Select final result and produce ConsensusResult metadata."""
        ...
```

**Why ABC not Protocol:**
- ABC enforces implementation at instantiation time (fail-fast)
- Matches existing PipelineStrategy pattern
- Protocol is better for structural subtyping / duck typing -- not needed here since strategies are explicitly registered

**Why not BaseModel + ABC:**
- Strategy configuration (threshold, max_calls) can be init params without Pydantic
- Avoids Pydantic model_config complexity for behavioral classes
- Plain `__init__` with default params is simpler for strategy config
- If serialization needed later, can add `model_dump()`-like method without full Pydantic

### Auto-Naming via `__init_subclass__`

Can replicate PipelineStrategy's auto-naming pattern:

```python
class ConsensusStrategy(ABC):
    NAME: str
    DISPLAY_NAME: str

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__.startswith('_'):
            return
        # Validate naming convention
        if not cls.__name__.endswith('Strategy'):
            raise ValueError(f"Must end with 'Strategy': {cls.__name__}")
        # Auto-derive name
        prefix = cls.__name__[:-8]
        cls.NAME = to_snake_case(prefix)
        cls.DISPLAY_NAME = prefix  # or use regex for spaced form
```

However, this conflicts with PipelineStrategy's `__init_subclass__` which also checks for 'Strategy' suffix. **Two options:**
1. Different suffix requirement (e.g., `ConsensusStrategy` suffix check is separate from `PipelineStrategy`)
2. Explicit `name` property on each subclass (no auto-naming)

Recommendation: Use explicit `name` property (abstractproperty) since there are only 4 strategies and naming collision with PipelineStrategy subclasses is a risk.

## 2. ConsensusResult Model Design

### Option A: Pydantic BaseModel (Recommended)

```python
from pydantic import BaseModel, Field, ConfigDict

class ConsensusResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    result: Any  # The selected instruction (BaseModel instance)
    confidence: float = Field(ge=0.0, le=1.0)
    strategy_name: str
    agreement_ratio: float = Field(ge=0.0, le=1.0)
    total_attempts: int
    group_count: int
    consensus_reached: bool
```

**Pros:**
- Built-in validation (confidence/agreement_ratio bounds)
- `model_dump()` for event serialization
- `frozen=True` for immutability (matches event pattern)
- Consistent with PipelineContext, LLMResultMixin patterns

### Option B: Frozen Dataclass

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ConsensusResult:
    result: Any
    confidence: float
    strategy_name: str
    agreement_ratio: float
    total_attempts: int
    group_count: int
    consensus_reached: bool
```

**Pros:**
- Matches event type pattern (frozen dataclass with slots)
- Lighter weight, no Pydantic overhead
- Matches StepDeps pattern (dataclass for internal containers)

**Cons:**
- No built-in validation for bounds
- No `model_dump()` (need `asdict()` from dataclasses)

### Recommendation

**Pydantic BaseModel** (Option A). Rationale:
- ConsensusResult flows to events and potentially to API responses
- Validation of confidence/agreement_ratio bounds prevents bugs
- `model_dump()` integrates cleanly with existing event serialization
- The overhead is negligible (single instantiation per consensus round)

### Current Return Value Mapping

Current `_execute_with_consensus()` returns:
```python
(result, input_tokens, output_tokens, total_requests)
```

ConsensusResult replaces the first element. Token tracking stays separate (it's an accumulator concern, not consensus concern). New return shape:

```python
(ConsensusResult, input_tokens, output_tokens, total_requests)
```

The caller extracts `consensus_result.result` for the instruction and uses metadata for events/logging.

## 3. Strategy Variant Algorithms

### MajorityVoteStrategy (reproduces current behavior)

Current algorithm (pipeline.py L1290-1386):
1. Loop up to `maximum_step_calls`
2. Each result grouped by `_instructions_match()` comparison
3. If any group reaches `consensus_threshold` -> return first member
4. If loop exhausts -> return first member of largest group

```python
class MajorityVoteStrategy(ConsensusStrategy):
    def __init__(self, threshold: int = 3):
        self._threshold = threshold

    @property
    def name(self) -> str:
        return "majority_vote"

    def should_continue(self, results, result_groups, attempt, max_attempts):
        # Stop if any group hit threshold
        for group in result_groups:
            if len(group) >= self._threshold:
                return False
        # Stop if exhausted attempts
        return attempt < max_attempts

    def select(self, results, result_groups):
        # Find largest group
        largest = max(result_groups, key=len)
        reached = len(largest) >= self._threshold
        return ConsensusResult(
            result=largest[0],
            confidence=len(largest) / len(results) if results else 0.0,
            strategy_name=self.name,
            agreement_ratio=len(largest) / len(results) if results else 0.0,
            total_attempts=len(results),
            group_count=len(result_groups),
            consensus_reached=reached,
        )
```

**Critical: `_instructions_match()` grouping logic must remain identical** to reproduce current behavior. The comparison functions move to consensus module as module-level utilities.

### ConfidenceWeightedStrategy

Uses `confidence_score` from LLMResultMixin to weight votes:

```python
class ConfidenceWeightedStrategy(ConsensusStrategy):
    def __init__(self, threshold: float = 0.8, min_samples: int = 3):
        self._threshold = threshold  # weighted confidence threshold
        self._min_samples = min_samples

    def should_continue(self, results, result_groups, attempt, max_attempts):
        if len(results) < self._min_samples:
            return attempt < max_attempts
        # Check if weighted confidence of best group exceeds threshold
        best_weighted = self._best_weighted_confidence(results, result_groups)
        return best_weighted < self._threshold and attempt < max_attempts

    def select(self, results, result_groups):
        # Weight each group by sum of confidence_scores
        best_group = max(result_groups, key=lambda g: sum(
            getattr(r, 'confidence_score', 0.5) for r in g
        ))
        weighted_conf = (
            sum(getattr(r, 'confidence_score', 0.5) for r in best_group)
            / sum(getattr(r, 'confidence_score', 0.5) for r in results)
        )
        return ConsensusResult(
            result=max(best_group, key=lambda r: getattr(r, 'confidence_score', 0.5)),
            confidence=weighted_conf,
            strategy_name=self.name,
            agreement_ratio=len(best_group) / len(results),
            total_attempts=len(results),
            group_count=len(result_groups),
            consensus_reached=weighted_conf >= self._threshold,
        )
```

**Edge case:** If output_type doesn't inherit LLMResultMixin, `confidence_score` won't exist. Use `getattr(r, 'confidence_score', 0.5)` fallback (neutral weight).

### AdaptiveStrategy

Dynamically adjusts behavior based on observed agreement:

```python
class AdaptiveStrategy(ConsensusStrategy):
    def __init__(self, initial_threshold: int = 3, min_threshold: int = 2):
        self._initial_threshold = initial_threshold
        self._min_threshold = min_threshold

    def should_continue(self, results, result_groups, attempt, max_attempts):
        # Adapt threshold based on diversity
        effective_threshold = self._effective_threshold(result_groups, attempt, max_attempts)
        for group in result_groups:
            if len(group) >= effective_threshold:
                return False
        return attempt < max_attempts

    def _effective_threshold(self, result_groups, attempt, max_attempts):
        # Lower threshold as attempts increase (diminishing returns)
        progress = attempt / max_attempts
        if progress > 0.7:
            return self._min_threshold
        return self._initial_threshold
```

### SoftVoteStrategy

Aggregates confidence scores across all results (not just matching groups):

```python
class SoftVoteStrategy(ConsensusStrategy):
    def __init__(self, min_samples: int = 3, confidence_floor: float = 0.7):
        self._min_samples = min_samples
        self._confidence_floor = confidence_floor

    def should_continue(self, results, result_groups, attempt, max_attempts):
        if len(results) < self._min_samples:
            return attempt < max_attempts
        # Stop when average confidence of best group exceeds floor
        best_avg = self._best_avg_confidence(result_groups)
        return best_avg < self._confidence_floor and attempt < max_attempts

    def select(self, results, result_groups):
        # Select group with highest average confidence
        best_group = max(result_groups, key=lambda g: (
            sum(getattr(r, 'confidence_score', 0.5) for r in g) / len(g)
        ))
        avg_confidence = (
            sum(getattr(r, 'confidence_score', 0.5) for r in best_group) / len(best_group)
        )
        return ConsensusResult(
            result=best_group[0],
            confidence=avg_confidence,
            strategy_name=self.name,
            agreement_ratio=len(best_group) / len(results),
            total_attempts=len(results),
            group_count=len(result_groups),
            consensus_reached=avg_confidence >= self._confidence_floor,
        )
```

## 4. Per-Step Configuration via StepDefinition

### Current StepDefinition (dataclass, strategy.py L23)

```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type
    action_after: Optional[str] = None
    extractions: List[Type['PipelineExtraction']] = field(default_factory=list)
    transformation: Optional[Type['PipelineTransformation']] = None
    context: Optional[Type] = None
    agent_name: str | None = None
    not_found_indicators: list[str] | None = None
```

### Adding consensus_strategy field

```python
@dataclass
class StepDefinition:
    # ... existing fields ...
    consensus_strategy: 'ConsensusStrategy | None' = None
```

**Type annotation note:** Use string literal for forward reference since consensus module imports would be circular. Or use `TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm_pipeline.consensus import ConsensusStrategy
```

### Pipeline-level vs Step-level config interaction

Current pipeline.execute() accepts `consensus_polling` dict:
```python
consensus_polling = {
    "enable": True,
    "consensus_threshold": 3,
    "maximum_step_calls": 5,
}
```

With per-step config, the resolution order should be:
1. Step-level: `step_def.consensus_strategy` (if set)
2. Pipeline-level: `consensus_polling` dict (default for all steps)
3. None: no consensus (single call)

The `step_definition` decorator's `create_definition()` should also accept `consensus_strategy`:

```python
@classmethod
def create_definition(cls, ..., consensus_strategy=None):
    return StepDefinition(..., consensus_strategy=consensus_strategy)
```

## 5. Module-Level Utilities vs Class Methods

### Current pattern (class methods on PipelineConfig)

```python
class PipelineConfig(ABC):
    @staticmethod
    def _get_mixin_fields(model_class): ...
    @staticmethod
    def _smart_compare(value1, value2, ...): ...
    @staticmethod
    def _instructions_match(instr1, instr2): ...
```

### Recommended: Module-level functions in consensus.py

```python
# llm_pipeline/consensus.py

def _get_mixin_fields(model_class: type[BaseModel]) -> set[str]:
    """Get field names from LLMResultMixin (excluded from comparison)."""
    from llm_pipeline.step import LLMResultMixin
    if not issubclass(model_class, LLMResultMixin):
        return set()
    return set(LLMResultMixin.model_fields.keys())

def _smart_compare(value1: Any, value2: Any, field_name: str = "", mixin_fields: set[str] | None = None) -> bool:
    """Recursive structural comparison, skipping strings and mixin fields."""
    ...

def instructions_match(instr1: BaseModel, instr2: BaseModel) -> bool:
    """Compare two instruction instances for consensus grouping."""
    mixin_fields = _get_mixin_fields(type(instr1))
    return _smart_compare(instr1.model_dump(), instr2.model_dump(), mixin_fields=mixin_fields)
```

**Rationale for module-level:**
- Functions have no state -- pure functions, no `self`
- Already `@staticmethod` on PipelineConfig (no instance access)
- Moving to consensus.py co-locates them with their only consumer
- `_smart_compare` and `_get_mixin_fields` stay private (underscore prefix)
- `instructions_match` becomes public (no underscore) since strategies use it

**Backward compatibility:** PipelineConfig._instructions_match is only called from _execute_with_consensus. After refactor, _execute_with_consensus delegates to strategy.select() which internally uses instructions_match from consensus module. No external callers to break.

## 6. Type Hints and Protocol Patterns

### Python 3.11+ Type Features

```python
# Union syntax (3.10+)
consensus_strategy: ConsensusStrategy | None = None

# Self type (3.11+) -- useful if strategies return self for chaining
from typing import Self

# TypeVar with bounds
from typing import TypeVar
TResult = TypeVar('TResult', bound=BaseModel)
```

### Protocol Alternative (not recommended, but documented)

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ConsensusStrategyProtocol(Protocol):
    @property
    def name(self) -> str: ...
    def should_continue(self, results, result_groups, attempt, max_attempts) -> bool: ...
    def select(self, results, result_groups) -> ConsensusResult: ...
```

**When Protocol would be better:**
- If third-party code needs to implement strategies without importing our ABC
- If duck typing is preferred over nominal typing
- Neither applies here -- this is an internal framework API

### Generic ConsensusResult

If different strategies produce different metadata, could use Generic:

```python
from typing import Generic, TypeVar
TMetadata = TypeVar('TMetadata')

class ConsensusResult(BaseModel, Generic[TMetadata]):
    result: Any
    confidence: float
    metadata: TMetadata
```

Not recommended for initial implementation -- adds complexity without clear benefit. All strategies share the same metadata fields (confidence, agreement_ratio, etc.).

## 7. Codebase-Specific Patterns to Follow

### File Location
- New file: `llm_pipeline/consensus.py` (flat module, same level as strategy.py, step.py)
- Task mentions `logistics_intelligence/core/schemas/pipeline/consensus.py` -- this is the OLD monolith path. Current package is `llm_pipeline/`.

### Export Pattern
```python
# llm_pipeline/consensus.py
__all__ = [
    "ConsensusStrategy",
    "ConsensusResult",
    "MajorityVoteStrategy",
    "ConfidenceWeightedStrategy",
    "AdaptiveStrategy",
    "SoftVoteStrategy",
    "instructions_match",
]
```

Add to `llm_pipeline/__init__.py`:
```python
from llm_pipeline.consensus import (
    ConsensusStrategy, ConsensusResult,
    MajorityVoteStrategy, ConfidenceWeightedStrategy,
    AdaptiveStrategy, SoftVoteStrategy,
)
```

### Naming Convention
- Classes: CamelCase with Strategy suffix (MajorityVoteStrategy)
- Module functions: snake_case (instructions_match)
- Private helpers: underscore prefix (_smart_compare, _get_mixin_fields)
- Constants: UPPER_SNAKE (if any)

### Event Integration
ConsensusResult metadata should populate existing consensus events:
- `ConsensusReached.threshold` maps to strategy's threshold
- `ConsensusAttempt.group_count` maps to `len(result_groups)`
- `ConsensusFailed.largest_group_size` maps to `max(len(g) for g in result_groups)`

New event fields could include `strategy_name` and `confidence` but this is a planning-phase decision.

### Testing Pattern
Follow test_consensus_events.py pattern:
- Mock `Agent.run_sync` with controlled responses
- Use `_make_responses()` helper to build response lists
- Test each strategy independently with known inputs
- Integration test via pipeline.execute() with consensus_polling

## 8. Summary of Recommended Patterns

| Component | Pattern | Rationale |
|---|---|---|
| ConsensusStrategy | Pure ABC | Matches PipelineStrategy, behavioral contract |
| ConsensusResult | Pydantic BaseModel (frozen) | Validation, serialization, event compat |
| Utility functions | Module-level in consensus.py | Pure functions, no state, co-located |
| Per-step config | Optional field on StepDefinition | Step-level overrides pipeline-level default |
| Type hints | 3.10+ union syntax, TYPE_CHECKING imports | Avoid circular imports, modern syntax |
| Module location | llm_pipeline/consensus.py | Flat module, follows existing structure |
| Strategy naming | Explicit name property (abstractproperty) | Avoid __init_subclass__ collision with PipelineStrategy |
