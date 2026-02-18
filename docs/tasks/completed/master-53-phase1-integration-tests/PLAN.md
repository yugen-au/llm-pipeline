# PLANNING

## Summary

Create `tests/events/test_event_types.py` to fill the single remaining gap in the events package test suite: unit-level tests of `types.py` internals (registry, `_derive_event_type`, serialization round-trip, frozen immutability, and mutable-container convention boundary). All 31 concrete event types must be covered. pytest-cov 7.0.0 is already installed; the implementing agent must measure a baseline before writing any tests and record the number in the task log.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** [available agents]
**Skills:** none

## Phases
1. **Baseline measurement**: Run coverage command before writing tests, record baseline % to task log
2. **Implementation**: Create `tests/events/test_event_types.py` with all test sections

## Architecture Decisions

### Test file location
**Choice:** `tests/events/test_event_types.py`
**Rationale:** CEO decision. Consolidates with the other 10 event test modules in `tests/events/`. `test_emitter.py` at tests root is the outlier.
**Alternatives:** `tests/test_event_types.py` (root) - rejected by CEO.

### event_factory approach
**Choice:** Module-level `EVENT_FIXTURES` list of `(event_type_str, kwargs_dict)` tuples for `@pytest.mark.parametrize`, plus a small `_make_event(cls, **overrides)` helper for non-parametrized tests.
**Rationale:** Matches existing codebase pattern (step-2 research section 6.2). Keeps parametrize IDs as readable event_type strings. PipelineStarted asymmetry (no kw_only) handled explicitly in its tuple - positional args passed as keyword args still work.
**Alternatives:** pytest fixture factory - adds indirection without benefit for a static fixture list.

### Mutable-container test design
**Choice:** Two sub-tests: (a) frozen prevents field reassignment -> `FrozenInstanceError` (subclass of `AttributeError`); (b) list/dict contents CAN be mutated (frozen only prevents the field reference being replaced, not mutation of the object it points to). Explicit assertion that `event.new_keys.append("x")` succeeds and mutates in-place.
**Rationale:** CEO decision. Documents the convention boundary documented in types.py docstring. Tests both sides: what frozen DOES enforce and what it does NOT.
**Alternatives:** Test only the frozen side - insufficient, misses the mutation-allowed side.

### Context snapshot depth
**Choice:** Add `TestContextSnapshotDepth` class that constructs `ContextUpdated` directly with a known dict, mutates the original dict, and asserts the event's `context_snapshot` is NOT affected (i.e., pipeline must have passed a copy). Also test that `context_snapshot` contains exact keys matching post-merge state in a two-step pipeline run (integration-style test reusing `SuccessPipeline` fixture).
**Rationale:** Task 15 recommendation #3 explicitly requested deeper context_snapshot coverage. Direct construction test is fast and deterministic; integration test validates the copy-on-emit behavior end-to-end.
**Alternatives:** Skip integration variant - misses the "snapshot is a copy, not a reference" validation.

### CacheHit special case in parametrized round-trip
**Choice:** Include `CacheHit` with `cached_at=datetime.utcnow()` in EVENT_FIXTURES. `resolve_event()` deserializes both `"timestamp"` and `"cached_at"` fields; the parametrized round-trip will exercise this path automatically.
**Rationale:** VALIDATED_RESEARCH confirms `resolve_event()` only deserializes these two datetime fields (types.py lines 137-142). CacheHit is the only event with a second datetime field.
**Alternatives:** Separate dedicated test for CacheHit datetime - add as extra assertion in `TestResolveEventSpecialCases` for clarity alongside the parametrized test.

## Implementation Steps

### Step 1: Create tests/events/test_event_types.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pytest-dev/pytest
**Group:** A

Pre-flight (before writing any test code):
1. Run coverage baseline: `pytest tests/events/ tests/test_emitter.py --cov=llm_pipeline/events --cov-report=term-missing --cov-branch -q 2>&1` and record the overall % to the task log using `task-master update-subtask`.

File structure to create at `tests/events/test_event_types.py`:

2. Module docstring: explain this file tests `types.py` internals (registry, derive, serialization, frozen, mutable-container convention).

3. Imports block:
   - `import json, pytest, dataclasses` from stdlib
   - `from datetime import datetime`
   - `from llm_pipeline.events.types import (PipelineEvent, StepScopedEvent, _EVENT_REGISTRY, _derive_event_type, CATEGORY_*, all 31 concrete event classes)`

