# Step 3: pydantic.create_model() for Instruction Deltas

## Summary

`pydantic.create_model()` is fully viable for dynamically creating modified instruction models at eval time. Empirically confirmed: works as `pydantic-ai Agent output_type`, supports field add/remove/modify, thread-safe for concurrent eval runs.

## Key Findings

### 1. create_model() as pydantic-ai output_type -- WORKS

```python
from pydantic import create_model, Field
from pydantic_ai import Agent

Modified = create_model('Modified', sentiment=(str, Field(default='', description='...')))
agent = Agent('test', output_type=Modified, defer_model_check=True)
# Agent created successfully, schema introspection works
```

pydantic-ai uses `model_json_schema()` internally to build the tool schema sent to the LLM. Dynamic models produce valid JSON schemas identical to static models. No special introspection that would reject dynamically created models.

Path in codebase: `pipeline.py:889-903` -- `instructions_type = step.instructions` passed directly to `build_step_agent(output_type=instructions_type)`. Swapping `instructions_type` with a dynamic model requires zero changes to agent construction.

### 2. model_fields Introspection

`BaseModel.model_fields` returns `dict[str, FieldInfo]` with all needed metadata:

| FieldInfo attr | Contains |
|---|---|
| `annotation` | Python type (e.g., `str`, `float`, `str | None`) |
| `default` | Default value or `PydanticUndefined` |
| `default_factory` | Callable for mutable defaults (e.g., `list`) |
| `description` | Field description string |
| `metadata` | List of constraint objects (`Ge`, `Le`, etc.) |

**Gotcha**: `fi.default` is `PydanticUndefined` (not `None`) when no default is set. Must check `fi.default is not PydanticUndefined` before using it. `None` is a valid default value (e.g., `notes: str | None = None`).

### 3. Field Reconstruction Function

```python
from pydantic import Field
from pydantic.fields import PydanticUndefined

def reconstruct_field(fi):
    """Reconstruct a (annotation, Field(...)) tuple from FieldInfo."""
    kw = {}
    if fi.description:
        kw['description'] = fi.description
    if fi.default is not PydanticUndefined:
        kw['default'] = fi.default
    elif fi.default_factory is not None:
        kw['default_factory'] = fi.default_factory
    for m in fi.metadata:
        for attr in ('ge', 'le', 'gt', 'lt', 'multiple_of', 'min_length', 'max_length', 'pattern'):
            if hasattr(m, attr) and getattr(m, attr) is not None:
                kw[attr] = getattr(m, attr)
    return (fi.annotation, Field(**kw))
```

### 4. Type String Resolution

Whitelist approach (no `eval()`):

```python
SAFE_TYPE_MAP = {
    'str': str,
    'int': int,
    'float': float,
    'bool': bool,
    'list[str]': list[str],
    'list[int]': list[int],
    'list[float]': list[float],
    'str | None': str | None,
    'int | None': int | None,
    'float | None': float | None,
    'bool | None': bool | None,
    'list[str] | None': list[str] | None,
}
```

Covers all practical eval use cases. Rejects arbitrary types (security). Extend map if new types needed.

### 5. Recommended Approach: Flat (No __base__)

Two approaches compared:

| Approach | Add | Remove | Modify | Methods | Validators |
|---|---|---|---|---|---|
| Flat (no `__base__`) | yes | yes | yes | lost | lost |
| `__base__=LLMResultMixin` | yes | **no** | yes (own fields only) | kept | kept (inherited) |

**Flat wins** for eval variants because:
- Full control: can add, remove, AND modify any field
- `__base__` approach **cannot remove inherited fields** (e.g., `confidence_score` from `LLMResultMixin`)
- Lost methods (`create_failure`, `get_example`) are internal helpers not needed during eval runs
- Lost validators acceptable -- evals compare output schema shape, not validation logic

### 6. Thread Safety -- CONFIRMED

`create_model()` is stateless. Each call returns a new independent class. Empirically tested with 20 concurrent creations via `ThreadPoolExecutor(max_workers=8)` -- all produced unique, correct models. Only requirement: unique model names per variant to avoid confusion (use `f"{base_name}_variant_{variant_id}"`).

### 7. apply_instruction_delta() Implementation Sketch

```python
def apply_instruction_delta(
    base_model: type[BaseModel],
    delta: dict,
    variant_id: str,
) -> type[BaseModel]:
    """Apply instruction delta to produce a modified Pydantic model."""
    remove_set = set(delta.get('remove', []))
    modify_map = {m['name']: m for m in delta.get('modify', [])}

    fields = {}
    for name, fi in base_model.model_fields.items():
        if name in remove_set:
            continue
        if name in modify_map:
            mod = modify_map[name]
            ann = SAFE_TYPE_MAP.get(mod.get('type', ''), fi.annotation)
            desc = mod.get('description', fi.description)
            default = mod.get('default', fi.default if fi.default is not PydanticUndefined else '')
            fields[name] = (ann, Field(default=default, description=desc))
        else:
            fields[name] = reconstruct_field(fi)

    for add_field in delta.get('add', []):
        ann = SAFE_TYPE_MAP.get(add_field.get('type', 'str'), str)
        fields[add_field['name']] = (
            ann,
            Field(default=add_field.get('default', ''), description=add_field.get('description', '')),
        )

    return create_model(f"{base_model.__name__}_v{variant_id}", **fields)
```

### 8. Integration Point in Pipeline

In `pipeline.py` line 889:
```python
instructions_type = step.instructions
```

For eval variant runs, insert delta application here:
```python
instructions_type = step.instructions
if variant and variant.instruction_deltas.get(step.step_name):
    instructions_type = apply_instruction_delta(
        instructions_type,
        variant.instruction_deltas[step.step_name],
        variant.id,
    )
```

No changes needed to `build_step_agent()`, `StepDefinition`, or `LLMStep` -- the dynamic model flows through the existing `output_type` parameter transparently.

## Edge Cases & Limitations

1. **ClassVar `example`**: Lost in flat approach. Not needed for eval runs (only used in `__init_subclass__` validation of static instruction classes).
2. **Nested Pydantic models** (e.g., `topics: list[TopicItem]`): Type string map cannot express these. If needed, preserve original field annotation unchanged (don't allow type changes on complex fields).
3. **Required fields** (no default): If delta adds a field without a default and the LLM omits it, pydantic-ai will retry. Safe behavior.
4. **model_validator / field_validator**: Lost in flat approach. If a production model has critical validators, could carry them via `__validators__` kwarg to `create_model()`. Not recommended for eval use case.
