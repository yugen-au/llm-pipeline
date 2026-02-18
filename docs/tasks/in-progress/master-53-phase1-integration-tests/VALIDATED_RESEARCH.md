# Research Summary

## Executive Summary

Validated step-1 (codebase analysis) and step-2 (testing patterns) against actual codebase. One critical factual error found: research claims 28 event types but codebase has **31** concrete event types. All test assertions referencing "28" would fail. Step-2 self-corrected step-1's CompositeEmitter gap (test_emitter.py exists with 20 tests). Coverage estimate of ~85% is unverified -- pytest-cov not currently installed in venv. Remaining research findings (event hierarchy, handler implementations, thread safety, test patterns, emission points) are accurate and validated against source code.

## Domain Findings

### Event Type Count (CRITICAL CORRECTION)
**Source:** step-1-codebase-event-system-analysis.md, section 1
**Issue:** Header says "All 28 Concrete Event Types" but the actual registry has 31 concrete types.

Verified count by category from `llm_pipeline/events/types.py`:
| Category | Count | Types |
| --- | --- | --- |
| Pipeline Lifecycle | 3 | PipelineStarted, PipelineCompleted, PipelineError |
| Step Lifecycle | 5 | StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted |
| Cache | 4 | CacheLookup, CacheHit, CacheMiss, CacheReconstruction |
| LLM Call | 6 | LLMCallPrepared, LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited |
| Consensus | 4 | ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed |
| Instructions/Context | 3 | InstructionsStored, InstructionsLogged, ContextUpdated |
| Transformation | 2 | TransformationStarting, TransformationCompleted |
| Extraction | 3 | ExtractionStarting, ExtractionCompleted, ExtractionError |
| State | 1 | StateSaved |
| **Total** | **31** | |

Note: The research tables themselves list all 31 types correctly -- only the header count "28" and all downstream references to "28" are wrong. Step-2 repeats "28" in test patterns (e.g., `assert len(_EVENT_REGISTRY) == 28`), which would fail.

### CompositeEmitter Gap (SELF-CORRECTED)
**Source:** step-1 section 7 gap 1, corrected by step-2 section 1
Step-1 listed "CompositeEmitter -- NO dedicated tests at all" as gap 1. Step-2 correctly identified `tests/test_emitter.py` with 20 tests covering: Protocol conformance (4), instantiation (4), emit dispatch (3), error isolation (3), thread safety (2), repr/slots (4). No action needed.

### Event Hierarchy and Registration Mechanism
**Source:** step-1 sections 1, 3
All claims validated against `llm_pipeline/events/types.py`:
- `_skip_registry` check uses `cls.__dict__` (line 99), not `hasattr()` -- subclasses of StepScopedEvent correctly register
- `_derive_event_type()` uses two-pass regex (lines 49-51) for CamelCase->snake_case
- `__post_init__` uses `object.__setattr__` to bypass frozen (line 108)
- `resolve_event()` raises `ValueError("Unknown event_type: ...")` for unknown types (line 135)
- `resolve_event()` deserializes datetime for "timestamp" and "cached_at" fields only (lines 137-142)

### Handler Implementations
**Source:** step-1 section 2, step-2 sections 3-4
All claims validated against `llm_pipeline/events/handlers.py`:
- InMemoryEventHandler thread-safe via `threading.Lock` (lines 103, 107, 116, 132)
- `get_events()` returns shallow copy outside lock (line 117)
- SQLiteEventHandler uses session-per-emit pattern (lines 164-176)
- LoggingEventHandler uses `DEFAULT_LEVEL_MAP` with category-based levels (lines 34-46, 69-70)

### Existing Test Infrastructure
**Source:** step-2 sections 1, 7
Validated against filesystem:
- 10 test files in `tests/events/` + 1 `tests/test_emitter.py` (confirmed via glob)
- No root conftest.py (confirmed)
- No `tests/events/__init__.py` (confirmed)
- `pyproject.toml`: `testpaths = ["tests"]`, `pythonpath = ["."]` (confirmed lines 28-29)
- conftest.py provides: MockProvider, 5 step types, 5 pipeline configs, 3 fixtures (confirmed)

