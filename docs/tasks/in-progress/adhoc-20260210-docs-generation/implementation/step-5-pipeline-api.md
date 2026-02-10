# IMPLEMENTATION - STEP 5: PIPELINE API
**Status:** completed

## Summary
Created comprehensive Pipeline API reference documentation (docs/api/pipeline.md) documenting PipelineConfig class, StepKeyDict helper class, all public methods, constructor parameters, properties, data access methods, extraction methods, execution methods, consensus polling helpers, and usage patterns. Added all missing items identified in VALIDATED_RESEARCH.md.

## Files
**Created:** docs/api/pipeline.md, docs/tasks/in-progress/adhoc-20260210-docs-generation/implementation/step-5-pipeline-api.md
**Modified:** none
**Deleted:** none

## Changes
### File: `docs/api/pipeline.md`
Created comprehensive Pipeline API reference documentation following established patterns from step.md and index.md.

Key sections included:
- PipelineConfig class with full inheritance documentation (extends ABC)
- Class-level configuration via __init_subclass__ with naming validation rules
- Constructor with all parameters: strategies, session, engine, provider, variable_resolver
- Properties: pipeline_name, instructions, context
- Data access methods: get_raw_data(), get_current_data(), get_sanitized_data(), get_data(), set_data()
- Extraction methods: store_extractions(), get_extractions()
- Execution methods: execute() with two-phase write pattern documentation, save(), ensure_table()
- Cache methods: clear_cache() with known limitation documented
- Customization methods: sanitize()
- Consensus polling helpers: _smart_compare(), _instructions_match(), _get_mixin_fields()
- Session management: close()
- Internal validation methods with error examples
- StepKeyDict class with key normalization algorithm
- Complete usage patterns with code examples

All corrections from VALIDATED_RESEARCH.md applied:
- Documented two-phase write pattern (flush during execution, commit in save)
- Corrected save() signature: save(session, tables) not save(session, engine)
- Documented clear_cache() bug (uses ReadOnlySession for writes)
- Added missing methods: get_raw_data(), get_current_data(), get_sanitized_data()
- Added missing class: StepKeyDict with normalization logic
- Added consensus helpers: _smart_compare(), _instructions_match(), _get_mixin_fields()

## Decisions
### Follow established documentation pattern
**Choice:** Match structure and style from step.md and index.md
**Rationale:** Consistency across API reference files. Used same section hierarchy, example formatting, "See Also" cross-references, and explanation depth.

### Document two-phase write pattern explicitly
**Choice:** Dedicated explanation in execute() and save() methods showing flush() during execution and commit() in save()
**Rationale:** VALIDATED_RESEARCH.md identified this as critical architecture pattern that was misrepresented as "all writes deferred to save()". Accurate documentation essential for users implementing FK relationships between extractions.

### Document clear_cache() as broken
**Choice:** Include method with "Known Limitation" warning and no workaround
**Rationale:** VALIDATED_RESEARCH.md confirmed bug exists (uses ReadOnlySession for delete/commit). Documenting as working would mislead users. Mark clearly as broken until fixed.

### Include StepKeyDict as documented class
**Choice:** Full section documenting StepKeyDict with algorithm and examples
**Rationale:** VALIDATED_RESEARCH.md identified as missing class. Critical for understanding why both Step classes and string keys work in pipeline.data and pipeline.instructions access patterns.

### Document consensus polling helpers
**Choice:** Full documentation of _smart_compare(), _instructions_match(), _get_mixin_fields() with comparison rules
**Rationale:** VALIDATED_RESEARCH.md identified as missing. These implement consensus polling logic with specific field-matching rules (exclude strings, None, mixin fields; exact-match numbers/booleans/list-lengths).

## Verification
[x] PipelineConfig class fully documented with ABC inheritance
[x] All constructor parameters documented with database session hierarchy
[x] All properties documented: pipeline_name, instructions, context
[x] Missing data access methods added: get_raw_data(), get_current_data(), get_sanitized_data()
[x] Missing StepKeyDict class documented with normalization algorithm
[x] Missing consensus helpers documented: _smart_compare(), _instructions_match(), _get_mixin_fields()
[x] Two-phase write pattern documented in execute() and save()
[x] Corrected save() signature: save(session, tables)
[x] clear_cache() documented with known limitation warning
[x] All public methods include signatures, parameters, returns, examples
[x] Usage patterns section with complete examples
[x] Cross-references to related API docs (step.md, strategy.md, etc.)
[x] Follows established documentation style from step.md and index.md
