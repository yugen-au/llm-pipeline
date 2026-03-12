# Research Summary

## Executive Summary

All 3 research agents' findings validated against codebase. Migration tasks 1-5 are structurally complete -- zero old LLM patterns remain in source code. 951/952 tests pass (1 failure unrelated). All 6 CEO decisions received. Task 6 scope finalized: 6 workstreams covering dep cleanup, dead code removal, docstring fixes, CLAUDE.md update, ~20-file docs sweep, and test fix. Two research corrections found: __pycache__ is gitignored (not a commit concern), and _query_prompt_keys dead code was missed by step-1 and step-3. No blockers remain -- ready for planning phase.

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

- `test_events_router_prefix` (`tests/test_ui.py:140-143`): expects `/events`, actual `/runs/{run_id}/events`
- Unrelated to pydantic-ai migration -- router is correct, test assertion is wrong
- CEO decision: fix in task 6 scope (Workstream F)

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Q1: Move pydantic-ai from optional to core deps? | YES -- required, not optional | Move `pydantic-ai>=1.0.5` from `[project.optional-dependencies]` to `[project.dependencies]`. Remove `pydantic-ai` optional group entirely. Keep in dev deps. |
| Q2: Remove google-generativeai from optional AND dev deps? | REMOVE entirely from both | Delete `gemini` optional group (pyproject.toml:23). Remove from dev deps (pyproject.toml:34). No downstream usage to protect. |
| Q3: Delete llm/ directory entirely or add ImportError shim? | DELETE entirely, no shim | Delete `llm_pipeline/llm/` directory including `__init__.py`. No backward compat concern -- transition happened in tasks 1-5. |
| Q4: Include _query_prompt_keys() removal in task 6? | YES, remove in task 6 | Delete `_query_prompt_keys()` function from `step.py:34-77`. Dead code, never called. |
| Q5: Docs update scope -- all ~20 files or subset? | ALL ~20 stale files updated in task 6 | Full docs sweep. Includes docs/api/llm.md (delete or rewrite), docs/index.md, docs/README.md, docs/api/, docs/architecture/, docs/guides/. Excludes docs/tasks/completed/ (historical). |
| Q6: Fix test_events_router_prefix in task 6 or track separately? | FIX in task 6 | Fix test assertion: change expected prefix from `/events` to `/runs/{run_id}/events` (test_ui.py:143). Router is correct, test is wrong. |

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
- None -- all 6 questions resolved by CEO

## Recommendations for Planning

### Workstream A: Dependency cleanup (pyproject.toml)
1. Move `pydantic-ai>=1.0.5` from optional to core `[project.dependencies]`
2. Delete `pydantic-ai` optional group from `[project.optional-dependencies]`
3. Delete `gemini` optional group (`google-generativeai`) from `[project.optional-dependencies]`
4. Remove `google-generativeai>=0.3.0` from dev deps

### Workstream B: Dead code removal
5. Delete `llm_pipeline/llm/` directory entirely (only contains stub `__init__.py` + gitignored `__pycache__/`)
6. Remove `_query_prompt_keys()` from `step.py:34-77`

### Workstream C: Stale source docstrings
7. Update `llm_pipeline/prompts/variables.py:26` -- replace `provider=GeminiProvider()` with pydantic-ai model string
8. Update `llm_pipeline/introspection.py:4-6` -- replace "LLM provider" wording

### Workstream D: CLAUDE.md update
9. Update `.claude/CLAUDE.md:12` -- remove google-generativeai from tech stack
10. Update `.claude/CLAUDE.md:23` -- replace LLMProvider/GeminiProvider with pydantic-ai agent architecture

### Workstream E: Documentation sweep (~20 files)
11. Delete or rewrite `docs/api/llm.md` (entire file documents removed code)
12. Update all stale docs files: docs/index.md, docs/README.md, docs/api/step.md, docs/api/pipeline.md, docs/api/index.md, docs/api/extraction.md, docs/api/prompts.md, docs/architecture/overview.md, docs/architecture/concepts.md, docs/architecture/limitations.md, docs/architecture/patterns.md, docs/architecture/diagrams/c4-container.mmd, docs/architecture/diagrams/c4-component.mmd, docs/guides/getting-started.md, docs/guides/basic-pipeline.md, docs/guides/prompts.md
13. Exclude docs/tasks/completed/ (historical records)

### Workstream F: Test fix
14. Fix `tests/test_ui.py:143` -- change expected prefix from `/events` to `/runs/{run_id}/events`

### Implementation Order
Recommended: A -> B -> F -> C -> D -> E (deps and dead code first, then cosmetic, docs last as largest effort)
