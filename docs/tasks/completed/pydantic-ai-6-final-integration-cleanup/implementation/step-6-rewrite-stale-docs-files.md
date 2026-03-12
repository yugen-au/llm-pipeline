# IMPLEMENTATION - STEP 6: REWRITE STALE DOCS FILES
**Status:** completed

## Summary
Removed all stale LLMProvider/GeminiProvider/google-generativeai references from 13 live docs files (2 of the 15 had no stale references). Replaced provider patterns with pydantic-ai model string pattern (`model='google-gla:gemini-2.0-flash-lite'`).

## Files
**Created:** none
**Modified:**
- `docs/guides/getting-started.md`
- `docs/guides/basic-pipeline.md`
- `docs/guides/prompts.md`
- `docs/architecture/overview.md`
- `docs/architecture/limitations.md`
- `docs/architecture/patterns.md`
- `docs/architecture/diagrams/c4-container.mmd`
- `docs/architecture/diagrams/c4-component.mmd`
- `docs/api/pipeline.md`
- `docs/api/step.md`
- `docs/api/extraction.md` (no changes needed - clean)
- `docs/api/prompts.md`
- `docs/README.md`
- `docs/index.md`
**Deleted:** none
**Skipped (no stale refs):**
- `docs/architecture/concepts.md`
- `docs/api/extraction.md`

## Changes

### File: `docs/guides/getting-started.md`
- Removed "Optional: Gemini Provider" install section
- Added pydantic-ai to core deps list
- Removed `from llm_pipeline.llm import LLMProvider` and `from llm_pipeline.llm.gemini import GeminiProvider` imports
- Replaced `GeminiProvider(model_name=...)` with `model='google-gla:gemini-2.0-flash-lite'`
- Replaced entire "Provider Configuration" section (GeminiProvider, RateLimiter, Custom Provider/LLMProvider ABC) with "Model Configuration" section showing pydantic-ai model strings
- Removed "google-generativeai not installed" troubleshooting entry
- Removed "GEMINI_API_KEY not set" GeminiProvider-specific fix
- Updated summary bullet

### File: `docs/guides/basic-pipeline.md`
- Replaced `pip install llm-pipeline[gemini]` with note about pydantic-ai core dep
- Replaced `GeminiProvider` import/instantiation with `model=` pattern
- Replaced "using configured provider" with "via pydantic-ai agents"
- Replaced all `provider=provider` constructor args
- Removed `from llm_pipeline.llm import execute_llm_step` reference
- Updated install command in complete example

### File: `docs/guides/prompts.md`
- Removed `from llm_pipeline.llm import GeminiProvider` import
- Replaced `provider=GeminiProvider()` with `model='google-gla:gemini-2.0-flash-lite'` (2 occurrences)
- Updated "See Also" link from llm.md to pipeline.md

### File: `docs/architecture/overview.md`
- Replaced GeminiProvider init example with model string
- Replaced "Custom LLM Provider" extension point with "LLM Model Selection" showing pydantic-ai strings
- Removed google-generativeai from optional deps, added pydantic-ai to core deps
- Replaced LLM Providers section with pydantic-ai model string description
- Updated API key management example
- Removed "Gemini-Only Provider" known limitation
- Replaced GeminiProvider() usage in migration example
- Updated file structure to show agents/ instead of llm/

### File: `docs/architecture/limitations.md`
- Removed entire "Provider Limitations / Gemini-Only LLM Provider" section (including custom provider code example)
- Updated summary table to remove "Gemini-only provider" row
- Removed "Add more providers" from future improvements

### File: `docs/architecture/patterns.md`
- Replaced entire "Custom LLM Provider" section (LLMProvider ABC, call_structured impl) with "LLM Model Selection" showing pydantic-ai model strings

### File: `docs/architecture/diagrams/c4-container.mmd`
- Replaced LLMProvider/GeminiProvider/SchemaFormatter/RateLimiter container with AgentRegistry/AgentBuilders
- Updated relationship edges
- Updated external LLM Service label
- Updated class definitions list

### File: `docs/architecture/diagrams/c4-component.mmd`
- Replaced `LLMProvider` ABC node with `AgentRegistry` pydantic-ai node

### File: `docs/api/pipeline.md`
- Replaced `provider` parameter with `model` in constructor signature and docs
- Replaced all `provider=provider` / `provider=gemini_provider` examples (~10 occurrences) with `model='google-gla:gemini-2.0-flash-lite'`
- Removed GeminiProvider import from usage pattern
- Updated validation note from "provider not set" to "model not set"

### File: `docs/api/step.md`
- Replaced "LLM Provider API Reference" link with "Pipeline API Reference"
- Removed `_query_prompt_keys()` from TOC and full section (function deleted in step 2)

### File: `docs/api/prompts.md`
- Replaced `from llm_pipeline.llm import GeminiProvider` and `provider=GeminiProvider()` with model string
- Replaced "LLM Provider API" see-also link with "Pipeline API"

### File: `docs/README.md`
- Updated LLM Integration description
- Replaced quick start code (removed GeminiProvider import, provider constructor)
- Replaced API module table LLM Provider row
- Replaced "Install with Gemini Support" and "Configure Gemini Provider" with "Configure LLM Model"
- Updated architecture overview LLM Integration line
- Removed google-generativeai from tech stack and optional requirements
- Updated Key Features and Known Limitations

### File: `docs/index.md`
- Replaced LLM Provider table row
- Updated "By Component" LLM Provider link
- Updated "By Concept" LLM Integration link
- Replaced API Quick Reference imports
- Updated file structure listing

## Decisions
### Replace pattern: provider= -> model=
**Choice:** Replaced all `provider=GeminiProvider(...)` with `model='google-gla:gemini-2.0-flash-lite'`
**Rationale:** Consistent with pydantic-ai model string pattern used throughout tasks 1-5. The model string is the new public API for specifying LLM providers.

### Remove vs rewrite Custom Provider section
**Choice:** Replaced Custom Provider / LLMProvider ABC extension point docs with short pydantic-ai model string section
**Rationale:** LLMProvider ABC no longer exists. Custom providers are now handled by pydantic-ai's model system, not by framework-level ABC implementation.

### _query_prompt_keys() documentation removal
**Choice:** Removed from step.md since function was deleted in step 2
**Rationale:** Documenting a deleted function would be misleading.

## Verification
[x] grep for GeminiProvider|LLMProvider|from llm_pipeline.llm|google-generativeai in docs/ (non-tasks) returns zero matches
[x] grep for call_structured|llm_pipeline[gemini] in docs/ (non-tasks) returns zero matches
[x] All 15 files checked; 13 modified, 2 had no stale references
[x] Mermaid diagrams updated consistently
[x] Cross-references (See Also links) updated from llm.md to pipeline.md
