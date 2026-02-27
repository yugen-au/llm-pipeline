# Research Summary

## Executive Summary

Cross-referenced both research files against actual codebase (context.py, pipeline.py, __init__.py, introspection.py, ui/routes/pipelines.py, ui/routes/runs.py). Line numbers, class structures, ClassVar patterns, and execute() flow all validated accurately. Five architectural questions surfaced and resolved with CEO decisions: new `input_data` param on execute(), placement in context.py, strict error on missing input, expanded scope including introspection + UI, and __init_subclass__ type guard.

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
- RESOLVED: step-1 pseudocode (L108-117) validates `initial_context`, step-2 (L263) proposes new `input_data` param. CEO decided: new `input_data` param on execute() for clean separation

### UI Integration State
**Source:** research/step-1-codebase-architecture.md

- pipelines.py L98-102: has_input_schema currently checks STEP instruction schemas, not pipeline-level input -- research correctly flags this
- runs.py L223-224: input_data passed as BOTH constructor arg AND initial_context to execute() -- RESOLVED: new `input_data` param on execute() separates concerns; runs.py will pass input_data= instead of mixing into initial_context
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
| Validation target: new input_data param on execute() vs validate initial_context? | New input_data param -- clean separation, aligns with runs.py pattern | execute() signature gains `input_data: Optional[Dict[str, Any]] = None`; runs.py passes input_data= separately from initial_context; validation only applies to input_data dict, not arbitrary context keys |
| File placement: context.py vs new input_data.py? | context.py -- pattern consistency | PipelineInputData lives alongside PipelineContext; both exported from same module; __init__.py adds one import line |
| No-input behavior when INPUT_DATA declared but execute() called without input? | Always error -- strict | If INPUT_DATA is set and input_data is None or empty, raise ValueError before pipeline run starts; no silent defaults |
| Scope: base class only or include introspection + UI? | Include introspection + UI route updates | Task 43 covers: base class, ClassVar, __init_subclass__ guard, execute() validation, introspection.get_metadata() adding pipeline_input_schema, pipelines.py has_input_schema using INPUT_DATA, runs.py passing input_data param, __init__.py export |
| Type guard: validate INPUT_DATA type at class definition? | Yes, __init_subclass__ -- fail fast at import | __init_subclass__ checks INPUT_DATA is PipelineInputData subclass if set; TypeError at import time prevents runtime surprises |

## Assumptions Validated
- [x] PipelineContext(BaseModel) with pass body exists in context.py
- [x] REGISTRY/STRATEGIES ClassVars use Type[...] = None pattern on PipelineConfig
- [x] __init_subclass__ enforces naming for registry/strategies keyword params
- [x] execute() flow: param setup -> run record -> events -> step loop (L424-817)
- [x] PipelineIntrospector._get_schema() handles BaseModel subclasses via model_json_schema()
- [x] No new dependencies needed -- pydantic>=2.0 already in pyproject.toml
- [x] Naming convention PipelineInputData / INPUT_DATA follows existing patterns
- [x] __init__.py exports PipelineContext -- same pattern for PipelineInputData
- [x] UI response models (PipelineMetadata.pipeline_input_schema, TriggerRunRequest.input_data) already prepared
- [x] New input_data param on execute() is clean separation -- aligns with runs.py TriggerRunRequest.input_data (CEO confirmed)
- [x] context.py is correct placement -- pattern consistency over semantic separation (CEO confirmed)
- [x] Strict error behavior when INPUT_DATA set but no input provided (CEO confirmed)
- [x] __init_subclass__ type guard for INPUT_DATA -- fail fast at import (CEO confirmed)
- [x] Scope includes introspection.get_metadata() + UI route updates (CEO confirmed)
- [x] introspection.py get_metadata() returns dict with no pipeline_input_schema key currently -- adding it is additive, no breaking change
- [x] pipelines.py has_input_schema (L98-102) currently checks step instruction schemas -- changing to check INPUT_DATA is behavioral change but more correct

## Open Items
- Discriminated unions incompatible with `ClassVar[Optional[Type[PipelineInputData]]]` -- defer to future task if needed
- runs.py currently passes input_data into BOTH constructor and initial_context (L223-224) -- must refactor to use new execute(input_data=) param instead

## Recommendations for Planning
1. Implement in order: (a) PipelineInputData base class in context.py, (b) INPUT_DATA ClassVar + __init_subclass__ guard in pipeline.py, (c) input_data param + validation in execute(), (d) introspection.get_metadata() adds pipeline_input_schema key, (e) pipelines.py has_input_schema checks INPUT_DATA, (f) runs.py uses execute(input_data=), (g) __init__.py export
2. Files touched: context.py, pipeline.py, introspection.py, ui/routes/pipelines.py, ui/routes/runs.py, __init__.py
3. execute() validation pseudocode: if cls.INPUT_DATA is not None and input_data is None, raise ValueError; if input_data provided and cls.INPUT_DATA is not None, call cls.INPUT_DATA.model_validate(input_data) wrapping ValidationError
4. introspection.get_metadata() should add `pipeline_input_schema: cls.INPUT_DATA.model_json_schema() if cls.INPUT_DATA else None` to metadata dict
5. pipelines.py L98-102 should change from checking step instruction schemas to checking `metadata.get("pipeline_input_schema") is not None`
6. runs.py L224 should change from `pipeline.execute(data=None, initial_context=body.input_data or {})` to `pipeline.execute(data=None, input_data=body.input_data)`
7. Tests: subclassing PipelineInputData, JSON schema generation, validation pass/fail, strict error on missing input, __init_subclass__ type guard rejection, introspection metadata inclusion
