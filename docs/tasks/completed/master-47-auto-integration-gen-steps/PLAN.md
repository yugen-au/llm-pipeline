# PLANNING

## Summary

Implement `StepIntegrator` (task 47) -- a one-shot file+DB writer that accepts a `GeneratedStep` Pydantic adapter model, writes generated Python files to a target directory, registers prompts in the DB, and AST-splices three locations in the target pipeline file (`get_steps()` list, `models=[...]` class keyword, `agents={...}` class keyword). On any failure the integrator rolls back the DB transaction and restores backed-up files. A `GeneratedStep` Pydantic model is added to `creator/models.py` as the typed boundary type; the raw AST locate+string-splice logic lives in a new `creator/ast_modifier.py` module.

## Plugin & Agents

**Plugin:** python-development
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **GeneratedStep model**: Add typed Pydantic adapter to `creator/models.py` with `from_draft()` factory -- no runtime dependencies on other new files.
2. **AST modifier**: Implement `creator/ast_modifier.py` -- locate+splice utilities for all three AST targets in a single file read/write cycle.
3. **StepIntegrator**: Implement `creator/integrator.py` -- orchestrates file writes, prompt DB registration, AST modifications, DraftStep status update, commit, and rollback.
4. **Tests**: Unit + integration tests covering all three modules.

## Architecture Decisions

### GeneratedStep as Typed Pydantic Adapter
**Choice:** New `GeneratedStep` Pydantic (not SQLModel) class in `creator/models.py` with explicit typed fields extracted from `DraftStep.generated_code` dict. Includes `@classmethod from_draft(cls, draft: DraftStep) -> GeneratedStep` factory.
**Rationale:** `DraftStep.generated_code` is an untyped JSON dict. `StepIntegrator.integrate()` must access `step_code`, `prompts_code`, `instructions_code`, `extraction_code`, etc. as typed attributes. Task 48 accept endpoint converts at API boundary. Validated by VALIDATED_RESEARCH Q2.
**Alternatives:** Accept DraftStep directly and do dict access inside integrator (rejected: untyped, fragile, leaks DB model into integration layer).

### Hybrid AST-locate + String-splice for Three Targets
**Choice:** `ast_modifier.py` uses `ast.parse()` to locate the precise source positions of three modification points (`get_steps()` return list, `models=[...]` keyword, `agents={...}` keyword), then does string-level splice preserving comments and formatting. All three modifications share a single file read/parse/splice/write cycle.
**Rationale:** Pure AST rewriting with `ast.unparse()` strips comments. Pure regex is brittle on multiline dicts/lists. Hybrid preserves source while allowing precise location. Co-location of all three targets in one pipeline file (confirmed in both `demo/pipeline.py` and `creator/pipeline.py`) means one file cycle. Validated by VALIDATED_RESEARCH step-2 and assumptions.
**Alternatives:** `ast.unparse()` round-trip (rejected: strips all comments/formatting), `libcst` (rejected: adds heavy dependency, not in project stack), pure regex (rejected: brittle on varied formatting).

### Inline Import Detection for get_steps()
**Choice:** When injecting the step import, walk `get_steps()` FunctionDef.body for `ImportFrom` nodes. If found (inline import pattern as in `creator/pipeline.py`), insert the new step class name into that `ImportFrom` node's names by splicing the source line. If not found (top-level import pattern as in `demo/pipeline.py`), append a new `from <target_module> import <StepClass>` at the top-level import block.
**Rationale:** Both patterns confirmed in codebase. Inline pattern in `creator/pipeline.py` uses `from llm_pipeline.creator.steps import (...)` inside method body. Detection via AST walk prevents duplicate/wrong-level imports.
**Alternatives:** Always add top-level import (rejected: causes circular import errors in creator-style pipelines).

