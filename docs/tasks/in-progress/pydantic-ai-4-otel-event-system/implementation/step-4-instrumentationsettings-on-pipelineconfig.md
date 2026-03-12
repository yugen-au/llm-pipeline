# IMPLEMENTATION - STEP 4: INSTRUMENTATION_SETTINGS ON PIPELINECONFIG
**Status:** completed

## Summary
Added `instrumentation_settings` parameter to `PipelineConfig.__init__` and threaded it to `build_step_agent()` as `instrument=`. Added TYPE_CHECKING import for `InstrumentationSettings`.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

Added TYPE_CHECKING import for InstrumentationSettings:
```python
# Before
if TYPE_CHECKING:
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies

# After
if TYPE_CHECKING:
    from pydantic_ai import InstrumentationSettings
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
```

Added `instrumentation_settings` parameter to `__init__`:
```python
# Before
def __init__(self, model, ..., run_id=None):

# After
def __init__(self, model, ..., run_id=None, instrumentation_settings: Any | None = None):
```

Stored as private attribute:
```python
# After
self._instrumentation_settings = instrumentation_settings
```

Threaded to `build_step_agent()` call (only call site in pipeline.py):
```python
# Before
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
    validators=step_validators,
)

# After
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
    validators=step_validators,
    instrument=self._instrumentation_settings,
)
```

## Decisions
### Parameter typing as Any
**Choice:** `instrumentation_settings: Any | None = None` instead of `"InstrumentationSettings" | None`
**Rationale:** Matches plan spec. Avoids runtime import of pydantic_ai.InstrumentationSettings; TYPE_CHECKING import provides IDE support. Consistent with existing pattern (e.g. `model_settings: Any | None`).

## Verification
[x] TYPE_CHECKING import for InstrumentationSettings added
[x] Parameter added to __init__ signature with docstring
[x] Stored as self._instrumentation_settings
[x] Threaded to all build_step_agent() calls (1 call site confirmed via grep)
[x] No other call sites for build_step_agent in pipeline.py
[x] Parameter is optional with None default -- backward compatible
