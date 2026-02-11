# llm-pipeline UI: Pipeline Debugger, Visual Editor & AI Step Creator

# Product Requirements Document

---

## 1. Executive Summary

llm-pipeline UI is a developer tool for inspecting, debugging, and building LLM data extraction pipelines. It targets developers who use the llm-pipeline framework for validated AI data extraction and transformation -- use cases where semantic analysis is required but accuracy is non-negotiable (logistics classification, document parsing, compliance extraction).

The product ships in three phases:

1. **Event System** (Phase 1): Structured observability layer capturing every pipeline execution detail -- rendered prompts, raw LLM responses, model metadata, validation errors, retry/consensus behavior -- without breaking the existing Python API.
2. **Pipeline Debugger** (Phase 2): Web UI for inspecting historical and live pipeline runs. Browse prompts, view context evolution, compare extractions, trigger runs from the browser.
3. **Step Creator & Visual Editor** (Phase 3): AI-powered step scaffolding from natural language, isolated sandbox testing, auto-integration into existing pipelines, and a linear visual pipeline editor with compile-to-validate.

The UI is supplementary tooling. It does not replace the Python API. It makes the existing framework observable, debuggable, and faster to iterate on.

---

## 2. Problem Statement

### PS-1: Black Box Execution

Pipeline execution has no structured observability. The only insight is Python `logging` calls scattered through `pipeline.py` and `gemini.py`. There is no mechanism for external consumers (UIs, monitoring, alerting) to observe execution programmatically. All runtime information goes to Python loggers with no structured format. Developers cannot trace a failed extraction back to the specific prompt, response, or validation error that caused it without reading logs line-by-line.

**Impact**: Debugging a failed pipeline run requires reading unstructured log output, mentally reconstructing execution flow, and guessing which step failed and why. A 10-step pipeline with consensus and retries can produce hundreds of log lines with no structured way to filter or navigate them.

### PS-2: Critical Data Discarded

The pipeline generates valuable debugging data at runtime but discards it:

- **Raw LLM response text**: `gemini.py:106` captures `response.text` into a local variable but only uses it for JSON extraction. The original text (which may contain markdown, explanations, or malformed JSON) is never persisted or exposed.
- **Rendered prompts**: `executor.py:79-100` builds `system_instruction` and `user_prompt` from prompt templates + variables via `PromptService`, but these rendered strings are discarded after the LLM call. Developers can see the template keys but not what was actually sent to the model.
- **Model name**: `state.py:87` has a `model` field on `PipelineStepState` but `pipeline.py`'s `_save_step_state()` never populates it. The model used for each step is lost.
- **Validation errors**: `gemini.py:138-181` logs validation failures (schema mismatches, Pydantic errors) to console but doesn't capture them structurally. When a step fails after 3 retries, the developer sees "LLM call failed" with no detail about what validation errors occurred on each attempt.
- **Retry/consensus details**: `pipeline.py`'s consensus logic logs to console only. Threshold met? How many attempts? Largest group size? All lost after execution.

**Impact**: Post-mortem analysis is impossible. When a pipeline produces incorrect extractions, the developer cannot inspect what the model actually returned, what prompt it received, or what validation errors occurred during retries.

### PS-3: No Rapid Prototyping

Creating a new pipeline step requires manually writing:
- An `Instructions` Pydantic model (field definitions, validators)
- A `Step` class decorated with `@step_definition` (prompt keys, extraction config)
- `Extraction` classes mapping LLM output to database models
- YAML prompt templates (system + user) registered in the prompts table
- Wiring into a `PipelineStrategy` and `PipelineDatabaseRegistry`

There is no way to preview or test a step in isolation against sample data. The shortest iteration cycle is "write code, run full pipeline, check logs." There is no visual representation of pipeline structure to aid understanding.

**Impact**: Adding a new step to an existing pipeline takes significant boilerplate time. Onboarding developers have no visual tool to understand how steps connect, what data flows where, or what the pipeline does at a high level.

---

## 3. Developer Value Proposition

- **Debug time**: From "read logs and guess" to "click the failed step, see the prompt, see the response, see the validation error." Minutes instead of hours for complex multi-step failures.
- **Prompt iteration**: View rendered prompts (not just template keys) side-by-side with LLM responses. Identify prompt issues without re-running the pipeline.
- **Context tracing**: JSON diff of context evolution across steps. See exactly what each step added or changed. Identify where bad data entered the pipeline.
- **Step creation** (Phase 3): Describe a step in natural language, get working code, test it in isolation, auto-integrate into the pipeline. Minutes instead of hours of boilerplate.
- **Onboarding**: Visual pipeline structure shows steps, strategies, schemas, and prompt templates. New developers understand the pipeline without reading every source file.

---

## 4. Goals & Non-Goals

### Goals

1. Add a structured event system that captures all pipeline execution detail without breaking the existing API
2. Provide a web-based debugger for inspecting historical and live pipeline runs, including prompts, responses, context evolution, and extractions
3. Enable pipeline introspection: browse pipeline structure, schemas, and prompt templates before running
4. Support both Python-initiated and UI-initiated pipeline execution
5. Build an AI-powered step creator with isolated sandbox testing and auto-integration (Phase 3)
6. Provide a linear visual pipeline editor with compile-to-validate (Phase 3)

### Non-Goals

- **Production monitoring/alerting platform**: Events supplement logging; this is not a replacement for production observability tooling
- **Multi-user authentication or RBAC**: Single-user localhost dev tool. No auth, no PII handling
- **Replacing the Python API**: UI is supplementary. All functionality remains accessible via Python
- **General-purpose automation platform**: This is not n8n or Airflow. Pipelines are validated AI data extraction with audit trails
- **Offline/mobile support**: Always-online desktop dev tool
- **Supporting non-Gemini providers in Phase 1**: Provider abstraction exists; others added later

---

## 5. User Personas

### Pipeline Developer

**Role**: Builds and maintains llm-pipeline pipelines for production data extraction.

**Needs**:
- Debug failed pipeline runs: trace from failure back to specific prompt, response, and validation error
- Inspect rendered prompts (not just template keys) to understand what the model received
- View context evolution across steps to identify where bad data entered
- Compare extraction results across runs to spot regressions
- Understand pipeline structure: which steps run in which order, what schemas they use, what prompts they reference

**Frustrations**: Unstructured log output, discarded runtime data, no visual pipeline representation, long debug cycles.

### Pipeline Consumer

**Role**: Runs existing pipelines against new data, reviews extraction output.

**Needs**:
- Trigger pipeline runs from a UI without writing Python
- Monitor live execution progress
- Review extraction results and compare across runs
- Spot regressions: same input, different output between runs
- Provide input data via forms (not JSON editing) when possible

**Frustrations**: Must ask a developer to run pipelines or write scripts. No easy way to compare runs.

### Pipeline Prototyper (Phase 3)

**Role**: Rapidly iterates on new pipeline steps and pipeline structure.

**Needs**:
- Generate step scaffolding from natural language descriptions
- Test steps in isolation against sample data
- Iterate on prompts and transformations without full pipeline runs
- Visually arrange steps and validate pipeline structure
- Auto-integrate generated steps into existing pipelines

**Frustrations**: Boilerplate overhead for new steps, no isolated testing, no visual pipeline builder.

---

## 6. Core Workflows

### WF-1: Debug a Failed Run

1. Open Run List, filter by pipeline name and date range
2. Click the failed run (status indicated by color/icon)
3. Run Detail shows step timeline; failed step highlighted
4. Click failed step to open Step Detail panel
5. View **Prompts** tab: rendered system instruction + user prompt sent to the model
6. View **LLM Response** tab: raw response text alongside parsed JSON (or parse failure)
7. View **Meta** tab: model name, attempt count, validation errors per attempt
8. Identify issue (bad prompt, malformed response, schema mismatch) and fix in code

