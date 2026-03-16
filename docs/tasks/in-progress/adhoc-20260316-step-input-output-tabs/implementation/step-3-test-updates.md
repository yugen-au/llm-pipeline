# IMPLEMENTATION - STEP 3: TEST UPDATES
**Status:** completed

## Summary
Added 7 backend unit tests for `_extract_raw_response` helper and 6 frontend tests verifying InstructionsTab/PromptsTab content after the Step 2 tab rewire. All 16 frontend tests and 7 backend tests pass.

## Files
**Created:** `tests/test_raw_response.py`
**Modified:** `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
**Deleted:** none

## Changes
### File: `tests/test_raw_response.py`
New file with 7 test cases for `_extract_raw_response()`:
- `test_tool_call_part_returns_json_args` - ToolCallPart args serialized to JSON string
- `test_text_part_returns_content` - TextPart content returned as-is
- `test_no_model_response_returns_none` - empty messages and non-ModelResponse messages return None
- `test_multiple_parts_joined_with_newline` - TextPart + ToolCallPart joined with `\n`
- `test_uses_last_model_response` - multiple ModelResponses uses last one
- `test_new_messages_exception_returns_none` - exception in new_messages() returns None gracefully
- `test_non_serializable_args_falls_back_to_str` - non-JSON-serializable args fall back to str()

### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
Added mock data constants and 6 new test cases:

```
# Before (imports)
import type { StepDetail, EventListResponse } from '@/api/types'

# After (imports)
import type { StepDetail, EventListResponse, PipelineMetadata, StepPromptsResponse } from '@/api/types'
```

Added `mockPipelineData` (PipelineMetadata with instructions_schema/instructions_class for "extract" step) and `mockPromptsData` (StepPromptsResponse with system/user prompt templates containing `{variable}` placeholders).

New tests:
- `InstructionsTab renders JSON schema from usePipeline metadata` - verifies instructions_class badge and schema field names rendered
- `InstructionsTab shows empty state when no pipeline schema available` - verifies "No schema available" text
- `PromptsTab renders prompt templates from useStepInstructions` - verifies prompt_type badges, prompt_key labels, and `{variable}` placeholder content
- `PromptsTab shows empty state when no prompt templates available` - verifies "No prompt templates registered" text
- `PromptsTab shows loading skeleton when instructions are loading` - verifies animate-pulse skeletons
- `PromptsTab shows error when instructions fail to load` - verifies "Failed to load prompts" error text

## Decisions
### Test file location for _extract_raw_response
**Choice:** Separate `tests/test_raw_response.py` rather than appending to `tests/test_pipeline.py`
**Rationale:** `test_pipeline.py` is large and focused on PipelineConfig integration; raw_response extraction is a standalone helper with its own concern. Separate file keeps tests focused and discoverable.

### Mock approach for pydantic-ai message types
**Choice:** MagicMock with `__class__` override for isinstance checks
**Rationale:** Avoids importing and constructing real pydantic-ai message objects which require valid constructor args. The `__class__` override makes `isinstance()` checks work correctly with mocks.

## Verification
[x] Backend tests pass: 7/7 in tests/test_raw_response.py
[x] Frontend tests pass: 16/16 in StepDetailPanel.test.tsx (8 original + 8 new)
[x] No regressions in existing tests
[x] InstructionsTab assertions verify JSON schema content (not prompt templates)
[x] PromptsTab assertions verify prompt template items with {variable} placeholders

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Underscore-prefixed function exported in tests (LOW) - added module docstring explaining why private function is tested directly
[x] MagicMock __class__ override fragility (LOW) - added comments on _model_response, _tool_call_part, _text_part explaining why __class__ override is needed

### Changes Made
#### File: `tests/test_raw_response.py`
Added explanatory comments for both review issues.

```
# Before (module docstring)
"""Unit tests for _extract_raw_response helper in pipeline.py."""

# After (module docstring)
"""Unit tests for _extract_raw_response helper in pipeline.py.

Testing _extract_raw_response directly despite underscore prefix because it is
a standalone utility with complex edge cases (ToolCallPart serialization,
multi-part joining, exception handling) that warrant isolated unit coverage.
"""
```

```
# Before (_model_response __class__ comment)
    # Make isinstance checks work
    mr.__class__ = ModelResponse

# After (_model_response __class__ comment)
    # Override __class__ so isinstance() checks in _extract_raw_response match
    # ModelResponse. MagicMock(spec=...) alone does not satisfy isinstance();
    # __class__ assignment is the lightest way to fake it without constructing
    # real pydantic-ai message objects (which require valid constructor args).
    mr.__class__ = ModelResponse
```

```
# Before (_tool_call_part / _text_part)
    p.__class__ = ToolCallPart  # (no comment)
    p.__class__ = TextPart      # (no comment)

# After
    # See _model_response docstring for why __class__ override is needed.
    p.__class__ = ToolCallPart
    # See _model_response docstring for why __class__ override is needed.
    p.__class__ = TextPart
```

Also verified Step 1/2 changes (type annotation on `_extract_raw_response`, `usePipeline` accepting `string | undefined`) do not break existing tests. No mock updates needed; `mockUsePipeline` is a `vi.fn()` that accepts any args.

### Verification
[x] Backend tests pass: 7/7 after comment additions
[x] Frontend tests pass: 16/16 unchanged
[x] Step 1/2 signature changes do not affect test behavior
