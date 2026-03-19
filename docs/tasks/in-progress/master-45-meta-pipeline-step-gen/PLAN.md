# PLANNING

## Summary

Build `llm_pipeline/creator/` package: a meta-pipeline that takes natural language step descriptions and produces scaffold code (step class, instructions class, extraction class, prompts YAML) via a 4-step LLM pipeline. Output artifacts remain in-memory in pipeline.context; Task 47 handles file writing. Uses existing framework patterns (PipelineConfig subclass, step_definition decorator, LLMResultMixin, PipelineExtraction) with Jinja2 templates assembling code from LLM-generated method bodies.

## Plugin & Agents

**Plugin:** python-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. Foundation: models.py, schemas.py, validators.py - data models, intermediate types, output validators
2. Templates: creator/templates/ package with Jinja2 environment and 4 .j2 template files
3. Prompts: creator/prompts.py with 8 prompt seed dicts (system+user x 4 steps)
4. Pipeline: pipeline.py with registry, strategies, agent registry, input data, StepCreatorPipeline
5. Steps: steps.py with 4 @step_definition step classes and GenerationRecordExtraction
6. Package wiring: __init__.py, pyproject.toml additions (optional dep + entry point)

## Architecture Decisions

### Granular method bodies via Jinja2 templates
**Choice:** LLM outputs method-level code snippets (prepare_calls_body, process_instructions_body, extraction_method_body). Jinja2 templates assemble full Python source files.
**Rationale:** CEO decision. Smaller LLM output scope is more reliable. Templates enforce framework conventions (imports, decorators, class declarations, naming) without LLM needing to reproduce boilerplate. Confirmed by step-2-pipeline-patterns.md section 10.
**Alternatives:** Monolithic code generation (LLM outputs complete Python source strings per artifact) -- superseded by CEO decision.

### DB persistence via GenerationRecord
**Choice:** `StepCreatorRegistry(PipelineDatabaseRegistry, models=[GenerationRecord])` with `GenerationRecordExtraction` in CodeValidationStep.
**Rationale:** CEO decision. Provides queryable generation history for Task 47 (StepIntegrator). `PipelineDatabaseRegistry` requires `models=` parameter; empty list would raise at extraction time. Confirmed at registry.py L50-57 and extraction.py L104.
**Alternatives:** `models=[]` (no DB) -- superseded by CEO decision.