### WF-2: Monitor Live Execution

**Python-initiated**: Developer adds `event_emitter=UIBridge()` to their pipeline config, runs Python code. UI auto-detects the active run via WebSocket.

**UI-initiated**: Developer selects pipeline from Pipeline Structure view, provides input via PipelineInputData-generated form (or JSON editor fallback), clicks "Run." Live Execution view shows real-time event stream and auto-updating step timeline.

Both paths converge on the same Live Execution view. Completed steps are immediately inspectable via Step Detail panel.

### WF-3: Browse Prompts and Schemas

1. Open Pipeline Structure view, select a pipeline
2. View step order, strategy branches, extraction models, transformation classes
3. Click a step to see its prompt templates (with variable highlighting), instruction schema fields, extraction model fields
4. Navigate to Prompt Browser for cross-pipeline prompt template browsing

### WF-4: Create a New Step (Phase 3)

1. Open Step Creator view
2. Describe the step in natural language (what it extracts, from what data, what validation rules)
3. Click "Generate" -- meta-pipeline produces Instructions class, Step class, Extraction classes, YAML prompts
4. Review/edit generated code in Monaco editor
5. Click "Test" -- code executes in Docker sandbox against sample data
6. View results in Step Detail component (reused from Phase 2)
7. Iterate: edit prompts, adjust transformations, re-test
8. Click "Accept" -- auto-integrates into existing pipeline (updates strategy, registry, registers prompts)

### WF-5: Build/Edit Pipeline Visually (Phase 3)

1. Open Visual Editor view
2. View pipeline as a linear step sequence within strategies
3. Add, remove, or reorder steps. Configure step properties (prompt keys, extractions, transformations)
4. Strategy branches shown visually but editing is linear per strategy
5. Click "Compile" -- instantiates the pipeline, runs `_validate_foreign_key_dependencies` (`pipeline.py:257`), `_validate_registry_order` (`pipeline.py:276`), `_build_execution_order` (`pipeline.py:223`)
6. If errors: structured validation errors displayed inline. Fix and re-compile
7. If success: pipeline definition saved. Draft persisted even with compile errors (cross-session)

**Rationale for compile-to-validate (not incremental)**: Pipeline requires end-to-end validation at instantiation. FK dependencies, registry order, and execution order are global constraints that cannot be checked per-step. A freeform canvas (n8n-style) would create false confidence; the compile step ensures the pipeline is actually valid.

---

## 7. User Stories

### Phase 1: Event System

**US-001**: As a pipeline developer, I want to subscribe to pipeline events programmatically so that I can build custom monitoring, alerting, or logging integrations.
- Acceptance: `PipelineEventEmitter` protocol with `emit()` method. `PipelineConfig.__init__()` accepts `event_emitter` parameter. Events emitted at all documented points in `execute()` flow.

**US-002**: As a pipeline developer, I want structured LLM call details (raw response, model name, attempt count, validation errors) so that I can debug extraction failures without reading unstructured logs.
- Acceptance: `LLMCallResult` dataclass returned by `call_structured()`. Contains `parsed`, `raw_response`, `model_name`, `attempt_count`, `validation_errors`. `LLMCallCompleted` event carries all fields.

**US-003**: As a pipeline developer, I want access to rendered prompts (the actual text sent to the model, not just template keys) so that I can verify prompt rendering is correct.
- Acceptance: `LLMCallStarting` event includes `rendered_system_prompt` and `rendered_user_prompt` captured from `executor.py:79-100` before the provider call.

**US-004**: As a pipeline developer, I want events persisted to the database so that I can analyze runs after the process exits.
- Acceptance: `SQLiteEventHandler` writes to `pipeline_events` table. Opt-in via handler configuration. Events queryable by `run_id` and `event_type`.

**US-005**: As a pipeline developer, I want zero overhead when events are not needed so that production pipelines are not affected.
- Acceptance: When `event_emitter is None`, event emission is a single `if` check. Benchmark: <1ms overhead per event point when no handler attached.

### Phase 2: UI Debugger

**US-006**: As a pipeline developer, I want to view a list of pipeline runs with filtering so that I can find specific runs to inspect.
- Acceptance: Run List view at `/`. Table with run_id, pipeline_name, started_at, status, step_count, total_time_ms. Filter by pipeline name and date range. Paginated. <200ms response for 10k+ runs.

**US-007**: As a pipeline developer, I want to inspect a run's step-by-step execution so that I can understand the execution flow and identify failures.
- Acceptance: Run Detail view at `/runs/$runId`. Step timeline showing execution order, status per step, timing. Click step to open Step Detail panel.

**US-008**: As a pipeline developer, I want to view rendered prompts alongside LLM response so that I can correlate prompt content with model output.
- Acceptance: Step Detail Prompts tab shows rendered system instruction and user prompt. LLM Response tab shows raw response text and parsed JSON side-by-side.

**US-009**: As a pipeline developer, I want to see context evolution across steps (JSON diff) so that I can trace where data was added, changed, or corrupted.
- Acceptance: Run Detail context evolution panel. JSON diff between consecutive steps. Additions highlighted green, removals red, changes yellow.

**US-010**: As a pipeline developer, I want to watch live execution in real-time when a pipeline runs from Python so that I can monitor progress without waiting for completion.
- Acceptance: Python code sets `event_emitter=UIBridge()`. UI detects active run via WebSocket at `/ws/runs/{run_id}`. Live event stream auto-scrolls. Step timeline updates as steps complete.

**US-011**: As a pipeline consumer, I want to trigger a pipeline run from the UI so that I can run pipelines without writing Python.
- Acceptance: POST `/api/runs` endpoint. Live Execution view with pipeline selector and input form. Pipeline executed via `asyncio.to_thread()`. Events streamed via WebSocket.

**US-012**: As a pipeline developer, I want to browse prompt templates with variable highlighting so that I can review and compare prompts across pipelines.
- Acceptance: Prompt Browser view at `/prompts`. Lists all templates from `prompts` table. Variable placeholders (`{variable_name}`) highlighted in template viewer.

**US-013**: As a pipeline developer, I want to launch the UI with a single CLI command so that there is minimal friction to start debugging.
- Acceptance: `llm-pipeline ui` starts FastAPI + serves frontend. `--dev` enables Vite hot reload. `--port` customizes port (default 8642). `--db` specifies database path.

**US-014**: As a pipeline developer, I want to inspect pipeline structure (steps, schemas, prompts) before running so that I can understand the pipeline without reading source code.
- Acceptance: Pipeline Structure view at `/pipelines`. Shows step order, strategies, prompt keys, extraction models, transformation classes, instruction class schemas, context class schemas. Metadata extracted via runtime introspection.

**US-015**: As a pipeline developer, I want to view extraction results per step so that I can verify what data was extracted and persisted.
- Acceptance: Step Detail Extractions tab. Table of extracted model instances with field values. Shows extraction class name, model class, instance count.

**US-016**: As a pipeline consumer, I want to provide input data via a form generated from PipelineInputData schema so that I can run pipelines without editing JSON manually.
- Acceptance: `PipelineInputData` base class (new Pydantic model, analogous to `PipelineContext`). Pipelines declare expected input shape by subclassing. UI generates form fields from schema. Falls back to JSON editor when no `PipelineInputData` defined.

**US-017**: As a pipeline developer, I want the UI to work during development with hot reload so that I can iterate on both pipeline code and UI simultaneously.
- Acceptance: `llm-pipeline ui --dev` starts Vite dev server with HMR proxying API requests to FastAPI backend. Frontend changes reflect immediately without page reload.

### Phase 3: Step Creator & Visual Editor

**US-018**: As a pipeline prototyper, I want to generate step scaffolding from natural language so that I can create new steps without writing boilerplate.
- Acceptance: Step Creator view at `/creator`. Input form: step name, description, input context. "Generate" button triggers meta-pipeline. Output: Instructions class, Step class, Extraction classes, YAML prompts.

