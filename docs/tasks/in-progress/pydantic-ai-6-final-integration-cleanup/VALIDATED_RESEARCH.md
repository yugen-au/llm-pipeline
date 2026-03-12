# Research Summary

## Executive Summary

All 3 research agents' findings validated against codebase. Migration tasks 1-5 are structurally complete -- zero old LLM patterns remain in source code. 951/952 tests pass (1 failure unrelated). Key cleanup items confirmed: pydantic-ai must become core dep (import fails without it), google-generativeai is unused, llm/ subpackage is dead, 1 dead function, 2 stale docstrings, ~20 stale docs files. Two research corrections found: __pycache__ is gitignored (not a commit concern), and _query_prompt_keys dead code was missed by step-1 and step-3.

## Domain Findings

### pydantic-ai Dependency Classification
**Source:** step-1, step-2, step-3 (all three)

- CONFIRMED: `validators.py:14` has top-level `from pydantic_ai import ModelRetry, RunContext`
- `__init__.py:43` imports from validators at module level
- Result: `import llm_pipeline` crashes without pydantic-ai installed
- Other pydantic_ai imports are safe (TYPE_CHECKING or inside function bodies)
- Lazy-import alternative considered and rejected: would require conditional imports in `__init__.py`, creating fragile API where symbols sometimes exist
- pydantic-ai IS the library's LLM integration layer -- making it core is correct

### google-generativeai Dead Dependency
**Source:** step-1, step-2, step-3

- CONFIRMED: zero `google.generativeai` imports in `llm_pipeline/` source
- Listed in `pyproject.toml:23` (optional) and `pyproject.toml:34` (dev)
- pydantic-ai handles Gemini internally via model strings like `google-gla:gemini-2.0-flash-lite`
- Downstream concern: logistics-intelligence may use google-generativeai independently, but that's logistics-intelligence's dependency, not llm-pipeline's

### Dead llm/ Subpackage
**Source:** step-1, step-2, step-3

- CONFIRMED: `llm_pipeline/llm/__init__.py` contains only a comment
- `__pycache__/` has 8 stale .pyc files (executor, gemini, provider, rate_limiter, result, schema, validation, __init__)
- Zero imports from `llm_pipeline.llm` in source or tests
- CORRECTION: `__pycache__/` is in `.gitignore` and NOT tracked by git -- step-1 overstated this as needing cleanup commit

### Dead Code: _query_prompt_keys()
**Source:** step-2 only (gap: step-1 and step-3 missed this)

- CONFIRMED: defined at `step.py:34-77`, never called from any `.py` in `llm_pipeline/` or `tests/`
- Queries DB for prompt keys by step name -- superseded by `StepDefinition.create_step()` inline logic
- Not part of old LLM provider pattern (prompt utility), but still dead code

### Stale Docstrings in Source
**Source:** step-2, step-3

- `llm_pipeline/prompts/variables.py:26`: `provider=GeminiProvider()` in docstring example -- CONFIRMED
- `llm_pipeline/introspection.py:4-6`: "LLM provider dependencies" wording -- CONFIRMED
- Both are cosmetic, no code impact

### Stale CLAUDE.md
**Source:** step-3

- `.claude/CLAUDE.md:12`: "Optional: google-generativeai (Gemini provider)"
- `.claude/CLAUDE.md:23`: "LLMProvider (abstract) with GeminiProvider implementation"
- Affects all future Claude agent sessions -- medium severity

### Stale Documentation (~20 files)
**Source:** step-3

- CONFIRMED via grep: extensive `from llm_pipeline.llm import` references across docs/
- Files span docs/index.md, docs/README.md, docs/api/, docs/architecture/, docs/guides/
- docs/api/llm.md is entirely about removed code
- Historical task docs (docs/tasks/completed/) correctly excluded from scope

### Pre-existing Test Failure
**Source:** step-1, step-2

- `test_events_router_prefix`: expects `/events`, actual `/runs/{run_id}/events`
- Unrelated to pydantic-ai migration
- Not in scope for task 6

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| [pending -- see Questions below] | [awaiting CEO input] | [TBD] |

## Assumptions Validated
- [x] Tasks 1-5 migration is structurally complete (zero old patterns in source)
- [x] 951/952 tests pass, 1 failure unrelated to migration
- [x] pydantic-ai is effectively a hard dependency (import fails without it)
- [x] google-generativeai has zero usage in llm_pipeline source
- [x] llm/ subpackage has zero imports from source or tests
- [x] _query_prompt_keys() is defined but never called anywhere
- [x] __pycache__ in llm/ is gitignored and not a source control issue
- [x] All __init__.py exports are current (44 symbols, no deprecated re-exports)
- [x] consensus.py has no stale references to old patterns
- [x] agent_builders.py uses TYPE_CHECKING for pydantic_ai imports (safe pattern)
- [x] pipeline.py uses lazy imports for pydantic_ai (inside function bodies)

## Open Items
- pydantic-ai dependency classification decision (Q1)
- google-generativeai removal scope (Q2)
- llm/ directory deletion approach (Q3)
- _query_prompt_keys removal scope (Q4)
- Documentation update scope (Q5)
- Pre-existing test failure ownership (Q6)

## Recommendations for Planning
1. Move `pydantic-ai>=1.0.5` from optional to core dependencies -- library already broken without it
2. Delete `llm_pipeline/llm/` directory entirely (clean delete, no shim) -- transition already happened in tasks 1-5
3. Remove `_query_prompt_keys()` from step.py -- dead code, never called
4. Update both stale docstrings (variables.py, introspection.py)
5. Update `.claude/CLAUDE.md` architecture section -- affects every future AI session
6. Scope docs update based on CEO decision -- recommend at minimum: delete docs/api/llm.md, update docs/index.md and docs/README.md
7. google-generativeai removal from pyproject.toml (both optional and dev) pending CEO confirmation of no downstream use
8. Pre-existing test failure should be tracked separately (not task 6 scope)
