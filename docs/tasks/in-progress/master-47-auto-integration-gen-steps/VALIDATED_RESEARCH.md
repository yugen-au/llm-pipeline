# Research Summary

## Executive Summary

Validated 3 research documents covering creator package patterns (step-1), AST code modification (step-2), and DB integration patterns (step-3) for the StepIntegrator (task 47). Cross-referencing against actual codebase revealed 4 critical gaps, 1 contradiction, and 3 unresolved architectural assumptions. All 5 CEO questions resolved in Q&A round 1.

Key findings: (1) AgentRegistry `agents={}` dict update was entirely missing from AST research -- CEO confirmed it is in scope, (2) strategy `get_steps()` has TWO import patterns (inline vs top-level) not both covered, (3) `GeneratedStep` Pydantic adapter type confirmed as the input interface, (4) prompt registration uses sandbox-guarded exec with context-field fallback, (5) integrator owns session.commit() for atomicity.

Post-resolution, 3 open items remain as implementation details (not architectural questions): inline import detection, single-line list expansion, Windows file locking.

## Domain Findings

### AgentRegistry AST Update -- Now In Scope
**Source:** step-2-ast-code-modification.md, creator/pipeline.py, demo/pipeline.py
**Resolved:** CEO Q1

Research step-2 covers AST modifications for two targets: `get_steps()` return list and `models=[]` class keyword. But the codebase requires THREE updates when integrating a new step:

1. Strategy `get_steps()` -- append `NewStep.create_definition()` (covered by research)
2. Registry `models=[...]` -- append new SQLModel class (covered by research)
3. AgentRegistry `agents={...}` -- add `"step_name": InstructionsClass` entry (NOT covered by research)

AgentRegistry uses a **dict** keyword (`agents={...}`), not a list. AST modification for dict insertion is structurally different from list append -- requires inserting a key-value pair, not just appending an element. Without this update, `agent_builders.py` cannot resolve the output type for the new step and pydantic-ai agent construction fails at runtime.

**CEO decision:** Both `models=[...]` and `agents={...}` updates are in scope. The AST modifier must handle dict-keyword insertion in addition to list-keyword append. The hybrid locate+splice approach applies to both, but the splice text differs: list append inserts `NewModel,` while dict append inserts `"step_name": InstructionsClass,`.

**Co-location advantage:** Both registry and agent_registry classes live in the same pipeline file (confirmed in `demo/pipeline.py` and `creator/pipeline.py`), so all three AST modifications (get_steps, models, agents) happen in a single file read/write cycle.

### Inline Import Pattern in get_steps()
**Source:** step-2-ast-code-modification.md, creator/pipeline.py L79-86

Research step-2's import injection section says "append to the import section" at file top. But `creator/pipeline.py` `DefaultCreatorStrategy.get_steps()` uses **inline imports inside the method body** to avoid circular dependencies:

```python
def get_steps(self):
    # Inline imports to avoid circular dependency with steps.py
    from llm_pipeline.creator.steps import (
        CodeGenerationStep,
        CodeValidationStep,
        PromptGenerationStep,
        RequirementsAnalysisStep,
    )
    return [...]
```

The demo `pipeline.py` uses top-level imports (steps defined in same file). The integrator must detect which pattern is used and inject imports accordingly -- inline import modification requires navigating into `FunctionDef.body` and modifying an `ImportFrom` node, a different AST operation than top-level import insertion.

**Implementation note:** Detection heuristic -- walk `get_steps` FunctionDef.body for `ImportFrom` nodes. If found, add the new step class to that existing import's names list. If not found, add a top-level import at the file's import section.

### GeneratedStep Input Type -- Pydantic Adapter
**Source:** step-1-creator-package-patterns.md Q1, step-3-db-integration-patterns.md section 5, task 47 spec, task 48 spec
**Resolved:** CEO Q2

Four sources referenced different input types:
- Task 47 spec: `integrate(self, generated: GeneratedStep, ...)` -- accesses `generated.step_code`, `generated.prompts`, `generated.extraction_model`
- Task 48 spec: `integrator.integrate(draft, request.target_pipeline)` -- passes DraftStep directly
- Research step-1 Q1: raises the question, proposes 3 options, no decision
- Research step-3: assumes DraftStep passed directly