**US-019**: As a pipeline prototyper, I want to preview and edit generated code so that I can refine output before accepting.
- Acceptance: Monaco editor in Step Creator view. Tabbed view: Step, Instructions, Extractions, Prompts. Syntax highlighting for Python and YAML.

**US-020**: As a pipeline prototyper, I want to test a generated step in an isolated sandbox so that I can verify behavior without affecting production data.
- Acceptance: Docker sandbox with `--network none`, 512MB memory, 1 CPU, 60s timeout. Pre-scan for dangerous imports (`os.system`, `subprocess`, `eval`, `exec`, `__import__`). Results viewable in Step Detail component (reused from Phase 2).

**US-021**: As a pipeline prototyper, I want auto-integration of accepted steps so that I don't have to manually wire strategy, registry, and prompts.
- Acceptance: "Accept" action writes generated files to codebase AND updates strategy definition, registry configuration, and registers prompt templates. One flow from natural language to working integrated step.

**US-022**: As a pipeline prototyper, I want draft steps saved even when they have compile errors so that I can resume work across sessions.
- Acceptance: Creator workspace stored in the pipeline's SQLite database. Drafts persisted with full state including code, test results, and error messages. Survives process restart.

**US-023**: As a pipeline prototyper, I want to iterate on generated steps (modify prompts, transformations, re-test) so that I can refine behavior before accepting.
- Acceptance: Edit any generated artifact in Monaco editor, click "Test" again. Results panel updates. Full edit-test-view cycle without leaving Creator view.

**US-024**: As a pipeline developer, I want to view a pipeline as a visual step sequence so that I can understand pipeline structure at a glance.
- Acceptance: Visual Editor view at `/editor`. Pipeline displayed as linear step sequence within each strategy. Steps show name, prompt keys, extraction models. Strategy branches shown visually.

**US-025**: As a pipeline developer, I want to edit pipeline structure visually (add/remove/reorder steps, configure properties) so that I can modify pipelines without editing Python.
- Acceptance: Drag to reorder steps. Add/remove step buttons. Click step to configure properties (prompt keys, extractions, transformations) via panel. Changes reflected in visual representation.

**US-026**: As a pipeline developer, I want to compile a visual pipeline and see structured validation errors so that I can fix issues iteratively.
- Acceptance: "Compile" button instantiates the pipeline class. Runs `_validate_foreign_key_dependencies`, `_validate_registry_order`, `_build_execution_order`. Validation errors displayed inline with step highlighting. Draft saved even with errors.

---

## 8. Functional Requirements

### FR-EV: Event System

**FR-EV-001**: Define `PipelineEventEmitter` as a Python `Protocol` with a single `emit(event: PipelineEvent)` method. All event handlers implement this protocol.

**FR-EV-002**: Define `PipelineEvent` base dataclass with fields: `event_type: str`, `run_id: str`, `timestamp: datetime`, `pipeline_name: str`.

**FR-EV-003**: Define **Pipeline Lifecycle** events:
| Event | Emission Point | Data |
|-------|---------------|------|
| `PipelineStarted` | `pipeline.py` start of `execute()` | strategy_count, use_cache, use_consensus |
| `PipelineCompleted` | `pipeline.py` end of `execute()` | steps_executed, total_time_ms |
| `PipelineError` | `execute()` exception handler | error_type, error_message, step_name |

**FR-EV-004**: Define **Step Lifecycle** events:
| Event | Emission Point | Data |
|-------|---------------|------|
| `StepSelecting` | Strategy selection loop | step_index, strategy_count |
| `StepSelected` | Strategy chosen | step_name, step_number, strategy_name |
| `StepSkipped` | `should_skip()` returned true | step_name, step_number, reason |
| `StepStarted` | Step execution begins | step_name, step_number, system_key, user_key |
| `StepCompleted` | Step added to executed set | step_name, step_number, execution_time_ms |

**FR-EV-005**: Define **Cache** events:
| Event | Emission Point | Data |
|-------|---------------|------|
| `CacheLookup` | Cache check begins | step_name, input_hash |
| `CacheHit` | Cached state found | step_name, input_hash, cached_at |
| `CacheMiss` | No cache found | step_name, input_hash |
| `CacheReconstruction` | Extraction reconstruction | step_name, model_count, instance_count |

**FR-EV-006**: Define **LLM Call** events:
| Event | Emission Point | Data |
|-------|---------------|------|
| `LLMCallPrepared` | `prepare_calls()` returned | step_name, call_count, system_key, user_key |
| `LLMCallStarting` | Before `execute_llm_step` | step_name, call_index, rendered_system_prompt, rendered_user_prompt |
| `LLMCallCompleted` | After `execute_llm_step` | step_name, call_index, raw_response, parsed_result, model_name, attempt_count, validation_errors |
| `LLMCallRetry` | Retry loop iteration in `gemini.py` | step_name, attempt, max_retries, error_type, error_message |
| `LLMCallFailed` | All retries exhausted | step_name, max_retries, last_error |
| `LLMCallRateLimited` | Rate limit detected in `gemini.py` | step_name, attempt, wait_seconds, backoff_type |

**FR-EV-007**: Define **Consensus** events:
| Event | Emission Point | Data |
|-------|---------------|------|
| `ConsensusStarted` | Consensus mode entered | step_name, threshold, max_calls |
| `ConsensusAttempt` | Each consensus call | step_name, attempt, group_count |
| `ConsensusReached` | Threshold met | step_name, attempt, threshold |
| `ConsensusFailed` | Max calls exhausted | step_name, max_calls, largest_group_size |

**FR-EV-008**: Define **Instructions & Context** events:
| Event | Emission Point | Data |
|-------|---------------|------|
| `InstructionsStored` | Instructions dict updated | step_name, instruction_count |
| `InstructionsLogged` | `log_instructions()` called | step_name |
| `ContextUpdated` | `process_instructions` + merge | step_name, new_keys, context_snapshot |

**FR-EV-009**: Define **Transformation** events:
| Event | Emission Point | Data |
|-------|---------------|------|
| `TransformationStarting` | Transformation class instantiated | step_name, transformation_class |
| `TransformationCompleted` | `set_data` called with result | step_name, data_key |

**FR-EV-010**: Define **Extraction** events:
| Event | Emission Point | Data |
|-------|---------------|------|
| `ExtractionStarting` | Extraction loop begins in `step.py` | step_name, extraction_class, model_class |
| `ExtractionCompleted` | Instances stored + flushed | step_name, extraction_class, model_class, instance_count |
| `ExtractionError` | Extraction exception | step_name, extraction_class, error_message |

**FR-EV-011**: Define **State** event:
| Event | Emission Point | Data |
|-------|---------------|------|
| `StateSaved` | `_save_step_state` called | step_name, step_number, input_hash, execution_time_ms |

**FR-EV-012**: Implement `CompositeEmitter` that forwards events to multiple handlers. Accepts a list of `PipelineEventEmitter` instances.

**FR-EV-013**: Implement `LoggingEventHandler` that emits events to Python logging. Configurable log level per event category. Supplements (does not replace) existing `logger.info` calls.

**FR-EV-014**: Implement `InMemoryEventHandler` that stores events in a list. Queryable by `run_id`. Thread-safe for concurrent access. Default handler when UI is active.

**FR-EV-015**: Implement `SQLiteEventHandler` that persists events to a `pipeline_events` table in the same SQLite database the pipeline uses. Opt-in (not default). Schema: `id, run_id, event_type, event_data (JSON), timestamp`. Indexes on `run_id` and `event_type`.

**FR-EV-016**: Zero overhead when no emitter configured. `PipelineConfig.__init__()` accepts optional `event_emitter` parameter. When `None`, event emission is a single `if` check at each emission point. Existing pipelines work unchanged.

### FR-PR: Provider API