### Multi-file package split
**Choice:** 6 Python modules (pipeline.py, steps.py, schemas.py, models.py, prompts.py, validators.py) + templates/ sub-package.
**Rationale:** CEO decision. ~17+ classes too large for single file (vs demo's 11 classes in ~290 lines). Each module has clear responsibility boundary.
**Alternatives:** Single pipeline.py following demo pattern -- superseded.

### CodeValidationStep naming (avoid ValidationContext collision)
**Choice:** `CodeValidationStep` / `CodeValidationInstructions` / `CodeValidationContext`.
**Rationale:** `ValidationContext` already exists at `llm_pipeline/types.py` L27-49 as a dataclass. Explicit rename avoids import ambiguity in consuming code.
**Alternatives:** Keep `ValidationStep` with namespace isolation -- rejected for clarity.

### DefaultCreatorStrategy (not pipeline-prefix-named)
**Choice:** `DefaultCreatorStrategy` (not `StepCreatorDefaultStrategy`).
**Rationale:** Demo confirms strategy naming does NOT follow pipeline prefix pattern -- `DefaultStrategy` at demo/pipeline.py L246 has no `TextAnalyzer` prefix. Framework enforces only `Strategy` suffix.
**Alternatives:** none.

### Jinja2 rendering in process_instructions() not PipelineTransformation
**Choice:** Template rendering inside `CodeGenerationStep.process_instructions()` and `PromptGenerationStep.process_instructions()`.
**Rationale:** PipelineTransformation is for data structure changes (DataFrame ops). Template rendering is pure computation deriving context values from LLM output -- canonical use of `process_instructions()`.
**Alternatives:** PipelineTransformation subclass -- rejected, wrong abstraction.

### Jinja2 as optional dependency
**Choice:** `creator = ["jinja2>=3.0"]` in `[project.optional-dependencies]` in pyproject.toml.
**Rationale:** Not all users need code generation. Core package stays lean. ImportError guard in `creator/__init__.py` provides clear error message.
**Alternatives:** Add jinja2 to core dependencies -- rejected (keeps core lean).

## Implementation Steps

### Step 1: Create models.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo, /pydantic/pydantic-ai
**Group:** A

1. Create `llm_pipeline/creator/models.py`
2. Define `FieldDefinition(BaseModel)` with fields: `name: str`, `type_annotation: str`, `description: str`, `default: str | None = None`, `is_required: bool = True`
3. Define `ExtractionTarget(BaseModel)` with fields: `model_name: str`, `fields: list[FieldDefinition]`, `source_field_mapping: dict[str, str]`
4. Define `GenerationRecord(SQLModel, table=True)` with `__tablename__ = "creator_generation_records"`, fields: `id: Optional[int] = Field(default=None, primary_key=True)`, `run_id: str`, `step_name_generated: str`, `files_generated: list[str] = Field(default_factory=list, sa_column=Column(JSON))`, `is_valid: bool = False`, `created_at: datetime`
5. Add `__all__` with all exported names

### Step 2: Create schemas.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** B

1. Create `llm_pipeline/creator/schemas.py`
2. Import `LLMResultMixin` from `llm_pipeline.step`, `PipelineContext` from `llm_pipeline.context`, `FieldDefinition` and `ExtractionTarget` from `.models`
3. Define `RequirementsAnalysisInstructions(LLMResultMixin)` with fields: `step_name: str`, `step_class_name: str`, `description: str`, `instruction_fields: list[FieldDefinition]`, `context_fields: list[FieldDefinition]`, `extraction_targets: list[ExtractionTarget]`, `input_variables: list[str]`, `output_context_keys: list[str]`; include `example: ClassVar[dict]` with realistic values
4. Define `CodeGenerationInstructions(LLMResultMixin)` with fields: `imports: list[str]`, `prepare_calls_body: str`, `process_instructions_body: str`, `extraction_method_body: str | None`, `should_skip_condition: str | None`; include `example: ClassVar[dict]`
5. Define `PromptGenerationInstructions(LLMResultMixin)` with fields: `system_prompt_content: str`, `user_prompt_template: str`, `required_variables: list[str]`, `prompt_category: str`; include `example: ClassVar[dict]`
6. Define `CodeValidationInstructions(LLMResultMixin)` with fields: `is_valid: bool`, `issues: list[str]`, `suggestions: list[str]`, `naming_valid: bool`, `imports_valid: bool`, `type_annotations_valid: bool`; include `example: ClassVar[dict]`
7. Define `RequirementsAnalysisContext(PipelineContext)` with fields: `step_name: str`, `step_class_name: str`, `instruction_fields: list[dict]`, `context_fields: list[dict]`, `extraction_targets: list[dict]`, `input_variables: list[str]`, `output_context_keys: list[str]`
8. Define `CodeGenerationContext(PipelineContext)` with fields: `step_code: str`, `instructions_code: str`, `extraction_code: str | None`
9. Define `PromptGenerationContext(PipelineContext)` with fields: `system_prompt: str`, `user_prompt_template: str`, `required_variables: list[str]`, `prompt_yaml: str`
10. Define `CodeValidationContext(PipelineContext)` with fields: `is_valid: bool`, `syntax_valid: bool`, `llm_review_valid: bool`, `issues: list[str]`, `all_artifacts: dict[str, str]`
11. Add `__all__` with all exported names

### Step 3: Create validators.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create `llm_pipeline/creator/validators.py`
2. Import `ast`, `re`, `Any` from typing, `ModelRetry` and `RunContext` from `pydantic_ai`, `StepDeps` from `llm_pipeline.agent_builders`
3. Implement `python_syntax_validator()` factory function: returns async validator that calls `ast.parse()` on string fields in the output object (prepare_calls_body, process_instructions_body, extraction_method_body); raises `ModelRetry` on `SyntaxError` with descriptive message
4. Implement `naming_convention_validator()` factory function: returns async validator that checks `step_class_name` ends with "Step", checks that `{prefix}Instructions` and `{prefix}Context` naming convention would be satisfied; raises `ModelRetry` on violation
5. Follow exact factory pattern from `llm_pipeline/validators.py` (async inner function, set `__name__` and `__qualname__`, return the inner function)
6. Add `__all__` = `["python_syntax_validator", "naming_convention_validator"]`

### Step 4: Create templates/__init__.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pallets/jinja
**Group:** C

1. Create `llm_pipeline/creator/templates/__init__.py`
2. Add ImportError guard: `try: from jinja2 import Environment, PackageLoader, pass_eval_context except ImportError: raise ImportError("llm-pipeline[creator] required: pip install llm-pipeline[creator]")`
3. Implement `get_template_env() -> Environment` function: create Environment with `PackageLoader("llm_pipeline.creator", "templates")`, `trim_blocks=True`, `lstrip_blocks=True`, `keep_trailing_newline=True`
4. Register custom filters on the environment: `snake_case` (delegates to `llm_pipeline.naming.to_snake_case`), `camel_case` (snake to CamelCase conversion using `str.title().replace("_", "")`), `indent_code` (adds N spaces of indentation to each line of a code block)
5. Implement `render_template(template_name: str, **context) -> str` helper that calls `get_template_env().get_template(template_name).render(**context)`
6. Add `__all__` = `["get_template_env", "render_template"]`

### Step 5: Create step.py.j2 template
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pallets/jinja
**Group:** D

1. Create `llm_pipeline/creator/templates/step.py.j2`
2. Template renders a complete Python step module with: file docstring, imports block (standard `from llm_pipeline.step import LLMStep, step_definition` + any `imports` from LLM output), `@step_definition(instructions=..., default_system_key=..., default_user_key=..., context=..., default_extractions=[...])` decorator, `class {step_class_name}(LLMStep):` with docstring, `def prepare_calls(self):` with indented `prepare_calls_body`, `def process_instructions(self, instructions):` with indented `process_instructions_body`
3. Use Jinja2 `indent_code` filter for indenting multi-line method bodies to 8 spaces
4. Use conditional block for `should_skip_condition` to optionally include `def should_skip(self):`
5. Include `{% for import_line in imports %}{{ import_line }}{% endfor %}` section for additional imports

### Step 6: Create instructions.py.j2 template
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pallets/jinja
**Group:** D

1. Create `llm_pipeline/creator/templates/instructions.py.j2`
2. Template renders a complete Python instructions module with: file docstring, `from typing import ClassVar`, `from llm_pipeline.step import LLMResultMixin`, field-type imports derived from `fields` parameter, `class {class_name}(LLMResultMixin):` with docstring
3. For each field in `fields` list: render `{field.name}: {field.type_annotation} = {field.default or '""'}` or `{field.name}: {field.type_annotation}` if required
4. Render `example: ClassVar[dict] = {...}` using the `example_dict` variable passed to template
5. Use Jinja2 conditionals for optional fields (those with `is_required=False`)

### Step 7: Create extraction.py.j2 template
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pallets/jinja
**Group:** D

1. Create `llm_pipeline/creator/templates/extraction.py.j2`
2. Template renders a complete Python extraction module with: file docstring, `from llm_pipeline.extraction import PipelineExtraction`, `from .models import {model_name}` (adjustable), `class {class_name}(PipelineExtraction, model={model_name}):` with docstring
3. Render `def default(self, results: list[{instructions_class_name}]) -> list[{model_name}]:` with indented `extraction_method_body` using `indent_code` filter
4. Include conditional block: if `extraction_method_body` is None, render minimal pass-through extraction returning empty list

### Step 8: Create prompts.yaml.j2 template
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pallets/jinja
**Group:** D

1. Create `llm_pipeline/creator/templates/prompts.yaml.j2`
2. Template renders YAML-like Python dict definitions (matching demo/prompts.py dict format, not actual YAML files -- the file name reflects content type not file format since output is Python dict source)
3. Render two Python dicts: `{STEP_NAME_UPPER}_SYSTEM` and `{STEP_NAME_UPPER}_USER` following exact schema from demo/prompts.py (prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables, description)
4. Render `ALL_PROMPTS = [...]` list at end
5. Variables passed: `step_name`, `step_class_name`, `system_content`, `user_content`, `required_variables` (list), `category`

### Step 9: Create prompts.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. Create `llm_pipeline/creator/prompts.py`
2. Follow exact pattern from `llm_pipeline/demo/prompts.py`
3. Define 8 prompt seed dicts: `REQUIREMENTS_ANALYSIS_SYSTEM`, `REQUIREMENTS_ANALYSIS_USER`, `CODE_GENERATION_SYSTEM`, `CODE_GENERATION_USER`, `PROMPT_GENERATION_SYSTEM`, `PROMPT_GENERATION_USER`, `CODE_VALIDATION_SYSTEM`, `CODE_VALIDATION_USER`
4. Each dict has keys: `prompt_key`, `prompt_name`, `prompt_type`, `category` ("step_creator"), `step_name`, `content`, `required_variables`, `description`
5. Prompt content for RequirementsAnalysis: system instructs LLM to parse NL descriptions into structured step specifications (field names, types, context variables, extraction targets); user template has `{description}` variable
6. Prompt content for CodeGeneration: system instructs LLM to generate Python method bodies for prepare_calls() and process_instructions() following llm-pipeline framework patterns; user template has `{step_name}`, `{step_class_name}`, `{instruction_fields}`, `{context_fields}`, `{input_variables}`, `{output_context_keys}` variables
7. Prompt content for PromptGeneration: system instructs LLM to write clear system prompts and user prompt templates with appropriate variable placeholders; user template has `{step_name}`, `{description}`, `{input_variables}` variables
8. Prompt content for CodeValidation: system instructs LLM to review generated Python code for correctness, naming convention compliance, and type annotation validity; user template has `{step_code}`, `{instructions_code}`, `{extraction_code}`, `{system_prompt}`, `{user_prompt_template}` variables
9. Define `ALL_PROMPTS: list[dict]` listing all 8 dicts
10. Implement `seed_prompts(cls, engine: Engine) -> None` following demo/prompts.py pattern: create GenerationRecord table via SQLModel.metadata.create_all(), open Session, for each prompt in ALL_PROMPTS check if exists by (prompt_key, prompt_type), insert if not, commit
11. Add `__all__` = `["ALL_PROMPTS", "seed_prompts"]`

### Step 10: Create pipeline.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo, /pydantic/pydantic-ai
**Group:** F

1. Create `llm_pipeline/creator/pipeline.py`
2. Import all required framework classes: `AgentRegistry`, `PipelineContext`, `PipelineInputData`, `PipelineConfig`, `PipelineDatabaseRegistry`, `PipelineStrategy`, `PipelineStrategies`
3. Import `GenerationRecord` from `.models`, `RequirementsAnalysisInstructions`, `CodeGenerationInstructions`, `PromptGenerationInstructions`, `CodeValidationInstructions` from `.schemas`
4. Define `StepCreatorInputData(PipelineInputData)` with fields: `description: str`, `target_pipeline: str | None = None`, `include_extraction: bool = True`, `include_transformation: bool = False`
5. Define `StepCreatorRegistry(PipelineDatabaseRegistry, models=[GenerationRecord])` as pass-through class with docstring
6. Define `StepCreatorAgentRegistry(AgentRegistry, agents={"requirements_analysis": RequirementsAnalysisInstructions, "code_generation": CodeGenerationInstructions, "prompt_generation": PromptGenerationInstructions, "code_validation": CodeValidationInstructions})` -- steps.py imports are deferred here; use TYPE_CHECKING guard or import inline
7. Define `DefaultCreatorStrategy(PipelineStrategy)` with `can_handle(self, context) -> bool: return True`; `get_steps()` returns list of 4 step definitions (import step classes inline to avoid circular imports)
8. Define `StepCreatorStrategies(PipelineStrategies, strategies=[DefaultCreatorStrategy])` as pass-through class
9. Define `StepCreatorPipeline(PipelineConfig, registry=StepCreatorRegistry, strategies=StepCreatorStrategies, agent_registry=StepCreatorAgentRegistry)` with `INPUT_DATA: ClassVar[type] = StepCreatorInputData` and `seed_prompts(cls, engine)` classmethod calling `from llm_pipeline.creator.prompts import seed_prompts as _seed; _seed(cls, engine)`
10. Add `__all__` with all public names

### Step 11: Create steps.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** G

1. Create `llm_pipeline/creator/steps.py`
2. Import `LLMStep`, `step_definition` from `llm_pipeline.step`, `PipelineExtraction` from `llm_pipeline.extraction`, `GenerationRecord` from `.models`, all Instructions classes and Context classes from `.schemas`, `render_template` from `.templates`
3. Define `GenerationRecordExtraction(PipelineExtraction, model=GenerationRecord)` with `default(self, results: list[CodeValidationInstructions]) -> list[GenerationRecord]` that creates one `GenerationRecord` per result with `run_id=self.pipeline.run_id`, `step_name_generated=self.pipeline.context["step_name"]`, `files_generated=list(self.pipeline.context.get("all_artifacts", {}).keys())`, `is_valid=results[0].is_valid`, `created_at=datetime.now(timezone.utc)`
4. Define `RequirementsAnalysisStep(LLMStep)` decorated with `@step_definition(instructions=RequirementsAnalysisInstructions, default_system_key="requirements_analysis", default_user_key="requirements_analysis", context=RequirementsAnalysisContext)`; implement `prepare_calls(self)` returning `[{"variables": {"description": self.pipeline.validated_input.description}}]`; implement `process_instructions(self, instructions)` returning `RequirementsAnalysisContext` populated from `instructions[0]` fields converted to dict via `model_dump()`
5. Define `CodeGenerationStep(LLMStep)` decorated with `@step_definition(instructions=CodeGenerationInstructions, default_system_key="code_generation", default_user_key="code_generation", context=CodeGenerationContext)`; implement `prepare_calls(self)` using Step 1 context fields to build variables dict; implement `process_instructions(self, instructions)` that calls `render_template("step.py.j2", ...)`, `render_template("instructions.py.j2", ...)`, and conditionally `render_template("extraction.py.j2", ...)` if `pipeline.validated_input.include_extraction`; return `CodeGenerationContext(step_code=..., instructions_code=..., extraction_code=...)`
6. Define `PromptGenerationStep(LLMStep)` decorated with `@step_definition(instructions=PromptGenerationInstructions, default_system_key="prompt_generation", default_user_key="prompt_generation", context=PromptGenerationContext)`; implement `prepare_calls(self)` using Step 1 + Step 2 context; implement `process_instructions(self, instructions)` that renders `prompts.yaml.j2` and returns `PromptGenerationContext`
7. Define `CodeValidationStep(LLMStep)` decorated with `@step_definition(instructions=CodeValidationInstructions, default_system_key="code_validation", default_user_key="code_validation", default_extractions=[GenerationRecordExtraction], context=CodeValidationContext)`; implement `prepare_calls(self)` passing all generated code artifacts from pipeline context; implement `process_instructions(self, instructions)` that runs `ast.parse()` programmatic check on each code string, combines with LLM `is_valid` result, builds `all_artifacts` dict mapping filename to code string, returns `CodeValidationContext`
8. Add `__all__` = `["RequirementsAnalysisStep", "CodeGenerationStep", "PromptGenerationStep", "CodeValidationStep", "GenerationRecordExtraction"]`

### Step 12: Create creator/__init__.py and update pyproject.toml
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** H

1. Create `llm_pipeline/creator/__init__.py`
2. Add ImportError guard at top: `try: import jinja2 except ImportError: raise ImportError("llm_pipeline.creator requires jinja2. Install with: pip install llm-pipeline[creator]")`
3. Import and re-export `StepCreatorPipeline` from `.pipeline` as primary public API
4. Add `__all__` = `["StepCreatorPipeline"]`
5. Edit `pyproject.toml`: add `creator = ["jinja2>=3.0"]` to `[project.optional-dependencies]`
6. Edit `pyproject.toml`: add `step_creator = "llm_pipeline.creator:StepCreatorPipeline"` to `[project.entry-points."llm_pipeline.pipelines"]`
7. Edit `llm_pipeline/__init__.py`: add `from llm_pipeline.creator import StepCreatorPipeline` under a try/except ImportError guard (optional import -- only available when jinja2 installed), add `"StepCreatorPipeline"` to `__all__` (conditionally or always)

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Circular imports: steps.py imports schemas.py; pipeline.py imports steps.py (for get_steps()) | High | Use inline imports inside get_steps() method body in pipeline.py; TYPE_CHECKING guards throughout |
| `step_definition` decorator validation fires at class definition time -- if naming mis-matches it raises ValueError | High | Use exact naming from research: {StepPrefix}Instructions, {StepPrefix}Context -- double-check all 4 steps before writing |
| `GenerationRecord` JSON column (files_generated) requires SQLAlchemy Column(JSON) import -- not a standard SQLModel field | Medium | Follow SQLModel JSON field pattern: `Field(sa_column=Column(JSON))` with `from sqlalchemy import Column, JSON` |
| `PackageLoader("llm_pipeline.creator", "templates")` requires package to be installed or on PYTHONPATH -- fails in editable install if templates/ not included | Medium | Ensure `llm_pipeline/creator/templates/__init__.py` exists so templates/ is a Python package; Jinja2 PackageLoader uses importlib.resources |
| Template render context variable mismatches: Jinja2 silently ignores undefined vars by default | Medium | Configure Jinja2 Environment with `undefined=StrictUndefined` so missing template variables raise at render time |
| DefaultCreatorStrategy.get_steps() references step classes that must be imported -- creates import cycle with pipeline.py | Medium | Import step classes inline inside get_steps() method: `from llm_pipeline.creator.steps import ...` |
| CodeValidationStep.process_instructions() running ast.parse() on method bodies that are intentionally incomplete (e.g., using pipeline.context vars) may produce SyntaxError | Low | Only parse method bodies wrapped in a minimal function stub (`def f():\n{body}`) to provide valid syntax context |
| Prompt content quality: meta-step prompts must instruct LLM clearly enough to produce valid Python method bodies | Medium | Include concrete examples in system prompts; reference llm-pipeline framework patterns explicitly (self.pipeline.context, self.pipeline.validated_input) |

## Success Criteria

- [ ] `llm_pipeline/creator/` package exists with all 8 files: `__init__.py`, `pipeline.py`, `steps.py`, `schemas.py`, `models.py`, `prompts.py`, `validators.py`, `templates/__init__.py`
- [ ] 4 Jinja2 template files exist: `creator/templates/step.py.j2`, `instructions.py.j2`, `extraction.py.j2`, `prompts.yaml.j2`
- [ ] `from llm_pipeline.creator import StepCreatorPipeline` works (with jinja2 installed)
- [ ] `StepCreatorPipeline.__init_subclass__` validation passes: correct Registry/Strategies/AgentRegistry naming enforced by framework
- [ ] All 4 `@step_definition` decorators succeed at class definition (naming convention validated)
- [ ] `GenerationRecord` table creatable via `SQLModel.metadata.create_all(engine)`
- [ ] `GenerationRecordExtraction` correctly linked to `CodeValidationStep` via `default_extractions`
- [ ] `StepCreatorPipeline.seed_prompts(engine)` seeds 8 prompts to DB idempotently
- [ ] `pyproject.toml` has `creator = ["jinja2>=3.0"]` in optional-dependencies
- [ ] `pyproject.toml` has `step_creator = "llm_pipeline.creator:StepCreatorPipeline"` entry point
- [ ] `pytest` passes with no new failures

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Framework naming convention enforcement is strict (raises at import time if mismatched); circular import risk is real with 6 modules cross-importing; Jinja2 PackageLoader has installation requirements that could silently fail. These risks are manageable with careful naming and inline imports, but require diligence. No external service dependencies.
**Suggested Exclusions:** review
