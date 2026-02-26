# Research Summary

## Executive Summary

Cross-referenced both research files against actual codebase (context.py, pipeline.py, __init__.py, introspection.py, ui/routes/pipelines.py, ui/routes/runs.py). Line numbers, class structures, ClassVar patterns, and execute() flow all validated accurately. Five architectural assumptions surfaced that require CEO clarification before planning can proceed, primarily around validation target (initial_context vs new input_data param), file placement, and scope boundaries.

## Domain Findings

### Codebase Structure Validation
**Source:** research/step-1-codebase-architecture.md

- File path prefix in research says `src/llm_pipeline/` but actual location is `llm_pipeline/` -- cosmetic, no impact on design
- Line counts, ClassVar declarations, execute() flow, and __init_subclass__ behavior all verified accurate against actual source
- context.py: 36 lines, PipelineContext(BaseModel) with pass body, __all__ export -- confirmed
- pipeline.py: 1150 lines, execute() L424-817, ClassVars at L105-106, __init_subclass__ L108-137 -- confirmed
- __init__.py: 78 lines, 36 exports -- confirmed
- introspection.py: _get_schema() at L82-95 already handles BaseModel subclasses via model_json_schema() -- confirmed

### Execute Flow and Validation Insertion Point
**Source:** research/step-1-codebase-architecture.md, research/step-2-pydantic-input-patterns.md

- Research correctly identifies insertion point between L463 (end of consensus config parsing) and L464 (self._context = initial_context.copy())
- Research correctly notes validation should happen BEFORE PipelineRun record creation (L471-478)
- CONFLICT: step-1 pseudocode (L108-117) validates `initial_context`, but step-2 (L263) proposes adding a new `input_data` parameter to execute(). These are contradictory approaches

### UI Integration State
**Source:** research/step-1-codebase-architecture.md

- pipelines.py L98-102: has_input_schema currently checks STEP instruction schemas, not pipeline-level input -- research correctly flags this
- runs.py L223-224: input_data passed as BOTH constructor arg AND initial_context to execute() -- dual-path creates ambiguity about where validation belongs
- PipelineMetadata.pipeline_input_schema field already exists (L62) -- ready for integration
- TriggerRunRequest.input_data field already exists (L63) -- ready for integration

### Pydantic v2 Patterns
**Source:** research/step-2-pydantic-input-patterns.md

- model_json_schema(), model_validate(), Field() metadata, nested model $defs -- all standard Pydantic v2 behavior, no issues
- json_schema_extra for custom UI hints (x-ui-widget etc) -- valid pattern
- Discriminated unions mentioned but incompatible with ClassVar type annotation `Type[PipelineInputData]` -- gap identified

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| pending -- see questions below | | |

## Assumptions Validated
- [x] PipelineContext(BaseModel) with pass body exists in context.py
- [x] REGISTRY/STRATEGIES ClassVars use Type[...] = None pattern on PipelineConfig
- [x] __init_subclass__ enforces naming for registry/strategies keyword params
- [x] execute() flow: param setup -> run record -> events -> step loop (L424-817)
- [x] PipelineIntrospector._get_schema() handles BaseModel subclasses
- [x] No new dependencies needed -- pydantic>=2.0 already in pyproject.toml
- [x] Naming convention PipelineInputData / INPUT_DATA follows existing patterns
- [x] __init__.py exports PipelineContext -- same pattern for PipelineInputData
- [x] UI response models (PipelineMetadata.pipeline_input_schema, TriggerRunRequest.input_data) already prepared

## Open Items
- Validation target: initial_context vs new input_data param on execute() -- contradictory proposals in research
- File placement: context.py vs new input_data.py -- semantic direction mismatch (context.py = step outputs, PipelineInputData = pipeline inputs)
- Validation behavior when INPUT_DATA declared but no input provided at runtime
- Scope: whether introspection.py and UI route changes belong in task 43 or follow-up tasks
- Type guard: whether to validate INPUT_DATA is PipelineInputData subclass at class definition time
- Discriminated unions incompatible with ClassVar[Optional[Type[PipelineInputData]]] annotation

## Recommendations for Planning
1. Resolve validation target question first -- it affects execute() signature, UI route integration, and test design
2. Keep task 43 scope to: base class + ClassVar + validation in execute() + __init__.py export; defer introspection and UI route changes to follow-up tasks
3. Add runtime type check in __init__ (not __init_subclass__) for INPUT_DATA since it's a plain ClassVar override
4. Use Pydantic defaults behavior for "INPUT_DATA set but no input" case (validate with defaults, error only if required fields missing)
5. Place PipelineInputData in context.py for pattern consistency unless CEO prefers semantic separation
