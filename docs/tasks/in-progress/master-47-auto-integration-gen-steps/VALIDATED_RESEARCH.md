# Research Summary

## Executive Summary

Validated 3 research documents covering creator package patterns (step-1), AST code modification (step-2), and DB integration patterns (step-3) for the StepIntegrator (task 47). Cross-referencing against actual codebase revealed 4 critical gaps, 1 contradiction, and 3 unresolved architectural assumptions. The research is largely accurate on individual findings but fails to address cross-cutting concerns that emerge when the three domains intersect.

Key findings: (1) AgentRegistry `agents={}` dict update is entirely missing from AST research, (2) strategy `get_steps()` has TWO import patterns (inline vs top-level) not both covered, (3) no consensus on input type (GeneratedStep vs DraftStep), (4) prompt data source has a field-loss gap between PromptGenerationInstructions and PromptGenerationContext.

## Domain Findings

### AgentRegistry AST Update Missing
**Source:** step-2-ast-code-modification.md, creator/pipeline.py, demo/pipeline.py

Research step-2 covers AST modifications for two targets: `get_steps()` return list and `models=[]` class keyword. But the codebase requires THREE updates when integrating a new step:

1. Strategy `get_steps()` -- append `NewStep.create_definition()` (covered)
2. Registry `models=[...]` -- append new SQLModel class (covered)
3. AgentRegistry `agents={...}` -- add `"step_name": InstructionsClass` entry (NOT covered)

AgentRegistry uses a **dict** keyword (`agents={...}`), not a list. AST modification for dict insertion is structurally different from list append -- requires inserting a key-value pair, not just appending an element. Without this update, `agent_builders.py` cannot resolve the output type for the new step and pydantic-ai agent construction fails at runtime.

### Inline Import Pattern in get_steps()
**Source:** step-2-ast-code-modification.md, creator/pipeline.py L79-86

Research step-2's import injection section says "append to the import section" at file top. But `creator/pipeline.py` `DefaultCreatorStrategy.get_steps()` uses **inline imports inside the method body** to avoid circular dependencies:

```python
def get_steps(self):
    from llm_pipeline.creator.steps import (
        CodeGenerationStep, CodeValidationStep, ...
    )
    return [...]
```

The demo `pipeline.py` uses top-level imports (steps defined in same file). The integrator must detect which pattern is used and inject imports accordingly -- inline import modification requires navigating into `FunctionDef.body` and modifying an `ImportFrom` node, a different AST operation than top-level import insertion.

### GeneratedStep Input Type Undefined
**Source:** step-1-creator-package-patterns.md Q1, step-3-db-integration-patterns.md section 5, task 47 spec, task 48 spec

Four sources reference different input types:
- Task 47 spec: `integrate(self, generated: GeneratedStep, ...)` -- accesses `generated.step_code`, `generated.prompts`, `generated.extraction_model`
- Task 48 spec: `integrator.integrate(draft, request.target_pipeline)` -- passes DraftStep directly
- Research step-1 Q1: raises the question, proposes 3 options, no decision
- Research step-3: assumes DraftStep passed directly

`DraftStep.generated_code` is a `dict` (JSON column) containing the `all_artifacts` dict. It does NOT have `.step_code`, `.prompts`, or `.extraction_model` attributes referenced in the task 47 spec. An adapter/wrapper type or dict-key access pattern is needed.

### Prompt Data Field Loss
**Source:** step-1-creator-package-patterns.md Q3, creator/schemas.py, creator/templates/prompts.yaml.j2

`PromptGenerationInstructions` has `prompt_category: str` but `PromptGenerationContext` does NOT propagate it. For DB registration via option (b) (structured context data), the integrator would need to pull `prompt_category` from a different context layer or use a hardcoded default. The `category` field in the Prompt model is optional but useful for filtering prompts by pipeline.

The rendered `{step_name}_prompts.py` artifact DOES contain the category (set during template rendering in `PromptGenerationStep.process_instructions`), so option (a) (parsing artifact) preserves it, but requires executing or parsing Python source.

### Rollback and Atomicity Constraints
**Source:** step-3-db-integration-patterns.md section 6

Research correctly identifies the try/rollback/finally pattern for DB operations. However:
- File + DB is inherently non-atomic (no 2PC). Process crash between file write and DB commit leaves orphaned files. Acceptable tradeoff but needs documentation.
- `os.replace()` on Windows can fail if target file is open (file locking). Dev environment is Windows 11.
- `.py.bak` files from the safety pattern may persist on crash.

### Strategies/Registry Co-location
**Source:** step-2-ast-code-modification.md summary table

