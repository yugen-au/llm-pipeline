# Step 2: Python Dataclass Patterns for LLMCallResult

## 1. dataclass vs Pydantic BaseModel

### Recommendation: stdlib `@dataclass` (current choice is correct)

| Criterion | stdlib dataclass | Pydantic BaseModel |
|-----------|------------------|--------------------|
| Construction overhead | ~10ns | ~100-500ns |
| Immutability | `frozen=True` (FrozenInstanceError) | `ConfigDict(frozen=True)` (ValidationError) |
| Memory (slots) | `slots=True` native | Not supported (uses `__dict__`) |
| Validation on init | None (fields are trusted) | Full type coercion + validation |
| Serialization | `dataclasses.asdict()` + custom | `model_dump()` / `model_dump_json()` |
| Schema generation | Manual | `model_json_schema()` auto |
| Runtime deps | stdlib only | pydantic >= 2.0 |

**Why dataclass wins for LLMCallResult:**

1. **Value object semantics** -- LLMCallResult is a transport record between provider and executor layers. It captures already-validated data (parsed dict passed Pydantic validation inside the provider, attempt_count is provider-controlled, etc.). Re-validating on construction adds overhead with no safety benefit.

2. **Hot path performance** -- Created on every LLM call. stdlib dataclass construction is 10-50x faster than Pydantic BaseModel instantiation with validation.

3. **Consistency with event system** -- PipelineEvent and all 31 concrete events use `@dataclass(frozen=True, slots=True)`. LLMCallResult sits in the same "immutable record" category.

4. **Library dependency minimization** -- As a reusable library, minimizing Pydantic dependency surface is preferable. Core data transport objects should use stdlib where sufficient.

5. **No user input** -- Pydantic excels at validating external/untrusted input. LLMCallResult fields are populated by provider implementation code, not user data.

**When Pydantic BaseModel IS appropriate in this codebase:**
- Domain models with user-facing validation (PipelineContext, LLMResultMixin)
- Models that need schema generation for LLM prompts (result_class in call_structured)
- Models that participate in Pydantic's validation ecosystem (model_validate, model_dump)

---

## 2. Field Design Patterns

### Current Fields

```python
@dataclass(frozen=True, slots=True)
class LLMCallResult:
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)
```

### All-defaults pattern

All fields have defaults. This is intentional and correct for a value object:
- Enables keyword-only construction with partial overrides
- Supports testing convenience (`LLMCallResult()` is a valid "empty" result)
- Factory methods (see section 7) provide domain-semantic constructors

### Optional fields (`| None`)

`parsed`, `raw_response`, `model_name` are `T | None` because:
- `parsed` is None on failure (all retries exhausted)
- `raw_response` is None if no LLM response received (network error, no response.text)
- `model_name` is None for provider-agnostic contexts (testing, stubs)

### Mutable defaults and frozen interaction

**Critical pitfall:** `frozen=True` prevents field reassignment but does NOT prevent mutation of mutable containers:

```python
result = LLMCallResult(parsed={"key": "val"}, validation_errors=["err"])
result.parsed = {}          # FrozenInstanceError (prevented)
result.parsed["new"] = "x"  # ALLOWED (dict mutation, not reassignment)
result.validation_errors.append("x")  # ALLOWED (list mutation)
```

**Mitigation options:**

| Approach | Pros | Cons |
|----------|------|------|
| Convention + docs (current) | Zero overhead, matches PipelineEvent pattern | Relies on developer discipline |
| Deep-copy on init | True isolation | Performance overhead, complex `__post_init__` with frozen |
| tuple for lists, MappingProxyType for dicts | Truly immutable at runtime | Breaks caller ergonomics, tuple != list interface |

**Recommendation:** Convention + docs. This is the existing pattern in PipelineEvent (which has `dict[str, Any]` and `list[str]` fields with the same "must not be mutated" docstring convention). Consistency > theoretical purity.

### `field(default_factory=list)` for mutable defaults

Required by Python dataclasses to avoid the mutable default argument trap. Already correctly used for `validation_errors`. Standard pattern, no changes needed.

---

## 3. Serialization Patterns

### Current state

LLMCallResult has no serialization methods. PipelineEvent has:

