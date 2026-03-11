# Step 3: Code Examples Validation

## Scope
Validate Task 57's proposed README code examples against actual codebase.

---

## Example 1: Event System Usage

### Proposed Code
```python
from llm_pipeline import PipelineConfig
from llm_pipeline.events import InMemoryEventHandler, CompositeEmitter

handler = InMemoryEventHandler()
pipeline = MyPipeline(event_emitter=handler, provider=provider)
pipeline.execute(data, context)

for event in handler.get_events(pipeline.run_id):
    print(f'{event.event_type}: {event.timestamp}')
```

### Validation Results

| Element | Status | Notes |
|---------|--------|-------|
| `from llm_pipeline import PipelineConfig` | VALID | Exported from `__init__.py:19` |
| `from llm_pipeline.events import InMemoryEventHandler, CompositeEmitter` | VALID | Both in `events/__init__.py:76-79` |
| `InMemoryEventHandler()` | VALID | No-arg constructor (`handlers.py:102`) |
| `MyPipeline(event_emitter=handler, provider=provider)` | VALID | `PipelineConfig.__init__` accepts `event_emitter` (`pipeline.py:157`) |
| `pipeline.execute(data, context)` | INACCURATE | Second param is `initial_context`, not `context`. Works positionally but misleading |
| `pipeline.run_id` | VALID | Set in `__init__` (`pipeline.py:215`) |
| `handler.get_events(pipeline.run_id)` return type | BUG | Returns `list[dict]`, NOT `PipelineEvent` objects |
| `event.event_type` / `event.timestamp` | BUG | Dict access needed: `event['event_type']`, `event['timestamp']` |

### Issues Found

**Issue 1 (MEDIUM): `get_events` returns dicts, not event objects**
- `InMemoryEventHandler.emit()` calls `event.to_dict()` before storing (`handlers.py:109`)
- `get_events()` returns `list[dict]` (`handlers.py:111`)
- Task example uses dot notation (`event.event_type`) which would raise `AttributeError`
- Fix: use `event['event_type']` and `event['timestamp']`

**Issue 2 (LOW): execute() parameter name**
- Actual signature: `execute(data=None, initial_context=None, input_data=None, use_cache=False, consensus_polling=None)`
- Task shows: `pipeline.execute(data, context)` - positionally works but `context` is not the param name
- Fix: `pipeline.execute(data, initial_context={})` or just `pipeline.execute(data)`

### Corrected Example
```python
from llm_pipeline import PipelineConfig
from llm_pipeline.events import InMemoryEventHandler, CompositeEmitter

handler = InMemoryEventHandler()
pipeline = MyPipeline(event_emitter=handler, provider=provider)
pipeline.execute(data)

for event in handler.get_events(pipeline.run_id):
    print(f"{event['event_type']}: {event['timestamp']}")
```

---

## Example 2: UI Usage

### Proposed Code
```bash
pip install llm-pipeline[ui]
llm-pipeline ui
llm-pipeline ui --dev --port 8642
```

### Validation Results

| Element | Status | Notes |
|---------|--------|-------|
| `pip install llm-pipeline[ui]` | VALID | Optional dep in `pyproject.toml:24` - fastapi, uvicorn, python-multipart |
| `llm-pipeline ui` | VALID | Entry point `pyproject.toml:20`, subcommand in `cli.py:18` |
| `--dev` flag | VALID | `cli.py:19-21` |
| `--port` flag | VALID | `cli.py:22-24`, default 8642 |
| `--db` flag (not shown) | EXISTS | `cli.py:25-27` - optional SQLite path, worth mentioning |

### Additional CLI info (for completeness)
- `llm-pipeline ui --db /path/to/pipeline.db` - connect to specific DB
- Dev mode starts Vite + FastAPI if frontend dir exists, otherwise uvicorn reload-only
- Prod mode serves `frontend/dist/` as static files if present

### No corrections needed for this example.

---

## Example 3: LLMCallResult Changes

### Proposed Code
```python
# Before (0.1.x)
result_dict = provider.call_structured(...)

# After (0.2.x)
result = provider.call_structured(...)
print(result.parsed)             # Same as before
print(result.raw_response)       # NEW: original text
print(result.model_name)         # NEW: model used
print(result.validation_errors)  # NEW: any errors
```

### Validation Results (from `llm_pipeline/llm/result.py`)

| Attribute | Status | Type | Default |
|-----------|--------|------|---------|
| `.parsed` | VALID | `dict[str, Any] \| None` | `None` |
| `.raw_response` | VALID | `str \| None` | `None` |
| `.model_name` | VALID | `str \| None` | `None` |
| `.validation_errors` | VALID | `list[str]` | `[]` |
| `.attempt_count` | NOT SHOWN | `int` | `1` |

### Additional API not shown in task example
- `result.is_success` - property, `True` when `parsed is not None`
- `result.is_failure` - property, `True` when `parsed is None`
- `result.to_dict()` - serialize to dict
- `result.to_json()` - serialize to JSON string
- `LLMCallResult.success(parsed, raw_response, model_name, ...)` - factory
- `LLMCallResult.failure(raw_response, model_name, attempt_count, validation_errors)` - factory
- Class is `@dataclass(frozen=True, slots=True)` - immutable

### No corrections needed for the attributes shown. Consider mentioning `attempt_count` and `is_success`/`is_failure` for completeness.

---

## Import Path Summary

All referenced imports verified against actual `__init__.py` and `events/__init__.py`:

| Import | Location | Valid |
|--------|----------|-------|
| `llm_pipeline.PipelineConfig` | `__init__.py:19` | Yes |
| `llm_pipeline.events.InMemoryEventHandler` | `events/__init__.py:78` | Yes |
| `llm_pipeline.events.CompositeEmitter` | `events/__init__.py:75` | Yes |
| `llm_pipeline.LLMCallResult` | `__init__.py:31` | Yes |
| `llm_pipeline.events.LLMCallResult` | `events/__init__.py:83` | Yes |
| `llm_pipeline.PipelineEventEmitter` | `__init__.py:29` | Yes |
| `llm_pipeline.InMemoryEventHandler` | `__init__.py:30` | Yes |

Note: `InMemoryEventHandler` and `CompositeEmitter` are available from BOTH `llm_pipeline` (top-level) and `llm_pipeline.events`. Task example imports from `llm_pipeline.events` which is valid and arguably more explicit.

---

## Summary of Required Corrections

1. **MUST FIX**: Event handler example uses dot notation on dicts - change to bracket notation
2. **SHOULD FIX**: `execute(data, context)` -> `execute(data)` or `execute(data, initial_context={})`
3. **NICE TO HAVE**: Mention `attempt_count`, `is_success`/`is_failure` on LLMCallResult
4. **NICE TO HAVE**: Mention `--db` CLI flag