### Prompt Registration via AST Security Scan + Controlled exec()
**Choice:** (1) `CodeSecurityValidator().validate(prompts_code)` AST scan; (2) if clean, `exec(prompts_code, {"__builtins__": {}})` to extract `namespace["ALL_PROMPTS"]`; (3) fallback to direct field reconstruction from `GeneratedStep` if exec fails. Use idempotent check-then-insert pattern matching `creator/prompts.py:seed_prompts()`.
**Rationale:** `prompts.yaml.j2` renders a Python module with only dict literals, list literals, and `from __future__ import annotations` -- no side effects. AST scan confirms no blocked patterns. Controlled exec in empty builtins namespace is safe for this controlled template output. `StepSandbox.run()` confirmed to NOT extract runtime values -- it only does import checking. Validated by VALIDATED_RESEARCH Q3.
**Alternatives:** Parse prompts.py with pure AST value extraction (rejected: complex, brittle for nested dict literals), always fallback (rejected: loses category field which is only in rendered file).

### Integrator Owns session.commit()
**Choice:** `StepIntegrator.integrate()` accepts a writable `Session` from caller, commits internally inside try/except, rolls back and cleans up files on failure, re-raises exception.
**Rationale:** Gives integrator full atomicity control over file writes + DB changes as a unit. DraftStep status update (`status="accepted"`) happens inside same transaction before commit. Task 48 accept endpoint creates session, passes to integrator, does NOT commit. Validated by VALIDATED_RESEARCH Q4.
**Alternatives:** Endpoint owns commit (rejected: split commit responsibility, no atomicity for file+DB), context manager pattern (acceptable but adds complexity for one-shot use).

### target_dir Creation in Integrator
**Choice:** `integrator.py` calls `target_dir.mkdir(parents=True, exist_ok=True)`. If `__init__.py` does not exist, writes an empty one. Tracks whether directory was newly created; if integration fails and dir was newly created, deletes it entirely during rollback.
**Rationale:** Simplifies task 48 accept endpoint -- caller specifies path, integrator ensures it exists. Validated by VALIDATED_RESEARCH Q5.
**Alternatives:** Pre-require existing directory (rejected: burdens callers unnecessarily).

### Single-line List/Dict Expansion
**Choice:** When AST locator finds `models=[ExistingModel]` or `agents={"key": Val}` on a single line, expand to multiline format before inserting new element. Normalizes format for future insertions and avoids complex same-line splice logic.
**Rationale:** Simpler implementation; post-insertion file is more readable. Open item from VALIDATED_RESEARCH.
**Alternatives:** Inline same-line insert (rejected: edge cases with trailing comma/paren on same line).

## Implementation Steps

### Step 1: GeneratedStep Model
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Read `llm_pipeline/creator/models.py` (currently has `FieldDefinition`, `ExtractionTarget`, `GenerationRecord`).
2. Add `GeneratedStep(BaseModel)` class with fields: `step_name: str`, `step_class_name: str`, `instructions_class_name: str`, `step_code: str`, `instructions_code: str`, `prompts_code: str`, `extraction_code: str | None = None`, `all_artifacts: dict[str, str]`.
3. Add `@classmethod from_draft(cls, draft: "DraftStep") -> "GeneratedStep"` that: derives `step_class_name` as `to_pascal_case(step_name) + "Step"`, derives `instructions_class_name` as `to_pascal_case(step_name) + "Instructions"`, extracts file contents from `draft.generated_code` using keys `f"{step_name}_step.py"` etc., builds `all_artifacts` from the full dict.
4. Add `GeneratedStep` to `__all__`.
5. Add `IntegrationResult(BaseModel)` class with fields: `files_written: list[str]`, `prompts_registered: int`, `pipeline_file_updated: bool`, `target_dir: str`. Add to `__all__`.

