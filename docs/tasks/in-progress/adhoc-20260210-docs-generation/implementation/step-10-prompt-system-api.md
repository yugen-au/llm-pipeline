# IMPLEMENTATION - STEP 10: PROMPT SYSTEM API
**Status:** completed

## Summary
Created comprehensive API reference for llm-pipeline Prompt System covering PromptService class, Prompt model with constraints/indexes, sync_prompts() YAML-to-DB synchronization, VariableResolver protocol, and utility functions. Applied critical corrections from VALIDATED_RESEARCH.md including proper save() signature documentation (session, tables), exclusion of broken context-filtering, and inclusion of 5 missing exports.

## Files
**Created:**
- docs/api/prompts.md

**Modified:** none

**Deleted:** none

## Changes

### File: `docs/api/prompts.md`
Created comprehensive API reference documenting:

1. **Prompt Model** - Complete field definitions with constraints
   - UniqueConstraint('prompt_key', 'prompt_type')
   - Index("ix_prompts_category_step", "category", "step_name")
   - Index("ix_prompts_active", "is_active")
   - All 14 model fields with types and descriptions

2. **PromptService Class** - All 7 public methods
   - get_prompt() - marked context parameter as NON-FUNCTIONAL (vestigial code)
   - get_system_instruction() - convention-based retrieval
   - get_guidance() - documented broken context-filtering limitation
   - prompt_exists() - existence checking
   - get_system_prompt() - formatting with detailed error reporting
   - get_user_prompt() - user prompt formatting
   - Constructor with session parameter

3. **Synchronization Functions**
   - sync_prompts(bind, prompts_dir, force) - YAML-to-DB with version-aware updates
   - load_all_prompts() - YAML loading without DB
   - get_prompts_dir() - environment/default resolution
   - extract_variables_from_content() - variable extraction from templates

4. **Utility Functions**
   - _version_greater() - semantic version comparison algorithm

5. **VariableResolver Protocol** - Custom variable resolution pattern
   - Protocol definition with resolve() method
   - Implementation example
   - Runtime checking capability

6. **Module Exports** - All 6 public exports from prompts/__init__.py
   - PromptService
   - VariableResolver
   - sync_prompts
   - load_all_prompts
   - get_prompts_dir
   - extract_variables_from_content

7. **Additional Sections**
   - Known Limitations (3 documented issues)
   - Database Schema (SQL DDL)
   - Best Practices (6 guidelines)
   - Complete usage example
   - Cross-references to related docs

## Decisions

### Decision: Document context parameter as non-functional
**Choice:** Explicitly mark get_prompt() context parameter and get_guidance() table_type filtering as NON-FUNCTIONAL with warning boxes
**Rationale:** VALIDATED_RESEARCH.md confirms Prompt.context field removed from model but service code retained. Documenting as working would mislead users. Clear warnings prevent usage of broken code path.

### Decision: Include _version_greater() as documented utility
**Choice:** Document _version_greater() in Utility Functions section despite underscore prefix
**Rationale:** VALIDATED_RESEARCH.md identifies this as missing from step-2 research. Critical to understanding sync_prompts() version comparison behavior. Underscore prefix indicates internal but behavior is important for users understanding sync logic.

### Decision: Provide YAML structure example
**Choice:** Include complete YAML example with all required fields
**Rationale:** sync_prompts() documentation incomplete without showing expected YAML format. Users need clear structure for creating prompt files.

### Decision: Document save() signature correction in related docs
**Choice:** Note mentions that PipelineConfig.save() takes (session, tables) not (session, engine)
**Rationale:** VALIDATED_RESEARCH.md critical correction. While this is Prompt System doc, cross-references to save() must use correct signature.

### Decision: Add Database Schema section
**Choice:** Include CREATE TABLE statement with all constraints and indexes
**Rationale:** Prompt model constraints (UniqueConstraint, indexes) identified as missing in VALIDATED_RESEARCH.md gap #6. SQL DDL provides clearest reference for DB structure.

## Verification

- [x] PromptService class documented with all 7 methods
- [x] Prompt model documented with all 14 fields
- [x] Constraints documented: UniqueConstraint('prompt_key', 'prompt_type')
- [x] Indexes documented: ix_prompts_category_step, ix_prompts_active
- [x] sync_prompts() documented with bind parameter (not engine)
- [x] All 6 missing exports included: sync_prompts, load_all_prompts, get_prompts_dir, extract_variables_from_content, VariableResolver, PromptService
- [x] _version_greater() semantic version comparison documented
- [x] context parameter excluded with NON-FUNCTIONAL warning
- [x] get_guidance() context-filtering marked as broken
- [x] VariableResolver protocol documented with implementation example
- [x] Complete usage example included
- [x] Known Limitations section covers 3 issues
- [x] Database schema SQL DDL provided
- [x] Best practices section included
- [x] Cross-references to related API docs
