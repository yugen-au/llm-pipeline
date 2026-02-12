# IMPLEMENTATION - STEP 1: ADD HELPER METHODS
**Status:** completed

## Summary
Added 6 helper methods to LLMCallResult dataclass: to_dict(), to_json(), is_success/is_failure properties, success()/failure() factory classmethods.

## Files
**Created:** none
**Modified:** llm_pipeline/llm/result.py
**Deleted:** none

## Changes
### File: `llm_pipeline/llm/result.py`
Added imports (json, asdict) and 6 methods to the existing frozen dataclass.

```python
# Before
from dataclasses import dataclass, field
# ... 5 fields only, no methods

# After
import json
from dataclasses import asdict, dataclass, field
# ... 5 fields + 6 methods:
# to_dict() -> dict[str, Any]: returns asdict(self)
# to_json() -> str: returns json.dumps(self.to_dict())
# @property is_success -> bool: self.parsed is not None
# @property is_failure -> bool: self.parsed is None
# @classmethod success(...): enforces parsed not None, defaults validation_errors=[]
# @classmethod failure(...): parsed=None default, accepts empty validation_errors
```

## Decisions
### Docstring style
**Choice:** Matched PipelineEvent section-comment + short-docstring pattern
**Rationale:** Consistency with events/types.py (section headers like `# -- Serialization --`, concise docstrings)

### failure() parsed parameter typing
**Choice:** `parsed: None = None` (typed as None with default None)
**Rationale:** Makes it impossible to pass non-None parsed to failure() at type-check level, enforces invariant without runtime check

### success() ValueError guard
**Choice:** Runtime check `if parsed is None: raise ValueError`
**Rationale:** Type hint alone (`dict[str, Any]`) doesn't prevent None at runtime; explicit guard matches factory pattern expectations

## Verification
[x] to_dict() returns dict with all 5 fields
[x] to_json() returns valid JSON string matching to_dict()
[x] is_success True when parsed is not None, False otherwise
[x] is_failure True when parsed is None, False otherwise
[x] success() factory enforces parsed not None (ValueError on None)
[x] failure() factory accepts empty validation_errors (timeout/network case)
[x] Partial success (parsed + validation_errors) counts as is_success=True
[x] All 32 existing tests still pass
[x] Import smoke test passes

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] `failure()` factory does not guard against non-None `parsed` at runtime (LOW, Step 1)

### Changes Made
#### File: `llm_pipeline/llm/result.py`
Added symmetric runtime ValueError guard to failure() classmethod.

```python
# Before
        """Create a failed result with no parsed output.

        An empty validation_errors list is valid for timeout or network
        failures where no validation was attempted.
        """
        return cls(

# After
        """Create a failed result with no parsed output.

        An empty validation_errors list is valid for timeout or network
        failures where no validation was attempted.

        Raises:
            ValueError: If parsed is not None.
        """
        if parsed is not None:
            raise ValueError("parsed must be None for a failure result")
        return cls(
```

### Verification
[x] failure() with parsed=None works normally
[x] failure() with parsed=non-None raises ValueError
[x] success() guard unchanged and still works
[x] All 50 tests pass (no regressions)
