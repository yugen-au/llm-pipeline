# Architecture Review

## Overall Assessment
**Status:** complete

Solid implementation of per-agent OTel instrumentation and token usage tracking. All 10 steps are coherent, properly integrated, and backward-compatible. The architecture decisions (per-agent vs global, include_content=False default, sum-all-consensus tokens) are well-reasoned and correctly implemented. 865 tests pass with only 1 pre-existing UI test failure unrelated to this task. The 28 new token tracking tests provide good coverage across normal path, consensus path, None/zero edge cases, and instrumentation threading.

## Project Guidelines Compliance
**CLAUDE.md:** C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md

| Guideline | Status | Notes |
| --- | --- | --- |
| Tests pass | pass | 865 passed, 1 pre-existing failure (test_events_router_prefix), 6 skipped |
| No hardcoded values | pass | All token fields are Optional, thresholds are parameterized |
| Error handling present | pass | Defensive None checks on usage(), OperationalError catch in migration, UnexpectedModelBehavior handled |
| Pydantic v2 / SQLModel patterns | pass | PipelineStepState uses Field(default=None) correctly |
| Build with hatchling | pass | pyproject.toml [otel] group properly structured |

## Issues Found
### Critical
None

### High
None

### Medium

#### PRAGMA migration is SQLite-only; silent skip on non-SQLite engines
**Step:** 1
**Details:** `_migrate_step_state_token_columns()` uses `PRAGMA table_info` which is SQLite-specific. If a non-SQLite engine is passed to `init_pipeline_db()`, the `PRAGMA` call fails and is silently caught by `except OperationalError: pass`. The columns would not be added to an existing non-SQLite table. This is consistent with the existing `SQLiteEventHandler.__init__` migration pattern and the library's current SQLite focus, but should be documented if multi-DB support is planned.

#### StepCompleted emitted with token data on cached path shows None (correct but undocumented)
**Step:** 5
**Details:** When a step is served from cache, `StepCompleted` is emitted with `input_tokens=None, output_tokens=None, total_tokens=None` because `_step_total_requests` remains 0. This is semantically correct (no LLM calls were made), but the `StepCompleted` docstring and `docs/observability.md` do not mention this behavior. Consumers filtering events by token fields should be aware that cached steps emit None tokens.

### Low

#### Redundant total_tokens computation guard in _save_step_state
**Step:** 7
**Details:** `_save_step_state()` (line 1139) has a guard to compute `total_tokens` from `input_tokens + output_tokens` when `total_tokens is None`. However, all callers already compute and pass `total_tokens` explicitly (line 917, and the consensus path via step accumulators). The guard is defensive and harmless but represents dead code in current usage. Acceptable as future-proofing.

#### _mock_usage helper duplicated across test files
**Step:** 10
**Details:** `_mock_usage()` is defined in both `tests/events/conftest.py` (line 374) and `tests/test_token_tracking.py` (line 103) with slightly different signatures (conftest version has no params, test_token_tracking version accepts input_tokens/output_tokens). Could be consolidated into conftest with optional params. Minor DRY concern, no functional issue.

#### docs/observability.md does not mention total_requests on StepCompleted
**Step:** 9
**Details:** The `StepCompleted` event table in `docs/observability.md` (line 130-138) lists `input_tokens`, `output_tokens`, `total_tokens` but does not include `total_requests`. While `StepCompleted` indeed does not have a `total_requests` field (only `PipelineStepState` does), the documentation could clarify this distinction more explicitly to avoid confusion about where `total_requests` is available.

#### consensus _has_any_usage flag not propagated to step-level guard
**Step:** 6
**Details:** In the consensus path, `_execute_with_consensus` returns `None` for token totals when `_has_any_usage is False`. At the call site (line 828), `_c_input or 0` converts `None` to `0`, so `_step_input_tokens` accumulates `0`. Later, the `_step_total_requests > 0` guard (line 920) still triggers because `_consensus_requests` is always incremented, meaning the step-level token values would be `0` (not `None`) even when no provider returned usage. This is functionally correct -- the step did make requests, they just returned no usage data -- but semantically it reports 0 tokens instead of None. Matches test expectations (test_step_completed_tokens_zero_when_no_usage asserts 0).

## Review Checklist
[x] Architecture patterns followed - per-agent instrumentation via constructor injection, clean separation of token capture (pipeline.py) from storage (state.py) from events (types.py)
[x] Code quality and maintainability - clear variable naming (_step_*, _call_*, _consensus_*), consistent defensive None checks, good docstrings
[x] Error handling present - usage() None handling, OperationalError catch in migration, UnexpectedModelBehavior in both paths
[x] No hardcoded values - all fields default to None, thresholds parameterized
[x] Project conventions followed - Optional[int] with Field(), frozen dataclass field ordering valid, snake_case naming, existing migration pattern matched
[x] Security considerations - include_content=False documented and no internal InstrumentationSettings creation with content enabled
[x] Properly scoped (DRY, YAGNI, no over-engineering) - minimal changes, no new event types, no unnecessary abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/state.py | pass | 4 nullable token fields correctly placed after execution_time_ms; Field descriptors consistent |
| llm_pipeline/db/__init__.py | pass | PRAGMA-based migration follows existing pattern; OperationalError guard for missing table; called after create_all |
| llm_pipeline/events/types.py | pass | Token fields on LLMCallCompleted and StepCompleted use default=None after required fields; frozen dataclass ordering valid with kw_only=True |
| llm_pipeline/agent_builders.py | pass | instrument param correctly typed as Any, conditionally passed to Agent(); import under TYPE_CHECKING; docstring updated |
| llm_pipeline/pipeline.py | pass | instrumentation_settings threaded through __init__ to build_step_agent; token accumulators scoped correctly before cache branch; consensus tuple unpacking clean; _save_step_state explicit params |
| pyproject.toml | pass | [otel] group with correct deps; both deps also added to [dev] |
| docs/observability.md | pass | Comprehensive docs covering install, config, include_content, token fields, SQL examples, console exporter example |
| tests/test_token_tracking.py | pass | 28 tests covering all 7 test scenarios from plan; proper use of mocks, fixtures, InMemoryEventHandler |

## New Issues Introduced
- None detected. All changes are additive (nullable columns, optional params, new fields with defaults). Backward compatibility preserved.

## Recommendation
**Decision:** APPROVE

Implementation is architecturally sound, well-tested, and consistent with existing codebase patterns. The medium issues are documentation gaps, not code defects. The low issues are minor DRY/documentation improvements that can be addressed in a follow-up. No blocking issues found.
