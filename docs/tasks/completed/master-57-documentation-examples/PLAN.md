# PLANNING

## Summary

Rewrite the nearly-empty README.md with self-contained runnable usage examples for the event system, UI, and LLMCallResult. Fix three existing doc files with confirmed inaccuracies (docs/api/llm.md return type and missing params, docs/index.md missing Events row, docs/architecture/overview.md observability section). Fix one code typo in llm_pipeline/__init__.py (LLMCallStarted -> LLMCallStarting). Total: 5 files modified, no new files created.

## Plugin & Agents

**Plugin:** code-documentation
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Implementation**: Apply all 5 file changes - README rewrite, 3 doc fixes, 1 code typo

## Architecture Decisions

### Example Style for Event System
**Choice:** Use InMemoryEventHandler directly without instantiating a full pipeline. Show dict bracket notation for accessing stored events.
**Rationale:** VALIDATED_RESEARCH.md confirms `get_events()` returns `list[dict]` (handlers.py:109 calls `event.to_dict()` before storing). Dot notation would raise AttributeError. Self-contained runnable snippet requirement rules out hypothetical MyPipeline class. Direct handler usage is simpler and demonstrates the API correctly.
**Alternatives:** Show handler attached to a minimal pipeline class; rejected because CEO confirmed no hypothetical user classes.

### LLMCallResult Example Approach
**Choice:** Use factory methods (`LLMCallResult.success()`, `LLMCallResult.failure()`) for self-contained example. Show `parsed`, `raw_response`, `model_name`, `attempt_count`, `is_success`, `is_failure`.
**Rationale:** Factory methods allow snippet to run without a real LLM provider. CEO confirmed current API only, no before/after version comparison. Research step-3 confirms all attributes are valid from result.py.
**Alternatives:** Call real provider; rejected because snippet must be self-contained and runnable without API keys.

### llm.md Fix Scope
**Choice:** Fix `call_structured()` return type annotation (Optional[Dict] -> LLMCallResult) and add the 4 missing params (event_emitter, step_name, run_id, pipeline_name). Also fix the example code that uses old dict-based return.
**Rationale:** VALIDATED_RESEARCH.md confirms both issues: llm.md line 63 shows Optional[Dict] while provider.py:50 returns LLMCallResult; provider.py:45-48 has 4 params absent from docs.
**Alternatives:** Rewrite full llm.md; rejected as out of scope - only fix confirmed inaccuracies.

### docs/index.md Events Row Placement
**Choice:** Add Events row to Module Index table between State and Registry rows (reflecting __init__.py export grouping).
**Rationale:** The existing 9-row table covers Pipeline through Registry. Events handlers (InMemoryEventHandler, CompositeEmitter, etc.) are top-level exports alongside State and Registry. Inserting between them follows the natural logical grouping visible in __init__.py.
**Alternatives:** Append as last row; no strong reason to prefer, insertion maintains logical ordering.

### overview.md Observability Section
**Choice:** Update the observability section to mention the event system and InMemoryEventHandler as the primary observability mechanism alongside existing state-based querying.
**Rationale:** The current observability section in overview.md only shows PipelineStepState queries and logging. The event system (task 53, now done) is the primary real-time observability mechanism and is completely absent from this section. LLM Integration cross-reference also needs events added.
**Alternatives:** Leave overview.md as-is; rejected because CEO confirmed this fix is in scope.

## Implementation Steps

### Step 1: Fix typo in llm_pipeline/__init__.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open `llm_pipeline/__init__.py`
2. On line 16 in the module docstring, change `LLMCallStarted` to `LLMCallStarting`
3. The line currently reads: `from llm_pipeline.events import PipelineStarted, StepStarted, LLMCallStarted`
4. Corrected line: `from llm_pipeline.events import PipelineStarted, StepStarted, LLMCallStarting`

### Step 2: Fix docs/api/llm.md - return type and missing params
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open `docs/api/llm.md`
2. Find the `call_structured()` method signature block (around line 51-63)
3. Change return type annotation from `-> Optional[Dict[str, Any]]` to `-> LLMCallResult`
4. Update the **Returns:** description from `Optional[Dict[str, Any]] - Validated JSON response dict, or None if all retries failed` to `LLMCallResult - result object containing parsed output, raw_response, model_name, attempt_count, and validation_errors`
5. Add 4 missing parameters to the **Parameters:** list after `validation_context`:
   - `event_emitter` (Optional[PipelineEventEmitter]): Event emitter for LLM call events
   - `step_name` (Optional[str]): Step name for event scoping
   - `run_id` (Optional[str]): Run identifier for event correlation
   - `pipeline_name` (Optional[str]): Pipeline name for event scoping