Research step-2 correctly notes: "Both targets exist in a SINGLE file per pipeline." Verified: `demo/pipeline.py` contains Registry, AgentRegistry, Strategy, Strategies, and PipelineConfig all in one file. `creator/pipeline.py` also follows this pattern. This means strategy, registry, and agent_registry modifications can share one file read/write cycle.

### Session Lifecycle Patterns
**Source:** step-3-db-integration-patterns.md sections 3-4

Research correctly identifies Pattern C (context manager with single commit) as best match for prompt registration idempotency. Pattern D (try/rollback/finally) is correct for the overall integrator transaction. The recommendation to use `Session(engine)` over `Session(bind=)` is consistent with newer codebase patterns.

However, commit ownership is ambiguous -- section 6 puts commit inside integrator, section 7 notes "either endpoint or integrator should own commit -- not both" and recommends integrator ownership. This conflicts with the pipeline's own pattern where flush happens during execution but commit is deferred to save().

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Pending -- see Questions below | | |

## Assumptions Validated

- [x] `get_steps()` ALWAYS returns a list literal directly (no intermediate variable) -- confirmed in both demo/pipeline.py and creator/pipeline.py
- [x] Registry uses `models=[...]` class keyword, never `MODELS = [...]` assignment -- confirmed in registry.py and both pipeline files
- [x] `UniqueConstraint('prompt_key', 'prompt_type')` on Prompt model -- confirmed in db/prompt.py L41
- [x] `DraftStep` has `UniqueConstraint("name")` -- confirmed in state.py L236
- [x] `seed_prompts()` uses idempotent check-then-insert with single commit -- confirmed in creator/prompts.py L256-267
- [x] Both demo and creator pipeline files contain all wiring classes in one file -- confirmed
- [x] `PipelineStrategies` uses `strategies=[...]` class keyword -- confirmed in strategy.py
- [x] `AgentRegistry` uses `agents={...}` class keyword (dict, not list) -- confirmed in agent_registry.py
- [x] `StepDefinition.step_name` is derived from class name via `to_snake_case(cls.__name__, strip_suffix='Step')` -- confirmed in strategy.py L46
- [x] ReadOnlySession blocks all write operations -- confirmed (research step-3 section 4)
- [x] `CodeValidationContext.all_artifacts` dict keys match `{step_name}_step.py` etc. format -- confirmed in steps.py L301-307
- [x] Pipeline context accumulates fields flatly -- confirmed by how steps access `self.pipeline.context.get(...)` dict-style

## Open Items

- AgentRegistry `agents={}` AST modification not researched -- dict insertion differs from list append
- Inline import injection in `get_steps()` body not addressed by step-2 research
- `GeneratedStep` type needs definition -- task 47 spec interface doesn't match DraftStep fields
- `prompt_category` field lost between PromptGenerationInstructions and PromptGenerationContext
- Session commit ownership (integrator vs caller) unresolved
- target_dir package creation (new package with `__init__.py` vs existing directory) unspecified
- Windows `os.replace()` file locking edge case not addressed in safety pattern

## Recommendations for Planning

1. Define `GeneratedStep` as a Pydantic model wrapping DraftStep -- extracts `all_artifacts` dict, `step_name`, and prompt data into typed attributes. Accept DraftStep at the API boundary (task 48), convert to GeneratedStep inside the accept endpoint before passing to integrator.
2. Add AgentRegistry `agents={}` dict update to AST modifier scope. Use same hybrid locate+splice approach but with dict entry insertion (`"key": Value,`) instead of list element append.
3. AST import injection must detect inline vs top-level patterns. Check if `get_steps` body contains `ImportFrom` nodes; if yes, modify the inline import. If no, add to file-level imports.
4. For prompt DB registration, use option (a) with safe exec -- `exec()` the rendered prompts.py in a restricted namespace to extract `ALL_PROMPTS` list. The code is framework-generated from a controlled Jinja2 template, not arbitrary user input. This preserves category and all fields consistently.
5. Caller (accept endpoint) should own `session.commit()`, not the integrator. Integrator should flush but not commit. This matches the pipeline's own pattern and gives the endpoint transactional control over DraftStep.status update + any event records.
6. target_dir should be an existing directory. Integrator should NOT create `__init__.py` or package structure -- that responsibility belongs to a higher-level "create pipeline" workflow (out of scope for task 47). Document this constraint.
7. Handle single-line lists (e.g., `models=[Topic]`) by expanding to multiline format during insertion. This is simpler than supporting inline insertion and normalizes the format.
8. Document file+DB non-atomicity as a known limitation. On partial failure, DraftStep.status remains unchanged, serving as the recovery signal.
