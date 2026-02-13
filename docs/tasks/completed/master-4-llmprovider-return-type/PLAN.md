# PLANNING

## Summary
Update LLMProvider.call_structured() abstract method return type from Optional[Dict] to LLMCallResult. Modify GeminiProvider's 3 exit points (not-found, success, exhaustion) to construct and return LLMCallResult with parsed, raw_response, model_name, attempt_count, validation_errors. Update MockProvider in tests. CEO decision: accept temporary test breakage - Task 5 updates executor.py to handle new type.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** code-modifier, test-engineer
**Skills:** none

## Phases
1. Implementation - Code changes to ABC, GeminiProvider, MockProvider

## Architecture Decisions

### Exit Point Construction Strategy
**Choice:** Use plain constructor for not-found and exhaustion exits, success() factory for success exit
**Rationale:** Plain constructor accepts str | None for raw_response (needed for exhaustion where all attempts may have thrown exceptions before capturing response.text). success() factory validates parsed is non-None. Validated research recommends plain constructor for not-found case - semantically distinct from retry-exhaustion failure.
**Alternatives:** Use factories for all exits - rejected because failure() requires raw_response: str (non-Optional), causing mismatch when all attempts fail with exceptions. Use plain constructor everywhere - valid but success() factory provides useful validation.

### State Tracking in GeminiProvider
**Choice:** Track last_raw_response: str | None and accumulated_errors: list[str] across retry loop
**Rationale:** attempt_count already tracked via loop variable. raw_response available at each attempt as response.text. validation_errors accumulate across attempts (validation, array validation, Pydantic errors). Tracking enables full LLMCallResult construction at exhaustion exit.
**Alternatives:** Construct LLMCallResult on each attempt - rejected because success exit needs accumulated_errors from prior attempts. Track attempt history list - overkill for current needs.

### MockProvider Wrapping
**Choice:** Wrap dict responses in LLMCallResult.success(), None responses in plain constructor with parsed=None
**Rationale:** MockProvider has fixed responses list + fallback to None. Dict responses are valid parsed output - use success() factory. None case represents failure - use plain constructor. Mock model_name as "mock-model", attempt_count as 1, raw_response as json.dumps(response) or "".
**Alternatives:** Use failure() factory for None case - rejected because failure() requires raw_response: str and validation_errors: list[str], adding unnecessary ceremony for simple mock.

## Implementation Steps

### Step 1: Update LLMProvider ABC return type
**Agent:** python-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Open llm_pipeline/llm/provider.py
2. Add import: `from llm_pipeline.llm.result import LLMCallResult`
3. Change call_structured() return annotation from `-> Optional[Dict[str, Any]]` to `-> LLMCallResult`
4. Update docstring return section to reflect new type

### Step 2: Update GeminiProvider to construct LLMCallResult
**Agent:** python-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Open llm_pipeline/llm/gemini.py
2. Add import: `from .result import LLMCallResult`
3. Before retry loop (~line 90), initialize tracking: `last_raw_response: str | None = None` and `accumulated_errors: list[str] = []`
4. Inside loop after capturing response.text (~line 106), assign: `last_raw_response = response_text`
5. After each validation failure (validation, array validation, Pydantic), append error strings to accumulated_errors list
6. Replace not-found exit (~line 114) from `return None` to: `return LLMCallResult(parsed=None, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=[])`
7. Replace success exit (~line 184) from `return response_json` to: `return LLMCallResult.success(parsed=response_json, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=accumulated_errors)`
8. Replace exhaustion exit (~line 216) from `return None` to: `return LLMCallResult(parsed=None, raw_response=last_raw_response, model_name=self.model_name, attempt_count=max_retries, validation_errors=accumulated_errors)`

### Step 3: Update MockProvider to return LLMCallResult
**Agent:** python-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Open tests/test_pipeline.py
2. Add import after LLMProvider import: `from llm_pipeline.llm.result import LLMCallResult`
3. Import json module for mock raw_response: `import json`
4. Replace call_structured() body dict return (~line 43-45) with: `return LLMCallResult.success(parsed=response, raw_response=json.dumps(response), model_name="mock-model", attempt_count=1)`
5. Replace None return (~line 46) with: `return LLMCallResult(parsed=None, raw_response="", model_name="mock-model", attempt_count=1, validation_errors=[])`

### Step 4: Update __init__.py exports if needed
**Agent:** python-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Open llm_pipeline/llm/__init__.py
2. Verify LLMCallResult already exported (validated research confirms it is)
3. If missing, add to __all__ list: `"LLMCallResult"`

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Integration tests (test_full_execution, test_save_persists_to_db, test_step_state_saved) break because executor.py still expects Optional[Dict] | High | CEO decision: accept temporary breakage. Task 5 follows immediately to update executor.py. Inform test automator failures are INTENTIONAL. |
| GeminiProvider state tracking (accumulated_errors) increases memory per call | Low | Validation errors are short strings, max_retries defaults to 3, negligible memory overhead. |
| MockProvider simplified wrapping may not cover all test scenarios | Medium | MockProvider is test-only code. If additional scenarios arise, expand MockProvider constructor to accept LLMCallResult parameters. |
| Plain constructor accepts mutable containers (parsed dict, validation_errors list) - mutation post-construction violates frozen=True intent | Low | Dataclass frozen=True prevents reassignment, not mutation of contained objects. Documentation warns against mutation. GeminiProvider constructs fresh lists/dicts per call. |

## Success Criteria
- [ ] LLMProvider.call_structured() ABC signature returns LLMCallResult (type checker passes)
- [ ] GeminiProvider returns LLMCallResult at all 3 exit points with correct fields
- [ ] MockProvider returns LLMCallResult (wrapped dict or parsed=None)
- [ ] llm_pipeline/llm/__init__.py exports LLMCallResult
- [ ] No syntax errors, mypy/pylint clean on modified files
- [ ] Unit tests for GeminiProvider return type added (success, not-found, exhaustion)
- [ ] Integration tests break as expected (executor.py incompatibility documented)

## Phase Recommendation
**Risk Level:** medium
**Reasoning:** Changes are localized to ABC + 2 implementations. Type signature change is breaking but scope is narrow (single call site in executor.py). Research validated all decisions. Main risk is downstream breakage (intended, documented). No schema changes, no external API changes.
**Suggested Exclusions:** review
