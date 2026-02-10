# IMPLEMENTATION - STEP 16: KNOWN LIMITATIONS
**Status:** completed

## Summary
Created comprehensive Known Limitations documentation at docs/architecture/limitations.md covering 5 critical issues: clear_cache() ReadOnlySession bug, Prompt.context vestigial code, single-level inheritance requirement, Gemini-only provider, and deprecated save_step_yaml(). Included workarounds, code examples, and impact analysis.

## Files
**Created:**
- docs/architecture/limitations.md

**Modified:** none
**Deleted:** none

## Changes

### File: `docs/architecture/limitations.md`
Created complete limitations documentation with 5 major sections:

1. **Database Session Limitations**
   - clear_cache() bug: uses `self.session` (ReadOnlySession) instead of `_real_session` for delete/commit operations
   - Documented exact error, impact (rarely triggered due to use_cache=False default), and proper fix

2. **Prompt System Limitations**
   - get_prompt() context parameter: references non-existent Prompt.context field
   - Vestigial code from earlier version when context field existed (evidence: _legacy/ folder)
   - Affects get_guidance() which passes context internally
   - Works only when context=None (common case)

3. **Inheritance and Naming Validation**
   - Single-level inheritance requirement: validation only checks immediate parent
   - By design - all concrete classes directly subclass base in practice
   - Underscore prefix escape hatch for intermediate abstract classes
   - Low impact given intended usage patterns

4. **Provider Limitations**
   - Only GeminiProvider implementation shipped
   - Documented how to create custom providers extending LLMProvider abstract class
   - Included full code example for OpenAI provider implementation

5. **Deprecated Features**
   - save_step_yaml() marked as legacy dead code
   - Used by old execute_pipeline(), never called by current PipelineConfig.execute()

Structure includes:
- Detailed code examples showing bugs and fixes
- Impact analysis for each limitation
- Workarounds where available
- Summary table with severity ratings
- Future improvements section
- Issue reporting guidance

## Decisions

### Decision: Detailed Code Examples with Bug/Fix Comparison
**Choice:** Include exact source code showing bug location, runtime errors, and proper fix implementation
**Rationale:** Users need concrete understanding of why certain features fail and how to avoid them. Code examples prevent misuse and guide future fixes. Critical for clear_cache() and get_prompt() context issues.

### Decision: Severity Ratings in Summary Table
**Choice:** Classify each limitation as Low/Medium severity with workaround availability
**Rationale:** Helps users prioritize which limitations affect their use case. Medium severity for bugs that fail at runtime (clear_cache, context filtering), Low for design constraints (inheritance, provider choice).

### Decision: Custom Provider Implementation Guide
**Choice:** Full code skeleton for implementing custom LLMProvider (OpenAI example)
**Rationale:** Gemini-only limitation is significant for users requiring alternative models. Providing implementation template reduces friction for extending framework.

### Decision: Link Limitations to VALIDATED_RESEARCH.md Findings
**Choice:** Document all 5 contradictions/gaps identified in validation:
- Q2 resolution: clear_cache() ReadOnlySession bug
- Q3 resolution: Prompt.context vestigial code
- Q5 resolution: single-level inheritance by design
- Plus provider limitation and deprecated features
**Rationale:** Ensures validated research corrections are properly documented for users. Prevents misleading documentation that claims broken features work.

## Verification
- [x] All 5 critical issues documented (clear_cache bug, context filtering, inheritance, provider, deprecated)
- [x] Workarounds provided where applicable
- [x] Code examples show exact bug locations with line numbers
- [x] Proper fix implementations documented for clear_cache() and get_prompt()
- [x] Impact analysis included for each limitation
- [x] Summary table categorizes severity and workaround availability
- [x] Custom provider implementation guide included with full example
- [x] Matches Step 16 requirements from PLAN.md
- [x] All content sourced from VALIDATED_RESEARCH.md findings and actual source code
