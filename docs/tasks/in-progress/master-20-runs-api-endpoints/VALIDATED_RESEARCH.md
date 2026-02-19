# Research Summary

## Executive Summary

Cross-referenced all 3 research documents against actual codebase (`state.py`, `pipeline.py`, `deps.py`, `app.py`, `events/models.py`, `session/readonly.py`, `db/__init__.py`). Model schemas, indexes, dependency injection patterns, and FastAPI app factory are accurately documented. However, 5 hidden assumptions, 4 inter-document contradictions, and 3 blocking architectural questions were identified that must be resolved before planning.

The most critical finding: POST /runs has a **run_id mismatch problem** -- `PipelineConfig.__init__()` generates its own `run_id` internally (line 200), so the endpoint cannot pre-generate a run_id to return to the caller. None of the 3 research docs address this.

## Domain Findings

### Finding 1: run_id Ownership Conflict (POST /runs)
**Source:** step-2, verified against `llm_pipeline/pipeline.py` line 200

Step 2's POST skeleton generates `run_id = str(uuid.uuid4())` in the endpoint and returns it immediately. But `PipelineConfig.__init__()` also generates `self.run_id = str(uuid.uuid4())`. These produce **two different UUIDs**. The client gets one run_id, the pipeline uses another. All step states, events, and run instances are recorded under the pipeline's internal run_id, making the returned run_id useless for subsequent GET queries.

Resolution options:
- a) Add optional `run_id` parameter to `PipelineConfig.__init__()` -- requires modifying core library
- b) Instantiate pipeline first, read `pipeline.run_id`, return it, then execute in background -- requires splitting construction from execution
- c) Defer POST /runs entirely

### Finding 2: PipelineRun Table Write Integration Undefined
**Source:** step-3 (Option C recommendation), verified against `llm_pipeline/pipeline.py`

Step 3 recommends a `PipelineRun` table with "2 writes per run" but does not specify WHO writes. Three possibilities exist with different architectural impacts:

1. **Core pipeline.py** writes during execute() -- affects ALL pipeline users (API + direct Python), most consistent
2. **Event handler** writes on pipeline_started/pipeline_completed events -- decoupled but event_emitter is optional (line 157), so runs without emitters would be invisible
3. **POST endpoint + background function** writes -- only API-triggered runs visible, direct Python usage invisible

The pipeline's transaction model adds complexity: step states use `flush()` not `commit()` (line 947), and `commit()` only happens in `save()` (line 990). A "running" status PipelineRun record would need its own committed transaction to be visible to concurrent GET queries.

### Finding 3: Pipeline Resolution Complexity for POST /runs
**Source:** step-2 section 8, verified against `llm_pipeline/pipeline.py` lines 85-213

Step 2 suggests `resolve_pipeline(pipeline_name)` but underestimates the dependency graph. Constructing a PipelineConfig subclass requires:
- `registry=` class argument (enforced by `__init_subclass__`, line 118)
- `strategies=` class argument (enforced, line 171)
- `provider: LLMProvider` instance (required for execute(), line 434)
- `engine` or `session` (optional, auto-SQLite if omitted)
- `event_emitter` (optional)

No pipeline registry or factory pattern exists in the codebase. Building one is a significant scope expansion beyond "implement runs endpoints."

### Finding 4: SQLite Concurrent Access Not Addressed
**Source:** step-3 section 1.4, verified against `llm_pipeline/db/__init__.py`

Step 3 notes "SQLite: no parallel writes" but doesn't address the API concurrency scenario:
- FastAPI runs sync GET endpoints in threadpool (concurrent readers)
- BackgroundTasks runs POST pipeline execution in threadpool (writer)
- `init_pipeline_db()` creates engine with `create_engine(url, echo=False)` -- no WAL mode
- Default SQLite journal mode blocks readers during writes

Without WAL mode, a long-running pipeline execution would block all GET queries. This should be configured explicitly.

### Finding 5: Event Persistence is Optional
**Source:** step-1, step-3 (Option B), verified against `llm_pipeline/pipeline.py` line 157