**FR-PR-001**: Define `LLMCallResult` dataclass:
```python
@dataclass
class LLMCallResult:
    parsed: dict[str, Any] | None       # Validated JSON dict (same as current return)
    raw_response: str | None             # Original LLM response text before JSON extraction
    model_name: str | None               # Model identifier (e.g., "gemini-2.0-flash-lite")
    attempt_count: int                   # Number of attempts (1 = first try success)
    validation_errors: list[str]         # Accumulated validation errors across attempts
```

**FR-PR-002**: Update `LLMProvider` ABC (`provider.py:11`): `call_structured()` returns `LLMCallResult` instead of `Optional[Dict[str, Any]]`. This is a clean break with no backward compatibility shim. Custom `LLMProvider` implementations must update their return type.

**FR-PR-003**: Update `GeminiProvider.call_structured()` (`gemini.py:28`): build and return `LLMCallResult`. Capture raw response text, model name, attempt count, and accumulated validation errors.

**FR-PR-004**: Update `executor.py`: handle `LLMCallResult` return type. `result_dict = provider.call_structured(...)` becomes `result = provider.call_structured(...)`, uses `result.parsed`.

**FR-PR-005**: Update `_save_step_state()` in `pipeline.py`: populate `PipelineStepState.model` from `LLMCallResult.model_name`.

### FR-PI: Pipeline Introspection

**FR-PI-001**: Implement pipeline metadata extraction via runtime introspection. Import pipeline classes and inspect their structure. Extract: pipeline name, strategies (from `PipelineStrategies`), step order (from `_build_execution_order`), prompt keys per step, extraction models per step, transformation classes per step.

**FR-PI-002**: Extract schema metadata: instruction class fields (from Pydantic model), extraction model fields, context class fields. Provide field names, types, descriptions, and constraints.

**FR-PI-003**: Load prompt templates from the `prompts` database table for display. Show template text with variable placeholders identified.

**FR-PI-004**: Define `PipelineInputData` as a new Pydantic base class (analogous to `PipelineContext`) declaring the expected input shape for a pipeline. Pipelines that support UI-initiated runs subclass `PipelineInputData` to declare their input fields. The UI generates form fields from the Pydantic schema. File uploads are a future extension (dependency on input type safety first).

**FR-PI-005**: Graceful error display when introspection fails. Reuse existing validation error messaging (from `_validate_foreign_key_dependencies`, `_validate_registry_order`). Surface structured error messages rather than raw tracebacks. May require adjustments to existing validation/error messaging to support UI display.

### FR-BE: Backend

**FR-BE-001**: `GET /api/runs` -- List pipeline runs. Paginated, filterable by pipeline name and date range. Data source: `pipeline_run_instances` table. Response: array of run summaries (run_id, pipeline_name, started_at, status, step_count, total_time_ms).

**FR-BE-002**: `GET /api/runs/{run_id}` -- Run summary. Data source: `pipeline_run_instances` + `pipeline_step_states` WHERE `run_id`. Response: run metadata + step list with status and timing.

**FR-BE-003**: `GET /api/runs/{run_id}/steps` -- All steps for a run. Data source: `pipeline_step_states` WHERE `run_id` ORDER BY `step_number`. Response: array of step summaries.

**FR-BE-004**: `GET /api/runs/{run_id}/steps/{step_number}` -- Single step detail. Data source: `pipeline_step_states` WHERE `run_id` AND `step_number`. Response: full step state including result_data, context_snapshot, prompt keys, model, execution_time_ms.

**FR-BE-005**: `GET /api/runs/{run_id}/events` -- All events for a run. Data source: `InMemoryEventHandler` (active runs) or `pipeline_events` table (persisted). Response: array of typed events.

**FR-BE-006**: `GET /api/runs/{run_id}/context` -- Context evolution. Data source: `pipeline_step_states.context_snapshot` aggregated across steps. Response: ordered array of context snapshots with step names.

**FR-BE-007**: `GET /api/prompts` -- List all prompt templates. Data source: `prompts` table. Response: array of templates with keys, types, and template text.

**FR-BE-008**: `GET /api/pipelines` -- List discovered pipelines. Data source: runtime introspection per FR-PI-001. Response: array of pipeline metadata (name, strategies, step order, schemas).

**FR-BE-009**: `GET /api/pipelines/{pipeline_name}` -- Single pipeline detail with full introspection data per FR-PI-001 through FR-PI-003.

**FR-BE-010**: WebSocket at `/ws/runs/{run_id}` for live event streaming. Events forwarded from `InMemoryEventHandler` to connected WebSocket clients. Support 100+ concurrent connections.

**FR-BE-011**: Sync-to-async bridge. Pipeline execution is synchronous. The backend runs it via `asyncio.to_thread()` and forwards events to WebSocket clients through `asyncio.Queue`.

**FR-BE-012**: `POST /api/runs` -- Trigger a new pipeline run from the UI. Request body: pipeline name + input data (matching `PipelineInputData` schema or raw JSON). Response: run_id. Execution begins asynchronously; events streamed via WebSocket.

### FR-FE: Frontend

**FR-FE-001**: TanStack Router with file-based routing and Zod search params. Route tree generated via `routeTree.gen.ts`. Type-safe navigation throughout.

**FR-FE-002**: **Run List** view at `/`. Table of pipeline runs with columns: run_id (truncated), pipeline_name, started_at, status, step_count, total_time_ms. Filter by pipeline name and date range. Click row navigates to Run Detail.

**FR-FE-003**: **Run Detail** view at `/runs/$runId`. Step timeline component showing execution flow. Context evolution panel with JSON diff between steps. Click step opens Step Detail panel.

**FR-FE-004**: **Step Detail** slide-over panel with tabs:
- **Input**: Step input data
- **Prompts**: Rendered system instruction + user prompt (from `LLMCallStarting` event)
- **LLM Response**: Raw response text + parsed JSON side-by-side
- **Instructions**: Pydantic model dump of step instructions
- **Context Diff**: JSON diff showing what this step added/changed
- **Extractions**: Table of extracted model instances with field values
- **Meta**: Timing, model name, attempt count, cache status, validation errors

**FR-FE-005**: **Live Execution** view at `/live`. Pipeline selector + input form (generated from `PipelineInputData` schema, JSON editor fallback). WebSocket-connected event stream (auto-scrolling). Auto-updating step timeline. Step Detail panel for completed steps. Supports both Python-initiated (auto-detect) and UI-initiated runs.

**FR-FE-006**: **Prompt Browser** view at `/prompts`. List all prompt templates. Template viewer with variable highlighting (`{variable_name}`). Filter by prompt type (system/user) and pipeline.

**FR-FE-007**: **Pipeline Structure** view at `/pipelines`. Visual representation of introspected pipeline: step order, strategy branches, prompt keys, extraction models, instruction schemas. Click-through to prompt templates and schema details.

**FR-FE-008**: `PipelineInputData`-driven form for UI-initiated runs. Generate form fields from Pydantic schema (text inputs, numbers, dropdowns for enums, nested objects as fieldsets). Fall back to JSON editor when no `PipelineInputData` defined.

**FR-FE-009**: TanStack Query for all server state (runs, steps, events, prompts, pipelines). Cache invalidation on WebSocket events. Optimistic updates where appropriate.

**FR-FE-010**: Zustand for UI state (active filters, selected step, panel open/close, theme preference).

**FR-FE-011**: Route-level code splitting. Each view loaded on demand. Monaco editor (Phase 3) lazy-loaded.

### FR-CLI: CLI

**FR-CLI-001**: `llm-pipeline ui` command starts the FastAPI server and serves the frontend (production mode, static files from `dist/`).

**FR-CLI-002**: `--dev` flag starts Vite dev server with HMR, proxying API requests to the FastAPI backend.

**FR-CLI-003**: `--port` flag sets the server port. Default: 8642.

