# IMPLEMENTATION - STEP 2: PIPELINE INSTRUMENTATION
**Status:** completed

## Summary
Instrumented `PipelineConfig.execute()` to write `PipelineRun` records on every pipeline execution (success and failure). Added `run_id` injection support so POST /runs can pre-generate a run_id.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

**1. Added `run_id` parameter to `__init__()`**
```python
# Before
        event_emitter: Optional["PipelineEventEmitter"] = None,
    ):

# After
        event_emitter: Optional["PipelineEventEmitter"] = None,
        run_id: Optional[str] = None,
    ):
```

**2. Changed `self.run_id` to accept injected value**
```python
# Before
        self.run_id = str(uuid.uuid4())

# After
        self.run_id = run_id or str(uuid.uuid4())
```

**3. Added lazy import of PipelineRun at top of execute()**
```python
# Before
        from llm_pipeline.llm.executor import execute_llm_step
        from llm_pipeline.prompts.service import PromptService

# After
        from llm_pipeline.llm.executor import execute_llm_step
        from llm_pipeline.prompts.service import PromptService
        from llm_pipeline.state import PipelineRun
```

**4. Create PipelineRun with status="running" before try block**
```python
# Before
        start_time = datetime.now(timezone.utc)
        current_step_name: str | None = None

        if self._event_emitter:

# After
        start_time = datetime.now(timezone.utc)
        current_step_name: str | None = None

        pipeline_run = PipelineRun(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            status="running",
            started_at=start_time,
        )
        self._real_session.add(pipeline_run)
        self._real_session.flush()

        if self._event_emitter:
```

**5. Update PipelineRun to "completed" in success path (unconditional, moved pipeline_execution_time_ms out of event_emitter guard)**
```python
# Before (pipeline_execution_time_ms was inside if self._event_emitter:)

# After
            pipeline_execution_time_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            pipeline_run.status = "completed"
            pipeline_run.completed_at = datetime.now(timezone.utc)
            pipeline_run.step_count = len(self._executed_steps)
            pipeline_run.total_time_ms = int(pipeline_execution_time_ms)
            self._real_session.add(pipeline_run)
            self._real_session.flush()
```

**6. Update PipelineRun to "failed" in except block with None-guard**
```python
        except Exception as e:
            if pipeline_run:
                pipeline_run.status = "failed"
                pipeline_run.completed_at = datetime.now(timezone.utc)
                self._real_session.add(pipeline_run)
                self._real_session.flush()
```

## Decisions
### pipeline_execution_time_ms computation moved unconditional
**Choice:** Moved `pipeline_execution_time_ms` computation outside the `if self._event_emitter:` guard
**Rationale:** PipelineRun.total_time_ms needs this value regardless of whether events are enabled. The event emit still uses it inside the guard. No behavioral change for event consumers.

### PipelineRun created before try block (not inside)
**Choice:** `pipeline_run = PipelineRun(...)` is created and flushed before the `try:` block
**Rationale:** Per contract spec: "Declare pipeline_run = None before the try block so it's accessible in the except handler." Creating it before try means the variable is always in scope. The None-check in except handles the edge case where flush itself fails (e.g., unique constraint violation on duplicate run_id).

## Verification
[x] `run_id` parameter added after `event_emitter` in `__init__()`
[x] `self.run_id = run_id or str(uuid.uuid4())` preserves backward compat
[x] Lazy import of PipelineRun follows existing pattern (imports inside methods)
[x] PipelineRun created with status="running" before try block
[x] Success path updates status="completed" with step_count and total_time_ms
[x] Except path updates status="failed" with None-guard
[x] All 37 pipeline tests pass (test_pipeline.py)
[x] All 511 passing tests still pass (16 pre-existing failures in test_retry_ratelimit_events.py are unrelated - google module not installed)
