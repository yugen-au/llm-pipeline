# IMPLEMENTATION - STEP 9: DOCS/OBSERVABILITY.MD
**Status:** completed

## Summary
Created docs/observability.md covering OTel setup, token tracking, event enrichment, and environment variables. All 8 sections from the plan are included.

## Files
**Created:** docs/observability.md
**Modified:** none
**Deleted:** none

## Changes
### File: `docs/observability.md`
New file with sections: Overview, Installation, Configuration, Content Capture (include_content), Token Tracking (per-step DB fields + SQL cost aggregation + migration note), Event Fields (LLMCallCompleted per-call + StepCompleted aggregate), Example (console span exporter), Environment Variables (OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS, OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES).

## Decisions
### Doc structure mirrors plan sections
**Choice:** 8 sections matching plan spec, with sub-sections for token tracking (DB fields, SQL queries, migration) and events (per-call vs aggregate)
**Rationale:** plan specified exact sections; sub-sections added for clarity without deviating from scope

### Security warning on include_content
**Choice:** explicit warning to only enable in dev or with access controls
**Rationale:** matches CEO decision Q2 (security-first default); doc should reinforce the decision

### SQL examples use standard SQL
**Choice:** portable SQL (no SQLite-specific syntax) for cost aggregation examples
**Rationale:** pipeline supports PostgreSQL in production; examples should work on both SQLite and PostgreSQL

## Verification
[x] Overview section describes spans for model requests and token usage
[x] Installation section shows `pip install llm-pipeline[otel]`
[x] Configuration section shows InstrumentationSettings + TracerProvider + OTLP exporter
[x] include_content section documents default=False and opt-in pattern
[x] Token tracking section covers PipelineStepState fields (input_tokens, output_tokens, total_tokens, total_requests)
[x] Token tracking section includes SQL cost aggregation examples
[x] Event fields section covers LLMCallCompleted (per-call) and StepCompleted (step-aggregate)
[x] Example section provides minimal console span exporter working example
[x] Environment variables section covers OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS, OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES
[x] No pydantic-ai global Agent.instrument_all() mentioned (per-agent only)
[x] Consensus token aggregation behavior documented in Event Fields section

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] docs/observability.md does not mention total_requests on StepCompleted vs PipelineStepState distinction

### Changes Made
#### File: `docs/observability.md`
Clarified that `total_requests` is DB-only (not on events) in two places:

```
# Before (Token Tracking table)
| `total_requests` | `int \| None` | Number of LLM requests made (includes consensus attempts) |

# After
| `total_requests` | `int \| None` | Number of LLM requests made (includes consensus attempts). **DB-only** -- not available on event objects. |
```

```
# Before (StepCompleted section, after table)
The `StepCompleted` totals match what is persisted to `PipelineStepState`, giving you the true cost of the step including all consensus attempts.

# After
The `StepCompleted` token totals match what is persisted to `PipelineStepState`, giving you the true cost of the step including all consensus attempts.

> **Note:** `total_requests` is only available on the `PipelineStepState` database record, not on `StepCompleted` events. To count requests per step, query the database rather than accumulating from events.
```

### Verification
[x] PipelineStepState table marks total_requests as DB-only
[x] StepCompleted section has explicit note that total_requests is absent from events
[x] Guidance on where to get request counts (query DB, not events)
