# IMPLEMENTATION - STEP 6: CREATE INSTRUCTIONS.PY.J2
**Status:** completed

## Summary
Created `llm_pipeline/creator/templates/instructions.py.j2` Jinja2 template that renders a complete Python instructions/LLMResultMixin class module. Also added `format_dict` filter to templates/__init__.py for clean Python dict literal rendering.

## Files
**Created:** `llm_pipeline/creator/templates/instructions.py.j2`
**Modified:** `llm_pipeline/creator/templates/__init__.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/templates/instructions.py.j2`
New Jinja2 template rendering a complete Python module with:
- File docstring
- `from typing import ClassVar` and `from llm_pipeline.step import LLMResultMixin` imports
- Additional imports loop for field-type dependencies
- Class declaration extending LLMResultMixin with docstring
- Field rendering: required fields without defaults, optional fields with `default` or fallback `""`
- `example: ClassVar[dict]` rendered via `format_dict` + `indent` filters

### File: `llm_pipeline/creator/templates/__init__.py`
Added `_format_dict` filter and registered it on the Jinja2 Environment. Produces clean multi-line Python dict literals with configurable indent, matching the hand-written style in demo/pipeline.py.

```
# Before
(no format_dict filter)

# After
def _format_dict(value: dict, indent: int = 4) -> str:
    ...
env.filters["format_dict"] = _format_dict
```

## Decisions
### Dict formatting approach
**Choice:** Custom `_format_dict` filter producing one key per line, combined with Jinja2 built-in `indent` filter for class-body alignment
**Rationale:** Jinja2's built-in `pprint` filter sorts keys and produces misaligned continuation lines. `repr()` on complex dicts produces single-line output. Custom filter matches demo's hand-written style exactly.

### Default fallback for optional fields
**Choice:** `{{ field.default if field.default is not none else '""' }}`
**Rationale:** Plan step 6.3 specifies `field.default or '""'` fallback. Using `is not none` rather than truthiness check to allow `False`, `0`, `[]` as valid explicit defaults.

## Verification
[x] Template renders valid Python for all test cases (ast.parse passes)
[x] Output matches demo SentimentAnalysisInstructions pattern
[x] Required fields render without defaults
[x] Optional fields render with explicit default or `""` fallback
[x] Additional imports render correctly
[x] Empty fields list and empty example_dict handled
[x] Existing test suite passes (1049 passed, 6 pre-existing failures unrelated)