4. `EVENT_FIXTURES` module-level list: list of `(event_type_str, kwargs_dict)` tuples for all 31 events. Notes for building this list:
   - Common base kwargs: `run_id="test-run-id"`, `pipeline_name="test_pipeline"`
   - StepScopedEvent subclasses: add `step_name="test_step"` to defaults
   - PipelineStarted: positional-compatible (no kw_only), use keyword form `PipelineStarted(run_id=..., pipeline_name=...)`
   - PipelineCompleted: add `execution_time_ms=100.0`, `steps_executed=2`
   - PipelineError: add `error_type="ValueError"`, `error_message="test error"`, optional `traceback=None`
   - CacheHit: add `cached_at=datetime(2024, 1, 1, 12, 0, 0)` (fixed datetime for determinism)
   - CacheLookup, CacheMiss: add `input_hash="abc123"`
   - CacheReconstruction: add `model_count=2`, `instance_count=5`
   - StepSelecting: add `step_index=0`, `strategy_count=1`
   - StepSelected: add `step_number=1`, `strategy_name="test_strategy"`
   - StepSkipped: add `step_number=1`, `reason="should_skip returned True"`
   - StepStarted: add `step_number=1`
   - StepCompleted: add `step_number=1`, `execution_time_ms=50.0`
   - LLMCallPrepared: add `call_count=1`
   - LLMCallStarting: add `call_index=0`, `rendered_system_prompt="sys"`, `rendered_user_prompt="usr"`
   - LLMCallCompleted: add `call_index=0`, `raw_response="resp"`, `parsed_result={"key": "val"}`, `model_name="mock-model"`, `attempt_count=1`
   - LLMCallRetry: add `attempt=1`, `max_retries=3`, `error_type="ValueError"`, `error_message="err"`
   - LLMCallFailed: add `max_retries=3`, `last_error="failed"`
   - LLMCallRateLimited: add `attempt=1`, `wait_seconds=1.0`, `backoff_type="exponential"`
   - ConsensusStarted: add `threshold=2`, `max_calls=6`
   - ConsensusAttempt: add `attempt=1`, `group_count=3`
   - ConsensusReached: add `attempt=2`, `threshold=2`
   - ConsensusFailed: add `max_calls=6`, `largest_group_size=1`
   - InstructionsStored: add `instruction_count=3`
   - InstructionsLogged: add `logged_keys=["test_step"]`
   - ContextUpdated: add `new_keys=["total"]`, `context_snapshot={"total": 5}`
   - TransformationStarting: add `transformation_class="TestTransformation"`, `cached=False`
   - TransformationCompleted: add `data_key="output"`, `execution_time_ms=10.0`, `cached=False`
   - ExtractionStarting: add `extraction_class="TestExtraction"`, `model_class="Item"`
   - ExtractionCompleted: add `extraction_class="TestExtraction"`, `model_class="Item"`, `instance_count=2`, `execution_time_ms=5.0`
   - ExtractionError: add `extraction_class="TestExtraction"`, `error_type="ValueError"`, `error_message="extraction failed"`
   - StateSaved: add `step_number=1`, `input_hash="abc123"`, `execution_time_ms=20.0`

5. `class TestDeriveEventType`: parametrized tests for `_derive_event_type()`:
   - Parametrize `(camel, expected_snake)` pairs including at minimum: `PipelineStarted->pipeline_started`, `LLMCallStarting->llm_call_starting`, `LLMCallCompleted->llm_call_completed`, `CacheHit->cache_hit`, `StepCompleted->step_completed`, `ConsensusReached->consensus_reached`, `ExtractionError->extraction_error`, `StateSaved->state_saved`
   - `test_derive_event_type`: assert `_derive_event_type(camel) == expected_snake`

6. `class TestEventRegistry`:
   - `test_registry_has_31_event_types`: `assert len(_EVENT_REGISTRY) == 31`
   - `test_step_scoped_event_not_in_registry`: `assert "step_scoped_event" not in _EVENT_REGISTRY`
   - `test_pipeline_event_base_not_in_registry`: `assert "pipeline_event" not in _EVENT_REGISTRY`
   - `test_all_values_are_pipeline_event_subclasses`: for cls in `_EVENT_REGISTRY.values()`, assert `issubclass(cls, PipelineEvent)`
   - `test_resolve_event_unknown_type_raises_value_error`: `pytest.raises(ValueError, match="Unknown event_type")` calling `PipelineEvent.resolve_event("no_such_type", {})`
   - Parametrized `test_each_event_type_registered(event_type, kwargs)` over `EVENT_FIXTURES`: assert `event_type in _EVENT_REGISTRY`

