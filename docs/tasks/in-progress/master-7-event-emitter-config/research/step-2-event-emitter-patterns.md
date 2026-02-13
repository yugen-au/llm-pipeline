# Research: Event Emitter Integration Patterns

## 1. Existing Event System (Task 2 Output)

### PipelineEventEmitter Protocol
**File:** `llm_pipeline/events/emitter.py`

- `@runtime_checkable` Protocol with single method: `emit(self, event: PipelineEvent) -> None`
- Duck-typing compatible: any object with conforming `emit()` works
- Follows `VariableResolver` pattern exactly (single method, `@runtime_checkable`, `__all__` export)

### CompositeEmitter
**File:** `llm_pipeline/events/emitter.py`

- Accepts `list[PipelineEventEmitter]`, stores as immutable `tuple`
- Sequential dispatch with per-handler `Exception` catch + `logger.exception()`
- `__slots__ = ("_handlers",)`, `__repr__` showing handler count
- No Lock needed (immutable tuple, no dynamic add/remove API)
- Satisfies `PipelineEventEmitter` Protocol itself (has `emit()` method)

### PipelineEvent Base
**File:** `llm_pipeline/events/types.py`

- `@dataclass(frozen=True, slots=True)` -- immutable, safe to share across handlers
- Base fields: `run_id: str`, `pipeline_name: str`, `timestamp: datetime`
- `event_type: str` -- derived automatically from class name via `__init_subclass__`
- 31 concrete event subclasses across 9 categories
- `StepScopedEvent` intermediate base adds optional `step_name: str | None`

### Exports
**File:** `llm_pipeline/events/__init__.py`

- Re-exports all event types, `PipelineEventEmitter`, `CompositeEmitter`, `LLMCallResult`
- 44+ symbols in `__all__`

### Task 2 Deviations from Spec
None. Implementation followed plan exactly (confirmed in SUMMARY.md).

## 2. PipelineConfig Architecture

### Class Design
**File:** `llm_pipeline/pipeline.py:73`

- `PipelineConfig(ABC)` -- abstract base class, NOT Pydantic
- Uses `__init_subclass__` for registry/strategies metaclass-style configuration
- `ClassVar` attributes: `REGISTRY`, `STRATEGIES`

### Current `__init__` Signature (line 127)
```python
def __init__(
    self,
    strategies: Optional[List["PipelineStrategy"]] = None,
    session: Optional[Session] = None,
    engine: Optional[Engine] = None,
    provider: Optional["LLMProvider"] = None,
    variable_resolver: Optional["VariableResolver"] = None,
):
```

### Private Attribute Storage Pattern
All optional dependencies stored as private underscore attrs:
- `self._provider = provider` (line 148)
- `self._variable_resolver = variable_resolver` (line 149)
- `self._strategies = strategies` (line 163)

### TYPE_CHECKING Import Pattern
**File:** `llm_pipeline/pipeline.py:35-40`

```python
if TYPE_CHECKING:
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
    from llm_pipeline.registry import PipelineDatabaseRegistry
    from llm_pipeline.state import PipelineStepState
    from llm_pipeline.llm.provider import LLMProvider
    from llm_pipeline.prompts.variables import VariableResolver
```

All TYPE_CHECKING imports use specific submodule paths (not the package `__init__`).
Type annotations in signatures use string literals: `Optional["LLMProvider"]`, `Optional["VariableResolver"]`.

### Optional Protocol Usage Pattern (variable_resolver)
**File:** `llm_pipeline/step.py:280`

```python
if system_key and hasattr(self.pipeline, '_variable_resolver') and self.pipeline._variable_resolver:
    system_var_class = self.pipeline._variable_resolver.resolve(system_key, 'system')
```

Note: `hasattr` check is a safety pattern but not strictly necessary since `_variable_resolver` is always set in `__init__`. The simpler `if self._event_emitter is not None:` pattern (as in task 7 spec) is sufficient and preferred.

## 3. Zero-Overhead Conditional Emission Pattern

### Requirement
When `event_emitter is None`, the `_emit()` call is a single `if` check. No event object construction.

### Pattern Analysis
The `_emit()` method itself is trivial:
```python
def _emit(self, event: PipelineEvent) -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

Zero overhead is achieved at the **call site**, not in `_emit()`. Task 8 (downstream) shows the pattern:
```python
if self._event_emitter:
    self._emit(PipelineStarted(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
    ))
```

The event object is only constructed inside the `if` block. When `_event_emitter is None`, execution skips event construction entirely. The `_emit()` helper provides a single forwarding point for all emission (useful for future interception/logging).

### Python Cost Analysis
- `if self._event_emitter is not None:` -- attribute lookup + identity comparison with None
- CPython cost: ~50ns (single `LOAD_ATTR` + `COMPARE_OP` + `POP_JUMP_IF_FALSE`)
- Well under 1ms threshold per the test strategy

### Why Both `if` Check AND `_emit()` Helper?
1. Call site `if` check: prevents event object construction (zero overhead)
2. `_emit()` helper: centralizes forwarding, enables future interception (logging, filtering) without touching every call site
3. Double-check in `_emit()` is redundant when callers gate, but protects against direct `_emit()` calls without gating

## 4. Integration Blueprint

### TYPE_CHECKING Addition
Add to existing `TYPE_CHECKING` block in `pipeline.py:35-40`:
```python
from llm_pipeline.events.emitter import PipelineEventEmitter
from llm_pipeline.events.types import PipelineEvent
```

### `__init__` Parameter Addition
Add after `variable_resolver` parameter:
```python
event_emitter: Optional["PipelineEventEmitter"] = None,
```

### Storage
```python
self._event_emitter = event_emitter
```
Place after `self._variable_resolver = variable_resolver` (line 149) for consistency.

### `_emit()` Helper Method
Place after `__init__` and before `instructions` property (between line ~200 and the first `@property`). Alternatively, group it with the other private helpers near the bottom -- but since it's conceptually tied to configuration, placing it near the stored attribute makes sense.

### Docstring Update
Add to existing `__init__` docstring Args section:
```
event_emitter: Optional PipelineEventEmitter for receiving pipeline events.
    When None (default), no events are emitted and zero overhead is incurred.
```

## 5. Downstream Compatibility (Task 8)

Task 8 will add actual `_emit()` calls inside `execute()`:
- `PipelineStarted` at start of execute
- `PipelineCompleted` at end of execute
- `PipelineError` in except block

All use the `if self._event_emitter:` gate pattern before event construction. Task 7 only needs to provide the `_event_emitter` attribute and `_emit()` method.

## 6. Upstream Task 2 Verification

Task 2 (done) produced:
- `PipelineEventEmitter` Protocol in `llm_pipeline/events/emitter.py` -- verified exists and matches spec
- `CompositeEmitter` in same file -- verified
- Both exported via `llm_pipeline/events/__init__.py` -- verified
- No deviations from plan (confirmed in SUMMARY.md)

## 7. Codebase Conventions Confirmed

| Convention | Pattern | Verified |
|---|---|---|
| Private attrs | Single underscore: `self._provider` | Yes (pipeline.py:148) |
| TYPE_CHECKING imports | Specific submodules, string annotations | Yes (pipeline.py:35-40) |
| Optional params | `Optional["Type"] = None` | Yes (pipeline.py:127-134) |
| Docstring style | Google-style with Args section | Yes (pipeline.py:136-144) |
| Module logger | `logger = logging.getLogger(__name__)` | Yes (pipeline.py:33) |
| `__all__` exports | Present on all modules | Yes |

## 8. Open Questions
None. Task spec is unambiguous. Upstream work matches expectations. All codebase patterns are clear.