**FR-CLI-004**: `--db` flag specifies the SQLite database path. Defaults to the pipeline's configured database.

### FR-CR: Creator (Phase 3)

**FR-CR-001**: Meta-pipeline (llm-pipeline eating its own dogfood) with 4 steps:
| Step | Input | Output |
|------|-------|--------|
| `RequirementsAnalysisStep` | NL description + input schema | Structured requirements (fields, types, validation rules, extraction targets) |
| `CodeGenerationStep` | Structured requirements | Python source (Instructions, Step, Extraction classes) |
| `PromptGenerationStep` | Requirements + generated code | YAML prompt templates (system + user) |
| `ValidationStep` | All generated artifacts | Validation report (import checks, naming compliance, signature verification) |

**FR-CR-002**: Generated artifacts: Instructions Pydantic model, Step class with `@step_definition` decorator, Extraction classes, YAML prompt templates (system + user).

**FR-CR-003**: Docker sandbox for testing generated code:
| Constraint | Value |
|-----------|-------|
| Network | `--network none` |
| Memory | 512MB limit |
| CPU | 1 CPU |
| Timeout | 60 seconds |
| Filesystem | Read-only root, writable `/workspace` only |
| Security | Pre-scan for `os.system`, `subprocess`, `eval`, `exec`, `__import__` |

**FR-CR-004**: Auto-integration on "Accept": update strategy definition to include new step, update registry configuration, register prompt templates in the prompts table. One flow from natural language to working integrated step.

**FR-CR-005**: Cross-session persistence. Creator workspace (drafts, generated code, test results, error messages) stored in the pipeline's SQLite database. Drafts survive process restart. Errored drafts preserved for continued iteration.

**FR-CR-006**: Iteration support. Edit any generated artifact (code, prompts, transformations) in Monaco editor. Re-test via sandbox. Re-compile to validate. Full edit-test-iterate cycle without leaving Creator view.

### FR-VE: Visual Editor (Phase 3)

**FR-VE-001**: Display pipeline as visual step sequence within each strategy. Steps show name, prompt keys, extraction models, transformation classes.

**FR-VE-002**: Add, remove, and reorder steps within a strategy. Drag-and-drop or button-based reordering.

**FR-VE-003**: Configure step properties via click-to-edit panel: prompt keys, extraction class assignments, transformation class assignments.

**FR-VE-004**: Strategy branch visualization. Show how strategies branch and which steps belong to which strategy. Editing is linear per strategy (not freeform canvas).

**FR-VE-005**: "Compile" button instantiates the pipeline class. Runs `_validate_foreign_key_dependencies` (`pipeline.py:257`), `_validate_registry_order` (`pipeline.py:276`), `_build_execution_order` (`pipeline.py:223`). Displays structured validation errors inline with step highlighting.

**FR-VE-006**: Draft persistence. Visual editor state (step arrangement, property configuration) saved to database even when compilation fails. Cross-session persistence.

**FR-VE-007**: Pipeline validation cannot be done incrementally. Full pipeline instantiation is required because FK dependencies, registry order, and execution order are global constraints checked at `PipelineConfig.__init__()`. The compile step is the only way to validate.

---

## 9. Technical Architecture & Stack

### TA-EV: Event System

**TA-EV-001**: New package `llm_pipeline/events/`:
```
llm_pipeline/events/
    __init__.py          # Public API exports
    types.py             # ~35 event dataclasses inheriting PipelineEvent base
    emitter.py           # PipelineEventEmitter protocol + CompositeEmitter
    handlers.py          # LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler
    result.py            # LLMCallResult dataclass
```

**TA-EV-002**: `PipelineEventEmitter` is a `typing.Protocol`, not an ABC. This allows duck-typing and avoids forcing inheritance on custom handlers.

**TA-EV-003**: `CompositeEmitter` wraps multiple handlers. Each handler's `emit()` called sequentially. If a handler raises, the error is logged but does not prevent other handlers from receiving the event.

### TA-BE: Backend

**TA-BE-001**: FastAPI application factory in `llm_pipeline/ui/app.py`. Mounts route modules and static file serving.

**TA-BE-002**: Route modules:
```
llm_pipeline/ui/routes/
    __init__.py
    runs.py           # /api/runs endpoints
    steps.py          # /api/runs/{run_id}/steps endpoints
    events.py         # /api/runs/{run_id}/events endpoints
    prompts.py        # /api/prompts endpoints
    pipelines.py      # /api/pipelines endpoints (introspection)
    websocket.py      # /ws/runs/{run_id} WebSocket handler
    creator.py        # /api/creator/* endpoints [Phase 3]
```

**TA-BE-003**: Sync-to-async bridge: pipeline execution runs in `asyncio.to_thread()`. Events forwarded to WebSocket clients via `asyncio.Queue`. Each active run has one queue; multiple WebSocket clients consume from copies.

**TA-BE-004**: Pipeline introspection service. Imports pipeline classes, inspects `PipelineStrategies`, `PipelineDatabaseRegistry`, `PipelineConfig`. Extracts metadata without executing the pipeline. Caches introspection results.

**TA-BE-005**: WebSocket lifecycle: client connects to `/ws/runs/{run_id}`. If run is active, events streamed in real-time. If run is complete, all persisted events sent as batch then connection closed. Heartbeat ping every 30s.

### TA-FE: Frontend

**TA-FE-001**: React 19, TypeScript, Vite. Bundled as static files into `llm_pipeline/ui/frontend/dist/`. Served by FastAPI in production.

**TA-FE-002**: TanStack Router file-based routing with `routeTree.gen.ts`:
```
src/routes/
    __root.tsx          # Root layout (sidebar + outlet)
    index.tsx           # "/" -> RunList
    runs/
        $runId.tsx      # "/runs/$runId" -> RunDetail
    live.tsx            # "/live" -> LiveExecution
    prompts.tsx         # "/prompts" -> PromptBrowser
    pipelines/
        index.tsx       # "/pipelines" -> Pipeline list + structure
    creator.tsx         # "/creator" [Phase 3]
    editor.tsx          # "/editor" [Phase 3]
```

**TA-FE-003**: TanStack Query for server state management. Query keys namespaced by resource type. Automatic refetching on window focus. Cache time: 5 minutes for run lists, 30 seconds for active run data.

**TA-FE-004**: Zustand for UI-only state: active filters, selected step ID, panel visibility, theme preference, sidebar collapsed state.

**TA-FE-005**: Tailwind CSS + shadcn/ui component library. Dark mode default (developer tool convention). Color tokens for step status (pending: gray, running: blue, completed: green, failed: red, skipped: yellow).

**TA-FE-006**: Monaco editor for Phase 3 (Step Creator). Lazy-loaded via dynamic import. Python and YAML language support. Read-only mode for prompt viewing in Phase 2.

### TA-PK: Packaging

**TA-PK-001**: `pyproject.toml` additions:
```toml
[project.optional-dependencies]
ui = [
    "fastapi>=0.100",
    "uvicorn>=0.20",
    "websockets>=11.0",
]

[project.scripts]
llm-pipeline = "llm_pipeline.ui.cli:main"
```

**TA-PK-002**: Frontend build: `npm run build` in `llm_pipeline/ui/frontend/` outputs to `dist/`. This `dist/` directory is included in the Python package via `pyproject.toml` package-data configuration.

**TA-PK-003**: Development mode: Vite dev server runs on a separate port, proxies `/api` and `/ws` requests to the FastAPI backend. No pre-built frontend needed during development.

**TA-PK-004**: Import guard: `llm_pipeline/ui/__init__.py` checks for FastAPI availability. If `[ui]` extra not installed, raises `ImportError` with message: `pip install llm-pipeline[ui]`.

---

## 10. Data Model & API Specification

### Data Models

