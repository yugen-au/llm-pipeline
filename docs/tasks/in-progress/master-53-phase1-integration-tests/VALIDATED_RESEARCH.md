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
| Should tests cover mutable-container mutation edge case? (CEO input needed) | YES -- test both frozen-prevents-reassignment AND list/dict contents can be mutated. Documents convention boundary. | Add dedicated mutable-container tests to test_event_types.py immutability section |
| Coverage baseline -- install dev deps or accept estimate? (CEO input needed) | Install pytest-cov, measure actual baseline BEFORE writing tests. | Must install pytest-cov as first implementation step; baseline measurement gates test design |
| test_event_types.py placement: tests/events/ or tests/ root? (CEO input needed) | tests/events/ -- consolidate with other event tests there. | File goes to tests/events/test_event_types.py; consistent with existing event test layout |

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
All CEO questions resolved. No open items remain.

### Resolved
- ~~Coverage baseline unknown~~ -- RESOLVED: install pytest-cov, measure actual baseline before writing tests
- ~~Mutable-container convention boundary~~ -- RESOLVED: YES, test both frozen-prevents-reassignment and mutable-contents-allowed
- ~~Test file placement~~ -- RESOLVED: tests/events/ (consolidate with other event tests)
- ~~Task 53 description mismatch~~ -- RESOLVED: CEO decision overrides original task description; use tests/events/ path

## Recommendations for Planning

### Pre-implementation (must do first)
1. **Install pytest-cov** and measure actual coverage baseline before writing any tests (CEO decision)
2. Coverage command: `pytest tests/events/ tests/test_emitter.py --cov=llm_pipeline/events --cov-report=term-missing --cov-branch -v`
3. Record baseline number in task log to measure improvement

### Test design
4. Correct all "28" references to "31" in test assertions and documentation
5. Parametrized test fixtures for all 31 event types must include CacheHit with `cached_at` as a datetime field (special case in resolve_event deserialization)
6. PipelineStarted accepts positional args (no kw_only) -- event_factory fixture must handle this asymmetry
7. **Mutable-container convention tests** (CEO decision): verify frozen prevents field reassignment AND verify list/dict contents CAN be mutated (documents convention boundary per types.py docstring)
8. Include deeper context_snapshot tests per task 15 recommendation #3

### File organization
9. **Place test_event_types.py in `tests/events/`** (CEO decision) -- consolidate with other event tests; test_emitter.py at root is the outlier, not the standard
