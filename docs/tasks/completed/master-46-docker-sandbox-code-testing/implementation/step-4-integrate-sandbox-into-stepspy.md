# IMPLEMENTATION - STEP 4: INTEGRATE SANDBOX INTO STEPS.PY
**Status:** completed

## Summary
Integrated StepSandbox and SampleDataGenerator into CodeValidationStep.process_instructions() with lazy import guard and graceful degradation.

## Files
**Created:** none
**Modified:** llm_pipeline/creator/steps.py
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/steps.py`
Added lazy import guard at module top, consolidated FieldDefinition import, and extended CodeValidationStep.process_instructions() with sandbox integration.

```
# Before (imports)
from .models import GenerationRecord
from .schemas import (...)
from .templates import render_template

# After (imports)
from .models import FieldDefinition, GenerationRecord
from .schemas import (...)
from .templates import render_template

try:
    from .sandbox import StepSandbox
    from .sample_data import SampleDataGenerator
    _SANDBOX_AVAILABLE = True
except ImportError:
    _SANDBOX_AVAILABLE = False
```

```
# Before (process_instructions return)
is_valid = syntax_valid and inst.is_valid
return CodeValidationContext(
    is_valid=is_valid, syntax_valid=syntax_valid,
    llm_review_valid=inst.is_valid, issues=inst.issues,
    all_artifacts=all_artifacts,
)

# After (process_instructions with sandbox)
# Sandbox validation block after all_artifacts built:
# 1. Reconstruct FieldDefinition list from context dicts
# 2. Generate sample data via SampleDataGenerator
# 3. Run StepSandbox().run(artifacts, sample_data)
# 4. Set sandbox_valid, sandbox_skipped, sandbox_output
# 5. Extend issues with security_issues
# 6. is_valid = syntax_valid and inst.is_valid and (sandbox_valid or sandbox_skipped)
return CodeValidationContext(
    is_valid=is_valid, syntax_valid=syntax_valid,
    llm_review_valid=inst.is_valid, issues=issues,
    all_artifacts=all_artifacts,
    sandbox_valid=sandbox_valid, sandbox_skipped=sandbox_skipped,
    sandbox_output=sandbox_output,
)
```

## Decisions
### Issues list mutation
**Choice:** Copy inst.issues into mutable list before extending with security_issues
**Rationale:** inst.issues is from Pydantic model default; mutating in-place would be unsafe. `list(inst.issues)` creates a safe copy.

### Fallback when _SANDBOX_AVAILABLE=False
**Choice:** Set sandbox_output="sandbox module not available", sandbox_skipped=True, sandbox_valid=False
**Rationale:** Matches safe defaults in CodeValidationContext schema. is_valid passes through since sandbox_skipped=True.

## Verification
[x] syntax check passes (ast.parse)
[x] lazy import guard uses try/except ImportError with _SANDBOX_AVAILABLE flag
[x] FieldDefinition reconstructed from context dicts
[x] SampleDataGenerator generates sample data when fields present, None when empty
[x] StepSandbox().run() called with all_artifacts and sample_data
[x] sandbox_valid, sandbox_skipped, sandbox_output set on returned context
[x] is_valid logic: syntax_valid and inst.is_valid and (sandbox_valid or sandbox_skipped)
[x] security_issues appended to issues list
[x] duplicate .models import consolidated
