# Research Summary

## Executive Summary

Research findings are accurate and well-sourced. The core discovery -- that the event system already exists (28 event types, emitter protocol, 3 handlers, full pipeline integration) -- is confirmed by codebase inspection. Task 4's actual scope reduces to: (a) enable pydantic-ai OTel instrumentation, (b) capture token usage from RunResult.usage(), (c) enrich existing events + PipelineStepState with token fields, (d) create docs/observability.md. Six architectural decisions require CEO input before planning can proceed.

## Domain Findings

### Event System Already Exists
**Source:** research/step-2-pipeline-event-system-patterns.md, research/step-3-current-codebase-analysis.md, events/types.py

Confirmed: 28 event types across 9 categories (pipeline_lifecycle, step_lifecycle, cache, llm_call, consensus, instructions_context, transformation, extraction, state). Full infrastructure: PipelineEventEmitter protocol, CompositeEmitter, LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, PipelineEventRecord. Pipeline.execute() has ~20 emission points. Task description's "Define pipeline event types (StepPrepared, StepStarting, StepCompleted)" is outdated -- StepStarted, StepCompleted, LLMCallPrepared already exist.

3 orphaned event types (LLMCallRetry, LLMCallFailed, LLMCallRateLimited) exist but are never emitted after Task 2 deleted GeminiProvider. CEO deferred removal in Task 2 as "breaking events API change."

### Token Usage Not Captured
**Source:** research/step-1-otel-pydantic-ai-instrumentation.md, research/step-3-current-codebase-analysis.md, pipeline.py L809-814, L1227-1228

Confirmed: `run_result.usage()` is never called in either the normal path (pipeline.py L814) or consensus path (L1228). `run_result` goes out of scope with usage data discarded. Task 2 SUMMARY.md explicitly deferred this: "run_result.usage() for token logging is detailed in Task 4."

pydantic-ai RunUsage API (confirmed via Context7 v1.0.5): `input_tokens: int`, `output_tokens: int`, `requests: int`. No `request_tokens`/`response_tokens` fields -- task description field names don't match pydantic-ai.

### PipelineStepState Missing Token Fields
**Source:** research/step-3-current-codebase-analysis.md, state.py L24-103

Confirmed: PipelineStepState has `execution_time_ms` for timing but zero token-related fields. Fields needed: token counts (input, output) and request count. DB migration required via ADD COLUMN pattern (SQLite-compatible).

### OTel Instrumentation Not Enabled
**Source:** research/step-1-otel-pydantic-ai-instrumentation.md, agent_builders.py L98-107

Confirmed: `build_step_agent()` creates Agent without `instrument=` parameter. No `InstrumentationSettings` import anywhere. No OTel deps in pyproject.toml. Two activation patterns available:
- `Agent.instrument_all(settings)` -- process-wide, affects ALL pydantic-ai agents
- `Agent(instrument=settings)` -- per-agent, scoped to pipeline agents only

### pydantic-ai OTel API (Context7 v1.0.5)
**Source:** Context7 /pydantic/pydantic-ai/v1_0_5

`InstrumentationSettings` accepts: `tracer_provider` (TracerProvider), `event_logger_provider` (EventLoggerProvider), `include_content` (bool, default True), `include_binary_content` (bool). Both `Agent.instrument_all(settings)` and `Agent(instrument=settings)` are supported. Requires `opentelemetry-sdk` at runtime when instrumentation is enabled.

### Upstream Task 2 Deviations
**Source:** Task 2 SUMMARY.md, Taskmaster get_task(2)

No deviations affecting Task 4. Key accepted constraints: `LLMCallCompleted.raw_response` always None, `attempt_count` always 1. These are pydantic-ai limitations, not blockers for token work.

### Downstream Task 6 Scope
**Source:** Taskmaster get_task(6)

Task 6 is "Final Integration, Comprehensive Testing, and Cleanup" -- depends on tasks 1-5. End-to-end OTel integration testing belongs there. Task 4 should include unit tests for token capture and event enrichment but not full integration tests.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Pending -- see Questions below | - | - |

## Assumptions Validated
- [x] Event system exists with 28 types, protocol emitter, 3 handlers (confirmed via events/types.py, emitter.py, handlers.py)
- [x] run_result.usage() never called in pipeline.py (confirmed L809-814, L1227-1228)
- [x] PipelineStepState has no token fields (confirmed state.py L24-103)
- [x] No instrument= parameter on Agent construction (confirmed agent_builders.py L98-107)
- [x] No OTel deps in pyproject.toml (confirmed L22-36)
- [x] pydantic-ai RunUsage uses input_tokens/output_tokens, not request_tokens/response_tokens (confirmed Context7)
- [x] Task 2 explicitly deferred token capture to Task 4 (confirmed SUMMARY.md)
- [x] _save_step_state has clean insertion point for token params (confirmed pipeline.py L1063-1114)
- [x] LLMCallCompleted has no token fields but supports adding optional fields via dataclass defaults (confirmed events/types.py L329-344)

## Open Items
- Q1-Q6 below must be answered before planning phase

## Recommendations for Planning
1. **Scope reduction**: Task description should be updated -- "create pipeline event system" is complete, actual work is OTel enablement + token capture + event enrichment + docs
2. **Token field naming**: Use pydantic-ai convention (input_tokens/output_tokens) not task description's request_tokens/response_tokens
3. **Enrich existing events**: Add token fields to LLMCallCompleted (per-call) and StepCompleted (per-step aggregate), don't create new event types
4. **PipelineStepState fields**: Add input_tokens, output_tokens, total_requests as nullable int columns with ADD COLUMN migration
5. **total_tokens**: Consider whether to store as derived field (input + output) or compute on read. Storing enables efficient SQL aggregation but is redundant
6. **Test scope**: Unit tests for token capture in Task 4; end-to-end OTel integration tests deferred to Task 6
7. **Instrumentation helper**: If using public helper pattern, create llm_pipeline/instrumentation.py with thin wrapper around Agent.instrument_all(). Export from __init__.py. Document in docs/observability.md
8. **DB migration**: Use ADD COLUMN IF NOT EXISTS pattern (SQLite-compatible, consistent with existing SQLiteEventHandler.__init__ pattern in handlers.py)
