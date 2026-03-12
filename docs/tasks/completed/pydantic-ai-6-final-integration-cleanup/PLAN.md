# PLANNING

## Summary

Remove all pydantic-ai migration remnants: promote pydantic-ai to core dependency, drop google-generativeai entirely, delete the llm/ stub directory, remove the `_query_prompt_keys()` dead function, fix the pre-existing test assertion failure, update 2 stale source docstrings, update CLAUDE.md tech stack section, and rewrite ~15 stale docs files that still reference the old LLMProvider/GeminiProvider pattern (plus delete docs/api/llm.md which documents removed code).

## Plugin & Agents

**Plugin:** python-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Implementation**: Code changes across 6 workstreams (deps, dead code, test fix, source docstrings, CLAUDE.md, docs sweep)

## Architecture Decisions

### No backward-compatibility shim for llm/ deletion
**Choice:** Delete `llm_pipeline/llm/` entirely with no ImportError shim.
**Rationale:** Tasks 1-5 completed the migration. Zero imports from `llm_pipeline.llm` exist in source or tests. All consumers have migrated. A shim would leave misleading dead code.
**Alternatives:** ImportError shim in `__init__.py` for downstream consumers -- rejected because transition is complete and logistics-intelligence already migrated.

### pydantic-ai promoted to core dependency
**Choice:** Move `pydantic-ai>=1.0.5` from `[project.optional-dependencies]` to `[project.dependencies]`. Remove the `pydantic-ai` optional group. Keep in dev deps.
**Rationale:** `validators.py:14` has top-level `from pydantic_ai import ModelRetry, RunContext` which is re-exported at module level via `__init__.py:43`. `import llm_pipeline` crashes without pydantic-ai -- it is a hard dependency in practice.
**Alternatives:** Lazy import pattern -- rejected: would require conditional imports in `__init__.py`, creating fragile API.

### Delete docs/api/llm.md rather than rewrite
**Choice:** Delete `docs/api/llm.md` entirely. Update `docs/api/index.md` link to remove the LLM Provider reference.
**Rationale:** The file documents `LLMProvider`, `GeminiProvider`, `RateLimiter`, `flatten_schema`, `format_schema_for_llm` -- all removed in tasks 1-3. No equivalent replacement module exists; pydantic-ai is used directly.
**Alternatives:** Rewrite as pydantic-ai integration docs -- excluded from scope, would be a new docs addition not a cleanup.

## Implementation Steps

### Step 1: Update pyproject.toml dependencies
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `pyproject.toml` `[project.dependencies]`, add `"pydantic-ai>=1.0.5"` after `"pyyaml>=6.0"`.
2. In `[project.optional-dependencies]`, remove the `gemini = ["google-generativeai>=0.3.0"]` line entirely.
3. In `[project.optional-dependencies]`, remove the `pydantic-ai = ["pydantic-ai>=1.0.5"]` line entirely.
4. In the `dev` optional dependency list, remove `"google-generativeai>=0.3.0"` line.
5. The `ui` and `otel` optional groups are unchanged. The `pydantic-ai` entry remains in dev deps.

### Step 2: Delete llm/ directory and remove _query_prompt_keys()
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Delete `llm_pipeline/llm/__init__.py` (the only tracked file in the directory -- `__pycache__/` is gitignored).
2. In `llm_pipeline/step.py`, remove lines 34-77 (the entire `_query_prompt_keys()` function including its docstring). Also remove the `Tuple` type import on line 12 if it becomes unused after removal. Verify `Optional` is still used elsewhere in the file before removing it.

### Step 3: Fix test_events_router_prefix assertion
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `tests/test_ui.py` line 143, change the expected prefix from `"/events"` to `"/runs/{run_id}/events"` to match the actual router prefix at `llm_pipeline/ui/routes/events.py:14`.

