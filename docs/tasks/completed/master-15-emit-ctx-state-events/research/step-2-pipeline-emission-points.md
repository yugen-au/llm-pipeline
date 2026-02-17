# Step 2: Pipeline Emission Points for Context & State Events

## Overview

Maps exact code locations in `pipeline.py` where 4 new events (InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved) should be emitted. All event models already defined in `events/types.py` (L423-538).

## Import Addition Required

**File:** `llm_pipeline/pipeline.py` L35-42

Current import block does NOT include the 4 new event types. Add to the existing import:

```python
from llm_pipeline.events.types import (
    # ... existing imports ...
    InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved,
)
```

---

## Emission Point 1: InstructionsStored

**Event model** (types.py L426-432):
```python
class InstructionsStored(StepScopedEvent):
    EVENT_CATEGORY = CATEGORY_INSTRUCTIONS_CONTEXT
    instruction_count: int
```

**Emission locations:** 2 (cached path + fresh path)

### Location 1A: Cached Path - Line 573

```python
# L572-575 (cached path)
instructions = self._load_from_cache(cached_state, step)
self._instructions[step.step_name] = instructions  # <-- L573
new_context = step.process_instructions(instructions)
self._validate_and_merge_context(step, new_context)
```

Emit **immediately after L573** (`self._instructions[step.step_name] = instructions`):

```python
if self._event_emitter:
    self._emit(InstructionsStored(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        instruction_count=len(instructions),
    ))
```

**Data available:** `self.run_id`, `self.pipeline_name`, `step.step_name`, `len(instructions)` (instructions is a list from `_load_from_cache`)

### Location 1B: Fresh Path - Line 669

```python
# L667-671 (fresh path)
                    instructions.append(instruction)

                self._instructions[step.step_name] = instructions  # <-- L669
                new_context = step.process_instructions(instructions)
                self._validate_and_merge_context(step, new_context)
```

Emit **immediately after L669** (`self._instructions[step.step_name] = instructions`):

```python
if self._event_emitter:
    self._emit(InstructionsStored(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        instruction_count=len(instructions),
    ))
```

**Data available:** Same as 1A. `instructions` is a list built from LLM call results.

---

## Emission Point 2: InstructionsLogged

**Event model** (types.py L435-445):
```python
class InstructionsLogged(StepScopedEvent):
    EVENT_CATEGORY = CATEGORY_INSTRUCTIONS_CONTEXT
    logged_keys: list[str] = field(default_factory=list)
```

**Emission locations:** 2 (cached path + fresh path)

### Location 2A: Cached Path - Line 603

```python
# L603 (cached path, after extraction reconstruction)
step.log_instructions(instructions)
```

Emit **immediately after L603**:

```python
if self._event_emitter:
    self._emit(InstructionsLogged(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        logged_keys=[k for k in (step.system_instruction_key, step.user_prompt_key) if k is not None],
    ))
```

### Location 2B: Fresh Path - Line 707

```python
# L707 (fresh path, after _save_step_state)
step.log_instructions(instructions)
```

Emit **immediately after L707**:

```python
if self._event_emitter:
    self._emit(InstructionsLogged(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        logged_keys=[k for k in (step.system_instruction_key, step.user_prompt_key) if k is not None],
    ))
```

**Data available:** `step.system_instruction_key` (str|None), `step.user_prompt_key` (str|None). These are the prompt keys associated with the step's instructions that were just logged.

**logged_keys rationale:** `log_instructions()` is a no-op by default (step.py L317-319). Subclasses override to log custom info. The "logged keys" most naturally map to the prompt keys used for this step, since those identify which instructions were logged.

---

## Emission Point 3: ContextUpdated

**Event model** (types.py L448-459):
```python
class ContextUpdated(StepScopedEvent):
    EVENT_CATEGORY = CATEGORY_INSTRUCTIONS_CONTEXT
    new_keys: list[str]
    context_snapshot: dict[str, Any]
```

**Emission location:** 1 (inside `_validate_and_merge_context`, called from both paths)

### Location: _validate_and_merge_context() - After Line 372

```python
# L350-372
def _validate_and_merge_context(self, step, new_context: Any) -> None:
    from llm_pipeline.context import PipelineContext

    if hasattr(step, "_context") and step._context:
        context_class = step._context
        if not isinstance(new_context, context_class):
            raise TypeError(...)
        if isinstance(new_context, PipelineContext):
            new_context = new_context.model_dump()

    if new_context is None:
        new_context = {}
    elif isinstance(new_context, dict):
        pass
    else:
        raise TypeError(...)
    self._context.update(new_context)  # <-- L372
```