6. Update the **Example:** code block under `call_structured()` - the example uses `validate_and_return(response, result_class)` with `-> Optional[Dict[str, Any]]` return; update the return type annotation in the example to `-> LLMCallResult` (or remove return type annotation to avoid inconsistency with the abstract example)
7. Update the GeminiProvider example at lines ~162-172 - if result value is checked with `if result:`, update to check `if result.is_success:` and change `data = ParsedData(**result)` to `data = ParsedData(**result.parsed)` to match the actual LLMCallResult API

### Step 3: Fix docs/index.md - add Events row to Module Index table
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open `docs/index.md`
2. Find the Module Index table (between lines 33-44)
3. Add a new row after the State row and before the Registry row:
   `| **[Events](api/events.md)** | Event system for pipeline observability | `InMemoryEventHandler`, `CompositeEmitter`, `LoggingEventHandler` |`
   Note: docs/api/events.md does not exist (creating it is out of scope), so link to the events section of the existing api/index.md instead, or omit the link and just note the module. Use `**Events**` without a link to avoid broken link, or link to `#events` anchor if one exists. If no anchor exists, reference the module without a hyperlink.
4. Update the "LLM Integration" cross-reference entry under "By Concept" section to also mention the event system:
   Current: `- [LLM Provider API Reference](api/llm.md)` (only)
   Add: `- [Events](api/index.md) - InMemoryEventHandler, CompositeEmitter for observability`
5. Update the "Most Common Imports" quick reference block to include event imports:
   Add after `from llm_pipeline import PipelineDatabaseRegistry, ReadOnlySession`:
   ```python
   # Events (observability)
   from llm_pipeline import InMemoryEventHandler, CompositeEmitter, LoggingEventHandler
   from llm_pipeline.events import PipelineStarted, LLMCallStarting  # concrete events
   ```

### Step 4: Fix docs/architecture/overview.md - update observability section
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open `docs/architecture/overview.md`
2. Find the "Monitoring and Observability" section (around line 967)
3. Add an Event System subsection before the existing "Execution Metrics" subsection:
   ```markdown
   **Event System** (real-time):
   ```python
   from llm_pipeline import InMemoryEventHandler
   from llm_pipeline.events import PipelineStarted, LLMCallStarting

   handler = InMemoryEventHandler()
   pipeline = MyPipeline(provider=provider, event_emitter=handler)
   pipeline.execute(data)

   for event in handler.get_events(pipeline.run_id):
       print(f"{event['event_type']}: {event['timestamp']}")
   ```
   31 event types cover pipeline lifecycle, step lifecycle, LLM calls, cache hits, consensus polling, and more. Use `CompositeEmitter` to attach multiple handlers simultaneously.
   ```
4. The existing "Execution Metrics" and "Data Traceability" subsections remain unchanged.

### Step 5: Rewrite README.md with usage examples
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Open `README.md` (currently 3 lines: title + blank + description)
2. Rewrite with the following structure and content:

```markdown
# llm-pipeline

Declarative LLM pipeline orchestration framework.

## Installation

```bash
pip install llm-pipeline
```

## Event System

Observe pipeline execution in real time using the event system. `InMemoryEventHandler` collects all events for a run:

```python
from llm_pipeline import InMemoryEventHandler, CompositeEmitter

# Attach handler to pipeline at construction
handler = InMemoryEventHandler()
pipeline = MyPipeline(provider=provider, event_emitter=handler)
pipeline.execute(data)

# Events are stored as dicts
for event in handler.get_events(pipeline.run_id):
    print(f"{event['event_type']}: {event['timestamp']}")

# Filter by type
llm_events = handler.get_events_by_type('llm_call_starting', pipeline.run_id)
for event in llm_events:
    print(f"Prompt: {event['rendered_user_prompt']}")
```

Use `CompositeEmitter` to attach multiple handlers simultaneously:

```python
from llm_pipeline import InMemoryEventHandler, CompositeEmitter, LoggingEventHandler

memory_handler = InMemoryEventHandler()
log_handler = LoggingEventHandler()

