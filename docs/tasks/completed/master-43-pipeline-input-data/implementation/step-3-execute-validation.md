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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] _validated_input stored on pipeline but not exposed to steps -- added public `validated_input` property
[x] No unit tests for execute() input_data validation -- added 12 tests in 2 new test classes

### Changes Made
#### File: `llm_pipeline/pipeline.py`
Added `_validated_input = None` init in `__init__()` and public `validated_input` property.

```
# Before (__init__, after self._context init)
        # Execution tracking

# After
        # Validated input (populated by execute() when INPUT_DATA declared)
        self._validated_input = None

        # Execution tracking
```

```
# Before (after context property)
    @property
    def pipeline_name(self) -> str:

# After
    @property
    def validated_input(self) -> Any:
        """Validated input data from execute(input_data=...). Returns PipelineInputData instance if INPUT_DATA declared, raw dict otherwise, None if not provided."""
        return self._validated_input

    @property
    def pipeline_name(self) -> str:
```

#### File: `tests/test_pipeline_input_data.py`
Added imports, test infrastructure (MockProvider, EmptyStrategy, two pipeline classes with matching registry/strategies), and two test classes:

- `TestExecuteInputDataValidation` (8 tests): raises on None input, raises on empty dict, valid input succeeds, schema mismatch error, missing required field error, error includes pipeline name, no-schema pipeline skips validation, no-schema pipeline stores raw dict
- `TestValidatedInputProperty` (4 tests): returns PydanticModel after execute, returns None before execute, returns None when no schema and no input, returns raw dict when no schema

### Verification
[x] All 35 tests in test_pipeline_input_data.py pass
[x] Full test suite: 803 passed, 1 pre-existing failure (unrelated test_ui.py events router prefix)
[x] validated_input property accessible on pipeline instance before and after execute()
[x] _validated_input initialized in __init__ prevents AttributeError before execute()
[x] Syntax check passes
