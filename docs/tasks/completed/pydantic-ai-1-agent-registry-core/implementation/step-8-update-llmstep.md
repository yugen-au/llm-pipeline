# IMPLEMENTATION - STEP 8: UPDATE LLMSTEP
**Status:** completed

## Summary
Added get_agent() and build_user_prompt() concrete methods to LLMStep, deprecated create_llm_call() with DeprecationWarning. Added TYPE_CHECKING imports for AgentRegistry and Agent.

## Files
**Created:** none
**Modified:** llm_pipeline/step.py
**Deleted:** none

## Changes
### File: `llm_pipeline/step.py`
Added `import warnings` to file imports. Added TYPE_CHECKING imports for `Agent` (pydantic_ai) and `AgentRegistry` (llm_pipeline.agent_registry). Added two concrete methods to LLMStep class. Added deprecation warning as first statement in create_llm_call().

```
# Before (imports)
import logging
from abc import ABC, abstractmethod
...
if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig
    ...

# After (imports)
import logging
import warnings
from abc import ABC, abstractmethod
...
if TYPE_CHECKING:
    from pydantic_ai import Agent
    from llm_pipeline.agent_registry import AgentRegistry
    from llm_pipeline.pipeline import PipelineConfig
    ...
```

```
# Before (create_llm_call - first lines after docstring)
        system_key = system_instruction_key or self.system_instruction_key

# After (create_llm_call - first lines after docstring)
        warnings.warn(
            "create_llm_call() is deprecated, use get_agent() + build_user_prompt() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        system_key = system_instruction_key or self.system_instruction_key
```

New methods added between step_name property and store_extractions:
- `get_agent(self, registry) -> type`: looks up output_type via _agent_name override or step_name
- `build_user_prompt(self, variables, prompt_service, context) -> str`: builds user prompt, auto-dumps Pydantic models

## Decisions
### Return type annotation for get_agent()
**Choice:** `-> type` (returns the output_type class ref)
**Rationale:** Per PLAN.md, get_agent returns the output_type from registry for now. Task 2 will provide the full Agent instance via build_step_agent(). Docstring documents this clearly.

### Pydantic model_dump detection
**Choice:** `hasattr(variables, 'model_dump')` duck-typing check
**Rationale:** Avoids importing Pydantic BaseModel at runtime; works with any object that has model_dump (Pydantic v2 convention).

## Verification
[x] import warnings added
[x] TYPE_CHECKING imports for Agent and AgentRegistry added
[x] get_agent() uses getattr _agent_name fallback to step_name
[x] get_agent() calls registry.get_output_type()
[x] build_user_prompt() handles Pydantic model variables via model_dump
[x] build_user_prompt() delegates to prompt_service.get_user_prompt()
[x] create_llm_call() emits DeprecationWarning with stacklevel=2 as first statement
[x] create_llm_call() original implementation unchanged after warning
[x] All existing tests pass (1 pre-existing failure in test_ui unrelated)
[x] DeprecationWarning visible in test output from conftest calling create_llm_call()

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] MEDIUM: build_user_prompt() loses original Pydantic model instance -- passes dict as both variables= and variable_instance=, degrading PromptService diagnostic error messages that check hasattr(variable_instance, 'model_fields')

### Changes Made
#### File: `llm_pipeline/step.py`
Preserve original model reference before model_dump() so variable_instance retains the Pydantic model for diagnostics.

```
# Before
        if hasattr(variables, 'model_dump'):
            variables = variables.model_dump()
        return prompt_service.get_user_prompt(
            self.user_prompt_key,
            variables=variables,
            variable_instance=variables,
            context=context,
        )

# After
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

### Verification
[x] Original Pydantic model preserved as variable_instance
[x] Dict from model_dump() still passed as variables
[x] All 634 tests pass (1 pre-existing failure in test_ui unrelated)