```python
def to_dict(self) -> dict[str, Any]:
    d = asdict(self)
    for key, val in d.items():
        if isinstance(val, datetime):
            d[key] = val.isoformat()
    return d

def to_json(self) -> str:
    return json.dumps(self.to_dict())
```

### Recommendation: Add `to_dict()` and `to_json()`

LLMCallResult fields are all JSON-native types (dict, str, int, list[str], None). No datetime conversion needed, making serialization trivial:

```python
def to_dict(self) -> dict[str, Any]:
    """Serialize to plain dict. All fields are JSON-compatible."""
    return asdict(self)

def to_json(self) -> str:
    """Serialize to JSON string."""
    return json.dumps(asdict(self))
```

**Why add explicit methods vs relying on `dataclasses.asdict()` externally:**
1. API consistency with PipelineEvent (same library, same pattern)
2. Encapsulation -- if field types change later (e.g., add datetime), conversion logic lives in the class
3. Discoverability -- users see `result.to_dict()` in autocomplete

### `asdict()` behavior with nested structures

`dataclasses.asdict()` recursively converts nested dataclasses and copies dicts/lists. For LLMCallResult:
- `parsed` dict is deep-copied (new dict, isolated from original)
- `validation_errors` list is deep-copied
- `raw_response`, `model_name`, `attempt_count` are immutable scalars

This means `to_dict()` returns a fully independent copy, safe for mutation by callers.

### Alternative: `__json__` / custom encoder

Not recommended. No stdlib standard for `__json__`. The explicit `to_dict()`/`to_json()` methods are clearer and match the event system.

---

## 4. Type Annotation Best Practices (Python 3.11+)

### Use built-in generics (PEP 585)

Python 3.9+ supports `dict[str, Any]`, `list[str]`, `tuple[int, ...]` directly. No need for `typing.Dict`, `typing.List`, etc.

```python
# Correct (3.11+)
parsed: dict[str, Any] | None
validation_errors: list[str]

# Outdated (pre-3.9)
parsed: Optional[Dict[str, Any]]
validation_errors: List[str]
```

LLMCallResult already uses the correct modern syntax.

### Use PEP 604 union syntax

Python 3.10+ supports `X | Y` instead of `Union[X, Y]` and `X | None` instead of `Optional[X]`.

```python
# Correct (3.11+)
parsed: dict[str, Any] | None

# Outdated
parsed: Optional[Dict[str, Any]]
```

Already correctly used in LLMCallResult.

### `from __future__ import annotations`

Currently present in `result.py`. In Python 3.11+, this makes all annotations strings (lazy evaluation). Benefits:
- Forward references work without quotes
- Slight import-time speedup (annotations not evaluated)

Caveats:
- `slots=True` + `__init_subclass__` with zero-arg `super()` breaks (see events/types.py note)
- LLMCallResult has no `__init_subclass__`, so `from __future__ import annotations` is safe

**Recommendation:** Keep `from __future__ import annotations` in result.py. It's harmless and consistent with the file's existing style. Note that events/types.py intentionally omits it due to slots+super() interaction.

### `Any` import

Still required from `typing` module. No built-in equivalent for `Any`.

---

## 5. Integration Patterns: Result Dataclasses in Pipeline Architectures

### Provider -> Result -> Executor pattern

```
GeminiProvider.call_structured()
    |
    v
LLMCallResult(parsed=..., raw_response=..., model_name=..., ...)
    |
    v
execute_llm_step() reads .parsed, uses .model_name for logging
    |
    v
PipelineConfig orchestrator: can populate PipelineStepState.model,
    emit LLMCallCompleted event from result fields
```

### Key integration points

1. **GeminiProvider -> LLMCallResult** (Task 4): Provider builds LLMCallResult at every exit point:
   - Success: `LLMCallResult(parsed=response_json, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1)`
   - Failure: `LLMCallResult(parsed=None, raw_response=last_raw, model_name=self.model_name, attempt_count=max_retries, validation_errors=[...])`
   - Not-found: `LLMCallResult(parsed=None, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1)`

2. **execute_llm_step() consumption** (Task 4+): Replace `if result_dict is None` with `if result.parsed is None`. Access `result.model_name`, `result.attempt_count` for richer logging.

