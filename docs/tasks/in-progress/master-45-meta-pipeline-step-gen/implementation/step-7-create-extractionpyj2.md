# IMPLEMENTATION - STEP 7: CREATE EXTRACTION.PY.J2
**Status:** completed

## Summary
Created `llm_pipeline/creator/templates/extraction.py.j2` Jinja2 template that renders a complete Python PipelineExtraction subclass module from template variables.

## Files
**Created:** `llm_pipeline/creator/templates/extraction.py.j2`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/templates/extraction.py.j2`
New Jinja2 template rendering a Python module with:
- File docstring
- `from llm_pipeline.extraction import PipelineExtraction` import
- Dynamic model and instructions imports via `model_import` and `instructions_import` variables
- Class declaration: `class {class_name}(PipelineExtraction, model={model_name}):` with docstring
- `def default(self, results: list[{instructions_class_name}]) -> list[{model_name}]:` method
- Conditional: if `extraction_method_body` provided, renders indented body via `indent_code(8)` filter; if None, renders `return []`

## Decisions
### Template variable design
**Choice:** Used `model_import` and `instructions_import` as full import line strings rather than deriving import paths inside the template
**Rationale:** Matches step.py.j2 pattern where imports are passed as complete strings. Keeps template logic minimal; import path resolution belongs in the rendering caller (steps.py CodeGenerationStep).

### Fallback body for None extraction_method_body
**Choice:** `return []` (empty list) rather than `pass` or `raise NotImplementedError`
**Rationale:** PLAN.md Step 7.4 specifies "minimal pass-through extraction returning empty list". An empty list is type-correct for `-> list[Model]` and won't break pipeline execution.

## Verification
[x] Template renders valid Python with extraction_method_body provided (ast.parse passes)
[x] Template renders valid Python with extraction_method_body=None (ast.parse passes)
[x] Output matches demo TopicExtraction pattern from demo/pipeline.py
[x] indent_code filter correctly indents multi-line method bodies to 8 spaces
[x] StrictUndefined environment catches missing variables
[x] Existing test suite passes with no new failures (6 pre-existing failures unchanged)
