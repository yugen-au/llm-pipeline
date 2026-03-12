# IMPLEMENTATION - STEP 2: DELETE LLM/ DIR AND DEAD CODE
**Status:** completed

## Summary
Deleted vestigial `llm_pipeline/llm/__init__.py` and removed the dead `_query_prompt_keys()` function from `step.py`, along with the now-unused `Tuple` import.

## Files
**Created:** none
**Modified:** llm_pipeline/step.py
**Deleted:** llm_pipeline/llm/__init__.py

## Changes
### File: `llm_pipeline/llm/__init__.py`
Deleted entirely via `git rm`. Was a single-line stub comment. `__pycache__/` remains (gitignored, not tracked).

### File: `llm_pipeline/step.py`
Removed `Tuple` from typing import (line 12) and deleted `_query_prompt_keys()` function (lines 34-77).

```
# Before (line 12)
from typing import Any, List, Dict, TYPE_CHECKING, Type, Optional, ClassVar, Tuple

# After (line 12)
from typing import Any, List, Dict, TYPE_CHECKING, Type, Optional, ClassVar
```

```
# Before (lines 34-77)
def _query_prompt_keys(
    step_name: str,
    session: Any,
    strategy_name: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    ...  # 44 lines of dead code

# After
(removed entirely -- step_definition() now starts at line 34)
```

## Decisions
### Keep Optional import
**Choice:** Retained `Optional` in the typing import.
**Rationale:** `Optional` is used in 8+ locations throughout `step_definition()` and `LLMStep.build_user_prompt()` signatures.

### No __pycache__ cleanup
**Choice:** Did not manually delete `llm_pipeline/llm/__pycache__/`.
**Rationale:** Directory is gitignored, not tracked. `git rm` only removes tracked files.

## Verification
[x] `Tuple` has zero remaining usages in step.py after removal
[x] `Optional` is still used in 8+ locations in step.py (lines 36-38, 40, 96-98, 250)
[x] `_query_prompt_keys()` function fully removed
[x] `llm_pipeline/llm/__init__.py` removed from git tracking
[x] `step_definition()` decorator intact and starts at correct position
