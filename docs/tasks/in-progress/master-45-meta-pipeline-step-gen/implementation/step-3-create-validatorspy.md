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
