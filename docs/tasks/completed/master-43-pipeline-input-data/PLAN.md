# PLANNING

## Summary
Implement PipelineInputData base class for declarative pipeline input schemas. Add INPUT_DATA ClassVar to PipelineConfig with __init_subclass__ type guard, validate input_data param in execute(), integrate with introspection metadata, update UI routes to use pipeline-level input schemas instead of step-level instruction schemas.

## Plugin & Agents
**Plugin:** python-development, backend-development
**Subagents:** backend:api-developer, backend:integration-specialist
**Skills:** none

## Phases
1. **Implementation** - Add base class, ClassVar, validation, introspection, UI integration

## Architecture Decisions

### Input Validation Target
**Choice:** New `input_data` param on execute() method
**Rationale:** Clean separation of concerns. VALIDATED_RESEARCH.md CEO decision aligns with runs.py TriggerRunRequest.input_data pattern. Avoids polluting arbitrary initial_context dict with schema validation.
**Alternatives:** Validate initial_context dict directly (rejected - couples unrelated concepts)

### File Placement
**Choice:** PipelineInputData in context.py
**Rationale:** Pattern consistency - both PipelineContext and PipelineInputData are BaseModel subclasses used for pipeline data flow. VALIDATED_RESEARCH.md CEO decision.
**Alternatives:** New input_data.py file (rejected - semantic separation less important than pattern consistency)

### Missing Input Behavior
**Choice:** Always error if INPUT_DATA declared but input_data not provided
**Rationale:** Strict validation prevents runtime surprises. If pipeline declares input schema, input is mandatory. VALIDATED_RESEARCH.md CEO decision.
**Alternatives:** Silent defaults or None (rejected - hides configuration mistakes)

### Type Guard Timing
**Choice:** __init_subclass__ validates INPUT_DATA type at class definition
**Rationale:** Fail fast at import time if INPUT_DATA is not PipelineInputData subclass. Prevents runtime TypeError after pipeline instantiation. VALIDATED_RESEARCH.md CEO decision.
**Alternatives:** Runtime validation in execute() (rejected - defers error detection unnecessarily)

### Scope Boundaries
**Choice:** Include introspection + UI route updates in this task
**Rationale:** Base class alone has no value without integration. Task 43 delivers end-to-end pipeline input schema feature. VALIDATED_RESEARCH.md CEO decision.
**Alternatives:** Base class only, defer integration (rejected - incomplete feature delivery)

## Implementation Steps

### Step 1: Add PipelineInputData Base Class
**Agent:** backend:api-developer
**Skills:** none
**Context7 Docs:** /pydantic/pydantic
**Group:** A

1. Edit llm_pipeline/context.py
2. Add PipelineInputData class after PipelineContext class (L34)
3. Use same BaseModel inheritance pattern as PipelineContext
4. Add docstring: "Base class for pipeline input data. Pipelines that require structured input should define an InputData class inheriting from this base."
5. Update __all__ export to include "PipelineInputData" (L36)

### Step 2: Add INPUT_DATA ClassVar and Type Guard
**Agent:** backend:api-developer
**Skills:** none
**Context7 Docs:** /pydantic/pydantic
**Group:** A

1. Edit llm_pipeline/pipeline.py
2. Add INPUT_DATA ClassVar after STRATEGIES (L107): `INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None`
3. Add import at top: `from llm_pipeline.context import PipelineInputData`
4. Extend __init_subclass__ method (L108-137) to validate INPUT_DATA type before return:
   - After strategies validation block (L133)
   - Add: if INPUT_DATA set and not issubclass(INPUT_DATA, PipelineInputData), raise TypeError with message including class name
5. Include generic type check: `if cls.INPUT_DATA is not None and not (isinstance(cls.INPUT_DATA, type) and issubclass(cls.INPUT_DATA, PipelineInputData)): raise TypeError(...)`

### Step 3: Add input_data Param and Validation in execute()
**Agent:** backend:integration-specialist
**Skills:** none
**Context7 Docs:** /pydantic/pydantic
**Group:** B

