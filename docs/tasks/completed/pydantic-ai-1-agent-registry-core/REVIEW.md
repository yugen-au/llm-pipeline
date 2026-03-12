# Architecture Review

## Overall Assessment
**Status:** complete

Solid implementation. AgentRegistry faithfully mirrors PipelineDatabaseRegistry's Category A class-param pattern. StepDeps is clean. build_step_agent correctly uses defer_model_check and @agent.instructions. snake_case extraction to naming.py eliminates duplication and fixes the LLMStep.step_name single-regex bug. All 51 new tests pass, 853 existing tests pass (2 pre-existing failures unrelated to this change). Three issues found -- one HIGH, two MEDIUM.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`

| Guideline | Status | Notes |
| --- | --- | --- |
| Tests pass | pass | 51 new tests pass, 853 existing pass, 2 pre-existing failures (test_ui, test_wal) unrelated |
| No hardcoded values | pass | No hardcoded secrets, API keys, or magic strings |
| Error handling present | pass | KeyError with descriptive message in get_output_type, ValueError in __init_subclass__ |
| Python 3.11+ | pass | Uses `str \| None` union syntax, `dict[str, Any]` generics |
| Pydantic v2 | pass | BaseModel from pydantic, model_dump() usage correct |
| Hatchling build | pass | pyproject.toml optional dep added correctly |

## Issues Found
### Critical

None

### High
#### pydantic-ai runtime import in agent_builders.py breaks `import llm_pipeline` when pydantic-ai not installed
**Step:** 6, 11
**Details:** `agent_builders.py` line 11 has `from pydantic_ai import Agent, RunContext` as a runtime import. Since `__init__.py` unconditionally imports `from llm_pipeline.agent_builders import StepDeps, build_step_agent`, any user doing `import llm_pipeline` without pydantic-ai installed will get an ImportError. pydantic-ai is declared as an optional dependency in pyproject.toml (`[project.optional-dependencies].pydantic-ai`), so the package should remain importable without it.

**Fix:** Either (a) move the pydantic_ai import behind `TYPE_CHECKING` in agent_builders.py and use lazy imports inside `build_step_agent()`, or (b) wrap the `__init__.py` imports in a try/except ImportError block, or (c) guard with conditional import in agent_builders.py. Option (a) is cleanest and consistent with how step.py already handles it.

### Medium
#### build_user_prompt loses variable_instance model reference after model_dump()
**Step:** 8
**Details:** In `LLMStep.build_user_prompt()` (step.py lines 303-310), when `variables` has `model_dump`, the method calls `variables = variables.model_dump()` then passes the resulting dict as both `variables=` and `variable_instance=` to `prompt_service.get_user_prompt()`. The original Pydantic model instance is lost. PromptService uses `variable_instance` for diagnostic error reporting (`hasattr(variable_instance, 'model_fields')`) -- passing a dict degrades error messages. Should preserve original model as `variable_instance` before calling `model_dump()`.

**Fix:**
```python
variable_instance = variables
if hasattr(variables, 'model_dump'):
    variables = variables.model_dump()
return prompt_service.get_user_prompt(
    self.user_prompt_key,
    variables=variables,
    variable_instance=variable_instance,
    context=context,
)
```

#### PipelineConfig.pipeline_name property still uses single-regex (same bug that was fixed in LLMStep.step_name)
**Step:** 4
**Details:** `pipeline.py` line 274 still has `re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()` -- the single-regex variant that produces wrong results for consecutive capitals (e.g. `HTMLPipeline` -> `htmlpipeline` instead of `html`). The plan only specified refactoring 3 callsites (step.py, strategy.py StepDefinition, pipeline.py StepKeyDict), but this 4th callsite has the identical bug. `PipelineStrategy.__init_subclass__` in strategy.py lines 193-196 also still uses inline `import re` and `re.sub` rather than `to_snake_case`, though that one correctly uses the double-regex pattern and also generates display_name which to_snake_case doesn't handle.

**Fix:** Replace pipeline_name property body with `return to_snake_case(class_name, strip_suffix='Pipeline')`. The `import re` at the top of pipeline.py can be removed after this change since no other `re.` usage remains. The PipelineStrategy inline regex is less urgent since it already uses double-regex correctly, but could be partially refactored for consistency.

### Low
#### Unclosed SQLite connection warning in test
**Step:** 7
**Details:** `test_create_step_sets_agent_name_on_instance` creates an in-memory SQLite engine and Session but never closes them, producing `ResourceWarning: unclosed database`. Harmless but noisy.

**Fix:** Add `session.close(); engine.dispose()` at end of test, or use a context manager.