`DraftStep.generated_code` is a `dict` (JSON column) containing the `all_artifacts` dict from `CodeValidationContext`. It does NOT have `.step_code`, `.prompts`, or `.extraction_model` attributes referenced in the task 47 spec.

**CEO decision:** Create `GeneratedStep` as a new Pydantic model in `creator/models.py` with explicit typed fields extracted from `DraftStep.generated_code`. Task 48's accept endpoint converts DraftStep to GeneratedStep before passing to integrator. This provides type safety at the integrator boundary while keeping DraftStep as the DB-layer type.

**Required fields on GeneratedStep** (derived from `all_artifacts` dict keys and context data):
- `step_name: str` -- from DraftStep.name
- `step_class_name: str` -- derivable from step_name via PascalCase + "Step" suffix
- `instructions_class_name: str` -- derivable as "{StepPrefix}Instructions"
- `step_code: str` -- from `all_artifacts["{step_name}_step.py"]`
- `instructions_code: str` -- from `all_artifacts["{step_name}_instructions.py"]`
- `prompts_code: str` -- from `all_artifacts["{step_name}_prompts.py"]`
- `extraction_code: str | None` -- from `all_artifacts.get("{step_name}_extraction.py")`
- `all_artifacts: dict[str, str]` -- full dict for file writing

### Prompt DB Registration -- Sandbox-Guarded Exec with Fallback
**Source:** step-1-creator-package-patterns.md Q3, creator/schemas.py, creator/templates/prompts.yaml.j2
**Resolved:** CEO Q3

`PromptGenerationInstructions` has `prompt_category: str` but `PromptGenerationContext` does NOT propagate it. The rendered `{step_name}_prompts.py` artifact DOES contain category (set during Jinja2 template rendering), so executing the rendered file preserves all fields.

**CEO decision:** Use sandbox-guarded execution of the generated prompts.py to extract `ALL_PROMPTS` list. Fallback to context-field reconstruction if Docker/sandbox unavailable.

**Refinement based on codebase review:** `StepSandbox.run()` performs AST security scan + Docker import check but does NOT execute code to extract runtime values -- it returns `SandboxResult(import_ok, ...)`, not extracted data. The actual approach must be:

1. **AST security scan first** -- use `CodeSecurityValidator().validate(prompts_code)` (already available in `sandbox.py`) to check for blocked modules/builtins
2. **Controlled exec** -- if scan passes, `exec(prompts_code, namespace)` in a restricted dict namespace to extract `namespace["ALL_PROMPTS"]`. The code is framework-generated from `prompts.yaml.j2` (a controlled Jinja2 template), not arbitrary user input. The template only produces dict literals and list literals -- no imports, no function calls, no side effects (aside from `from __future__ import annotations` which is safe).
3. **Fallback** -- if exec fails or security scan flags issues, reconstruct prompt dicts from `GeneratedStep` fields (step_name, system_prompt content from `PromptGenerationContext.system_prompt`, etc). Category defaults to step_name in this case.

### Session Lifecycle -- Integrator Owns Commit
**Source:** step-3-db-integration-patterns.md sections 3, 6, 7
**Resolved:** CEO Q4

Research step-3 section 7 flagged ambiguity: "Either the endpoint or the integrator should own the commit -- not both."

**CEO decision:** Integrator owns `session.commit()`. Accepts writable Session from caller. This gives the integrator full atomicity control -- on any failure, it calls `session.rollback()` and cleans up written files before re-raising.

**Implication for task 48:** Accept endpoint creates `Session(engine)`, passes to integrator. Endpoint does NOT commit. If integrator succeeds, DraftStep.status update must happen inside the integrator's transaction (before commit). Endpoint just returns the result.

**Pattern alignment:** This aligns with research step-3's recommended Pattern D (try/rollback/finally) and deviates from the pipeline's own flush-then-commit-in-save pattern. Acceptable because the integrator is not a pipeline -- it's a one-shot file+DB writer.

