# IMPLEMENTATION - STEP 6: UPDATE EXPORTS
**Status:** completed

## Summary
Added imports and __all__ entries for not_found_validator, array_length_validator, and DEFAULT_NOT_FOUND_INDICATORS from llm_pipeline.validators to llm_pipeline/__init__.py. Verified ArrayValidationConfig and ValidationContext remain exported.

## Files
**Created:** none
**Modified:** llm_pipeline/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/__init__.py`
Added import line and three __all__ entries for validator public symbols.

```
# Before (line 35 did not exist)
from llm_pipeline.agent_builders import StepDeps, build_step_agent

# After
from llm_pipeline.agent_builders import StepDeps, build_step_agent
from llm_pipeline.validators import not_found_validator, array_length_validator, DEFAULT_NOT_FOUND_INDICATORS
```

```
# Before (__all__ ended with)
    "StepDeps",
    "build_step_agent",
]

# After
    "StepDeps",
    "build_step_agent",
    # Validators
    "not_found_validator",
    "array_length_validator",
    "DEFAULT_NOT_FOUND_INDICATORS",
]
```

## Decisions
None

## Verification
[x] Import statement added for all three symbols from llm_pipeline.validators
[x] __all__ updated with all three symbol strings
[x] ArrayValidationConfig remains exported (line 29 import, line 69 __all__)
[x] ValidationContext remains exported (line 29 import, line 70 __all__)
[x] python -c import test passes successfully
[x] No existing exports removed