1. Edit llm_pipeline/pipeline.py execute() method (L424-430)
2. Add input_data param after initial_context: `input_data: Optional[Dict[str, Any]] = None`
3. Insert validation logic after consensus config parsing (L463) and before `self._context = initial_context.copy()` (L464):
   - Get cls = type(self) or use self.__class__
   - If cls.INPUT_DATA is not None and (input_data is None or not input_data): raise ValueError("Pipeline {cls.pipeline_name} requires input_data but none provided")
   - If input_data and cls.INPUT_DATA is not None: validated = cls.INPUT_DATA.model_validate(input_data), wrap in try/except ValidationError, re-raise with pipeline name context
   - Store validated data: self._validated_input = validated if INPUT_DATA else input_data (for potential future use)
4. Validation happens BEFORE PipelineRun record creation (L471-478)

### Step 4: Update Introspection Metadata
**Agent:** backend:integration-specialist
**Skills:** none
**Context7 Docs:** /pydantic/pydantic
**Group:** B

1. Edit llm_pipeline/introspection.py get_metadata() method (L194-250)
2. Add pipeline_input_schema computation after execution_order derivation (before cache assignment, around L245)
3. Use _get_schema() static method (L82-95) which already handles BaseModel.model_json_schema()
4. Add: `pipeline_input_schema = self._get_schema(getattr(self._pipeline_cls, "INPUT_DATA", None))`
5. Include pipeline_input_schema in returned metadata dict and cache assignment

### Step 5: Update UI Pipelines Route has_input_schema Logic
**Agent:** backend:api-developer
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Edit llm_pipeline/ui/routes/pipelines.py list_pipelines() (L98-102)
2. Replace step instruction schema check with pipeline-level INPUT_DATA check
3. Change from: `any(step.get("instructions_schema") for strategy in strategies for step in strategy.get("steps", []))`
4. To: `metadata.get("pipeline_input_schema") is not None`
5. This aligns has_input_schema with actual pipeline input capability

### Step 6: Update UI Runs Route execute() Call
**Agent:** backend:integration-specialist
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Edit llm_pipeline/ui/routes/runs.py trigger_run() background run_pipeline function (L223-224)
2. Change L224 from: `pipeline.execute(data=None, initial_context=body.input_data or {})`
3. To: `pipeline.execute(data=None, input_data=body.input_data)`
4. Remove input_data from initial_context - clean separation of concerns
5. Note: factory() call (L223) already passes input_data constructor param - keep that unchanged (different concern)

### Step 7: Export PipelineInputData in Package Init
**Agent:** backend:api-developer
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Edit llm_pipeline/__init__.py
2. Update context import (L22): `from llm_pipeline.context import PipelineContext, PipelineInputData`
3. Add "PipelineInputData" to __all__ list (L50, after "PipelineContext")
4. Maintains alphabetical grouping within Data handling section

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Breaking change for existing pipelines calling execute() | Low | input_data param is Optional - existing calls work unchanged |
| runs.py L224 passes both input_data and initial_context - potential confusion | Medium | Step 6 removes input_data from initial_context to enforce separation |
| Type guard in __init_subclass__ may break dynamic class generation | Low | Standard issubclass check - only fails if INPUT_DATA is wrong type |
| Introspection cache invalidation if INPUT_DATA changes at runtime | Low | ClassVars not meant to change post-import - cache keyed by class id |
| UI still using step instruction schemas elsewhere | Medium | pipelines.py has_input_schema updated, but other UI code may need review in future tasks |

## Success Criteria

- [ ] PipelineInputData base class exists in context.py and exports correctly
- [ ] INPUT_DATA ClassVar declared on PipelineConfig with Optional[Type[PipelineInputData]] type
- [ ] __init_subclass__ raises TypeError if INPUT_DATA set but not PipelineInputData subclass
- [ ] execute() accepts input_data param and validates against INPUT_DATA schema if set
- [ ] execute() raises ValueError if INPUT_DATA declared but input_data not provided
- [ ] PipelineIntrospector.get_metadata() includes pipeline_input_schema key with JSON schema or None
- [ ] pipelines.py has_input_schema checks metadata.pipeline_input_schema instead of step instruction schemas
- [ ] runs.py trigger_run() passes input_data= to execute(), not in initial_context
- [ ] __init__.py exports PipelineInputData in __all__

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Additive feature with backward compatibility. New param is optional. Type guard fails at import not runtime. UI changes are scoped to specific routes. No database schema changes. No external dependencies.
**Suggested Exclusions:** testing, review
