# IMPLEMENTATION - STEP 2: CREATE SCHEMAS.PY
**Status:** completed

## Summary
Created `llm_pipeline/creator/schemas.py` with 4 Instructions classes (LLMResultMixin) and 4 Context classes (PipelineContext) for the meta-pipeline step generator.

## Files
**Created:** `llm_pipeline/creator/schemas.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/schemas.py`
New file with 8 classes:

**Instructions (LLMResultMixin subclasses):**
- `RequirementsAnalysisInstructions` -- step_name, step_class_name, description, instruction_fields (list[FieldDefinition]), context_fields (list[FieldDefinition]), extraction_targets (list[ExtractionTarget]), input_variables, output_context_keys
- `CodeGenerationInstructions` -- imports, prepare_calls_body, process_instructions_body, extraction_method_body (optional), should_skip_condition (optional)
- `PromptGenerationInstructions` -- system_prompt_content, user_prompt_template, required_variables, prompt_category
- `CodeValidationInstructions` -- is_valid, issues, suggestions, naming_valid, imports_valid, type_annotations_valid

**Contexts (PipelineContext subclasses):**
- `RequirementsAnalysisContext` -- step_name, step_class_name, instruction_fields (list[dict]), context_fields (list[dict]), extraction_targets (list[dict]), input_variables, output_context_keys
- `CodeGenerationContext` -- step_code, instructions_code, extraction_code (optional)
- `PromptGenerationContext` -- system_prompt, user_prompt_template, required_variables, prompt_yaml
- `CodeValidationContext` -- is_valid, syntax_valid, llm_review_valid, issues, all_artifacts (dict[str, str])

All Instructions classes have `example: ClassVar[dict]` validated at class definition time via `LLMResultMixin.__init_subclass__`.

## Decisions
### Field defaults on Instructions classes
**Choice:** All Instructions fields have empty defaults (empty string, empty list, False, None) matching demo pattern
**Rationale:** LLMResultMixin's create_failure() requires all fields to have defaults so safe_defaults can be minimal. Demo classes (SentimentAnalysisInstructions, etc.) use same pattern.

### Context fields use list[dict] not list[FieldDefinition]
**Choice:** RequirementsAnalysisContext uses `list[dict]` for instruction_fields/context_fields/extraction_targets instead of typed models
**Rationale:** PLAN.md Step 2 item 7 specifies `list[dict]` explicitly. Context holds serialized data for downstream template rendering; dict is more flexible for Jinja2 consumption.

## Verification
[x] All 8 classes import successfully via `from llm_pipeline.creator.schemas import *`
[x] All 4 example ClassVar dicts pass LLMResultMixin.__init_subclass__ validation
[x] __all__ exports all 8 class names
[x] 4 Instructions inherit from LLMResultMixin, 4 Contexts inherit from PipelineContext
[x] pytest passes with no new failures (7 pre-existing failures unrelated to this change)
[x] Graphiti updated with codebase context
