# PLANNING

## Summary
Update executor.py execute_llm_step() to handle LLMCallResult return type from provider.call_structured(). Change from storing dict to storing LLMCallResult, use result.parsed for validation, enrich failure messages with validation_errors, add explicit type annotation. Fixes 3 failing tests caused by task 4's return type change.

## Plugin & Agents
**Plugin:** backend-development
**Subagents:** python-developer
**Skills:** none

## Phases
1. Implementation - Update executor.py function to handle LLMCallResult return type
2. Testing - Run pytest to verify 3 failing tests now pass
3. Review - Code review for type safety and error handling

## Architecture Decisions

### Keep Executor Pydantic Re-validation
**Choice:** Retain Pydantic validation in executor despite provider already validating
**Rationale:** Provider validation serves retry logic; executor validation serves T model construction. Different purposes, both needed as defensive safety net.
**Alternatives:** Remove redundant validation - rejected, breaks separation of concerns

### Enrich Failure Message with validation_errors
**Choice:** Use f"LLM call failed: {'; '.join(result.validation_errors)}" with empty list handling
**Rationale:** CEO decision - surface provider-level validation errors for better debugging. validation_errors can be empty for network/timeout failures per result.py:90.
**Alternatives:** Keep generic "LLM call failed" message - rejected, loses diagnostic value

### Add Explicit Type Annotation
**Choice:** Add `result: LLMCallResult` annotation + import statement
**Rationale:** CEO decision - improves IDE support, code clarity, makes LLMCallResult dependency explicit
**Alternatives:** Rely on type inference - rejected, less explicit in critical path

## Implementation Steps

### Step 1: Update executor.py imports and function body
**Agent:** backend-development:python-developer
**Skills:** none
**Context7 Docs:** /python/pydantic
**Group:** A

1. Add import line 12: `from llm_pipeline.llm.result import LLMCallResult`
2. Rename variable line 103: `result_dict` → `result` with type annotation `result: LLMCallResult = provider.call_structured(...)`
3. Update None check line 111: `if result_dict is None:` → `if result.parsed is None:`
4. Update failure message line 112: `return result_class.create_failure("LLM call failed")` → `return result_class.create_failure(f"LLM call failed: {'; '.join(result.validation_errors)}" if result.validation_errors else "LLM call failed")`
5. Update Pydantic validation line 117: `result_class.model_validate(result_dict, ...)` → `result_class.model_validate(result.parsed, ...)`
6. Update fallback construction line 121: `result_class(**result_dict)` → `result_class(**result.parsed)`
7. Update docstring lines 34-38 to mention LLMCallResult: "2. Calling LLM via provider with structured output (returns LLMCallResult)"

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Empty validation_errors list breaks string join | Low | Use conditional: `'; '.join(result.validation_errors) if result.validation_errors else "LLM call failed"` |
| Type annotation breaks Python <3.10 | Low | Already using 3.11+ per pyproject.toml, modern syntax OK |
| Downstream tasks 11/16 expect different interface | Low | Verified out of scope - they modify pipeline.py, not executor.py |

## Success Criteria
- [ ] executor.py imports LLMCallResult from llm_pipeline.llm.result
- [ ] result variable has explicit LLMCallResult type annotation
- [ ] None check uses result.parsed instead of result
- [ ] Both Pydantic validation paths use result.parsed
- [ ] Failure message includes validation_errors when present
- [ ] Docstring mentions LLMCallResult in step 2
- [ ] All 3 previously failing tests pass (test_full_execution, test_save_persists_to_db, test_step_state_saved)
- [ ] Full pytest suite passes with no new failures

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Single file, 7 lines changed, well-defined scope, validation_errors handling is simple conditional, no cross-module impact, existing tests cover all paths
**Suggested Exclusions:** testing, review
