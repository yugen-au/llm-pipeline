# Research Summary

## Executive Summary

Both research documents are accurate on core findings: 3 GeminiProvider exit points, single production call site in executor.py:103, correct import path at llm_pipeline.llm.result, MockProvider needs updating, LLMCallCompleted.parsed_result vs LLMCallResult.parsed field asymmetry. All line numbers verified against source. One critical gap found and resolved: Task 4 changing MockProvider to return LLMCallResult will break integration tests because executor.py (Task 5 scope) still expects Optional[Dict]. CEO decision: accept temporary breakage -- Task 5 follows immediately. Minor contradiction between research docs on not-found exit construction resolved in favor of plain constructor. All questions answered, ready for planning.

## Domain Findings

### GeminiProvider Exit Points
**Source:** step-1, step-2, gemini.py verification

Three exit points confirmed at exact lines cited:
- Line 114: not-found indicator match -> `return None`
- Line 184: all validations pass -> `return response_json`
- Line 216: retry loop exhaustion -> `return None`

Exception handler (lines 186-213) does NOT create a 4th exit; last-attempt exceptions fall through to line 216.

### Call Site Analysis
**Source:** step-1, executor.py verification

Single production call site at executor.py:103. Grep confirms no other `.call_structured(` invocations in Python source files. executor.py:111 checks `if result_dict is None:`, lines 116-121 do Pydantic re-validation on the raw dict.

### LLMCallResult Structure
**Source:** step-2, result.py verification

5 fields, 2 factory classmethods, 2 properties, 2 serialization methods. All confirmed at llm_pipeline/llm/result.py. `frozen=True, slots=True`. Factory signatures:
- `success()`: requires `raw_response: str`, `model_name: str`, rejects parsed=None
- `failure()`: requires `raw_response: str` (NOT Optional), `validation_errors: list[str]`, rejects parsed!=None

### Import Path
**Source:** step-1, step-2, filesystem verification

Correct: `from llm_pipeline.llm.result import LLMCallResult` or relative `from .result import LLMCallResult`. Task 4 spec says `from events.result` which is wrong -- no events/result.py exists. Re-export from `llm_pipeline.events` is valid but canonical home is `llm_pipeline.llm.result`.

### Field Name Asymmetry
**Source:** step-1, step-2, events/types.py:336 verification

LLMCallCompleted uses `parsed_result` (line 336), LLMCallResult uses `parsed` (line 20). Mapping trivial but must be explicit when emitting events (future task scope).

### MockProvider & Test Suite
**Source:** step-1, test_pipeline.py:34-46 verification

MockProvider subclasses LLMProvider, returns raw dict or None. Used by TestPipelineExecution tests (lines 333-401) which exercise full pipeline flow through executor.py.

## Gaps & Contradictions Found

### CRITICAL: Test Breakage Window Between Task 4 and Task 5

Task 4 changes the ABC return type + MockProvider. Task 5 changes executor.py to handle LLMCallResult. Between these tasks, MockProvider returns LLMCallResult but executor.py still does `if result_dict is None:` -- LLMCallResult is never None, so the None check passes, then `result_class(**result_dict)` fails because Pydantic receives an LLMCallResult instead of a dict.

All integration tests in TestPipelineExecution (test_full_execution, test_save_persists_to_db, test_step_state_saved) will break.

### MINOR: Not-Found Exit Construction Contradiction

Step 1 research table says not-found should use `failure(raw_response=response_text, ...)`. Step 2 research says use plain constructor `LLMCallResult(parsed=None, ...)` because it's "semantically not a retry-exhaustion failure." Step 2 reasoning is more thorough and correct -- failure() factory is for the exhaustion case. But this needs a consistent decision.

### MINOR: failure() Factory raw_response Type Mismatch

failure() requires `raw_response: str` (non-Optional). For the exhaustion exit where all attempts threw exceptions before response.text was captured, `last_raw_response` could be None. Options: use empty string fallback `last_raw or ""`, or use plain constructor which accepts `str | None`.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Task 4 changes MockProvider -> LLMCallResult, but executor.py (Task 5) still expects Dict. All integration tests break between Task 4 and Task 5. Strategy? Options: (A) merge Task 4+5 into single atomic change, (B) Task 4 includes minimal executor.py patch, (C) accept temporary test failure, (D) other? | (C) Accept temporary test breakage. Task 5 follows immediately. Test automator must be informed failures from Optional[Dict] -> LLMCallResult change are INTENTIONAL, resolved by Task 5 (executor.py update). Do NOT fix in Task 4 scope. | Task 4 scope stays clean: ABC + GeminiProvider + MockProvider only. executor.py untouched. Known-broken tests: test_full_execution, test_save_persists_to_db, test_step_state_saved. |

## Assumptions Validated

- [x] 3 GeminiProvider exit points at lines 114, 184, 216 (verified against gemini.py)
- [x] Single production call site at executor.py:103 (grep confirmed)
- [x] Import path is `from llm_pipeline.llm.result import LLMCallResult` (no events/result.py)
- [x] MockProvider at test_pipeline.py:34 returns raw dict, must change for ABC compliance
- [x] No other LLMProvider subclasses exist (only GeminiProvider + MockProvider)
- [x] LLMCallResult frozen=True means fields immutable after construction
- [x] All data for LLMCallResult fields available inside GeminiProvider (model_name, response.text, attempt counter)
- [x] LLMCallCompleted.parsed_result vs LLMCallResult.parsed asymmetry exists (events/types.py:336 vs result.py:20)
- [x] failure() factory requires raw_response: str (not Optional) -- may need fallback for all-exception case
- [x] success() factory rejects parsed=None (ValueError)
- [x] Re-exports from both llm/__init__.py and events/__init__.py are in place

## Open Items

All resolved.

- ~~Test breakage strategy~~ -- RESOLVED: accept temporary breakage, Task 5 follows immediately, do NOT fix in Task 4 scope
- ~~Not-found construction approach~~ -- RESOLVED: use plain constructor `LLMCallResult(parsed=None, ...)` per Step 2 reasoning
- ~~Exhaustion exit raw_response~~ -- RESOLVED: use plain constructor which accepts `str | None`, avoids failure() factory's str requirement

## Recommendations for Planning

1. **Scope:** ABC (provider.py) + GeminiProvider (gemini.py) + MockProvider (test_pipeline.py) only. Do NOT touch executor.py.
2. **Known breakage:** TestPipelineExecution tests (test_full_execution, test_save_persists_to_db, test_step_state_saved) will fail after Task 4. Intentional -- resolved by Task 5.
3. **Not-found exit (line 114):** Use plain constructor `LLMCallResult(parsed=None, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=[])`.
4. **Success exit (line 184):** Use `LLMCallResult.success(parsed=response_json, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=accumulated_errors)`.
5. **Exhaustion exit (line 216):** Use plain constructor `LLMCallResult(parsed=None, raw_response=last_raw_response, model_name=self.model_name, attempt_count=max_retries, validation_errors=accumulated_errors)`.
6. **State tracking:** Initialize `last_raw_response: str | None = None` and `accumulated_errors: list[str] = []` before the retry loop.
7. **Import path:** Use `from .result import LLMCallResult` in gemini.py (same package). Correct Task 4 spec from `events.result`.
8. **MockProvider:** Wrap responses in `LLMCallResult(parsed=response)` or `LLMCallResult(parsed=None)` for None case.
9. **New tests:** Task 4 unit tests should cover GeminiProvider returning LLMCallResult for all 3 exit paths. Do NOT expect integration tests to pass.
