# IMPLEMENTATION - STEP 2: CLASSVAR TYPE GUARD
**Status:** completed

## Summary
Added INPUT_DATA ClassVar to PipelineConfig and extended __init_subclass__ to validate INPUT_DATA is a PipelineInputData subclass at class-definition time.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Added import for PipelineInputData, INPUT_DATA ClassVar declaration, and type guard in __init_subclass__.

```
# Before (imports, L29-31)
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import SQLModel, Session

# After (imports, L29-33)
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import SQLModel, Session

from llm_pipeline.context import PipelineInputData
```

```
# Before (ClassVars, L105-106)
    REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
    STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None

# After (ClassVars, L107-109)
    REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
    STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None
    INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None
```

```
# Before (__init_subclass__ end, L134-137)
        if registry is not None:
            cls.REGISTRY = registry
        if strategies is not None:
            cls.STRATEGIES = strategies

# After (__init_subclass__ end, L137-148)
        if registry is not None:
            cls.REGISTRY = registry
        if strategies is not None:
            cls.STRATEGIES = strategies

        if cls.INPUT_DATA is not None and not (
            isinstance(cls.INPUT_DATA, type) and issubclass(cls.INPUT_DATA, PipelineInputData)
        ):
            raise TypeError(
                f"{cls.__name__}.INPUT_DATA must be a PipelineInputData subclass, "
                f"got {cls.INPUT_DATA!r}"
            )
```

## Decisions
### Type guard error message format
**Choice:** Include class name and repr of invalid INPUT_DATA value
**Rationale:** Matches existing __init_subclass__ error patterns in this file; repr gives useful debug info for non-type values

### Guard placement
**Choice:** After strategies assignment, before __init__ method
**Rationale:** INPUT_DATA is independent of registry/strategies validation; placing after ensures all ClassVar assignments complete before type check runs

## Verification
[x] INPUT_DATA ClassVar declared with correct type annotation Optional[Type["PipelineInputData"]]
[x] Default value is None (existing pipelines unaffected)
[x] Import added at module level (not TYPE_CHECKING - needed at runtime for issubclass)
[x] isinstance(cls.INPUT_DATA, type) check prevents issubclass crash on non-type values
[x] TypeError raised (not ValueError) matching Python convention for type mismatches
[x] Error message includes cls.__name__ for debuggability

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] No unit tests for INPUT_DATA type guard behavior (medium, Step 2 portion)

### Changes Made
#### File: `tests/test_pipeline_input_data.py`
Added TestInputDataTypeGuard class (9 tests) covering all type guard paths:

```python
# Before
# (no type guard tests -- only base class and subclassing tests from Step 1)

# After
class TestInputDataTypeGuard:
    test_valid_input_data_subclass        # valid PipelineInputData subclass succeeds
    test_default_none_succeeds            # no INPUT_DATA (default None) succeeds
    test_explicit_none_succeeds           # INPUT_DATA=None explicitly succeeds
    test_bare_base_class_succeeds         # PipelineInputData itself accepted
    test_invalid_str_raises_type_error    # str rejected with TypeError
    test_invalid_int_raises_type_error    # int rejected with TypeError
    test_invalid_plain_basemodel_raises   # plain BaseModel (not PipelineInputData) rejected
    test_invalid_instance_raises          # instance (not class) rejected
    test_error_message_includes_class_name # TypeError message has pipeline class name
```

### Verification
[x] All 23 tests pass (14 existing + 9 new)
[x] Valid INPUT_DATA (subclass) case covered
[x] Invalid INPUT_DATA (str, int, plain BaseModel, instance) cases covered
[x] Default None case covered
[x] Explicit None case covered
[x] TypeError message includes class name verified
