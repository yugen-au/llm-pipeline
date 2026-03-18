# IMPLEMENTATION - STEP 11: CREATE STEPS.PY
**Status:** completed

## Summary
Created `llm_pipeline/creator/steps.py` with `GenerationRecordExtraction` and 4 `@step_definition` step classes for the meta-pipeline creator. Steps chain: RequirementsAnalysis -> CodeGeneration -> PromptGeneration -> CodeValidation.

## Files
**Created:** `llm_pipeline/creator/steps.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/steps.py`
New file. Key classes:

- `GenerationRecordExtraction(PipelineExtraction, model=GenerationRecord)` - `default()` reads `step_name` and `all_artifacts` from `self.pipeline.context`, `run_id` from `self.pipeline.run_id`, `is_valid` from `results[0].is_valid`.
- `RequirementsAnalysisStep` - `prepare_calls` passes `description` from `validated_input`; `process_instructions` returns `RequirementsAnalysisContext` with all fields `model_dump()`'d from instruction FieldDefinition/ExtractionTarget lists.
- `CodeGenerationStep` - `prepare_calls` reads Step 1 context keys; `process_instructions` derives `prefix`/class names from `step_class_name`, calls `render_template` for `step.py.j2`, `instructions.py.j2`, and conditionally `extraction.py.j2` (when `include_extraction=True` and extraction_targets non-empty).
- `PromptGenerationStep` - `prepare_calls` reads Step 1+2 context; `process_instructions` renders `prompts.yaml.j2` and returns `PromptGenerationContext`.
- `CodeValidationStep` - `default_extractions=[GenerationRecordExtraction]`; `process_instructions` runs `_syntax_check()` on all code strings (wraps in `def _f():` stub as per PLAN risk note), combines with `inst.is_valid`, builds `all_artifacts` dict, returns `CodeValidationContext`.

## Decisions
### ast.parse wrapping strategy
**Choice:** wrap code in `def _f():\n    {indented_code}` stub before parsing
**Rationale:** PLAN.md risk section specifies this to handle method bodies that reference outer-scope names. Full rendered source files (step_code, instructions_code) are also checked directly.

### extraction_code conditional on extraction_targets
**Choice:** only render `extraction.py.j2` if `include_extraction=True` AND `extraction_targets` list is non-empty
**Rationale:** No extraction targets means nothing to render; avoids template being called with empty first_target.

### Context field access via `.get()` with defaults
**Choice:** use `ctx.get(key, "")` throughout rather than `ctx[key]`
**Rationale:** Steps may run in isolation or with partial context; defensive access avoids KeyError.

## Verification
- [x] `from llm_pipeline.creator.steps import ...` imports without error
- [x] `@step_definition` decorators pass naming validation at class definition time
- [x] `pytest` passes with same 6 pre-existing failures, no regressions (1049 passed)
- [x] `GenerationRecordExtraction` ends with "Extraction" (naming convention enforced by PipelineExtraction.__init_subclass__)
- [x] `CodeValidationStep` includes `default_extractions=[GenerationRecordExtraction]`
- [x] All 4 step classes follow `{Prefix}Step` / `{Prefix}Instructions` / `{Prefix}Context` naming

## Review Fix Iteration 0
**Issues Source:** REVIEW.md (user-reported)
**Status:** fixed

### Issues Addressed
- [x] CRITICAL: render_template() calls missing required template variables (StrictUndefined crash)
- [x] MEDIUM: _syntax_check() wrapping full module source in function stub unnecessarily

### Changes Made
#### File: `llm_pipeline/creator/steps.py`

Fix 1 - step.py.j2 call: added `docstring`, `system_key=step_name`, `user_key=step_name`, `extractions=[]`

Fix 2 - instructions.py.j2 call: added `docstring`, `additional_imports=[]`

Fix 3 - extraction.py.j2 call: added `docstring`, `model_import`, `instructions_import`; removed spurious `fields` kwarg (not referenced in template)

Fix 4 - `_syntax_check()`: replaced stub-wrapping approach with `ast.parse(code, mode="exec")` directly; receives full module source not method bodies

### Verification
- [x] `from llm_pipeline.creator.steps import ...` imports without error
- [x] All 3 template variable sets match actual .j2 template variables verified by reading each template
- [x] `_syntax_check()` now calls `ast.parse(code, mode="exec")` directly
- [x] pytest passes with no new failures
