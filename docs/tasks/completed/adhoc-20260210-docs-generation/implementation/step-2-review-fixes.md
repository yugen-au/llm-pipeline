# IMPLEMENTATION - STEP 2 REVIEW FIXES
**Status:** completed

## Summary
Fixed 4 review issues in docs/architecture/concepts.md: PipelineRunInstance field names, extract_data() ordering, save() pseudo-code, and clear_cache() signature.

## Files
**Created:** none
**Modified:**
- docs/architecture/concepts.md

**Deleted:** none

## Changes
### File: `docs/architecture/concepts.md`

#### Fix 1: PipelineRunInstance field names (HIGH)
Changed `model_name` → `model_type` and `instance_id` → `model_id` in 4 locations:
- Line 1037-1038: Field documentation
- Line 528-529: save() pseudo-code
- Line 1052-1053: tracking example
- Line 1066: query example

**Source verification:** state.py lines 128-133 define fields as `model_type` and `model_id`.

#### Fix 2: extract_data() ordering (HIGH)
Moved `store_extractions()` call BEFORE `_real_session.add/flush` in pseudo-code at lines 500-514.

**Correct order:**
1. Extract instances
2. Store in pipeline.extractions
3. Add to session
4. Flush to assign IDs

**Source verification:** step.py lines 326-330 show store_extractions at line 327, then add/flush at 328-330.

#### Fix 3: save() pseudo-code (HIGH)
Fixed lines 518-534:
- Removed incorrect two-commit pattern (was: commit, add tracking, commit again)
- Corrected to use `session` parameter instead of `self._real_session`
- Fixed field names to `model_type`/`model_id`
- Single commit after tracking instances

**Source verification:** pipeline.py lines 752-762 show _track_created_instances adds to session, then single commit at line 749.

#### Fix 4: clear_cache() signature (LOW)
Changed line 1075 from `pipeline.clear_cache(step_name)` to `pipeline.clear_cache()`.

**Source verification:** pipeline.py line 560 shows signature `clear_cache(self) -> int` with no parameters.

## Decisions
### Decision: Verify all fixes against source code
**Choice:** Read actual source files (state.py, step.py, pipeline.py) to verify correct field names, method signatures, and ordering
**Rationale:** Documentation must match implementation exactly. Review identified factual contradictions that could mislead developers.

### Decision: Fix all locations for PipelineRunInstance fields
**Choice:** Search and fix all 4 occurrences of wrong field names
**Rationale:** Consistent incorrect naming throughout would reinforce wrong mental model. Must fix everywhere.

### Decision: Preserve pseudo-code format
**Choice:** Keep pseudo-code examples but correct their content
**Rationale:** Pseudo-code is pedagogically valuable for understanding two-phase write pattern. Only content was wrong, not the concept.

## Verification
[x] PipelineRunInstance uses model_type and model_id (verified in state.py)
[x] extract_data() calls store_extractions before add/flush (verified in step.py)
[x] save() uses single commit with session parameter (verified in pipeline.py)
[x] clear_cache() has no parameters (verified in pipeline.py)
[x] All 4 locations for field names corrected
[x] Pseudo-code ordering matches actual implementation
[x] Git diff shows 14 insertions, 17 deletions (net cleanup)
