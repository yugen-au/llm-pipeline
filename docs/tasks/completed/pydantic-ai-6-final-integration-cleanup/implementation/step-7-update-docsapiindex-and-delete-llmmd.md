# IMPLEMENTATION - STEP 7: UPDATE DOCS/API/INDEX AND DELETE LLM.MD
**Status:** completed

## Summary
Deleted docs/api/llm.md (documented removed LLMProvider/GeminiProvider/RateLimiter code) and cleaned docs/api/index.md of all stale LLM provider references, added pydantic-ai as core dependency in docs.

## Files
**Created:** none
**Modified:** docs/api/index.md
**Deleted:** docs/api/llm.md

## Changes
### File: `docs/api/llm.md`
Deleted entirely -- documented LLMProvider, GeminiProvider, RateLimiter, flatten_schema, format_schema_for_llm which were all removed in tasks 1-3.

### File: `docs/api/index.md`
1. Removed `### LLM Provider System` import block (lines 125-137)
2. Removed `- **[LLM Provider](llm.md)**` from Module Reference list
3. Removed `llm/` subtree (7 lines) from Package Structure diagram
4. Removed `google-generativeai >= 0.3.0` from Optional Dependencies
5. Added `pydantic-ai >= 1.0.5` to Core Dependencies list
6. Removed Gemini Provider Support install subsection and "All Features" section (which only existed for gemini+dev combo)

```
# Before (installation section)
### Optional Dependencies
#### Gemini Provider Support
...pip install llm-pipeline[gemini]...
#### Development Tools
...
#### All Features
...pip install llm-pipeline[gemini,dev]...

# After
### Optional Dependencies
#### Development Tools
...pip install llm-pipeline[dev]...
```

```
# Before (core deps)
- pyyaml >= 6.0

# After
- pyyaml >= 6.0
- pydantic-ai >= 1.0.5
```

## Decisions
None

## Verification
[x] docs/api/llm.md deleted
[x] grep for GeminiProvider|LLMProvider|llm_pipeline.llm|google-generativeai in docs/api/index.md returns zero matches
[x] pydantic-ai >= 1.0.5 present in Core Dependencies
[x] No broken markdown structure in final file
