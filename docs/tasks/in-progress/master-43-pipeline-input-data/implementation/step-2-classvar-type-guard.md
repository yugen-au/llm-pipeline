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