Emit **immediately after L372** (`self._context.update(new_context)`), only when new_context is non-empty:

```python
if new_context and self._event_emitter:
    self._emit(ContextUpdated(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        new_keys=list(new_context.keys()),
        context_snapshot=dict(self._context),
    ))
```

**Data available at this point:**
- `self.run_id`, `self.pipeline_name` - always available
- `step.step_name` - `step` param is the LLMStep instance with `.step_name` property
- `new_context.keys()` - after coercion to dict (L361/L363-366), always a dict
- `dict(self._context)` - shallow copy of full context AFTER merge (task requires "full context_snapshot for UI diff display")

**Called from:**
- Cached path L575: `self._validate_and_merge_context(step, new_context)`
- Fresh path L671: `self._validate_and_merge_context(step, new_context)`

**Guard note:** `new_context and self._event_emitter` - checks non-empty first (avoids event creation for no-op merges), then checks emitter exists (zero-overhead pattern).

**Snapshot note:** `dict(self._context)` creates a shallow copy. Project convention (types.py L6-7, L452-453) states mutable containers must not be mutated after creation. Shallow copy is consistent with existing pattern (e.g., LLMCallCompleted.parsed_result uses dict directly).

---

## Emission Point 4: StateSaved

**Event model** (types.py L530-538):
```python
class StateSaved(StepScopedEvent):
    EVENT_CATEGORY = CATEGORY_STATE
    step_number: int
    input_hash: str
    execution_time_ms: float
```

**Emission location:** 1 (inside `_save_step_state`, fresh path only)

### Location: _save_step_state() - After Line 910

```python
# L868-910
def _save_step_state(self, step, step_number, instructions, input_hash, execution_time_ms=None, model_name=None):
    from llm_pipeline.state import PipelineStepState
    from llm_pipeline.db.prompt import Prompt
    from sqlmodel import select

    serialized = [...]  # L873-882
    context_snapshot = {step.step_name: serialized}  # L884
    # ... prompt version lookup L885-893

    state = PipelineStepState(
        pipeline_name=self.pipeline_name,
        run_id=self.run_id,
        step_name=step.step_name,
        step_number=step_number,
        input_hash=input_hash,
        result_data=serialized,
        context_snapshot=context_snapshot,
        prompt_system_key=prompt_system_key,
        prompt_user_key=prompt_user_key,
        prompt_version=prompt_version,
        execution_time_ms=execution_time_ms,
        model=model_name,
    )  # L895-908
    self._real_session.add(state)  # L909
    self._real_session.flush()     # L910
```

Emit **immediately after L910** (`self._real_session.flush()`):

```python
if self._event_emitter:
    self._emit(StateSaved(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        step_number=step_number,
        input_hash=input_hash,
        execution_time_ms=float(execution_time_ms) if execution_time_ms is not None else 0.0,
    ))
```

**Data available:** All from method params:
- `step.step_name` - step instance
- `step_number` - int param
- `input_hash` - str param
- `execution_time_ms` - param (int|None, from L700-701 `int(...)`)

**Type note:** `execution_time_ms` in method param is `int` (cast at L700-701). StateSaved event field is `float`. Cast with `float()` for type safety. Handle `None` default param with `0.0`.

**Called from:** Fresh path only (L704-706):
```python
self._save_step_state(
    step, step_num, instructions, input_hash, execution_time_ms, model_name
)
```

---

## Summary Table

| Event | Location(s) | Line(s) | Path | Guard Pattern |
|-------|------------|---------|------|---------------|
| InstructionsStored | After `self._instructions[step.step_name] = instructions` | L573, L669 | Both | `if self._event_emitter:` |
| InstructionsLogged | After `step.log_instructions(instructions)` | L603, L707 | Both | `if self._event_emitter:` |
| ContextUpdated | After `self._context.update(new_context)` in `_validate_and_merge_context` | L372 | Both (via method call) | `if new_context and self._event_emitter:` |
| StateSaved | After `self._real_session.flush()` in `_save_step_state` | L910 | Fresh only | `if self._event_emitter:` |

## Total Code Changes

- **Import block** (L35-42): Add 4 event types
- **execute() cached path**: +2 emission blocks (InstructionsStored after L573, InstructionsLogged after L603)
- **execute() fresh path**: +2 emission blocks (InstructionsStored after L669, InstructionsLogged after L707)
- **_validate_and_merge_context()**: +1 emission block after L372
- **_save_step_state()**: +1 emission block after L910

**Estimated lines added:** ~36 (6 emission blocks x ~6 lines each)
