# IMPLEMENTATION - STEP 3: EXECUTE VALIDATION
**Status:** completed

## Summary
Added `input_data` parameter to `PipelineConfig.execute()` with validation against `INPUT_DATA` schema. Validation occurs before PipelineRun record creation, raising ValueError on missing/invalid input when INPUT_DATA is declared.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Added `ValidationError` import, `input_data` param to execute(), and validation block.

```
# Before (L29)
from pydantic import BaseModel

# After
from pydantic import BaseModel, ValidationError
```

```
# Before (execute signature)
def execute(
    self,
    data: Any = None,
    initial_context: Optional[Dict[str, Any]] = None,
    use_cache: bool = False,
    consensus_polling: Optional[Dict[str, Any]] = None,
) -> "PipelineConfig":

# After
def execute(
    self,
    data: Any = None,
    initial_context: Optional[Dict[str, Any]] = None,
    input_data: Optional[Dict[str, Any]] = None,
    use_cache: bool = False,
    consensus_polling: Optional[Dict[str, Any]] = None,
) -> "PipelineConfig":
```

```
# Before (after consensus config block, L475)
        self._context = initial_context.copy()

# After (validation block inserted before self._context assignment)
        # Validate input_data against INPUT_DATA schema if declared
        cls = self.__class__
        self._validated_input = None
        if cls.INPUT_DATA is not None:
            if input_data is None or not input_data:
                raise ValueError(
                    f"Pipeline '{self.pipeline_name}' requires input_data "
                    f"matching {cls.INPUT_DATA.__name__} schema but none provided"
                )
            try:
                self._validated_input = cls.INPUT_DATA.model_validate(input_data)
            except ValidationError as e:
                raise ValueError(
                    f"Pipeline '{self.pipeline_name}' input_data validation failed: {e}"
                ) from e
        elif input_data is not None:
            self._validated_input = input_data

        self._context = initial_context.copy()
```

## Decisions
### ValidationError re-raise as ValueError
**Choice:** Catch pydantic ValidationError and re-raise as ValueError with pipeline name context
**Rationale:** Consistent with existing execute() error pattern (all raises are ValueError). Adds pipeline name for debugging multi-pipeline systems. Chains original exception via `from e`.

### Store unvalidated input_data when no INPUT_DATA declared
**Choice:** `elif input_data is not None: self._validated_input = input_data` (raw dict)
**Rationale:** Pipelines without INPUT_DATA schema can still receive input_data for future use without validation. Prevents data loss while maintaining backward compat.

### Falsy check for empty dict
**Choice:** `if input_data is None or not input_data` catches both None and empty {}
**Rationale:** Plan specifies "None or empty" should raise. An empty dict {} is semantically equivalent to no input for schema validation purposes.

## Verification
[x] input_data param added after initial_context in execute() signature
[x] Validation block placed after consensus config parsing, before self._context assignment
[x] Validation occurs before PipelineRun record creation (L501)
[x] ValueError raised when INPUT_DATA declared but input_data missing/empty
[x] ValidationError caught and re-raised as ValueError with pipeline name
[x] _validated_input stores validated model instance (or raw dict if no schema)
[x] Syntax check passes (ast.parse)
[x] Backward compatible -- input_data defaults to None, existing calls unaffected