### Target Directory Creation -- Integrator Creates If Missing
**Source:** step-3-db-integration-patterns.md section 6
**Resolved:** CEO Q5

**CEO decision:** Integrator creates `target_dir` with `__init__.py` if it doesn't exist. This simplifies the accept endpoint -- caller only needs to specify WHERE, not pre-create the package.

**Implementation note:** Use `target_dir.mkdir(parents=True, exist_ok=True)`. If `__init__.py` doesn't exist, write an empty one (or one with `__all__`). Track created dirs/files for rollback -- if integration fails and the dir was newly created, remove it entirely.

### Rollback and Atomicity Constraints
**Source:** step-3-db-integration-patterns.md section 6

Research correctly identifies the try/rollback/finally pattern for DB operations. Additional constraints:
- File + DB is inherently non-atomic (no 2PC). Process crash between file write and DB commit leaves orphaned files. Acceptable tradeoff -- DraftStep.status remains unchanged, serving as recovery signal.
- `os.replace()` on Windows can fail if target file is open (file locking). Dev environment is Windows 11. Mitigate with retry or direct write_text.
- `.py.bak` files from the safety pattern may persist on crash. Minor, documented.

### Strategies/Registry Co-location
**Source:** step-2-ast-code-modification.md summary table

Research step-2 correctly notes: "Both targets exist in a SINGLE file per pipeline." Verified: `demo/pipeline.py` contains Registry, AgentRegistry, Strategy, Strategies, and PipelineConfig all in one file. `creator/pipeline.py` follows the same pattern. All three AST modifications (get_steps, models, agents) share one file read/write cycle.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Q1: Should integrator AST-update AgentRegistry `agents={}` dict in addition to Registry `models=[]`? | YES -- full integration so new step works at runtime. Both `models=[...]` and `agents={...}` updates in scope. | AST modifier scope expanded from 2 targets to 3. Dict-keyword insertion added as new operation type alongside list-keyword append. |
| Q2: Input type -- wrap DraftStep in GeneratedStep adapter or accept DraftStep directly? | GeneratedStep adapter -- new Pydantic model with explicit typed fields (step_code, prompts_code, etc.) for type safety. | New `GeneratedStep` model created in `creator/models.py`. Task 48 converts DraftStep to GeneratedStep at API boundary. Integrator interface is `integrate(self, generated: GeneratedStep, ...)`. |
| Q3: Prompt DB registration -- how to extract ALL_PROMPTS from generated prompts file? | Sandbox execution -- use StepSandbox to safely execute generated prompts.py, extract ALL_PROMPTS. Fallback to context-field reconstruction if Docker unavailable. | Refined: StepSandbox.run() doesn't extract values (returns SandboxResult only). Actual approach: (1) CodeSecurityValidator AST scan, (2) controlled `exec()` in restricted namespace, (3) fallback to context-field reconstruction. |
| Q4: Who owns session.commit() -- integrator or accept endpoint? | Integrator owns -- commits internally for atomicity. Accepts session from caller. | Integrator has full transaction control. DraftStep.status update happens inside integrator's transaction before commit. Endpoint does NOT commit. |
| Q5: Should target_dir be pre-existing or can integrator create it? | Integrator creates target_dir with `__init__.py` if missing. | Integrator calls `mkdir(parents=True, exist_ok=True)` and creates `__init__.py`. Newly created dirs tracked for rollback on failure. |

## Assumptions Validated

