# Research Summary

## Executive Summary

Validated 3 research files covering codebase architecture, pipeline patterns, and LLM code generation for Task 45 (Meta-Pipeline for Step Generation). Research is thorough and largely accurate. Found 3 factual errors and 5 cross-file inconsistencies, all now resolved. 3 architectural decisions resolved via CEO input. Core framework patterns (naming conventions, step_definition decorator, context chaining, agent builder) are well-understood and correctly documented across all files. Validation complete -- ready for planning.

## Domain Findings

### Codebase Architecture Accuracy
**Source:** step-1-codebase-architecture.md

Research accurately maps the full package structure, class hierarchy, and `__init_subclass__` configuration pattern. Verified against actual source code:
- `PipelineConfig.__init_subclass__` enforces `Pipeline` suffix and `{Prefix}Registry/Strategies/AgentRegistry` naming -- confirmed at pipeline.py L148-179
- `PipelineDatabaseRegistry.__init_subclass__` accepts `models=[]` (not-None check) -- confirmed at registry.py L50
- `_validate_foreign_key_dependencies` and `_validate_registry_order` both guard with `if not self.REGISTRY` then iterate `REGISTRY.MODELS` -- empty list = no-op, confirmed at pipeline.py L356-392
- `get_models()` raises on empty list but only called from `PipelineExtraction.__init__()` -- confirmed at extraction.py L104
- Demo uses `DefaultStrategy` (not prefixed) -- confirmed at demo/pipeline.py L246, strategy naming does NOT follow pipeline prefix pattern

### Registry Design (RESOLVED)
**Source:** step-1-codebase-architecture.md (section 6.3), step-2-pipeline-patterns.md (sections 4, 9)

Step 1 proposed `models=[]` (no DB extractions). Step 2 section 4 incorrectly stated "models= must be non-empty list" but then proposed `models=[GenerationRecord]` with extraction. Step 2's claim about the constraint is wrong (only applies when `get_models()` called from `PipelineExtraction.__init__()`), but its design choice for DB persistence is correct.

**CEO Decision:** Use `GenerationRecord` SQLModel + `GenerationRecordExtraction`. DB persistence provides queryable generation history for Task 47 (StepIntegrator). Step 2's design (section 9) is the canonical reference. Step 1's `models=[]` approach is superseded.

### ValidationContext Name Collision
**Source:** step-2-pipeline-patterns.md (section 9, NOTE)

Confirmed: `ValidationContext` exists in `llm_pipeline/types.py` as a dataclass (L27-49). Step 2 correctly identifies the collision and renames Step 4 to `CodeValidationStep/CodeValidationInstructions/CodeValidationContext`. However, step 3 section 9 still uses old naming (`ValidationStep`, `"validation"` agent key). The rename is the correct choice.

### Code Generation Approach (RESOLVED)
**Source:** step-2-pipeline-patterns.md (section 10), step-3-llm-code-generation.md (sections 5, 8)

Two competing designs for CodeGenerationInstructions:
- Step 2: LLM produces granular method bodies (`prepare_calls_body`, `process_instructions_body`), Jinja2 templates assemble full files
- Step 3: LLM produces complete Python source strings per artifact (`instructions_code`, `step_code`, `context_code`)

**CEO Decision:** Granular method bodies (step 2 approach). LLM outputs focused method-level snippets, Jinja2 templates handle boilerplate (imports, decorators, class declarations, naming). More reliable -- smaller LLM output scope, templates enforce framework conventions. Step 2's `CodeGenerationInstructions` schema (section 10, Step 2) is the canonical reference. Step 3's monolithic schema is superseded.

### Package Structure (RESOLVED)
**Source:** step-1 (section 6.1), step-2 (section 9), step-3 (section 9)

Three different proposals:
- Step 1: Single `pipeline.py` (following demo pattern) + `prompts.py` + `templates/`
- Step 2: Multi-file split (`pipeline.py`, `steps.py`, `schemas.py`, `models.py`, `prompts.py`, `templates/`)
- Step 3: `meta_pipeline.py` as main file

**CEO Decision:** Multi-file split. Creator has ~17+ classes vs demo's 11 in ~290 lines. Canonical structure:
```
llm_pipeline/creator/
    __init__.py          # re-exports StepCreatorPipeline
    pipeline.py          # StepCreatorPipeline, registry, strategies, agent registry, input data
    steps.py             # 4 step classes with @step_definition
    schemas.py           # Instructions + Context classes (LLMResultMixin / PipelineContext)
    models.py            # GenerationRecord SQLModel + intermediate Pydantic models (FieldDefinition etc.)
    prompts.py           # Prompt seed definitions for 4 meta-steps
    validators.py        # python_syntax_validator, naming_convention_validator factories
    templates/
        __init__.py      # Jinja2 Environment setup, render helpers, custom filters
        step.py.j2       # Step class template
        instructions.py.j2  # Instructions class template
        extraction.py.j2    # Extraction class template
        prompts.yaml.j2     # Prompt definitions template
```
Step 2's layout is the canonical reference, with `validators.py` added (from step 3's output validator patterns).

### Upstream Task 18 Context
**Source:** Graphiti memory, task 18 summary

Task 18 (Export Event System) completed with no deviations. All event types, emitters, and handlers properly exported. The creator package can import from `llm_pipeline.events` if event emission is desired. No blockers.

