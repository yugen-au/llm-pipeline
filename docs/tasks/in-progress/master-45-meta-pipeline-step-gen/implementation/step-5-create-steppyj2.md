# IMPLEMENTATION - STEP 5: CREATE STEP.PY.J2
**Status:** completed

## Summary
Created `llm_pipeline/creator/templates/step.py.j2` Jinja2 template that renders a complete Python step module with decorator, class, and method bodies.

## Files
**Created:** `llm_pipeline/creator/templates/step.py.j2`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/templates/step.py.j2`
New Jinja2 template rendering a Python step module. Includes:
- File docstring from `docstring` variable
- Standard `from llm_pipeline.step import LLMStep, step_definition` import
- `{% for import_line in imports %}` loop for additional imports
- `@step_definition(...)` decorator with instructions, system_key, user_key, context, and conditional extractions
- `class {{ step_class_name }}(LLMStep):` declaration
- `prepare_calls` method with `prepare_calls_body | indent_code(8)`
- `process_instructions` method with `process_instructions_body | indent_code(8)`
- Conditional `should_skip` method when `should_skip_condition` is not None

## Decisions
### indent_code(8) for method bodies
**Choice:** Use `indent_code(8)` (8 spaces = 2 indentation levels)
**Rationale:** Method bodies sit inside class (4 spaces) + method (4 spaces) = 8 spaces total. The `indent_code` filter from `templates/__init__.py` adds the specified width to every non-empty line.

### Conditional extractions block
**Choice:** Only render `default_extractions=[...]` line when `extractions` list is truthy
**Rationale:** Matches demo pattern where steps without extractions omit the parameter entirely from `@step_definition`.

## Verification
[x] Template renders valid Python with basic params (no extractions, no should_skip)
[x] Template renders valid Python with extractions list and should_skip_condition
[x] Template renders valid Python with empty imports list
[x] All rendered output passes `ast.parse()` syntax validation
[x] Output matches demo/pipeline.py step class structure