### Step 4: Update stale source docstrings
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/prompts/variables.py`, update the `VariableResolver` Protocol docstring example (line 26). Replace `provider=GeminiProvider()` with `model='google-gla:gemini-2.0-flash-lite'` in the pipeline construction example to reflect pydantic-ai model string pattern.
2. In `llm_pipeline/introspection.py` module docstring (lines 4-6), replace "LLM provider dependencies" with "pydantic-ai dependencies" (or just "external LLM dependencies") to reflect that the old LLMProvider/GeminiProvider pattern no longer applies.

### Step 5: Update .claude/CLAUDE.md tech stack section
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `.claude/CLAUDE.md` line 12, remove `- Optional: google-generativeai (Gemini provider)` from the Tech Stack section.
2. In `.claude/CLAUDE.md` line 23, replace `- LLMProvider (abstract) with GeminiProvider implementation` with `- pydantic-ai Agent system via AgentRegistry and agent_builders.py`.
3. In `.claude/CLAUDE.md` Dev Notes section, update `Test deps in [project.optional-dependencies].dev` to `Test deps and pydantic-ai in [project.optional-dependencies].dev; pydantic-ai also in core deps`.

### Step 6: Rewrite stale docs files (non-index, non-api-index)
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** C

Rewrite each file removing all references to `from llm_pipeline.llm import`, `LLMProvider`, `GeminiProvider`, `google-generativeai`, `gemini` optional extra, and old `call_structured()` patterns. Replace with pydantic-ai model string pattern (e.g., `model='google-gla:gemini-2.0-flash-lite'`) and remove provider construction examples. Each file's core content stays; only stale LLM provider references are updated.

Files to update:
1. `docs/guides/getting-started.md` -- Remove "Optional: Gemini Provider" install section, replace `from llm_pipeline.llm.gemini import GeminiProvider` import, replace `GeminiProvider(model_name=...)` instantiation with pydantic-ai model string, remove Custom Provider section showing LLMProvider ABC, remove `"google-generativeai not installed"` troubleshooting entry.
2. `docs/guides/basic-pipeline.md` -- Remove/replace GeminiProvider/LLMProvider imports and usage patterns.
3. `docs/guides/prompts.md` -- Remove/replace stale provider references.
4. `docs/architecture/overview.md` -- Remove LLMProvider/GeminiProvider from architecture description.
5. `docs/architecture/concepts.md` -- Remove/replace LLM Provider concept section.
6. `docs/architecture/limitations.md` -- Remove provider-specific limitations if any.
7. `docs/architecture/patterns.md` -- Remove LLMProvider/GeminiProvider pattern examples.
8. `docs/architecture/diagrams/c4-container.mmd` -- Remove GeminiProvider container if present.
9. `docs/architecture/diagrams/c4-component.mmd` -- Remove LLMProvider/GeminiProvider components if present.
10. `docs/api/pipeline.md` -- Remove provider parameter documentation (provider arg no longer exists).
11. `docs/api/step.md` -- Remove stale provider references if any.
12. `docs/api/extraction.md` -- Remove stale provider references if any.
13. `docs/api/prompts.md` -- Remove stale provider references if any.
14. `docs/README.md` -- Remove gemini optional install instructions, update architecture overview.
15. `docs/index.md` -- Remove GeminiProvider from quick start/overview examples.

### Step 7: Update docs/api/index.md and delete docs/api/llm.md
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Delete `docs/api/llm.md` entirely (documents removed LLMProvider/GeminiProvider/RateLimiter code).
2. In `docs/api/index.md`, remove the `### LLM Provider System` import block (lines 126-137 referencing `from llm_pipeline.llm import LLMProvider` etc.).
3. In `docs/api/index.md`, in the Module Reference list, remove the `- **[LLM Provider](llm.md)**` entry.
4. In `docs/api/index.md`, in the Package Structure diagram, remove the `llm/` subtree section.
5. In `docs/api/index.md`, remove `google-generativeai >= 0.3.0` from Optional Dependencies list.
6. In `docs/api/index.md`, add `pydantic-ai >= 1.0.5` to the Core Dependencies list.
7. In `docs/api/index.md`, remove `from llm_pipeline.llm.gemini import GeminiProvider` optional line from installation section.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Tuple import removal in step.py breaks other usages | Medium | Verify `Tuple` usage in step.py before removing the import; only remove if zero remaining uses |
| Docs sweep misses a stale reference | Low | After all steps complete, grep docs/ for `GeminiProvider\|LLMProvider\|llm_pipeline\.llm\|google-generativeai` to verify clean |
| llm/ directory deletion leaves orphan pyc files | Low | __pycache__ is gitignored -- no tracked files affected, git will not show changes |
| Test fix changes wrong line | Low | Actual prefix confirmed: `llm_pipeline/ui/routes/events.py:14` has `prefix="/runs/{run_id}/events"` |

## Success Criteria

- [ ] `pytest` passes all 952 tests (including previously failing test_events_router_prefix)
- [ ] `import llm_pipeline` succeeds without pydantic-ai installed returns clear missing-dep error (i.e., pydantic-ai is now a hard dep)
- [ ] `pyproject.toml` has no `gemini` or `pydantic-ai` optional groups
- [ ] `pyproject.toml` core `[project.dependencies]` includes `pydantic-ai>=1.0.5`
- [ ] `pyproject.toml` dev deps have no `google-generativeai` entry
- [ ] `llm_pipeline/llm/` directory does not exist (git-tracked files removed)
- [ ] `_query_prompt_keys()` function does not exist in `step.py`
- [ ] `grep -r "GeminiProvider\|LLMProvider\|from llm_pipeline\.llm\|google-generativeai" docs/` returns zero matches in the ~15 live docs files (excludes docs/tasks/)
- [ ] `docs/api/llm.md` does not exist
- [ ] `.claude/CLAUDE.md` has no mention of google-generativeai or LLMProvider/GeminiProvider

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All 6 workstreams are cleanups with no logic changes. The test fix is a 1-line assertion correction (test is wrong, router is correct). Dependency changes are additive (core) and subtractive (remove dead optional). Dead code removal is confirmed never-called. Docs are non-functional. No schema changes, no new abstractions, no integration risk.
**Suggested Exclusions:** testing, review
