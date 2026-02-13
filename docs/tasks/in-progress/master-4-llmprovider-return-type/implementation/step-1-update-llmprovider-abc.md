# IMPLEMENTATION - STEP 1: UPDATE LLMPROVIDER ABC
**Status:** completed

## Summary
Changed LLMProvider.call_structured() return type from Optional[Dict[str, Any]] to LLMCallResult. Removed unused Dict import. Updated docstring return description.

## Files
**Created:** none
**Modified:** llm_pipeline/llm/provider.py
**Deleted:** none

## Changes
### File: `llm_pipeline/llm/provider.py`
Changed return type annotation, added LLMCallResult import, removed unused Dict import, updated docstring.

```
# Before
from typing import Any, Dict, List, Optional, Type
# ...
) -> Optional[Dict[str, Any]]:
    """
    ...
    Returns:
        Validated JSON response dict, or None if all retries failed
    """

# After
from typing import Any, List, Optional, Type
from llm_pipeline.llm.result import LLMCallResult
# ...
) -> LLMCallResult:
    """
    ...
    Returns:
        LLMCallResult containing parsed output, raw response, model
        metadata, attempt count, and any validation errors.
    """
```

## Decisions
### Keep Optional/Any/List/Type imports
**Choice:** Only removed Dict from typing imports
**Rationale:** Optional, Any, List, Type still used in parameter annotations (not_found_indicators, array_validation, validation_context, result_class)

## Verification
[x] Import resolves: `python -c "from llm_pipeline.llm.provider import LLMProvider"` succeeds
[x] Dict import removed (no longer used in file)
[x] Optional/Any/List/Type imports retained (still used in parameters)
[x] Docstring updated to describe LLMCallResult return
[x] No syntax errors
