# PLANNING

## Summary
Add 4 cache event emissions (CacheLookup, CacheHit, CacheMiss, CacheReconstruction) to pipeline.py execute() method. All emissions follow established double-guard pattern from tasks 9/11. CacheReconstruction emits caller-side using step.step_name, skips when extractions empty. New test fixtures required for CacheReconstruction (pipeline with extractions).

## Plugin & Agents
**Plugin:** python-development
**Subagents:** python-developer
**Skills:** none

## Phases
1. Implementation - Add 4 cache event emissions + imports
2. Testing - Integration tests for all 4 events + fixtures
3. Validation - Verify event ordering and guard behavior

## Architecture Decisions

### CacheReconstruction Emission Location
**Choice:** Emit from execute() caller-side (L568) after _reconstruct_extractions_from_cache returns
**Rationale:** Consistent with tasks 9/11 pattern (all events emit from execute()), provides access to step.step_name (snake_case), avoids signature change to helper method
**Alternatives:** Emit inside _reconstruct_extractions_from_cache helper (rejected: inconsistent step_name format, breaks task 9/11 pattern)

### CacheReconstruction Empty-Extractions Behavior
**Choice:** Skip emission when step_def.extractions is empty
**Rationale:** Reduces noise, matches helper early-return at L766-767, no meaningful data to report (model_count=0, instance_count=0)
**Alternatives:** Emit with zeros (rejected: clutters event stream with no-op events)

### Double-Guard Pattern
**Choice:** Outer structural `if use_cache:` + inner `if self._event_emitter:` guard
**Rationale:** Structural confinement prevents events when use_cache=False, inner guard avoids dataclass construction cost when no emitter
**Alternatives:** Single combined guard (rejected: less clear intent, harder to verify structural confinement)

## Implementation Steps

### Step 1: Add Cache Event Imports
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Edit llm_pipeline/pipeline.py L35-39 import block
2. Add CacheLookup, CacheHit, CacheMiss, CacheReconstruction to existing events.types import

### Step 2: Emit CacheLookup Event
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Insert emission at L546 after `if use_cache:`, before `_find_cached_state` call
2. Guard: `if self._event_emitter:`
3. Fields: run_id, pipeline_name, step_name, input_hash

### Step 3: Emit CacheHit Event
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Insert emission at L549 inside `if cached_state:`, before logger
2. Guard: `if self._event_emitter:`
3. Fields: run_id, pipeline_name, step_name, input_hash, cached_at (from cached_state.created_at)

### Step 4: Emit CacheMiss Event
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Insert emission at L573 inside `if use_cache:`, before logger
2. Guard: `if self._event_emitter:`
3. Fields: run_id, pipeline_name, step_name, input_hash

### Step 5: Emit CacheReconstruction Event
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Insert emission at L568 after _reconstruct_extractions_from_cache returns, before zero-count check
2. Guard: `if self._event_emitter and step_def.extractions:`
3. Fields: run_id, pipeline_name, step_name, model_count (len(step_def.extractions)), instance_count (reconstructed_count return value)

### Step 6: Create CacheReconstruction Test Fixtures
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Add extraction test pipeline to tests/events/conftest.py with non-empty extractions list
2. Add registry with models for extraction pipeline
3. Seed PipelineRunInstance records for cache-hit scenario
4. Ensure prompt_version matches seeded_session default ("1.0")

### Step 7: Test CacheLookup + CacheMiss Path
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Create tests/events/test_cache_events.py
2. Test fresh DB + use_cache=True emits CacheLookup then CacheMiss
3. Verify input_hash present in both events
4. Verify ordering: CacheLookup precedes CacheMiss
5. Test no events when event_emitter=None

### Step 8: Test CacheLookup + CacheHit Path
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Two-run pattern: first run saves state, second run finds cache
2. Verify CacheLookup then CacheHit emitted on second run
3. Verify cached_at timestamp from first run present in CacheHit
4. Verify same input_hash in both events

### Step 9: Test CacheReconstruction Event
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Use new extraction test pipeline from Step 6
2. Verify CacheReconstruction emitted after CacheHit
3. Verify model_count and instance_count fields accurate
4. Verify no emission when extractions empty (guard test)
5. Verify ordering: CacheHit -> CacheReconstruction -> StepCompleted

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| CacheReconstruction fixtures complex (new pipeline + models + seeded state) | Medium | Follow existing SuccessPipeline pattern, reuse seeded_session fixture logic |
| Two-run cache-hit test flaky if prompt versions misaligned | Low | Hardcode prompt_version="1.0" in both runs, match seeded_session default |
| Event ordering tests fragile if execution flow changes | Low | Test only structural guarantees (CacheLookup before Hit/Miss), not absolute positions |

## Success Criteria
- [ ] All 4 cache events imported in pipeline.py
- [ ] CacheLookup emitted at L546 with correct fields
- [ ] CacheHit emitted at L549 with cached_at timestamp
- [ ] CacheMiss emitted at L573 with correct fields
- [ ] CacheReconstruction emitted at L568 with model/instance counts
- [ ] CacheReconstruction skips when extractions empty
- [ ] New extraction test pipeline in conftest with models
- [ ] test_cache_events.py covers all 4 events + no-emitter case
- [ ] Event ordering verified: CacheLookup -> Hit/Miss, Hit -> Reconstruction -> StepCompleted
- [ ] All tests pass, no warnings

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Straightforward event insertions following established pattern from tasks 9/11. Research validated all line numbers, field availability, and guard patterns. Only complexity is CacheReconstruction fixtures (new test pipeline with extractions), but conftest already has working pipeline patterns to follow.
**Suggested Exclusions:** testing, review