### Step 2: AST Modifier Module
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create `llm_pipeline/creator/ast_modifier.py` with module docstring explaining hybrid locate+splice approach.
2. Implement `_find_function_def(tree: ast.AST, name: str) -> ast.FunctionDef | None` -- walks module-level and class-level function defs.
3. Implement `_find_class_keyword_node(tree: ast.AST, class_name_pattern: str, keyword_name: str) -> tuple[ast.expr | None, int | None]` -- finds the keyword value node and its end lineno in a class definition matching the pattern (substring match on class name for flexibility).
4. Implement `_splice_into_list(source_lines: list[str], list_node: ast.List, new_element: str) -> list[str]` -- handles both multiline (appends before closing `]`) and single-line (expands to multiline first then appends) cases. Preserves indentation.
5. Implement `_splice_into_dict(source_lines: list[str], dict_node: ast.Dict, new_key: str, new_value: str) -> list[str]` -- same single/multiline detection and expansion logic for dict.
6. Implement `_detect_and_add_import(source_lines: list[str], tree: ast.AST, step_class: str, module_path: str, get_steps_func: ast.FunctionDef | None) -> list[str]` -- if `get_steps_func` body contains `ImportFrom` matching `module_path`, splice `step_class` into that import's names list; otherwise add top-level `from {module_path} import {step_class}` after last existing import.
7. Implement `_detect_and_add_registry_import(source_lines: list[str], tree: ast.AST, class_name: str, module_path: str) -> list[str]` -- always adds top-level import (no inline pattern for registry/agent_registry classes). Checks for existing import first to avoid duplicates.
8. Implement public `modify_pipeline_file(pipeline_file: Path, step_class: str, step_module: str, instructions_class: str, instructions_module: str, extraction_model: str | None, extraction_module: str | None, step_name: str) -> None` -- orchestrates the full read/parse/splice/write cycle: (a) read and backup file to `{filename}.py.bak`, (b) parse with `ast.parse()`, (c) locate all three targets, (d) apply import injections, (e) splice `get_steps()` list, (f) splice `models=[...]` (only if extraction_model provided), (g) splice `agents={...}`, (h) write modified source back, (i) return. Raises `ASTModificationError` on failure (custom exception class also defined in this module).
9. Add `__all__` with `["modify_pipeline_file", "ASTModificationError"]`.

### Step 3: StepIntegrator
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Create `llm_pipeline/creator/integrator.py` with module docstring.
2. Define `StepIntegrator` class with `__init__(self, session: Session, pipeline_file: Path | None = None)` -- session is accepted from caller (not created internally). `pipeline_file` is the target `pipeline.py` to AST-modify; if `None`, skip AST modifications.
3. Implement `integrate(self, generated: GeneratedStep, target_dir: Path, draft: DraftStep | None = None) -> IntegrationResult` -- the main public method:
   - **Phase 1 -- Dir setup**: call `_ensure_target_dir(target_dir)`, track if newly created.
   - **Phase 2 -- File writes**: call `_write_files(generated, target_dir)`, track `files_written` list. Use `Path.write_text(..., encoding="utf-8")`. On Windows avoid `os.replace()` for `.bak` -- use direct `write_text`.
   - **Phase 3 -- Prompt DB registration**: call `_register_prompts(generated)`, returns count of newly inserted prompts. Use idempotent check-then-insert pattern from `creator/prompts.py:seed_prompts()` (select existing before inserting). Use `self.session.add()`, do NOT commit yet.
   - **Phase 4 -- AST modifications**: if `self.pipeline_file` is set, call `ast_modifier.modify_pipeline_file(...)` with derived class/module names. This writes the modified pipeline file (with `.bak` backup).
   - **Phase 5 -- DraftStep status update**: if `draft` is not None, set `draft.status = "accepted"`, `self.session.add(draft)`.
   - **Phase 6 -- Commit**: `self.session.commit()`.
   - On any exception in phases 2-6: call `_rollback_files(files_written, target_dir, newly_created_dir)`, call `self.session.rollback()`, restore `.bak` files if AST step had started, re-raise.
   - Return `IntegrationResult(files_written=..., prompts_registered=..., pipeline_file_updated=..., target_dir=str(target_dir))`.
