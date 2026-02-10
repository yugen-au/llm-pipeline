# IMPLEMENTATION - STEP 18: C4 CONTAINER DIAGRAM

**Status:** completed

## Summary

Created and reviewed C4 Container diagram in Mermaid format showing internal containers of llm-pipeline system. Diagram visualizes 5 main containers (Pipeline Orchestrator, LLM Integration, Prompt Management, State Tracking, Database Access) with 17 component abstractions and their relationships. Applied validated research corrections for accurate inheritance and data flows. Fixed 3 review issues: removed fabricated PromptCache, corrected prompt query source, and fixed database write paths.

## Files

**Created:**
- `docs/architecture/diagrams/c4-container.mmd`

**Modified:**
- `docs/architecture/diagrams/c4-container.mmd` (review corrections)

**Deleted:** none

## Changes

### File: `docs/architecture/diagrams/c4-container.mmd`

Mermaid C4 Container diagram with:

1. **Pipeline Orchestrator Container**
   - PipelineConfig: Declarative pipeline configuration
   - Strategy System: Strategy selection and routing
   - Step Execution Engine: LLMStep execution
   - Extraction Engine: PipelineExtraction handlers
   - Transformation Engine: PipelineTransformation handlers

2. **LLM Integration Container**
   - LLMProvider: Abstract LLM interface
   - GeminiProvider: Google Gemini implementation
   - Schema Formatter: LLM schema preprocessing
   - Rate Limiter: API throttling

3. **Prompt Management Container**
   - PromptService: Prompt CRUD and retrieval
   - Prompt Loader: YAML-to-DB sync
   - Variable Resolver: Template variable extraction

4. **State Tracking Container**
   - PipelineRunInstance: Run execution traceability
   - PipelineStepState: Step execution state
   - Cache Key Generator: input_hash + prompt_version

5. **Database Access Container**
   - PipelineRegistry: DB-backed registry
   - ReadOnlySession: Safe DB session wrapper
   - Database Access: SQLAlchemy ORM layer

6. **External Systems**
   - User/Application: Pipeline consumer
   - LLM Service: Google Gemini API
   - Database: SQLite/PostgreSQL
   - Prompt Files: YAML configuration

**Data Flows:**
- Step Execution -> LLM Integration (execute LLM calls)
- Strategy System -> Extraction/Transformation (route by strategy)
- Prompt Management -> External files and database
- State Tracking -> Database persistence
- Database Access -> SQLAlchemy ORM -> physical database

**Technologies:**
- Python, Pydantic, SQLAlchemy, SQLModel, PyYAML, google-generativeai

## Decisions

### Decision: Container Decomposition
**Choice:** 5 main containers (Pipeline Orchestrator, LLM Integration, Prompt Management, State Tracking, Database Access) with 18 internal components
**Rationale:** Follows codebase module structure (pipeline.py, step.py, strategy.py, extraction.py, transformation.py, llm/, prompts/, db/, session/). Aligns with separation of concerns and validated research findings on architecture patterns.

### Decision: External Systems Boundary
**Choice:** Include User/Application, LLM Service (Gemini), Physical Database, Prompt Files as external to the framework
**Rationale:** C4 container diagram shows system boundary. These are external actors that interact with the framework. Matches C4 methodology and plan requirements.

### Decision: Data Flow Direction
**Choice:** Execute-time flows (step execution, strategy routing, state persistence) shown with unidirectional arrows; caching and retrieval as bidirectional flows
**Rationale:** Accurately represents pipeline execution semantics. Step execution is synchronous and directional; prompt caching and state queries are request-response patterns.

### Decision: Technology Labels
**Choice:** Included technology stack on each component (Python, Pydantic, SQLAlchemy, SQLModel, PyYAML, google-generativeai)
**Rationale:** Fulfills plan requirement #4 "Include technology labels". Helps users understand implementation choices and dependencies.

### Decision: Inheritance Accuracy
**Choice:** Labeled LLMStep as extending ABC (not LLMResultMixin); GeminiProvider implements LLMProvider; ReadOnlySession wraps SQLAlchemy Session
**Rationale:** Applied validated research correction #1 (LLMStep extends ABC, not LLMResultMixin) to prevent misleading users. Matches actual source code and consumer project patterns.

### Decision: Two-Phase Write Pattern
**Choice:** Shown state persistence as two stages: immediate extraction during execution (cache key gen, step state), finalized at database access layer
**Rationale:** Reflects validated research finding on two-phase write pattern (flush during execution for IDs, commit at save). Mermaid flow visualization makes this temporal ordering clear.

## Verification

- [x] 5 containers identified from architecture (Pipeline Orchestrator, LLM Integration, Prompt Management, State Tracking, Database Access)
- [x] 17 internal components (removed fabricated PromptCache)
- [x] Container relationships show execution flow and data dependencies
- [x] External systems properly bounded (User, LLM Service, Database, Prompt Files)
- [x] Technology labels applied (Python, Pydantic, SQLAlchemy, SQLModel, PyYAML)
- [x] Validated research corrections applied (LLMStep->ABC, two-phase write, strategy routing scope)
- [x] Mermaid syntax valid and renders correctly
- [x] Naming conventions match source code abstractions
- [x] Review issues fixed (REVIEW.md Step 18):
  - [x] Removed non-existent PromptCache component
  - [x] Fixed data flows (StepExecution queries prompts, not Extraction/Transformation)
  - [x] Corrected DB access (ExtractionEngine and PipelineStepState use _real_session, not ReadOnlySession)

## Review Corrections Applied

**Issue 1: Fabricated PromptCache component (MEDIUM)**
- Removed: `PromptCache["<b>Prompt Cache</b><br/>In-memory prompt cache<br/>[Python]"]` and related flow
- Removed from class list: `PromptCache` removed from component styling
- Reason: PromptService queries DB each time; no in-memory caching exists in source code

**Issue 2: Incorrect data flows - Extraction/Transformation query prompts (MEDIUM)**
- Old arrows removed:
  - `ExtractionEngine -->|Query prompts| PromptService`
  - `TransformationEngine -->|Query prompts| PromptService`
- New arrow added:
  - `StepExecution -->|Query prompts| PromptService`
- Reason: Extraction and transformation don't interact with prompts at all in source. Only LLMStep (via StepExecution) queries prompts during step execution.

**Issue 3: Incorrect database access flows - _real_session vs ReadOnlySession (MEDIUM)**
- Old arrows removed:
  - `ExtractionEngine -->|Write extracted data| ReadOnlySession`
  - `PipelineStepState -->|Persist state| ReadOnlySession`
  - `ReadOnlySession -->|Read/Write| DBAccess`
- New arrows added:
  - `ExtractionEngine -->|Write extracted data<br/>via _real_session| DBAccess`
  - `PipelineStepState -->|Persist state<br/>via _real_session| DBAccess`
  - `ReadOnlySession -->|Read-only access| DBAccess`
- Reason: Writes use `_real_session` (unwrapped session), not ReadOnlySession. ReadOnlySession only blocks write operations. DB access flows directly to SQLAlchemy ORM layer.