- [x] `get_steps()` ALWAYS returns a list literal directly (no intermediate variable) -- confirmed in both demo/pipeline.py and creator/pipeline.py
- [x] Registry uses `models=[...]` class keyword, never `MODELS = [...]` assignment -- confirmed in registry.py and both pipeline files
- [x] `UniqueConstraint('prompt_key', 'prompt_type')` on Prompt model -- confirmed in db/prompt.py
- [x] `DraftStep` has `UniqueConstraint("name")` -- confirmed in state.py
- [x] `seed_prompts()` uses idempotent check-then-insert with single commit -- confirmed in creator/prompts.py L256-267
- [x] Both demo and creator pipeline files contain all wiring classes in one file -- confirmed
- [x] `PipelineStrategies` uses `strategies=[...]` class keyword -- confirmed in strategy.py
- [x] `AgentRegistry` uses `agents={...}` class keyword (dict, not list) -- confirmed in agent_registry.py
- [x] `StepDefinition.step_name` is derived from class name via `to_snake_case(cls.__name__, strip_suffix='Step')` -- confirmed in strategy.py L46
- [x] ReadOnlySession blocks all write operations -- confirmed (research step-3 section 4)
- [x] `CodeValidationContext.all_artifacts` dict keys match `{step_name}_step.py` etc. format -- confirmed in steps.py L301-307
- [x] Pipeline context accumulates fields flatly -- confirmed by how steps access `self.pipeline.context.get(...)` dict-style
- [x] `prompts.yaml.j2` renders a Python module (not YAML) with dict literals and `ALL_PROMPTS` list -- confirmed in template source
- [x] Rendered prompt file contains `from __future__ import annotations` as only import -- safe for exec -- confirmed in template
- [x] `CodeSecurityValidator` in sandbox.py validates Python source via AST denylist scan -- confirmed, usable standalone without Docker
- [x] `StepSandbox.run()` returns SandboxResult, does NOT extract runtime values from executed code -- confirmed, cannot be used directly for ALL_PROMPTS extraction
- [x] `PipelineConfig.__init_subclass__` enforces naming: `{Prefix}Registry`, `{Prefix}Strategies`, `{Prefix}AgentRegistry` -- confirmed in pipeline.py

## Open Items

- Inline import detection in `get_steps()` body -- implementation detail, walk FunctionDef.body for ImportFrom nodes
- Single-line list expansion (e.g., `models=[Topic]`) -- expand to multiline during insertion, simpler than inline insert
- Windows `os.replace()` file locking -- mitigate with retry or direct write_text, edge case

## Recommendations for Planning

1. **GeneratedStep Pydantic model** -- define in `creator/models.py` with typed fields (`step_name`, `step_class_name`, `instructions_class_name`, `step_code`, `instructions_code`, `prompts_code`, `extraction_code`, `all_artifacts`). Add `@classmethod from_draft(cls, draft: DraftStep) -> GeneratedStep` factory that extracts fields from `draft.generated_code` dict.
2. **AST modifier scope: 3 targets** -- (a) `get_steps()` return list: append `NewStep.create_definition()`, (b) `models=[...]` class keyword: append model class name, (c) `agents={...}` class keyword: append `"step_name": InstructionsClass` entry. All three in a single file read/parse/splice/write cycle.
3. **Import injection: dual-pattern detection** -- check if `get_steps()` FunctionDef.body has `ImportFrom` nodes. If yes, add new step class to inline import names list. If no, add top-level import. For registry/agent_registry imports, always add at file top (no inline pattern exists for these).
4. **Prompt registration: 3-layer approach** -- (a) `CodeSecurityValidator().validate(prompts_code)` AST scan, (b) `exec(prompts_code, {"__builtins__": {}})` to extract `ALL_PROMPTS`, (c) fallback: reconstruct dicts from GeneratedStep fields with category defaulting to step_name. Use idempotent check-then-insert pattern from `seed_prompts()`.
5. **Integrator owns commit** -- accept Session from caller, commit inside try/except. On failure: `session.rollback()`, restore AST-modified files from backup, delete newly written files, re-raise.
6. **Directory creation** -- `target_dir.mkdir(parents=True, exist_ok=True)`, create `__init__.py` if missing. Track whether dir was newly created for rollback cleanup.
7. **Single-line list expansion** -- when the AST locator finds a list on a single line (e.g., `models=[Topic]`), expand to multiline format during splice, then insert the new element. Normalizes format for future insertions.
8. **File+DB non-atomicity** -- document as known limitation. DraftStep.status unchanged on failure serves as recovery signal. Orphaned files from crash can be detected by checking for files without corresponding "accepted" DraftStep records.
