# PLANNING

## Summary
Populate `PipelineStepState.model` field with LLM provider's model name. Use `self._provider.model_name` via getattr for safety. Single call site at pipeline.py:560 modified to pass model_name to `_save_step_state()`, which stores it in PipelineStepState construction. Non-breaking, pipeline.py-only change.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** code-modifier
**Skills:** none

## Phases
1. Implementation - Modify pipeline.py to extract and pass model_name
2. Testing - (CEO to decide inclusion)
3. Review - (CEO to decide inclusion)

## Architecture Decisions

### Use self._provider.model_name with getattr fallback
**Choice:** Extract model_name via `getattr(self._provider, 'model_name', None)` in execute() at call site, pass to _save_step_state()
**Rationale:**
- execute_llm_step() returns T not LLMCallResult, so model_name unavailable in result
- self._provider is available in execute() scope (pipeline.py:152, used at 535)
- GeminiProvider stores model_name as instance attribute (gemini.py:47)
- LLMProvider ABC has no model_name contract, getattr prevents AttributeError
- CEO approved Approach A over alternatives (VALIDATED_RESEARCH.md line 40)
**Alternatives:**
- Approach B: Modify executor.py to return (T, model_name) - rejected (breaks executor return type, requires multi-file change)
- Approach C: Add model_name property to LLMProvider ABC - deferred to future task (out of scope, unnecessary for task 16)

### Add model_name parameter to _save_step_state signature
**Choice:** Add optional `model_name: Optional[str] = None` param, set in PipelineStepState construction at line 715
**Rationale:**
- Explicit parameter more readable than extracting inside _save_step_state
- Call site at line 560 already in execute() where self._provider accessible
- Follows existing pattern (execution_time_ms optional param added line 687)
**Alternatives:** Extract model_name inside _save_step_state - rejected (would need self._provider access, method has no self reference beyond passed params)

## Implementation Steps

### Step 1: Add model_name param to _save_step_state signature
**Agent:** python-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open llm_pipeline/pipeline.py
2. Locate _save_step_state method definition at line 687
3. Add `model_name: Optional[str] = None` parameter after `execution_time_ms=None` in signature
4. Update PipelineStepState construction at line 715 to include `model=model_name` field

### Step 2: Pass model_name at call site in execute()
**Agent:** python-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open llm_pipeline/pipeline.py
2. Locate _save_step_state call at line 560-562
3. Before call, extract model_name: `model_name = getattr(self._provider, 'model_name', None)`
4. Pass model_name to _save_step_state call as final argument

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Provider lacks model_name attribute (non-Gemini) | Low | getattr with None default prevents AttributeError, model field remains NULL |
| PipelineStepState.model max_length=50 too short for future models | Low | Current Gemini names fit (24 chars max), monitor only, no immediate action |
| Cached states pre-task-16 retain model=None | Low | No migration needed, acceptable data inconsistency for historical records |

## Success Criteria
- [ ] _save_step_state signature includes `model_name: Optional[str] = None` param
- [ ] PipelineStepState construction at line 715 includes `model=model_name`
- [ ] execute() extracts model_name via getattr before _save_step_state call at line 560
- [ ] _save_step_state call passes model_name argument
- [ ] No syntax errors, code runs without AttributeError

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Single-file change, non-breaking, getattr prevents runtime errors, no schema migration, no external dependencies
**Suggested Exclusions:** testing, review