### Downstream Scope Boundaries
**Source:** Task Master tasks 46, 47

- Task 46 (Docker Sandbox): Depends on 45. Creates `StepSandbox` for testing generated code in isolated containers. OUT OF SCOPE.
- Task 47 (Auto-Integration): Depends on 45+46. Creates `StepIntegrator` that writes files to disk and updates strategy/registry/prompts. OUT OF SCOPE.
- Task 45 artifacts stay IN MEMORY in `pipeline.context`. No file writing, no sandbox execution.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Registry: DB persistence with GenerationRecord or empty models=[]? | DB persistence -- use GenerationRecord + extraction class | Step 2's design (section 9) is canonical. Enables Task 47 to query generation history. Step 1's models=[] superseded. |
| Code gen granularity: LLM outputs method bodies (granular) or complete source strings (monolithic)? | Granular -- LLM outputs method bodies, Jinja2 assembles files | Step 2's CodeGenerationInstructions schema is canonical (prepare_calls_body, process_instructions_body, extraction_method_body). Step 3's monolithic schema superseded. Templates enforce framework conventions. |
| Package file structure: single pipeline.py or multi-file split? | Multi-file split -- pipeline.py, steps.py, schemas.py, models.py, prompts.py, validators.py | Step 2's layout is canonical with validators.py added. ~17+ classes too large for single file. Each file has clear responsibility boundary. |

## Assumptions Validated

- [x] `__init_subclass__` declarative configuration is the core pattern -- all classes must use it
- [x] `models=[]` is framework-safe when no PipelineExtraction classes are used (verified, but superseded by CEO decision for models=[GenerationRecord])
- [x] Naming conventions enforced at class definition time: Pipeline, Registry, Strategies, AgentRegistry suffixes with prefix matching
- [x] Strategy classes only need `Strategy` suffix, do NOT need pipeline prefix
- [x] `step_definition` decorator enforces `{Prefix}Instructions`, `{Prefix}Context`, `{Prefix}Transformation` naming
- [x] `LLMResultMixin` base for all instruction schemas, with `example: ClassVar[dict]` for self-validation
- [x] `prepare_calls() -> List[StepCallParams]` is the only required abstract method on LLMStep
- [x] Context chaining via `process_instructions()` returning PipelineContext subclass, merged via `model_dump()`
- [x] `ValidationContext` collision in `llm_pipeline/types.py` is real -- rename to CodeValidation* is correct
- [x] Jinja2 template rendering in `process_instructions()` is appropriate (not PipelineTransformation)
- [x] Jinja2 as optional dependency `creator = ["jinja2>=3.0"]` is correct
- [x] Single always-true strategy (`DefaultCreatorStrategy`) is correct for initial implementation
- [x] Generated artifacts stay in-memory (pipeline.context) -- file writing is Task 47
- [x] Task 18 (upstream) completed with no deviations affecting Task 45
- [x] Prompt seeding follows demo pattern: Python dicts + `seed_prompts()` classmethod
- [x] DB persistence via GenerationRecord + GenerationRecordExtraction (CEO decision)
- [x] Granular code gen: LLM outputs method bodies, Jinja2 templates assemble files (CEO decision)
- [x] Multi-file package split: pipeline.py, steps.py, schemas.py, models.py, prompts.py, validators.py (CEO decision)
- [x] Step 2 research (pipeline-patterns.md) is the primary canonical reference for architecture

## Open Items

- Custom Jinja2 filters needed (`snake_case`, `camel_case`, `indent_code`) -- implementation detail for planning phase
- Exact `GenerationRecord` SQLModel fields (run_id, step_name_generated, files_generated, is_valid, created_at) -- finalize during planning
- Prompt content authoring for 4 meta-steps (system + user = 8 prompts) -- significant planning work
- Whether `example: ClassVar[dict]` for each Instructions class should include realistic multi-field examples or minimal ones -- planning decision

## Recommendations for Planning

1. Use `CodeValidationStep` / `CodeValidationInstructions` / `CodeValidationContext` naming -- collision with `llm_pipeline.types.ValidationContext` confirmed
2. Use `DefaultCreatorStrategy` name -- collision with demo's `DefaultStrategy` confirmed
3. Agent registry key for step 4 must be `"code_validation"` (not `"validation"`)
4. Carry forward step 2's detailed data flow design (sections 10, steps 1-4) as the primary architecture reference -- most complete and internally consistent
5. Add Jinja2 import guard in creator `__init__.py` (`try: import jinja2 except ImportError: raise ImportError("Install with pip install llm-pipeline[creator]")`)
6. Include `__all__` exports in every creator module (pattern from step 1 section 7)
7. Register entry point: `step_creator = "llm_pipeline.creator:StepCreatorPipeline"` in pyproject.toml
8. Output validators (`python_syntax_validator`, `naming_convention_validator`) go in `creator/validators.py` following existing `validators.py` factory pattern
9. Step 3 research code snippets (section 9 wiring) should NOT be used as-is -- they use old naming. Step 2 section 9 is canonical.
10. Step 2 section 4 claim "models= must be non-empty" is factually wrong -- do not propagate. The actual constraint is `get_models()` raises on empty, only called from `PipelineExtraction.__init__()`. Moot now since CEO chose non-empty models.