### Upstream Task Context
**Source:** Task 15 SUMMARY.md
Key facts from task 15 completion relevant to task 53:
- `InstructionsLogged.logged_keys` is always `[step.step_name]` (confirmed in task 15 summary)
- `ContextUpdated` always emits, including when `new_keys=[]` (task 15 decision)
- `StateSaved` emitted only on fresh path, not cached (task 15 design)
- Task 15 recommendation #3 explicitly says task 53 should add deeper `context_snapshot` coverage
- 318 tests passed at task 15 completion
- Unused `_ctx_state_events()` helper exists in test_ctx_state_events.py (LOW priority cleanup)

### Coverage Estimate
**Source:** step-2 section 8
The "~85% current, >93% target" estimates are unverified. `pytest-cov` is not installed in the current venv (no pip available either). The estimates appear reasonable based on code inspection (types.py utility functions are untested, event class definitions are exercised transitively) but exact numbers are unknown.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Event count 31 vs 28 -- simple miscount or were types added recently? | Verified via git log: types.py unchanged since task 14. All 31 types existed when research was conducted. Simple miscount in header; tables are accurate. | All test assertions using "28" must use "31" |
| Should tests cover mutable-container mutation edge case? (CEO input needed) | PENDING | Affects scope of test_event_types.py immutability tests |
| Coverage baseline -- install dev deps or accept estimate? (CEO input needed) | PENDING | Affects confidence in coverage target |
| test_event_types.py placement: tests/events/ or tests/ root? (CEO input needed) | PENDING | Affects file organization |

## Assumptions Validated
- [x] 9 event categories with correct category constants (validated against types.py lines 27-35)
- [x] StepScopedEvent excluded from registry via _skip_registry=True + cls.__dict__ check
- [x] PipelineEvent base not in registry (no _derived_event_type set on base)
- [x] CompositeEmitter error isolation: catches Exception, logs, continues (emitter.py lines 60-67)
- [x] CompositeEmitter sequential dispatch, not parallel (emitter.py line 59 for-loop)
- [x] InMemoryEventHandler stores events as dicts via to_dict() (handlers.py line 108)
- [x] test_emitter.py exists with 20 tests covering all CompositeEmitter behaviors
- [x] MockProvider returns LLMCallResult.success() with configurable responses (conftest.py lines 40-58)
- [x] PipelineStarted is the only event type accepting positional args (no kw_only on line 169)
- [x] resolve_event() handles only "timestamp" and "cached_at" datetime fields (types.py line 137)
- [x] Task 15 confirmed logged_keys=[step.step_name] pattern
- [x] Task 15 confirmed StateSaved fresh-path-only design
- [x] Task 15 recommended deeper context_snapshot coverage for task 53

## Open Items
- Coverage baseline unknown -- pytest-cov not installed in venv, actual percentage unverifiable until dev deps installed
- Mutable-container convention boundary: frozen dataclass prevents field reassignment but allows mutation of dict/list field contents (types.py docstring lines 6-7). Research test patterns do not cover this edge case. CEO decision needed on whether to test.
- Test file placement: research recommends `tests/events/test_event_types.py` but `test_emitter.py` (also testing events internals) lives at `tests/` root. Consistency question.
- Task 53 description in TaskMaster references creating `tests/test_events.py` (singular, at root) while research recommends 2 files in `tests/events/`. Mismatch with original task description.

## Recommendations for Planning
1. Correct all "28" references to "31" in test assertions and documentation
2. Parametrized test fixtures for all 31 event types must include CacheHit with `cached_at` as a datetime field (special case in resolve_event deserialization)
3. PipelineStarted accepts positional args (no kw_only) -- event_factory fixture must handle this asymmetry
4. Add mutable-container convention tests: verify frozen prevents field reassignment, verify list/dict contents CAN be mutated (documents the convention boundary per types.py docstring)
5. Place test_event_types.py in `tests/events/` to keep event tests consolidated (test_emitter.py at root is the outlier, not the standard)
6. Include deeper context_snapshot tests per task 15 recommendation #3
7. Install dev deps (pytest, pytest-cov) before implementation to establish actual coverage baseline
8. Coverage command: `pytest tests/events/ tests/test_emitter.py --cov=llm_pipeline/events --cov-report=term-missing --cov-branch -v`