4. Implement `_ensure_target_dir(target_dir: Path) -> bool` -- calls `mkdir(parents=True, exist_ok=True)`, writes empty `__init__.py` if missing, returns True if directory was newly created.
5. Implement `_write_files(generated: GeneratedStep, target_dir: Path) -> list[str]` -- iterates `generated.all_artifacts`, writes each file via `write_text`, returns list of absolute path strings.
6. Implement `_register_prompts(generated: GeneratedStep) -> int` -- runs `CodeSecurityValidator().validate(generated.prompts_code)` first. If issues found, falls back to `_reconstruct_prompts(generated)`. Otherwise `exec(generated.prompts_code, {"__builtins__": {}})` and extracts `namespace["ALL_PROMPTS"]`. Calls `_insert_prompts(prompt_list)` and returns count of inserted rows.
7. Implement `_insert_prompts(self, prompt_list: list[dict]) -> int` -- idempotent insert: `select(Prompt).where(Prompt.prompt_key == k, Prompt.prompt_type == t)`, skip if exists, else `session.add(Prompt(**d))`. Returns inserted count.
8. Implement `_reconstruct_prompts(generated: GeneratedStep) -> list[dict]` -- builds minimal system + user prompt dicts from `generated.step_name` and content derived from `generated.prompts_code` via basic string extraction. Category defaults to `generated.step_name`.
9. Implement `_rollback_files(files_written: list[str], target_dir: Path, newly_created: bool) -> None` -- deletes each written file, if `newly_created` removes entire dir with `shutil.rmtree(target_dir, ignore_errors=True)`, restores `.bak` files if they exist.
10. Add `__all__ = ["StepIntegrator"]`.
11. Update `llm_pipeline/creator/__init__.py` to export `StepIntegrator` from the module (keep jinja2 import guard at top, add import after).

### Step 4: Tests -- GeneratedStep and AST Modifier
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Create `tests/test_integrator_models.py` with `TestGeneratedStep` class:
   - `test_from_draft_extracts_step_code`: create `DraftStep` with `generated_code` dict matching `{step_name}_step.py` etc., assert `from_draft()` sets `step_code` correctly.
   - `test_from_draft_derives_class_names`: assert `step_class_name` is PascalCase + "Step", `instructions_class_name` is PascalCase + "Instructions".
   - `test_from_draft_extraction_code_none_when_missing`: `generated_code` without extraction key sets `extraction_code=None`.
   - `test_from_draft_all_artifacts_preserved`: `all_artifacts` contains all input dict entries.
2. Create `tests/test_ast_modifier.py` with `TestASTModifier` class. Uses `tmp_path` pytest fixture for writing temp pipeline files:
   - `test_splice_get_steps_multiline`: pipeline file with multiline `get_steps()` return list; after modify, new step appears.
   - `test_splice_get_steps_singleline`: pipeline file with single-line return list; after modify, list expanded to multiline with new step.
   - `test_splice_models_multiline` and `test_splice_models_singleline`: same for `models=[...]`.
   - `test_splice_agents_multiline` and `test_splice_agents_singleline`: same for `agents={...}`.
   - `test_inline_import_injection`: pipeline file with inline import in `get_steps()`; new step class appended to same ImportFrom node.
   - `test_toplevel_import_injection`: pipeline file with top-level imports; new `from x import Y` added at import block.
   - `test_bak_file_created`: after modify, `{file}.bak` exists.
   - `test_invalid_syntax_raises`: malformed pipeline source raises `ASTModificationError`.

### Step 5: Tests -- StepIntegrator
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Create `tests/test_step_integrator.py` with in-memory SQLite engine (from `create_engine("sqlite://")` + `init_pipeline_db(engine)`).
2. `TestStepIntegratorFileWrites`:
   - `test_files_written_to_target_dir`: after `integrate()`, all artifact files exist in `target_dir`.
   - `test_init_py_created_if_missing`: new target_dir gets `__init__.py`.
   - `test_integration_result_contains_paths`: `IntegrationResult.files_written` lists absolute paths.
3. `TestStepIntegratorPromptRegistration`:
   - `test_prompts_inserted_in_db`: after `integrate()`, `Prompt` rows exist for step's system+user prompts.
   - `test_idempotent_prompt_insertion`: second `integrate()` call with same step doesn't duplicate prompts.
   - `test_prompt_registration_fallback`: when prompts_code has security issue, fallback reconstruction still inserts prompts.