**DM-001**: `PipelineEvent` base dataclass:
```python
@dataclass
class PipelineEvent:
    event_type: str
    run_id: str
    pipeline_name: str
    timestamp: datetime
```
All ~35 events inherit from this base. Each adds category-specific fields as defined in FR-EV-003 through FR-EV-011.

**DM-002**: `LLMCallResult` dataclass (per FR-PR-001):
```python
@dataclass
class LLMCallResult:
    parsed: dict[str, Any] | None
    raw_response: str | None
    model_name: str | None
    attempt_count: int
    validation_errors: list[str]
```

**DM-003**: Existing tables (no schema changes):
- `pipeline_step_states` -- Step execution audit trail (defined in `state.py:24`)
- `pipeline_run_instances` -- Run-level metadata (defined in `state.py:107`)
- `prompts` -- Prompt templates (defined in `db/prompt.py`)

**DM-004**: New table `pipeline_events`:
```sql
CREATE TABLE pipeline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_data JSON NOT NULL,
    timestamp DATETIME NOT NULL
);
CREATE INDEX ix_pipeline_events_run_id ON pipeline_events(run_id);
CREATE INDEX ix_pipeline_events_event_type ON pipeline_events(event_type);
```

**DM-005**: New tables for Creator workspace (Phase 3):
```sql
CREATE TABLE draft_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    generated_code JSON NOT NULL,      -- {instructions, step, extractions, prompts}
    test_results JSON,                  -- last sandbox execution results
    validation_errors JSON,             -- last validation report
    status TEXT NOT NULL DEFAULT 'draft', -- draft, tested, accepted, error
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE draft_pipelines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    structure JSON NOT NULL,            -- step order, strategy config, property assignments
    compilation_errors JSON,            -- last compile result
    status TEXT NOT NULL DEFAULT 'draft',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

### REST API Specification

**API-001**: `GET /api/runs`
- Query params: `pipeline_name` (optional), `from_date` (optional), `to_date` (optional), `page` (default 1), `page_size` (default 50)
- Response: `{ runs: RunSummary[], total: int, page: int, page_size: int }`
- `RunSummary`: `{ run_id, pipeline_name, started_at, completed_at, status, step_count, total_time_ms }`

**API-002**: `GET /api/runs/{run_id}`
- Response: `{ run_id, pipeline_name, started_at, completed_at, status, steps: StepSummary[] }`
- `StepSummary`: `{ step_name, step_number, status, execution_time_ms, model, cached }`

**API-003**: `GET /api/runs/{run_id}/steps`
- Response: `{ steps: StepSummary[] }`

**API-004**: `GET /api/runs/{run_id}/steps/{step_number}`
- Response: `{ step_name, step_number, result_data, context_snapshot, prompt_system_key, prompt_user_key, prompt_version, model, execution_time_ms, input_hash, created_at }`

**API-005**: `GET /api/runs/{run_id}/events`
- Query params: `event_type` (optional filter)
- Response: `{ events: PipelineEvent[] }`

**API-006**: `GET /api/runs/{run_id}/context`
- Response: `{ steps: { step_name: str, step_number: int, context_snapshot: dict }[] }`

**API-007**: `GET /api/prompts`
- Query params: `prompt_type` (optional: system/user), `pipeline_name` (optional)
- Response: `{ prompts: PromptTemplate[] }`
- `PromptTemplate`: `{ key, type, template_text, variables: str[], pipeline_name }`

**API-008**: `GET /api/pipelines`
- Response: `{ pipelines: PipelineMetadata[] }`
- `PipelineMetadata`: `{ name, strategy_count, step_count, has_input_schema }`

**API-009**: `GET /api/pipelines/{pipeline_name}`
- Response: Full introspection data per FR-PI-001 through FR-PI-003. Includes strategies, step order, prompt keys, extraction models, instruction schemas, context schemas, prompt templates.

**API-010**: `POST /api/runs`
- Request: `{ pipeline_name: str, input_data: dict }`
- Response: `{ run_id: str }`
- Side effect: Pipeline execution starts asynchronously. Events streamed via WebSocket.

### WebSocket API

**API-011**: `WS /ws/runs/{run_id}`
- Server sends: JSON-serialized `PipelineEvent` objects as they occur
- Message format: `{ event_type: str, run_id: str, timestamp: str, ...event_specific_fields }`
- Connection lifecycle: connect -> receive events (or batch if run complete) -> server closes on run completion
- Heartbeat: server sends ping every 30 seconds

### Creator API (Phase 3)

**API-012**: `POST /api/creator/generate`
- Request: `{ step_name: str, description: str, input_context: dict }`
- Response: `{ draft_id: int, generated_code: { instructions: str, step: str, extractions: str, prompts: str }, validation_report: dict }`

**API-013**: `POST /api/creator/test/{draft_id}`
- Request: `{ sample_data: dict, code_overrides?: { instructions?: str, step?: str, extractions?: str, prompts?: str } }`
- Response: `{ success: bool, results: dict, errors: str[], execution_time_ms: int }`

**API-014**: `POST /api/creator/accept/{draft_id}`
- Request: `{ target_pipeline?: str, target_strategy?: str }`
- Response: `{ files_written: str[], strategy_updated: bool, registry_updated: bool, prompts_registered: bool }`

**API-015**: `GET /api/creator/drafts`
- Response: `{ drafts: DraftStep[] }`

**API-016**: `POST /api/editor/compile`
- Request: `{ pipeline_structure: dict }`
- Response: `{ success: bool, errors: ValidationError[], draft_id: int }`

---

## 11. Event Specification

Events are organized by category. Each event inherits from `PipelineEvent` (DM-001) and adds category-specific fields. ~35 events total across 9 categories.

### EVT-PL: Pipeline Lifecycle (3 events)

**EVT-PL-001** `PipelineStarted`: Emitted at start of `execute()` in `pipeline.py`. Fields: `strategy_count: int`, `use_cache: bool`, `use_consensus: bool`.

**EVT-PL-002** `PipelineCompleted`: Emitted at end of `execute()`. Fields: `steps_executed: int`, `total_time_ms: float`.

**EVT-PL-003** `PipelineError`: Emitted in `execute()` exception handler. Fields: `error_type: str`, `error_message: str`, `step_name: str | None`.

### EVT-ST: Step Lifecycle (5 events)

**EVT-ST-001** `StepSelecting`: Emitted at strategy selection loop. Fields: `step_index: int`, `strategy_count: int`.

**EVT-ST-002** `StepSelected`: Emitted when strategy chosen. Fields: `step_name: str`, `step_number: int`, `strategy_name: str`.

**EVT-ST-003** `StepSkipped`: Emitted when `should_skip()` returns true. Fields: `step_name: str`, `step_number: int`, `reason: str`.

**EVT-ST-004** `StepStarted`: Emitted when step execution begins. Fields: `step_name: str`, `step_number: int`, `system_key: str`, `user_key: str`.

**EVT-ST-005** `StepCompleted`: Emitted when step added to executed set. Fields: `step_name: str`, `step_number: int`, `execution_time_ms: float`.

### EVT-CA: Cache (4 events)

**EVT-CA-001** `CacheLookup`: Emitted when cache check begins. Fields: `step_name: str`, `input_hash: str`.

**EVT-CA-002** `CacheHit`: Emitted when cached state found. Fields: `step_name: str`, `input_hash: str`, `cached_at: datetime`.

**EVT-CA-003** `CacheMiss`: Emitted when no cache found. Fields: `step_name: str`, `input_hash: str`.

**EVT-CA-004** `CacheReconstruction`: Emitted during extraction reconstruction from cache. Fields: `step_name: str`, `model_count: int`, `instance_count: int`.

### EVT-LLM: LLM Calls (6 events)

**EVT-LLM-001** `LLMCallPrepared`: Emitted after `prepare_calls()`. Fields: `step_name: str`, `call_count: int`, `system_key: str`, `user_key: str`.

**EVT-LLM-002** `LLMCallStarting`: Emitted before `execute_llm_step`. Fields: `step_name: str`, `call_index: int`, `rendered_system_prompt: str`, `rendered_user_prompt: str`. Source: captured from locals in `executor.py:79-100`.

**EVT-LLM-003** `LLMCallCompleted`: Emitted after `execute_llm_step`. Fields: `step_name: str`, `call_index: int`, `raw_response: str | None`, `parsed_result: dict | None`, `model_name: str | None`, `attempt_count: int`, `validation_errors: list[str]`. Source: `LLMCallResult` fields.

**EVT-LLM-004** `LLMCallRetry`: Emitted on retry loop iteration in `gemini.py`. Fields: `step_name: str`, `attempt: int`, `max_retries: int`, `error_type: str`, `error_message: str`.

**EVT-LLM-005** `LLMCallFailed`: Emitted when all retries exhausted. Fields: `step_name: str`, `max_retries: int`, `last_error: str`.

**EVT-LLM-006** `LLMCallRateLimited`: Emitted on rate limit detection in `gemini.py`. Fields: `step_name: str`, `attempt: int`, `wait_seconds: float`, `backoff_type: str`.

### EVT-CON: Consensus (4 events)

**EVT-CON-001** `ConsensusStarted`: Emitted when consensus mode entered. Fields: `step_name: str`, `threshold: float`, `max_calls: int`.

**EVT-CON-002** `ConsensusAttempt`: Emitted per consensus call. Fields: `step_name: str`, `attempt: int`, `group_count: int`.

**EVT-CON-003** `ConsensusReached`: Emitted when threshold met. Fields: `step_name: str`, `attempt: int`, `threshold: float`.

**EVT-CON-004** `ConsensusFailed`: Emitted when max calls exhausted. Fields: `step_name: str`, `max_calls: int`, `largest_group_size: int`.

### EVT-INS: Instructions & Context (3 events)

**EVT-INS-001** `InstructionsStored`: Emitted when instructions dict updated. Fields: `step_name: str`, `instruction_count: int`.

**EVT-INS-002** `InstructionsLogged`: Emitted when `log_instructions()` called. Fields: `step_name: str`.

**EVT-INS-003** `ContextUpdated`: Emitted after `process_instructions` + context merge. Fields: `step_name: str`, `new_keys: list[str]`, `context_snapshot: dict`.

### EVT-TF: Transformation (2 events)

**EVT-TF-001** `TransformationStarting`: Emitted when transformation class instantiated. Fields: `step_name: str`, `transformation_class: str`.

**EVT-TF-002** `TransformationCompleted`: Emitted when `set_data` called with result. Fields: `step_name: str`, `data_key: str`.

### EVT-EX: Extraction (3 events)

**EVT-EX-001** `ExtractionStarting`: Emitted when extraction loop begins in `step.py`. Fields: `step_name: str`, `extraction_class: str`, `model_class: str`.

**EVT-EX-002** `ExtractionCompleted`: Emitted after instances stored and flushed. Fields: `step_name: str`, `extraction_class: str`, `model_class: str`, `instance_count: int`.

**EVT-EX-003** `ExtractionError`: Emitted on extraction exception. Fields: `step_name: str`, `extraction_class: str`, `error_message: str`.

### EVT-SA: State (1 event)

**EVT-SA-001** `StateSaved`: Emitted when `_save_step_state` called. Fields: `step_name: str`, `step_number: int`, `input_hash: str`, `execution_time_ms: float`.

---

## 12. Non-Functional Requirements

**NFR-001**: Event emission overhead with no handler attached: <1ms per event point (single `if` check).

**NFR-002**: Event emission overhead with `InMemoryEventHandler`: <5ms per event (list append + thread lock).

**NFR-003**: UI backend supports 100+ concurrent WebSocket connections without degradation.

**NFR-004**: Run list API response: <200ms for 10k+ runs (paginated query with indexes).

**NFR-005**: Step detail API response: <100ms (single row lookup by composite key).

**NFR-006**: Phase 3 Docker sandbox enforces zero network access (`--network none`), 512MB memory, 1 CPU, 60s timeout.

**NFR-007**: Backward compatibility: existing pipelines work unchanged without `event_emitter`. No import changes required for users who don't use events.

**NFR-008**: Python version: 3.11+ (same as existing requirement).

**NFR-009**: Frontend bundle size: <500KB gzip for Phase 2 views. Monaco editor (Phase 3) loaded lazily.

**NFR-010**: UI startup time: `llm-pipeline ui` serves first page within 3 seconds.

**NFR-011**: Hot reload latency (dev mode): frontend changes reflected in <1 second via Vite HMR.

**NFR-012**: Security: localhost-only by default. No authentication required. No PII stored. The UI does not expose any functionality beyond what the Python API already provides.

---

## 13. UI/UX Guidelines

### Design Principles

This is a developer tool, not a consumer product. Optimize for:
- **Information density**: Developers want data, not whitespace. Dense tables, collapsible panels, multi-panel layouts
- **Keyboard navigation**: All primary actions accessible via keyboard shortcuts (Cmd/Ctrl+K for command palette)
- **Dark mode default**: Developer tool convention. Light mode available as option
- **Desktop-targeted**: Minimum viewport 1280px. No mobile optimization. Designed for 1440px+ primary use

### Component Library

shadcn/ui provides the base component set. Customizations:
- Monospace font for all code/data display (JSON, prompts, responses)
- Step status colors: pending (gray-400), running (blue-500), completed (green-500), failed (red-500), skipped (yellow-500), cached (purple-500)
- Sidebar navigation: collapsible, icons + labels. Active route highlighted
- Slide-over panels: used for Step Detail to maintain context (run timeline visible behind panel)
- Toast notifications: for async operations (run started, run completed, generation complete)

### Layout

- **Root layout**: Sidebar (left, 240px collapsed to 48px) + main content area
- **Run Detail**: Split view -- timeline top, detail panel bottom (or side, user-resizable)
- **Live Execution**: Three-column -- pipeline selector (left), event stream (center), step detail (right)
- **Step Creator** (Phase 3): Three-panel -- input form (left), code editor (center), results (right)
- **Visual Editor** (Phase 3): Canvas area (center), step properties panel (right)

### Data Display

- JSON displayed with syntax highlighting and collapsible nodes (max depth 3 expanded by default)
- Large JSON objects (>100 keys) show summary with expand-on-demand
- Timestamps displayed in local timezone with relative time tooltip ("2 hours ago")
- Run IDs truncated to 8 characters in tables, full ID on hover/click
- Prompt templates display with `{variable_name}` highlighted in distinct color

---

## 14. Files to Create & Modify

### New Packages

| Package | Purpose | Phase |
|---------|---------|-------|
| `llm_pipeline/events/` | Event types, emitter protocol, handlers, LLMCallResult | 1 |
| `llm_pipeline/ui/` | FastAPI backend, CLI, frontend app | 2 |
| `llm_pipeline/creator/` | Meta-pipeline, sandbox, templates | 3 |

### Modified Files

| File | Changes | Phase |
|------|---------|-------|
| `llm_pipeline/pipeline.py` | Add `event_emitter` param, emit events throughout `execute()` | 1 |
| `llm_pipeline/llm/gemini.py` | Return `LLMCallResult`, capture raw response, emit retry events | 1 |
| `llm_pipeline/llm/executor.py` | Handle `LLMCallResult`, capture rendered prompts | 1 |
| `llm_pipeline/llm/provider.py` | Update `call_structured()` return type to `LLMCallResult` | 1 |
| `llm_pipeline/step.py` | Emit extraction events in `extract_data()` | 1 |
| `llm_pipeline/state.py` | No schema changes (model field already exists at line 87) | - |
| `llm_pipeline/__init__.py` | Export new event types and LLMCallResult | 1 |
| `pyproject.toml` | Add `[ui]` optional deps, CLI entry point, frontend package-data | 2 |

### New Event System Files (Phase 1)

```
llm_pipeline/events/
    __init__.py          # Public API: PipelineEventEmitter, CompositeEmitter, all event types
    types.py             # ~35 event dataclasses
    emitter.py           # PipelineEventEmitter protocol + CompositeEmitter
    handlers.py          # LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler
    result.py            # LLMCallResult dataclass
