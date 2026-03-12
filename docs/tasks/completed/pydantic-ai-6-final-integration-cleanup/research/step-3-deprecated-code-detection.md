# Step 3: Deprecated Code Detection

## Summary

Source code is **remarkably clean**. Tasks 1-5 removed all deprecated functions, classes, and imports from Python source. Remaining items are: 1 vestigial directory, 2 stale docstrings, config deps question, and massive docs debt.

---

## Source Code Findings

### CLEAN - Already Removed (no action needed)

| Pattern | Status | Notes |
|---------|--------|-------|
| `create_llm_call()` | REMOVED | 0 matches in llm_pipeline/ or tests/ |
| `execute_llm_step()` | REMOVED | 0 matches |
| `LLMProvider` class | REMOVED | 0 matches in .py files |
| `GeminiProvider` class | REMOVED | 0 matches in .py (except 1 docstring) |
| `RateLimiter` | REMOVED | 0 matches |
| `call_gemini_with_structured_output()` | REMOVED | 0 matches |
| `format_schema_for_llm()` | REMOVED | 0 matches |
| `validate_structured_output()` | REMOVED | 0 matches |
| `validate_array_response()` | REMOVED | 0 matches |
| `check_not_found_response()` | REMOVED | 0 matches |
| `ExecuteLLMStepParams` | REMOVED | 0 matches |
| `LLMCallResult` | REMOVED | 0 matches |
| `strict_types` | REMOVED | 0 matches |
| `warnings.warn` / `DeprecationWarning` | NONE | No deprecated-but-kept functions exist |
| `TODO` / `FIXME` / `HACK` | NONE | 0 matches in llm_pipeline/ |
| Backward-compat shims / re-exports | NONE | No shim functions found |
| `PYDANTIC_AI_DEFER_MODEL_CHECK` env var | CLEAN | Not used in any Python source. `defer_model_check=True` in agent_builders.py is the correct pydantic-ai API parameter (not the env var). |

### ACTION REQUIRED - Source Code

#### 1. Delete vestigial `llm_pipeline/llm/` subpackage

- **File:** `llm_pipeline/llm/__init__.py`
- **Content:** Single comment line: `# LLM subpackage - provider abstraction removed, use pydantic-ai agents via agent_builders.py`
- **Directory:** Only contains `__init__.py` and `__pycache__/`
- **Impact:** Previously contained `provider.py`, `gemini.py`, `utils.py`, `rate_limiter.py`, `executor.py` -- all deleted in Tasks 1-3
- **Action:** Delete entire `llm_pipeline/llm/` directory
- **QUESTION:** Should we keep `__init__.py` with an `ImportError` redirect for downstream consumers, or delete entirely? (see Q3 below)

#### 2. Stale docstring in `llm_pipeline/prompts/variables.py`

- **File:** `llm_pipeline/prompts/variables.py`
- **Line 26:** `provider=GeminiProvider(),` in `VariableResolver` Protocol docstring example
- **Action:** Update example to use pydantic-ai model string pattern (e.g., `model='google-gla:gemini-2.0-flash-lite'`)
- **Severity:** Low (docstring only, no code impact)

#### 3. Minor docstring in `llm_pipeline/introspection.py`

- **File:** `llm_pipeline/introspection.py`
- **Lines 4-6:** Module docstring: "No FastAPI, SQLAlchemy, or LLM provider dependencies. Operates entirely on..."
- **Action:** Update "LLM provider" wording to "pydantic-ai" or remove mention
- **Severity:** Very low

---

## Configuration Findings

### 4. pyproject.toml - google-generativeai dependency (NEEDS INPUT)

- **File:** `pyproject.toml`
- **Line 23:** `gemini = ["google-generativeai>=0.3.0"]` (optional dependency group)
- **Line 34:** `"google-generativeai>=0.3.0",` (in dev dependencies)
- **Issue:** With pydantic-ai, model providers are handled internally (model strings like `google-gla:gemini-2.0-flash-lite`). The explicit `google-generativeai` SDK dependency may now be unnecessary.
- **Risk:** Downstream projects (e.g., logistics-intelligence) might still import `google.generativeai` directly for non-pipeline uses.
- **QUESTION:** See Q1 below.

### 5. .claude/CLAUDE.md - Stale architecture description

- **File:** `.claude/CLAUDE.md`
- **Line 12:** `- Optional: google-generativeai (Gemini provider)` in Tech Stack
- **Line 23:** `- LLMProvider (abstract) with GeminiProvider implementation` in Architecture
- **Action:** Update to reflect pydantic-ai agent architecture
- **Severity:** Medium (affects AI agent context for all future sessions)

---

## Documentation Findings

### 6. Extensive stale docs (~20 files)

Non-task-history documentation files with references to removed LLMProvider/GeminiProvider/create_llm_call/execute_llm_step:

| File | Stale References |
|------|-----------------|
| `docs/index.md` | LLMProvider, GeminiProvider, RateLimiter imports |
| `docs/README.md` | GeminiProvider usage examples, LLMProvider references |
| `docs/api/llm.md` | **ENTIRE FILE** documents removed LLMProvider, GeminiProvider, execute_llm_step |
| `docs/api/step.md` | create_llm_call references, ExecuteLLMStepParams |
| `docs/api/pipeline.md` | provider parameter, GeminiProvider examples |
| `docs/api/index.md` | LLMProvider/GeminiProvider imports, module structure |
| `docs/api/extraction.md` | execute_llm_step reference |
| `docs/api/prompts.md` | GeminiProvider import/usage |
| `docs/architecture/overview.md` | Extensive LLMProvider/GeminiProvider/create_llm_call references |
| `docs/architecture/concepts.md` | create_llm_call, execute_llm_step references |
| `docs/architecture/limitations.md` | LLMProvider/GeminiProvider as "single provider" limitation |
| `docs/architecture/patterns.md` | LLMProvider implementation examples |
| `docs/architecture/diagrams/c4-container.mmd` | LLMProvider, GeminiProvider, RateLimiter nodes |
| `docs/architecture/diagrams/c4-component.mmd` | create_llm_call on LLMStep, LLMProvider/execute_llm_step |
| `docs/guides/getting-started.md` | LLMProvider/GeminiProvider setup, custom provider guide |
| `docs/guides/basic-pipeline.md` | GeminiProvider usage, execute_llm_step import |
| `docs/guides/prompts.md` | GeminiProvider reference |

**Note:** docs/tasks/completed/ files are historical records and should NOT be modified.

---

## Questions for CEO

1. **pyproject.toml `gemini` optional-deps:** pydantic-ai handles model providers internally via model strings. Is `google-generativeai` still needed as an explicit optional dependency? Does logistics-intelligence or any downstream project import `google.generativeai` directly outside of the pipeline framework?

2. **Documentation update scope:** Task 6 description says "Update any relevant documentation" but ~20 docs files have stale references. Should docs update be part of task 6 implementation, or tracked as a separate follow-up task?

3. **llm/ subpackage deletion:** Should we delete the entire `llm_pipeline/llm/` directory, or keep `__init__.py` with an `ImportError` + migration message for downstream consumers who might `from llm_pipeline.llm import ...`?