3. **Event construction from result**: LLMCallCompleted event has overlapping fields. Pattern:
   ```python
   LLMCallCompleted(
       ...,  # event base fields
       call_index=i,
       raw_response=result.raw_response,
       parsed_result=result.parsed,      # note: parsed_result vs parsed
       model_name=result.model_name,
       attempt_count=result.attempt_count,
       validation_errors=result.validation_errors,
   )
   ```

4. **State population**: `PipelineStepState.model` field (currently unpopulated) can be set from `result.model_name`.

### Why NOT embed LLMCallResult inside events

LLMCallCompleted and LLMCallResult share fields but serve different purposes:
- LLMCallResult: provider-to-executor transport (no run_id, no pipeline_name, no step_name)
- LLMCallCompleted: audit event with full pipeline context

Embedding would couple the event schema to the result schema. Keeping them separate allows independent evolution. The mapping between them is trivial (5 field assignments).

### `@property` convenience for success/failure checking

```python
@property
def is_success(self) -> bool:
    return self.parsed is not None

@property
def is_failure(self) -> bool:
    return self.parsed is None
```

These encode the domain contract: success = parsed data present. Avoids callers needing to know the None-check convention.

---

## 6. Equality, Hashing, and Repr

### Equality (`__eq__`)

`frozen=True` generates `__eq__` comparing all fields by value. This works correctly:
- `dict` equality is by-value in Python (`{"a": 1} == {"a": 1}` is True)
- `list` equality is by-value (`["err"] == ["err"]` is True)
- `None == None` is True

Useful for testing:
```python
assert result == LLMCallResult(parsed={"key": "val"}, model_name="gemini-2.0-flash-lite", attempt_count=1)
```

### Hashing (`__hash__`)

`frozen=True` generates `__hash__` from all fields. **Pitfall: dict and list are unhashable.**

```python
result = LLMCallResult(parsed={"key": "val"})
hash(result)  # TypeError: unhashable type: 'dict'

result = LLMCallResult()  # parsed=None, validation_errors=[]
hash(result)  # TypeError: unhashable type: 'list' (validation_errors is a list)
```

**Even with empty list**, `hash([])` raises TypeError. So LLMCallResult is **never hashable** with the current field set.

**Options:**

| Approach | Effect |
|----------|--------|
| Accept (document) | TypeError on hash(), cannot use as dict key or in set. Acceptable -- LLMCallResult has no use case for hashing. |
| `eq=True, frozen=True, unsafe_hash=True` | Forces hash based on id(). Loses value-based hash semantics. |
| Override `__hash__ = None` | Explicitly marks as unhashable. Redundant since frozen already generates one that fails. |
| Convert list to tuple | `validation_errors: tuple[str, ...]` -- changes interface, breaks caller ergonomics. |

**Recommendation:** Accept and document. No use case for hashing LLMCallResult. The frozen+dict/list combination means equality works but hashing does not. This is the same situation as PipelineEvent (which has dict and list fields). Standard Python behavior, well-understood.

### Repr (`__repr__`)

Auto-generated repr includes all fields with their values:
```
LLMCallResult(parsed={'key': 'val'}, raw_response='very long text...', model_name='gemini-2.0-flash-lite', attempt_count=1, validation_errors=[])
```

**Concern:** `raw_response` can be thousands of characters (full LLM output).

**Options:**
- Accept default: Logging frameworks handle truncation. Debuggers have their own display limits.
- Custom `__repr__` with truncation: Straightforward on frozen+slots dataclasses (just define the method).

**Recommendation:** Accept default repr initially. If raw_response length causes log noise in practice, add truncation later. Custom repr is a presentation concern, not a correctness concern. PipelineEvent uses default repr with similar large-payload fields.

---

## 7. Factory Methods

### Recommendation: Add `success()` and `failure()` classmethods

```python
@classmethod
def success(
    cls,
    parsed: dict[str, Any],
    raw_response: str | None = None,
    model_name: str | None = None,
    attempt_count: int = 1,
) -> LLMCallResult:
    """Create result for successful LLM call with parsed output."""
    return cls(
        parsed=parsed,
        raw_response=raw_response,
        model_name=model_name,
        attempt_count=attempt_count,
        validation_errors=[],
    )

@classmethod
def failure(
    cls,
    validation_errors: list[str],
    raw_response: str | None = None,
    model_name: str | None = None,
    attempt_count: int = 1,
) -> LLMCallResult:
    """Create result for failed LLM call (all retries exhausted)."""
    return cls(
        parsed=None,
        raw_response=raw_response,
        model_name=model_name,
        attempt_count=attempt_count,
        validation_errors=validation_errors,
    )
```

