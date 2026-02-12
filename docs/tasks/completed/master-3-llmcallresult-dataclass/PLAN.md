# PLANNING

## Summary
Add 6 helper methods to existing LLMCallResult dataclass (to_dict, to_json, is_success/is_failure properties, success/failure classmethod factories) and create comprehensive unit test suite covering all fields, methods, factories, immutability, and edge cases.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** python-developer
**Skills:** none

## Phases
1. Implementation: Add methods to llm_pipeline/llm/result.py
2. Testing: Create tests/test_llm_call_result.py with 100% coverage

## Architecture Decisions

### Decision: Keep stdlib dataclass over Pydantic
**Choice:** Retain @dataclass(frozen=True, slots=True)
**Rationale:** Validated in research - 10-50x faster construction, matches PipelineEvent pattern (all 31 events use stdlib dataclass), no runtime validation needed (internal value object), zero overhead hot path
**Alternatives:** Pydantic BaseModel rejected (unnecessary overhead, breaks consistency)

### Decision: is_success semantics
**Choice:** is_success = parsed is not None, ignore validation_errors
**Rationale:** CEO validated - validation_errors are diagnostic from prior attempts only. Partial success (parsed + errors) counts as success. Simple None-check, no compound condition
**Alternatives:** is_success = parsed and not validation_errors rejected (incorrect semantics per CEO)

### Decision: Serialization pattern
**Choice:** to_dict() using asdict(), to_json() wrapping json.dumps(to_dict())
**Rationale:** Matches PipelineEvent.to_dict/to_json pattern exactly. All LLMCallResult fields JSON-native (no datetime conversion needed), zero custom logic required
**Alternatives:** Custom dict construction rejected (unnecessary complexity, breaks consistency)

### Decision: Factory pattern
**Choice:** success() and failure() classmethods with invariant enforcement
**Rationale:** Matches existing LLMResultMixin.create_failure() pattern, encapsulates construction rules (success forces parsed non-None, failure forces parsed=None), prevents invalid states
**Alternatives:** Plain constructor rejected (no invariant enforcement, error-prone)

## Implementation Steps

### Step 1: Add helper methods to LLMCallResult
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Read llm_pipeline/llm/result.py to get current dataclass definition
2. Add imports: json, asdict from dataclasses
3. Add to_dict() method: return asdict(self) (all fields JSON-native, no datetime conversion)
4. Add to_json() method: return json.dumps(self.to_dict())
5. Add @property is_success(self) -> bool: return self.parsed is not None
6. Add @property is_failure(self) -> bool: return self.parsed is None
7. Add @classmethod success(...) factory: enforce parsed is not None, default validation_errors=[], return LLMCallResult(...)
8. Add @classmethod failure(...) factory: enforce parsed=None, require validation_errors param (document empty list valid for timeout/network), return LLMCallResult(...)
9. Add docstrings matching PipelineEvent style

### Step 2: Create unit test suite
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** /pytest-dev/pytest
**Group:** B

1. Create tests/test_llm_call_result.py
2. Add imports: pytest, LLMCallResult from llm_pipeline.llm
3. Add test_instantiation_defaults: verify parsed=None, raw_response=None, model_name=None, attempt_count=1, validation_errors=[]
4. Add test_instantiation_all_fields: set all fields, verify all set
5. Add test_success_factory: call LLMCallResult.success(), verify parsed non-None, validation_errors=[], is_success=True, is_failure=False
6. Add test_failure_factory: call LLMCallResult.failure(), verify parsed=None, is_success=False, is_failure=True
7. Add test_failure_factory_empty_errors: call failure(validation_errors=[]), verify accepted (timeout/network case)
8. Add test_to_dict_all_none: call to_dict() on default instance, verify all keys present with None/default values
9. Add test_to_dict_all_set: call to_dict() with all fields set, verify dict matches
10. Add test_to_json_structure: call to_json(), json.loads result, verify valid JSON dict
11. Add test_is_success_true: parsed={}, verify is_success=True
12. Add test_is_success_false: parsed=None, verify is_success=False
13. Add test_partial_success: parsed={}, validation_errors=["prior error"], verify is_success=True (errors ignored)
14. Add test_is_failure_true: parsed=None, verify is_failure=True
15. Add test_is_failure_false: parsed={}, verify is_failure=False
16. Add test_frozen_immutability: create instance, attempt field reassignment, verify FrozenInstanceError
17. Add test_equality: create two instances with same values, verify ==
18. Add test_inequality: create two instances with different values, verify !=

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Task 4 import path references events/result.py not llm/result.py | Low | Document in PLAN.md - Task 4 needs import path update to llm_pipeline.llm.result or llm_pipeline.events (re-export) |
| failure() factory with empty validation_errors may confuse users | Low | Add docstring note: empty list valid for timeout/network failures where no validation occurred |
| Unhashable frozen dataclass (dict/list fields) | Low | Acceptable - matches PipelineEvent pattern, no hashing use case, CEO aware |

## Success Criteria

- [ ] to_dict() returns dict with all 5 fields, no datetime conversion logic
- [ ] to_json() returns valid JSON string matching to_dict() output
- [ ] is_success property returns True when parsed is not None, False otherwise
- [ ] is_failure property returns True when parsed is None, False otherwise
- [ ] success() factory creates instance with parsed non-None, validation_errors=[]
- [ ] failure() factory creates instance with parsed=None, accepts empty validation_errors
- [ ] All helper methods have docstrings matching PipelineEvent style
- [ ] test_llm_call_result.py created with 18 tests covering all methods, factories, fields, immutability
- [ ] All tests pass with pytest
- [ ] No existing tests broken (verified llm_pipeline not used in test_pipeline.py yet)
- [ ] Partial success case (parsed + errors) verified as is_success=True

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Pure additive changes to unused dataclass (no dependencies yet per research), no DB/API changes, simple stdlib patterns matching existing codebase conventions, comprehensive test coverage planned
**Suggested Exclusions:** testing, review