## Review Checklist
[x] Architecture patterns followed -- AgentRegistry mirrors PipelineDatabaseRegistry exactly; Category A class-param __init_subclass__ pattern
[x] Code quality and maintainability -- Clean separation of concerns; naming.py eliminates duplication; good docstrings
[x] Error handling present -- ValueError in __init_subclass__, KeyError in get_output_type with helpful messages
[x] No hardcoded values
[x] Project conventions followed -- Flat file layout in llm_pipeline/, snake_case naming, __all__ exports, TYPE_CHECKING guards
[x] Security considerations -- No secrets, no SQL injection, no user input in eval
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- Minimal surface area; no premature abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/naming.py | pass | Clean utility, correct double-regex, good docstring with examples |
| llm_pipeline/agent_registry.py | pass | Faithful mirror of PipelineDatabaseRegistry pattern |
| llm_pipeline/agent_builders.py | fail | Runtime pydantic_ai import breaks optional dep contract (HIGH) |
| llm_pipeline/step.py | pass | step_name fix correct; get_agent/build_user_prompt well-structured; build_user_prompt has variable_instance loss (MEDIUM) |
| llm_pipeline/strategy.py | pass | agent_name field, step_name property, create_step agent_name propagation all correct |
| llm_pipeline/pipeline.py | pass | agent_registry= param follows registry=/strategies= precedent; pipeline_name still has single-regex bug (MEDIUM, pre-existing but now exposed by naming.py existence) |
| llm_pipeline/__init__.py | pass | Exports correctly organized |
| pyproject.toml | pass | Optional dep and dev dep both at >=1.0.5 |
| tests/test_agent_registry_core.py | pass | 51 tests, thorough coverage of all new code paths |

## New Issues Introduced
- HIGH: `import llm_pipeline` fails without pydantic-ai installed due to unconditional runtime import in agent_builders.py (Step 6/11)
- MEDIUM: build_user_prompt loses Pydantic model reference for variable_instance diagnostic (Step 8)
- MEDIUM: pipeline_name property has same single-regex bug that was fixed in step_name (Step 4 scope gap; pre-existing bug now inconsistent with fix)
- LOW: Unclosed SQLite connection in test (Step 7)

## Recommendation
**Decision:** CONDITIONAL

Fix the HIGH issue (pydantic-ai runtime import) before merge. The MEDIUM issues are recommended fixes but not blocking -- build_user_prompt variable_instance loss is a diagnostic degradation not a functional break, and pipeline_name single-regex is a pre-existing bug outside the stated scope.

---

# Re-Review: Fix Verification

## Overall Assessment
**Status:** complete

All 4 previously identified issues are correctly resolved. No new issues introduced by the fixes. 51 new tests pass, 854 existing tests pass (up from 853; the pre-existing WAL test now passes). Only 1 pre-existing failure remains (test_events_router_prefix, unrelated UI test).

## Fix Verification

### Fix 1: pydantic-ai runtime import (was HIGH) -- RESOLVED
**File:** `llm_pipeline/agent_builders.py`
**Verification:**
- `from __future__ import annotations` added at line 8, enabling string-form annotations
- `from pydantic_ai import Agent, RunContext` moved inside `TYPE_CHECKING` block at line 14
- Lazy import `from pydantic_ai import Agent, RunContext` added inside `build_step_agent()` function body at line 75
- `StepDeps` dataclass has no pydantic_ai references, safe to import unconditionally
- `__init__.py` import of `StepDeps, build_step_agent` will not trigger pydantic_ai load at import time

### Fix 2: build_user_prompt variable_instance loss (was MEDIUM) -- RESOLVED
**File:** `llm_pipeline/step.py`
**Verification:**
- Line 303: `variable_instance = variables` preserves original reference before mutation
- Line 305: `variables = variables.model_dump()` only mutates the local binding
- Line 309: `variable_instance=variable_instance` passes original Pydantic model to PromptService
- PromptService diagnostic path (`hasattr(variable_instance, 'model_fields')`) will now work correctly

### Fix 3: pipeline_name single-regex bug (was MEDIUM) -- RESOLVED
**File:** `llm_pipeline/pipeline.py`
**Verification:**
- Line 272: `return to_snake_case(class_name, strip_suffix="Pipeline")` replaces old single-regex
- `import re` removed from pipeline.py (no remaining `re.` usage confirmed)
- Consecutive capitals like `HTMLPipeline` will now correctly produce `html` instead of `htmlpipeline`

### Fix 4: Unclosed SQLite connection in test (was LOW) -- RESOLVED
**File:** `tests/test_agent_registry_core.py`
**Verification:**
- Lines 453-454: `session.close()` and `engine.dispose()` added after assertion
- ResourceWarning no longer appears in test output

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`

| Guideline | Status | Notes |
| --- | --- | --- |
| Tests pass | pass | 51 new + 854 existing pass; 1 pre-existing failure (UI test) unrelated |
| No hardcoded values | pass | Unchanged from initial review |
| Error handling present | pass | Unchanged from initial review |
| Python 3.11+ | pass | `from __future__ import annotations` added correctly for forward refs |
| Pydantic v2 | pass | Unchanged from initial review |
| Hatchling build | pass | Unchanged from initial review |

## Issues Found
### Critical
None

### High
None

### Medium
None

### Low
None

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/agent_builders.py | pass | TYPE_CHECKING guard + lazy import correctly implemented |
| llm_pipeline/step.py | pass | variable_instance preserved before model_dump() |
| llm_pipeline/pipeline.py | pass | to_snake_case replaces single-regex, `import re` removed |
| tests/test_agent_registry_core.py | pass | session.close() + engine.dispose() added, no ResourceWarning |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE

All 4 issues from initial review are correctly fixed. Fixes are minimal and targeted. No regressions (854 pass, up from 853). Implementation is ready to merge.