Step 3 Option B (derive runs from pipeline_events) is fragile: `event_emitter` is an optional constructor parameter. Pipelines instantiated without an emitter produce zero event records. Only `PipelineStepState` records are guaranteed (written unconditionally in `_save_step_state`, line 905). This makes Option A (GROUP BY step_states) the only reliable no-schema-change approach.

### Finding 6: Pre-existing Bug in clear_cache()
**Source:** verified in `llm_pipeline/pipeline.py` lines 791-805

`clear_cache()` calls `self.session.delete()` and `self.session.commit()`, but `self.session` is a `ReadOnlySession` which raises `RuntimeError` on both operations. This is out of scope for task 20 but indicates the code may have untested write paths.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| pending - see Questions below | | |

## Assumptions Validated
- [x] PipelineStepState schema matches research (all columns, types, indexes verified)
- [x] PipelineRunInstance schema matches research (columns, indexes, purpose verified)
- [x] PipelineEventRecord schema matches research (columns, indexes verified)
- [x] ReadOnlySession blocks all write operations listed in research
- [x] ReadOnlySession allows exec, execute, scalar, scalars, get, query (verified)
- [x] deps.py yields ReadOnlySession, closes underlying Session in finally block
- [x] create_app() mounts routers with prefix="/api", lazy imports inside function body
- [x] runs.py route stub exists with `prefix="/runs"` and empty router
- [x] PipelineConfig.execute() emits PipelineStarted and PipelineCompleted events
- [x] PipelineConfig.execute() is sync (not async)
- [x] Step states are saved via flush() (not commit) during execution
- [x] pipeline.save() is the only place commit() is called on the real session
- [x] run_id is generated in PipelineConfig.__init__() with no external override option
- [x] No pipeline registry or factory pattern exists in the codebase
- [x] init_pipeline_db() returns the engine (used by app.state.engine)
- [x] get_session() returns a writable Session (not ReadOnlySession)

## Assumptions Invalidated
- [x] POST /runs can pre-generate run_id and pass to pipeline -- INVALID: PipelineConfig generates its own run_id with no injection point
- [x] Pipeline resolution is a simple name-to-class mapping -- INVALID: requires full dependency graph (registry, strategies, provider, engine, emitter)
- [x] Status can be derived from existing data reliably -- PARTIALLY INVALID: step_states have no status; events are optionally persisted; only Option C provides reliable status

## Open Items
- run_id injection into PipelineConfig (blocked on Q2/Q3)
- SQLite WAL mode configuration for concurrent API usage
- clear_cache() bug (out of scope, should be tracked separately)
- Redundant index cleanup (Step 3 recommendation, low risk, can proceed without CEO input)
- httpx dev dependency for TestClient (noted in Step 1, minor)

## Recommendations for Planning
1. **Resolve PipelineRun table decision first** -- it determines query patterns, response models, write integration, and whether status filtering is possible
2. **Defer POST /runs to a separate task** -- the run_id mismatch, pipeline resolution, and dependency injection complexity make it a distinct piece of work that shouldn't block GET endpoints
3. **If PipelineRun table adopted, integrate writes into pipeline.py core** -- guarantees all runs (API + direct) are tracked; event-handler approach is fragile due to optional emitter
4. **Add PipelineConfig run_id parameter** as a prerequisite if POST /runs is ever implemented -- `__init__(self, ..., run_id: Optional[str] = None)` with fallback to uuid4()
5. **Configure SQLite WAL mode** in init_pipeline_db() for concurrent read/write safety
6. **Use def (sync) for all endpoints** -- researchers agree, codebase is entirely sync
7. **Use offset/limit pagination** -- researchers agree, sufficient for 10k runs
8. **Adopt Step 2's RunListParams Pydantic model** but fix Optional fields: completed_at should be Optional[datetime], total_time_ms should be Optional[int]
9. **Remove status filter from RunListParams** if no PipelineRun table (status doesn't exist in GROUP BY approach)
10. **Remove redundant indexes** on run_id (Step 3 section 3.1) -- safe, no CEO input needed
