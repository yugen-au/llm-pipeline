# IMPLEMENTATION - STEP 4: TESTS MODELS+AST
**Status:** completed

## Summary
Created unit tests for `GeneratedStep`/`IntegrationResult` models and `modify_pipeline_file()` AST modifier. 53 tests, all passing in 0.99s.

## Files
**Created:** `tests/test_integrator_models.py`, `tests/test_ast_modifier.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/test_integrator_models.py`
22 tests across `TestGeneratedStep` and `TestIntegrationResult`.

`TestGeneratedStep` covers: step_code/instructions_code/prompts_code/extraction_code extraction, PascalCase class name derivation for single/multi/three-segment names, extraction_code=None when key absent, all_artifacts preservation and copy independence, extra keys preserved, correct artifact counts, KeyError on missing required keys.

`TestIntegrationResult` covers: full construction, empty files_written, pipeline_file_updated=False, multiple paths ordering.

### File: `tests/test_ast_modifier.py`
31 tests in `TestASTModifier` covering all plan-specified cases.

Templates defined as string concatenation (not f-strings or heredocs) to avoid `{{`/`}}` escaping issues with literal `{`/`}` in Python source.

```
# Before (caused template bug - plain strings not f-strings, {{ stayed literal)
_TOPLEVEL_IMPORT_TEMPLATE = """\
...agents={{...}}..."""

# After (string concat, literal braces)
_TOPLEVEL_IMPORT_TEMPLATE = (
    '...agents={\n'
    '    ...\n'
    '})\n'
)
```

## Decisions
### Template String Format
**Choice:** String concatenation with single-quoted lines rather than triple-quoted heredocs.
**Rationale:** Triple-quoted strings with `{`/`}` chars require either f-string double-brace escaping (`{{`/`}}`) or raw strings. Since templates contain Python class syntax with dict/list literals, using plain string concat avoids any escaping. Discovered bug during first run where `{{` stayed literal in non-f-strings.

### Test Coverage for Error Paths
**Choice:** Added tests for missing `get_steps`, missing `AgentRegistry.agents`, missing `Registry.models` (when extraction provided), and syntax error recovery.
**Rationale:** Contract specifies `test_invalid_syntax_raises` and `test_bak_file_created`; added the missing-target cases as they represent distinct `ASTModificationError` raise sites in the implementation.

## Verification
- [x] 53 tests collected and passed (`pytest tests/test_integrator_models.py tests/test_ast_modifier.py -v`)
- [x] No warnings in test output
- [x] All plan-specified test cases implemented (Step 4 section)
- [x] Templates produce valid Python (verified by `ast.parse()` tests)
- [x] Both inline and top-level import patterns tested
- [x] .bak file creation and content verified
- [x] Invalid syntax raises `ASTModificationError` and restores original