**Benefits:**
1. **Domain semantics** -- `LLMCallResult.success(parsed=data)` vs `LLMCallResult(parsed=data)` clearly communicates intent
2. **Enforced invariants** -- `success()` forces `parsed` to be provided (not None), `failure()` forces `validation_errors` to be provided
3. **Downstream readability** -- Task 4's GeminiProvider code becomes:
   ```python
   return LLMCallResult.success(parsed=response_json, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1)
   # vs
   return LLMCallResult(parsed=response_json, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=[])
   ```
4. **Consistency** -- LLMResultMixin (Pydantic BaseModel in step.py) already uses `create_failure()` classmethod pattern

**Note:** Factory methods on frozen dataclasses work fine. They call `cls(...)` which goes through normal `__init__`. No `object.__setattr__` needed.

---

## 8. Summary: Recommended Enhancements to Current LLMCallResult

| Enhancement | Priority | Rationale |
|-------------|----------|-----------|
| `to_dict()` method | High | Consistency with PipelineEvent, needed for state serialization |
| `to_json()` method | High | Consistency with PipelineEvent, JSON logging/storage |
| `success()` classmethod | High | Domain semantics, enforced invariants, Task 4 readability |
| `failure()` classmethod | High | Domain semantics, enforced invariants, Task 4 readability |
| `is_success` property | Medium | Convenience, encapsulates None-check convention |
| `is_failure` property | Medium | Convenience, complements is_success |
| Docstring on hash behavior | Low | Documents that frozen+dict/list means unhashable |
| Custom `__repr__` (truncation) | Low | Defer unless log noise becomes an issue |

### Proposed complete implementation

```python
"""LLM call result dataclass for structured capture of LLM responses."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    """Immutable record of a single LLM call's outcome.

    Captures parsed output, raw response text, model metadata, and any
    validation errors encountered during response processing.

    Fields containing mutable containers (parsed dict, validation_errors list)
    must not be mutated after creation.

    Note: Despite frozen=True, instances are NOT hashable because dict and
    list fields are unhashable. Equality comparison (__eq__) works correctly.
    """

    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)

    # -- Predicates --------------------------------------------------------

    @property
    def is_success(self) -> bool:
        """True when parsed output is present."""
        return self.parsed is not None

    @property
    def is_failure(self) -> bool:
        """True when no parsed output (all retries exhausted or error)."""
        return self.parsed is None

    # -- Serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict. All fields are JSON-compatible."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))

    # -- Factory methods ---------------------------------------------------

    @classmethod
    def success(
        cls,
        parsed: dict[str, Any],
        raw_response: str | None = None,
        model_name: str | None = None,
        attempt_count: int = 1,
    ) -> LLMCallResult:
        """Create result for successful LLM call with parsed output."""
        return cls(
            parsed=parsed,
            raw_response=raw_response,
            model_name=model_name,
            attempt_count=attempt_count,
            validation_errors=[],
        )

    @classmethod
    def failure(
        cls,
        validation_errors: list[str],
        raw_response: str | None = None,
        model_name: str | None = None,
        attempt_count: int = 1,
    ) -> LLMCallResult:
        """Create result for failed LLM call (all retries exhausted)."""
        return cls(
            parsed=None,
            raw_response=raw_response,
            model_name=model_name,
            attempt_count=attempt_count,
            validation_errors=validation_errors,
        )
```

---

## 9. Codebase Consistency Notes

| Pattern | LLMCallResult | PipelineEvent | types.py dataclasses |
|---------|---------------|---------------|----------------------|
| `frozen=True` | Yes | Yes | No |
| `slots=True` | Yes | Yes | No |
| `from __future__ import annotations` | Yes | No (slots+super issue) | No |
| Serialization methods | to_dict, to_json (proposed) | to_dict, to_json | to_dict (ValidationContext) |
| Factory methods | success, failure (proposed) | resolve_event (deserialization) | None |
| Type annotation style | Modern (dict, list, \|) | Modern | Legacy (Dict, List, Optional) |