emitter = CompositeEmitter([memory_handler, log_handler])
pipeline = MyPipeline(provider=provider, event_emitter=emitter)
```

31 event types are available in `llm_pipeline.events`, covering pipeline lifecycle, step execution, LLM calls, cache hits, consensus polling, and more.

## UI

The optional web UI provides a dashboard for browsing pipeline runs and events.

```bash
pip install llm-pipeline[ui]

# Start UI (default port 8642)
llm-pipeline ui

# Development mode with hot reload
llm-pipeline ui --dev --port 8642

# Connect to a specific database
llm-pipeline ui --db /path/to/pipeline.db
```

## LLMCallResult

`provider.call_structured()` returns an `LLMCallResult` with structured output and metadata:

```python
from llm_pipeline import LLMCallResult

# Construct directly using factory methods (for testing)
result = LLMCallResult.success(
    parsed={"name": "widget", "count": 5},
    raw_response='{"name": "widget", "count": 5}',
    model_name="gemini-2.0-flash-lite",
    attempt_count=1,
)

print(result.parsed)            # {'name': 'widget', 'count': 5}
print(result.raw_response)      # original text from LLM
print(result.model_name)        # model that produced the result
print(result.attempt_count)     # number of attempts (includes retries)
print(result.validation_errors) # list of validation error strings
print(result.is_success)        # True when parsed is not None
print(result.is_failure)        # True when parsed is None

# Failure case
failed = LLMCallResult.failure(
    raw_response="I cannot extract the requested data.",
    model_name="gemini-2.0-flash-lite",
    attempt_count=3,
    validation_errors=["Field 'count' must be a positive integer"],
)
print(failed.is_failure)  # True
```

## Documentation

Full documentation: [docs/](docs/)
```

3. Preserve the original first 3 lines (title + blank + description) and append sections after.
   Actually: rewrite the full file. The original 3 lines are just the title and description which will be kept at the top of the new content.

Note: Step 5 must run in Group B (after or separate from Group A steps) because it does not share files with steps 1-4. However since README.md is independent and steps 1-4 are all independent of each other and of step 5, steps 1-4 can be Group A (concurrent) and step 5 can also be Group A since README.md is not modified by any other step. All 5 steps can be Group A.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| docs/api/events.md does not exist - adding Events row to index.md with a broken link | Medium | Use plain text `**Events**` without hyperlink in the index table, or link to api/index.md anchor. Verified: creating events.md is out of scope. |
| GeminiProvider example in llm.md uses old dict-based result API in both the method example and the full usage example at bottom | Medium | Fix all dict-based result access patterns in llm.md to use LLMCallResult attributes (result.parsed instead of result, etc.) |
| README event example implies users have a MyPipeline class - must be clear this is a placeholder | Low | Add comment clarifying MyPipeline is the user's pipeline subclass, or frame example with context |
| Typo fix in __init__.py changes the module docstring which is user-visible | Low | The fix is correct (LLMCallStarting is the real class name per events/types.py) - risk is near zero |

## Success Criteria

- [ ] `llm_pipeline/__init__.py` line 16 imports `LLMCallStarting` not `LLMCallStarted`
- [ ] `docs/api/llm.md` `call_structured()` signature shows `-> LLMCallResult` return type
- [ ] `docs/api/llm.md` `call_structured()` parameters include `event_emitter`, `step_name`, `run_id`, `pipeline_name`
- [ ] `docs/api/llm.md` example code uses `result.parsed` / `result.is_success` not dict-style return
- [ ] `docs/index.md` Module Index table includes Events row
- [ ] `docs/index.md` Most Common Imports block includes event system imports
- [ ] `docs/architecture/overview.md` Monitoring and Observability section mentions event system with example
- [ ] `README.md` contains runnable event system example using dict bracket notation (`event['event_type']`)
- [ ] `README.md` contains UI CLI example with `--dev`, `--port`, `--db` flags
- [ ] `README.md` contains LLMCallResult example using factory methods showing all key attributes
- [ ] `pytest` passes with no regressions (no Python files changed except `__init__.py` docstring)

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All changes are documentation-only except a one-word docstring fix in `__init__.py`. The docstring fix corrects an incorrect symbol name and does not affect imports or runtime behavior. No new files are created. All code examples have been pre-validated against source in research step 3. The only execution risk is a broken link in index.md for the Events row (docs/api/events.md does not exist) - mitigated by using plain text or existing anchor link.
**Suggested Exclusions:** testing, review
