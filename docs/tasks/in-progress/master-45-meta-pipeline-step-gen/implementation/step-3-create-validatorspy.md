# IMPLEMENTATION - STEP 3: CREATE VALIDATORS.PY
**Status:** completed

## Summary
Created `llm_pipeline/creator/validators.py` with two validator factory functions for the meta-pipeline's code generation output: `python_syntax_validator()` and `naming_convention_validator()`. Both follow the exact factory pattern from `llm_pipeline/validators.py`.

## Files
**Created:** `llm_pipeline/creator/validators.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/validators.py`
New file with two factory functions:

- `python_syntax_validator()` -- returns async validator that `ast.parse()`s `prepare_calls_body`, `process_instructions_body`, and `extraction_method_body` string fields. Bodies wrapped in `def f():\n{indented_body}` stub before parsing. Raises `ModelRetry` on `SyntaxError` with field name and error details.

- `naming_convention_validator()` -- returns async validator that checks `step_class_name` ends with `"Step"`, prefix is non-empty, and derived `{Prefix}Instructions` / `{Prefix}Context` names are valid Python identifiers. Raises `ModelRetry` on violations.

Both use the factory pattern: async inner function, `__name__`/`__qualname__` set, returned by outer factory.

`__all__ = ["python_syntax_validator", "naming_convention_validator"]`

## Decisions
### Body fields are optional/nullable
**Choice:** Skip fields that are None, non-string, or empty-whitespace
**Rationale:** `extraction_method_body` is `str | None` in CodeGenerationInstructions schema; other bodies could theoretically be empty during partial generation

### Naming validator returns output unchanged for non-string/missing step_class_name
**Choice:** Early return if `step_class_name` attr missing or not a string
**Rationale:** Validator may be registered on agents whose output type lacks this field; graceful no-op avoids AttributeError

## Verification
[x] File parses without syntax errors (`ast.parse`)
[x] `from llm_pipeline.creator.validators import python_syntax_validator, naming_convention_validator` succeeds
[x] Factory functions return async callables with correct `__name__`
[x] `python_syntax_validator` catches invalid syntax and raises ModelRetry
[x] `python_syntax_validator` passes valid method bodies
[x] `naming_convention_validator` rejects names without "Step" suffix
[x] `naming_convention_validator` rejects empty prefix ("Step")
[x] `naming_convention_validator` passes valid names ("DataProcessingStep")
[x] Full test suite: 1049 passed, no new failures (5 pre-existing failures unrelated)

---

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
- [x] validators.py is unreachable dead code — no wiring mechanism exists (HIGH)
  - `AgentSpec` has no `validators=` field
  - `pipeline.py` agent-building path hard-codes `[not_found_validator(), array_length_validator()]` with no extension point
  - `StepDefinition` has no `validators` field
  - Zero imports of `validators` across all `llm_pipeline/creator/*.py` files (grep confirmed)
  - `_STEP_SUFFIX_RE` defined on line 19 but never referenced in the module

### Changes Made
#### File: `llm_pipeline/creator/validators.py`
Deleted entirely via `git rm`. No code in the creator package imported or referenced it. Syntax checking for rendered module code is handled by `_syntax_check()` in `steps.py`; naming convention enforcement is applied at import time by the `step_definition` decorator.

```
# Before
llm_pipeline/creator/validators.py  (126 lines — two unwired factory functions)

# After
(file does not exist)
```

### Verification
[x] `git rm` successful; file absent from `llm_pipeline/creator/`
[x] grep for `validators` across `llm_pipeline/creator/*.py` returns no results
[x] grep for `from.*creator.*validators` / `import.*creator.*validators` across `llm_pipeline/` returns no results
[x] No `__init__.py` or other creator module imported or re-exported from validators

---

## Review Fix Iteration 1
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
- [x] validators.py is unreachable dead code (HIGH) — confirm removal persists

### Changes Made
No changes required. `llm_pipeline/creator/validators.py` does not exist; confirmed absent from filesystem. Removal was completed in Iteration 0 via `git rm`.

### Verification
[x] `ls llm_pipeline/creator/` confirms file absent (no `validators.py` in directory listing)
