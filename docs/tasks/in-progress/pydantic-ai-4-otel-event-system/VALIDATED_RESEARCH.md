# Research Summary

## Executive Summary

Research findings are accurate and well-sourced. The core discovery -- that the event system already exists (28 event types, emitter protocol, 3 handlers, full pipeline integration) -- is confirmed by codebase inspection. Task 4's actual scope reduces to: (a) enable pydantic-ai OTel instrumentation via per-agent `instrument=` parameter, (b) capture token usage from RunResult.usage() and store in PipelineStepState, (c) enrich existing LLMCallCompleted and StepCompleted events with token fields, (d) create docs/observability.md. All six architectural decisions resolved by CEO -- validation complete.

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
| Q1: Global Agent.instrument_all() vs per-agent instrument= in build_step_agent()? | Per-agent via instrument= in build_step_agent(). Pipeline agents only, don't touch consumer's non-pipeline agents. | InstrumentationSettings threaded through PipelineConfig -> build_step_agent(). No public helper needed. No process-wide side effects. |
| Q2: include_content default True (task desc) or False (security-first)? | False by default. Security-first, consumer opts in. | Default InstrumentationSettings(include_content=False). Prompts/completions NOT sent to OTel backend unless consumer explicitly enables. |
| Q3: Consensus token aggregation -- sum all attempts or only winner? | Sum all attempts on PipelineStepState (true cost). Per-call tokens on individual LLMCallCompleted events. | Two granularity levels: LLMCallCompleted has per-call tokens, PipelineStepState/StepCompleted have step-aggregate sums. |
| Q4: Field naming -- input_tokens/output_tokens (pydantic-ai) vs request_tokens/response_tokens (task desc)? | Match pydantic-ai convention: input_tokens, output_tokens, total_tokens. | Task description field names overridden. Consistent with pydantic-ai RunUsage API and OTel gen_ai semantic conventions. |
| Q5: OTel deps -- new [otel] group vs bundle with [pydantic-ai]? | New [otel] optional group in pyproject.toml. Keeps base light. | opentelemetry-sdk and opentelemetry-exporter-otlp-proto-http in [otel] group. OTel is fully opt-in. |
| Q6: total_tokens -- store as derived field or compute on read? | Store as field on PipelineStepState for SQL aggregation convenience. | input_tokens + output_tokens computed at write time, stored as total_tokens column. Enables efficient cost queries. |

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
- None -- all 6 architectural decisions resolved

## Recommendations for Planning
1. **Scope reduction**: Update task description -- "create pipeline event system" is done, actual work is OTel enablement + token capture + event enrichment + docs
2. **Per-agent instrumentation flow**: Accept optional `InstrumentationSettings` in PipelineConfig (or build_step_agent), pass `instrument=settings` to Agent constructor. When None/not provided, no instrumentation. No process-wide side effects.
3. **include_content=False default**: When constructing InstrumentationSettings internally, default include_content=False. Consumer can override by passing their own InstrumentationSettings.
4. **Token field naming**: input_tokens, output_tokens, total_tokens everywhere (pydantic-ai convention). Update task description to match.
5. **Enrich existing events**: Add input_tokens, output_tokens to LLMCallCompleted (per-call granularity) and StepCompleted (step-aggregate). No new event types.
6. **PipelineStepState fields**: Add input_tokens (nullable int), output_tokens (nullable int), total_tokens (nullable int, computed input+output at write time), total_requests (nullable int) with ADD COLUMN migration.
7. **Consensus aggregation**: In _execute_with_consensus(), accumulate tokens across all agent.run_sync() calls. Each call emits LLMCallCompleted with per-call tokens. Final StepCompleted and PipelineStepState get summed totals.
8. **OTel deps**: New `[otel]` group in pyproject.toml with opentelemetry-sdk>=1.20.0 and opentelemetry-exporter-otlp-proto-http>=1.20.0. Add to [dev] as well.
9. **Test scope**: Unit tests for token capture, event enrichment, PipelineStepState persistence in Task 4. End-to-end OTel integration tests deferred to Task 6.
10. **DB migration**: Use ADD COLUMN IF NOT EXISTS pattern (SQLite-compatible, consistent with existing SQLiteEventHandler.__init__ pattern in handlers.py)
11. **docs/observability.md**: Document per-agent instrumentation setup, OTel dependency installation, include_content opt-in, token tracking fields, example OTLP exporter configuration