7. `class TestEventCategory`:
   - Build `EXPECTED_CATEGORIES` dict mapping event_type_str to expected category constant (all 31 entries, correct category per VALIDATED_RESEARCH table)
   - Parametrize `test_event_category(event_type, expected_category)`: get cls from registry, assert `cls.EVENT_CATEGORY == expected_category`

8. `class TestEventImmutability`:
   - `test_frozen_prevents_run_id_reassignment`: create `PipelineStarted`, try `event.run_id = "x"`, assert raises `AttributeError` (FrozenInstanceError is a subclass)
   - `test_frozen_prevents_pipeline_name_reassignment`: same pattern for `pipeline_name`
   - `test_frozen_prevents_new_attribute`: try `event.new_attr = "x"`, assert raises `AttributeError`
   - `test_frozen_prevents_event_type_reassignment`: try to reassign `event.event_type`, assert raises `AttributeError`
   - `test_event_type_field_set_correctly_by_post_init`: create `PipelineStarted`, assert `event.event_type == "pipeline_started"` (verifies `__post_init__` bypass via `object.__setattr__`)

9. `class TestMutableContainerConvention` (CEO decision - documents convention boundary):
   - `test_frozen_prevents_list_field_reassignment`: create `InstructionsLogged(logged_keys=["a"])`, try `event.logged_keys = ["b"]`, assert raises `AttributeError`
   - `test_list_contents_can_be_mutated_by_convention`: create `InstructionsLogged(logged_keys=["a"])`, do `event.logged_keys.append("b")`, assert `event.logged_keys == ["a", "b"]` (mutation succeeds - frozen does NOT prevent this). Add inline comment: `# frozen prevents reassignment but not mutation of the container's contents`
   - `test_frozen_prevents_dict_field_reassignment`: create `ContextUpdated(new_keys=[], context_snapshot={"k": "v"}, ...)`, try `event.context_snapshot = {}`, assert raises `AttributeError`
   - `test_dict_contents_can_be_mutated_by_convention`: same event, do `event.context_snapshot["new_key"] = "x"`, assert `"new_key" in event.context_snapshot`. Add inline comment explaining convention.

10. `class TestEventSerialization`:
    - `test_to_dict_contains_event_type`: create `PipelineStarted`, call `to_dict()`, assert `d["event_type"] == "pipeline_started"`
    - `test_to_dict_timestamp_is_iso_string`: assert `isinstance(d["timestamp"], str)` and `datetime.fromisoformat(d["timestamp"])` does not raise
    - `test_to_dict_cached_at_is_iso_string`: create `CacheHit` with fixed `cached_at`, call `to_dict()`, assert `d["cached_at"]` is ISO string
    - `test_to_json_returns_valid_json`: create `PipelineCompleted`, call `to_json()`, assert `json.loads(result)` does not raise and contains `event_type`
    - `test_to_dict_all_required_fields_present`: for `PipelineStarted`, assert `run_id`, `pipeline_name`, `timestamp`, `event_type` all in dict
    - Parametrized `test_to_dict_contains_event_type_parametrized(event_type, kwargs)` over `EVENT_FIXTURES`: construct event, call `to_dict()`, assert `d["event_type"] == event_type`

11. `class TestResolveEvent`:
    - Parametrized `test_round_trip_all_event_types(event_type, kwargs)` over `EVENT_FIXTURES`: construct event, serialize with `to_dict()`, restore with `PipelineEvent.resolve_event(event_type, d)`, assert `restored.event_type == event_type` and `restored.run_id == kwargs["run_id"]`
    - `test_round_trip_preserves_all_base_fields`: use `PipelineCompleted`, assert restored `execution_time_ms`, `steps_executed` match original
    - `test_cache_hit_cached_at_deserialized_as_datetime`: construct `CacheHit` with `cached_at=datetime(2024, 1, 1, 12, 0, 0)`, round-trip, assert `isinstance(restored.cached_at, datetime)`
    - `test_resolve_event_strips_event_type_from_data`: pass data dict with `event_type` key included, assert no `TypeError` (resolve_event pops it)
    - `test_resolve_event_unknown_type_raises_value_error`: assert `ValueError` raised with unknown type string (already in TestEventRegistry but repeat here for explicitness)

