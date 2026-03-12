# IMPLEMENTATION - STEP 5: DELETE CREATE_LLM_CALL
**Status:** completed

## Summary
Deleted create_llm_call() method from LLMStep and ExecuteLLMStepParams class from types.py. Cleaned up associated imports and docstrings.

## Files
**Created:** none
**Modified:** llm_pipeline/step.py, llm_pipeline/types.py
**Deleted:** none

## Changes
### File: `llm_pipeline/step.py`
Removed `import warnings` (only used by create_llm_call deprecation), removed `ExecuteLLMStepParams` from TYPE_CHECKING block, deleted entire create_llm_call() method (lines 317-359).
```
# Before
import warnings
...
if TYPE_CHECKING:
    from llm_pipeline.types import ExecuteLLMStepParams
...
    def create_llm_call(self, variables, ...) -> 'ExecuteLLMStepParams':
        ...  # 42-line method

# After
# No warnings import, no ExecuteLLMStepParams import, no create_llm_call method
```

### File: `llm_pipeline/types.py`
Deleted ExecuteLLMStepParams class (lines 74-89), removed from __all__, removed now-unused `Type` and `BaseModel` imports, cleaned up StepCallParams docstring that referenced create_llm_call().
```
# Before
from typing import Any, Dict, List, Optional, Type, TypedDict
from pydantic import BaseModel
...
class ExecuteLLMStepParams(StepCallParams): ...
__all__ = [..., "ExecuteLLMStepParams"]

# After
from typing import Any, Dict, List, Optional, TypedDict
# No BaseModel import, no ExecuteLLMStepParams class
__all__ = ["ArrayValidationConfig", "ValidationContext", "StepCallParams"]
```

## Decisions
### Unused import cleanup
**Choice:** Removed `Type`, `BaseModel` imports from types.py and `warnings` from step.py
**Rationale:** Only consumers were deleted code; leaving them would cause linter warnings

### StepCallParams docstring cleanup
**Choice:** Removed reference to create_llm_call() from StepCallParams docstring
**Rationale:** Stale documentation referencing deleted method

## Verification
[x] create_llm_call() method absent from LLMStep class
[x] ExecuteLLMStepParams absent from types.py
[x] ExecuteLLMStepParams absent from types.py __all__
[x] No unused imports remain in modified files
[x] pipeline.py call site (line 730) is outside Step 5 scope, handled by Steps 3-4
[x] Test file references (14 files) outside Step 5 scope, handled by Steps 7-9