```

### New Backend Files (Phase 2)

```
llm_pipeline/ui/
    __init__.py          # Import guard for [ui] extra
    cli.py               # CLI entry point (llm-pipeline ui)
    app.py               # FastAPI application factory
    bridge.py            # Sync-to-async pipeline execution bridge
    introspection.py     # Pipeline introspection service
    routes/
        __init__.py
        runs.py          # /api/runs endpoints
        steps.py         # /api/runs/{run_id}/steps endpoints
        events.py        # /api/runs/{run_id}/events endpoints
        prompts.py       # /api/prompts endpoints
        pipelines.py     # /api/pipelines endpoints
        websocket.py     # /ws/runs/{run_id} WebSocket handler
```

### Frontend File Tree (Phase 2)

```
llm_pipeline/ui/frontend/
    package.json
    tsconfig.json
    vite.config.ts
    tailwind.config.ts
    src/
        main.tsx
        routeTree.gen.ts         # TanStack Router generated
        routes/
            __root.tsx           # Root layout (sidebar + outlet)
            index.tsx            # "/" -> RunList
            runs/
                $runId.tsx       # "/runs/$runId" -> RunDetail
            live.tsx             # "/live" -> LiveExecution
            prompts.tsx          # "/prompts" -> PromptBrowser
            pipelines/
                index.tsx        # "/pipelines" -> Pipeline list + structure
            creator.tsx          # "/creator" [Phase 3]
            editor.tsx           # "/editor" [Phase 3]
        api/                     # TanStack Query hooks
            runs.ts
            steps.ts
            events.ts
            prompts.ts
            pipelines.ts
            websocket.ts
        stores/                  # Zustand stores
            ui.ts
            filters.ts
        components/
            StepTimeline.tsx
            JsonDiff.tsx
            ContextEvolution.tsx
            EventStream.tsx
            PromptViewer.tsx
            InputForm.tsx        # PipelineInputData-generated form
        lib/
            types.ts             # Shared TypeScript types
            utils.ts