4. `TestStepIntegratorRollback`:
   - `test_rollback_deletes_files_on_db_error`: mock `session.commit()` to raise; assert written files deleted.
   - `test_rollback_removes_new_dir_on_failure`: if target_dir was newly created, rollback removes it.
   - `test_rollback_restores_bak_on_ast_failure`: mock AST modifier to raise after writing bak; bak restored.
5. `TestStepIntegratorDraftStatusUpdate`:
   - `test_draft_status_set_to_accepted`: pass `draft=DraftStep(...)` to `integrate()`; after call, `draft.status == "accepted"` in DB.
   - `test_draft_status_not_updated_if_none`: `draft=None` completes without error.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| File+DB non-atomicity: crash between file write and DB commit leaves orphaned files | Medium | DraftStep.status remains "draft" as recovery signal; document known limitation; orphaned files detectable by checking files without "accepted" DraftStep |
| Windows file locking on write_text for .bak files | Low | Use `Path.write_text()` directly instead of `os.replace()`; avoid temp-file rename pattern on Windows |
| Single-line list/dict expansion changes source formatting | Low | Only expand when insertion needed; document in ast_modifier docstring; bak file allows manual recovery |
| exec() on prompts_code escapes sandbox despite restricted builtins | Low | AST security scan runs first via CodeSecurityValidator denylist; prompts.yaml.j2 is framework-controlled template with no imports beyond `from __future__ import annotations`; restricted `{"__builtins__": {}}` namespace |
| Inline import detection fails if get_steps() uses unusual import form | Low | Fall back to top-level import if ImportFrom walk yields no results; document limitation |
| AST modifier partial write (crash mid-file-write) leaves corrupt pipeline file | Medium | .bak created before any write; rollback restores from .bak; if crash mid-write OS leaves partial file, .bak recovery still works on next run |
| DraftStep.updated_at not refreshed on status update | Low | Set `draft.updated_at = utc_now()` alongside `draft.status = "accepted"` in phase 5 |

## Success Criteria

- [ ] `GeneratedStep.from_draft(draft)` correctly extracts all artifact fields from `DraftStep.generated_code` dict
- [ ] `ast_modifier.modify_pipeline_file()` correctly splices `get_steps()` list in demo/pipeline.py-style file (top-level imports)
- [ ] `ast_modifier.modify_pipeline_file()` correctly splices `get_steps()` list in creator/pipeline.py-style file (inline imports)
- [ ] `ast_modifier.modify_pipeline_file()` correctly splices `models=[...]` class keyword
- [ ] `ast_modifier.modify_pipeline_file()` correctly splices `agents={...}` class keyword
- [ ] All three splices happen in single read/write cycle (one `.bak` file created)
- [ ] `StepIntegrator.integrate()` writes all artifact files to target_dir
- [ ] `StepIntegrator.integrate()` creates target_dir + `__init__.py` if missing
- [ ] `StepIntegrator.integrate()` registers prompts in DB using idempotent check-then-insert
- [ ] `StepIntegrator.integrate()` commits session after all writes succeed
- [ ] `StepIntegrator.integrate()` rolls back session and deletes written files on any failure
- [ ] `DraftStep.status` set to "accepted" inside same transaction when `draft` passed
- [ ] `IntegrationResult` returned with correct `files_written`, `prompts_registered`, `pipeline_file_updated`
- [ ] `StepIntegrator` exported from `llm_pipeline/creator/__init__.py`
- [ ] All new tests pass with `pytest`

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** AST modification of existing files is non-trivial and has two risky operations: (1) the hybrid locate+splice must handle both inline and top-level import patterns, and (2) rollback must correctly restore .bak files. File+DB non-atomicity is a known accepted limitation. The exec()-based prompt extraction has a security scan gate but is still a controlled dynamic evaluation. These risks are mitigated but introduce implementation complexity above simple CRUD work.
**Suggested Exclusions:** review
