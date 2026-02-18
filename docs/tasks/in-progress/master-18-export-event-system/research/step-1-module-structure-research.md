# Step 1: Module Structure Research - Event System Exports

## Current File Inventory

### llm_pipeline/events/ directory
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports from types, emitter, models, llm.result |
| `types.py` | Base classes + 28 concrete event dataclasses + 9 category constants + registry helpers |
| `emitter.py` | PipelineEventEmitter protocol + CompositeEmitter |
| `handlers.py` | LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, DEFAULT_LEVEL_MAP |
| `models.py` | PipelineEventRecord (SQLModel table) |

### llm_pipeline/llm/result.py
- `LLMCallResult` - frozen dataclass for LLM call outcomes

---

## Detailed Export Inventory

### types.py __all__ (46 items)
**Base classes:** PipelineEvent, StepScopedEvent
**Category constants (9):** CATEGORY_PIPELINE_LIFECYCLE, CATEGORY_STEP_LIFECYCLE, CATEGORY_CACHE, CATEGORY_LLM_CALL, CATEGORY_CONSENSUS, CATEGORY_INSTRUCTIONS_CONTEXT, CATEGORY_TRANSFORMATION, CATEGORY_EXTRACTION, CATEGORY_STATE
**Concrete events (28):**
- Pipeline Lifecycle: PipelineStarted, PipelineCompleted, PipelineError
- Step Lifecycle: StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
- Cache: CacheLookup, CacheHit, CacheMiss, CacheReconstruction
- LLM Call: LLMCallPrepared, LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited
- Consensus: ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed
- Instructions/Context: InstructionsStored, InstructionsLogged, ContextUpdated
- Transformation: TransformationStarting, TransformationCompleted
- Extraction: ExtractionStarting, ExtractionCompleted, ExtractionError
- State: StateSaved

**Internal (not in __all__):** _EVENT_REGISTRY, _derive_event_type

### emitter.py __all__ (2 items)
PipelineEventEmitter, CompositeEmitter

### handlers.py __all__ (5 items)
DEFAULT_LEVEL_MAP, LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, PipelineEventRecord

### models.py __all__ (1 item)
PipelineEventRecord

### llm/result.py (no __all__, 1 class)
LLMCallResult

---

## Current events/__init__.py Exports (43 items in __all__)

Imports from: types.py (all), emitter.py (both), models.py (PipelineEventRecord), llm.result (LLMCallResult)
Also defines: resolve_event alias

**MISSING from events/__init__.py:**
- LoggingEventHandler (in handlers.py)
- InMemoryEventHandler (in handlers.py)
- SQLiteEventHandler (in handlers.py)
- DEFAULT_LEVEL_MAP (in handlers.py)

---

## Current llm_pipeline/__init__.py Exports (17 items in __all__)

From events system, ONLY exports: `PipelineEventRecord`

**MISSING from top-level __init__.py (all event system items except PipelineEventRecord):**
- Base: PipelineEvent, StepScopedEvent
- Emitters: PipelineEventEmitter, CompositeEmitter
- LLMCallResult
- Handlers: LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler
- All 28 concrete event types
- 9 category constants
- resolve_event, DEFAULT_LEVEL_MAP

---

## Existing Export Patterns in Other Subpackages

| Subpackage | Top-level re-export? | Access pattern |
|------------|---------------------|----------------|
| llm/ | NO (LLMProvider not at top level) | `from llm_pipeline.llm import LLMProvider` |
| db/ | YES (init_pipeline_db) | `from llm_pipeline import init_pipeline_db` |
| session/ | YES (ReadOnlySession) | `from llm_pipeline import ReadOnlySession` |
| events/ | PARTIAL (PipelineEventRecord only) | `from llm_pipeline import PipelineEventRecord` |

Pattern: Core orchestration types at top level. Provider/implementation details in submodules.

---

## Gap Summary

### Confirmed fix needed (no ambiguity):
1. **events/__init__.py** must add handler imports: LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, DEFAULT_LEVEL_MAP

### Architectural decision needed:
2. **llm_pipeline/__init__.py** top-level export scope - see questions below

---

## Downstream Impact
- Task 19 (FastAPI backend) depends on importable event system
- Task 43 (PipelineInputData) depends on working __init__.py exports
- Task 45 (Meta-pipeline) depends on working __init__.py exports
- All three just need events importable from either `llm_pipeline` or `llm_pipeline.events`