```

### New Creator Files (Phase 3)

```
llm_pipeline/creator/
    __init__.py
    meta_pipeline.py           # Meta-pipeline definition (4 steps)
    steps/
        __init__.py
        requirements.py        # RequirementsAnalysisStep
        code_generation.py     # CodeGenerationStep
        prompt_generation.py   # PromptGenerationStep
        validation.py          # ValidationStep
    sandbox.py                 # Docker sandbox management
    integrator.py              # Auto-integration (strategy, registry, prompts)
    templates/                 # Jinja2 code generation templates
        step.py.j2
        instructions.py.j2
        extraction.py.j2
        prompts.yaml.j2
    prompts/                   # YAML prompts for the meta-pipeline
        requirements_analysis.system.yaml
        requirements_analysis.user.yaml
        code_generation.system.yaml
        code_generation.user.yaml
        prompt_generation.system.yaml
        prompt_generation.user.yaml
        validation.system.yaml
        validation.user.yaml

llm_pipeline/ui/routes/
    creator.py                 # /api/creator/* endpoints
    editor.py                  # /api/editor/* endpoints
```

---

## 15. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Event emission overhead in hot path | Pipeline execution slows down | No-op when `event_emitter is None` (single `if` check). Benchmark in CI. Handler `emit()` must be non-blocking |
| `LLMCallResult` breaking change | Custom `LLMProvider` implementations break | Clean break documented in changelog. Only affects third-party providers. Migration is straightforward (wrap return value) |
| TanStack Router ecosystem maturity | Fewer examples/community resources than React Router | TanStack Router is production-ready with strong TypeScript support. File-based routing reduces boilerplate. Fallback: migrate to React Router if critical issues found |
| Frontend build complexity | Additional build step, Node.js dev dependency | Vite builds to static files; no Node.js required at runtime. Pre-built frontend included in Python package. Only developers contributing to UI need Node.js |
| Docker dependency in Phase 3 | Users without Docker cannot use sandbox | Docker only required for sandbox testing. Graceful error if Docker not available ("Docker required for sandbox testing"). Generated code can still be reviewed and accepted without testing |
| Visual editor complexity (Phase 3) | Scope creep, delayed delivery | Linear editor only (not freeform canvas). Compile-to-validate avoids incremental validation complexity. MVP: step reordering + property editing + compile |
| Pipeline introspection fragility | Changes to pipeline internals break UI | Introspection service uses public API where possible. Integration tests verify introspection against real pipeline classes. Graceful degradation when introspection fails (show error, not crash) |

---

## 16. Acceptance Criteria

### Phase 1: Event System

- [ ] All ~35 events emitted at correct points in `execute()` flow (cross-reference EVT-* IDs)
- [ ] `LLMCallResult` returned by `GeminiProvider.call_structured()` (FR-PR-001 through FR-PR-003)
- [ ] `PipelineStepState.model` populated from `LLMCallResult.model_name` (FR-PR-005)
- [ ] Existing pipelines work unchanged without `event_emitter` (FR-EV-016)
- [ ] Event emission adds <1ms overhead when no handler attached (NFR-001)
- [ ] `InMemoryEventHandler` stores and retrieves events by run_id, thread-safe (FR-EV-014)
- [ ] `SQLiteEventHandler` persists to `pipeline_events` table with indexes (FR-EV-015)
- [ ] `CompositeEmitter` forwards to multiple handlers, error isolation (FR-EV-012)
- [ ] Unit tests for all event types and all three handlers

### Phase 2: UI Debugger

- [ ] All REST endpoints return correct data (API-001 through API-010)
- [ ] WebSocket streams events in real-time during pipeline execution (API-011)
- [ ] Run List view loads with <200ms for 10k+ runs (NFR-004)
- [ ] Step Detail shows all 7 tabs with correct data (FR-FE-004)
- [ ] Live Execution supports both Python-initiated and UI-initiated runs (FR-FE-005)
- [ ] Prompt Browser displays templates with variable highlighting (FR-FE-006)
- [ ] Pipeline Structure view shows introspected pipeline metadata (FR-FE-007)
- [ ] PipelineInputData-driven form generates from Pydantic schema (FR-FE-008)
- [ ] `llm-pipeline ui` starts server, `--dev` enables hot reload (FR-CLI-001, FR-CLI-002)
- [ ] `pip install llm-pipeline[ui]` installs all required dependencies (TA-PK-001)
- [ ] Import guard shows helpful error when `[ui]` not installed (TA-PK-004)
- [ ] 100+ concurrent WebSocket connections supported (NFR-003)

### Phase 3: Step Creator & Visual Editor

- [ ] Meta-pipeline generates valid Instructions, Step, Extraction, and YAML files from NL description (FR-CR-001, FR-CR-002)
- [ ] Docker sandbox enforces all constraints (FR-CR-003)
- [ ] Generated step executes in sandbox and produces viewable results (US-020)
- [ ] Auto-integration updates strategy, registry, and registers prompts (FR-CR-004)
- [ ] Cross-session persistence: drafts survive process restart (FR-CR-005)
- [ ] Full generate-edit-test-iterate-accept cycle works end-to-end (US-018 through US-023)
- [ ] Visual editor displays pipeline as linear step sequence (FR-VE-001)
- [ ] Add/remove/reorder steps and configure properties (FR-VE-002, FR-VE-003)
- [ ] Compile button validates pipeline and displays structured errors (FR-VE-005)
- [ ] Draft pipelines persist with compile errors (FR-VE-006)
- [ ] Strategy branches visualized (FR-VE-004)