12. `class TestPipelineStartedPositionalArgs`:
    - `test_pipeline_started_accepts_positional_args`: call `PipelineStarted("run-1", "my_pipeline")` (positional), assert `event.run_id == "run-1"` and `event.pipeline_name == "my_pipeline"` and `event.event_type == "pipeline_started"`
    - `test_pipeline_completed_requires_kw_only`: assert `TypeError` when calling `PipelineCompleted("run-1", "my_pipeline", 100.0, 2)` positionally (kw_only=True enforced)

13. `class TestContextSnapshotDepth` (per task 15 recommendation #3):
    - `test_context_snapshot_is_independent_of_source_dict`: create a `source_dict = {"total": 5}`, construct `ContextUpdated(context_snapshot=source_dict, ...)`. Mutate `source_dict["total"] = 999`. Assert `event.context_snapshot["total"] == 5` IF the pipeline passes a copy, else document that the event holds a reference (the test may reveal that pipeline code does NOT copy - the test result informs whether a fix is needed; note this in the test's docstring and mark as `xfail` if the pipeline does not copy, with `reason="pipeline passes reference, not copy; see task 15 recommendation"`). Note: this test is for the event object directly, not the pipeline - `dataclasses.asdict` is used in `to_dict()` but not on construction. The direct test reveals that frozen prevents reassignment of the dict field but NOT mutation via reference.
    - `test_context_snapshot_contains_all_merged_keys_integration`: integration test using `SuccessPipeline` fixture (import from conftest) - run two-step pipeline, get ContextUpdated events, assert last `context_snapshot` contains `"total"` key (from SimpleContext). Import `MockProvider, SuccessPipeline` from conftest.
    - `test_context_snapshot_new_keys_reflects_step_output`: same integration run, assert `new_keys` for each step contains `"total"` (SimpleStep returns SimpleContext with `total` field).

14. Run full test suite after writing to verify all new tests pass: `pytest tests/events/test_event_types.py -v` and then `pytest tests/events/ tests/test_emitter.py --cov=llm_pipeline/events --cov-report=term-missing --cov-branch -q` to measure post-implementation coverage.

15. Record post-implementation coverage % to task log using `task-master update-subtask`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| context_snapshot test may reveal pipeline passes reference not copy | Medium | Use `xfail` with informative reason if assertion fails; do not change production code (out of scope) |
| PipelineCompleted kw_only test may be fragile if Python version changes kw_only behavior | Low | Test is informational; use try/except pattern or mark accordingly |
| EVENT_FIXTURES list grows stale if new event types added in future | Low | `test_registry_has_31_event_types` will fail immediately if count changes, prompting fixture update |
| CacheHit cached_at round-trip may have timezone offset if utcnow vs utc-aware | Low | Use `datetime(2024, 1, 1, 12, 0, 0)` (naive, fixed) in EVENT_FIXTURES for determinism |
| Import of `_EVENT_REGISTRY` and `_derive_event_type` (private) in tests | Low | These are documented as internal helpers; test file is the single consumer; acceptable for test-only access |

## Success Criteria
- [ ] `tests/events/test_event_types.py` created and all tests in it pass
- [ ] `assert len(_EVENT_REGISTRY) == 31` passes (no "28" references anywhere in file)
- [ ] Parametrized round-trip test covers all 31 event types including CacheHit with cached_at
- [ ] Mutable-container convention tests: both frozen-prevents-reassignment AND list/dict-contents-can-mutate assertions present
- [ ] Context snapshot depth tests present: at least one integration test and one direct test
- [ ] PipelineStarted positional-args test present
- [ ] Baseline coverage % recorded in task log before writing tests
- [ ] Post-implementation coverage % recorded in task log; target >93% for events package
- [ ] Full test suite still passes (318 existing + new tests): `pytest tests/` exit code 0

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Pure test addition. No production code changes. All research validated. CEO questions resolved. Single file, well-understood patterns consistent with existing 10 test modules.
**Suggested Exclusions:** testing, review
