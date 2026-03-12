# IMPLEMENTATION - STEP 6: CREATE AGENT_BUILDERS.PY
**Status:** completed

## Summary
Created `llm_pipeline/agent_builders.py` with StepDeps dataclass (8 fields for pipeline dependency injection) and build_step_agent() factory function that constructs pydantic-ai Agent instances with dynamic system prompt resolution.

## Files
**Created:** `llm_pipeline/agent_builders.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/agent_builders.py`
New file. Contains two exports:

1. `@dataclass StepDeps` -- 8-field dependency container for RunContext[StepDeps]:
   - Required: `session: Any`, `pipeline_context: dict[str, Any]`, `prompt_service: Any`
   - Required metadata: `run_id: str`, `pipeline_name: str`, `step_name: str`
   - Optional: `event_emitter: Any | None = None`, `variable_resolver: Any | None = None`

2. `build_step_agent()` -- factory function returning `Agent[StepDeps, Any]`:
   - Params: step_name, output_type, model=None, system_instruction_key=None, retries=3, model_settings=None
   - Constructs Agent with `defer_model_check=True` (allows model=None for testing)
   - Registers `@agent.instructions` decorated `_inject_system_prompt()` that resolves system prompt via deps.prompt_service
   - Instructions function mirrors create_llm_call() pattern: checks variable_resolver, instantiates var class, calls get_system_prompt with variables dict and variable_instance; falls back to get_prompt for raw template

```python
# Key pattern -- @agent.instructions mirrors create_llm_call() from step.py
@agent.instructions
def _inject_system_prompt(ctx: RunContext[StepDeps]) -> str:
    if ctx.deps.variable_resolver:
        var_class = ctx.deps.variable_resolver.resolve(sys_key, 'system')
        if var_class:
            system_variables = var_class()
            variables_dict = (
                system_variables.model_dump()
                if hasattr(system_variables, 'model_dump')
                else system_variables
            )
            return ctx.deps.prompt_service.get_system_prompt(
                prompt_key=sys_key,
                variables=variables_dict,
                variable_instance=system_variables,
            )
    return ctx.deps.prompt_service.get_prompt(
        prompt_key=sys_key, prompt_type='system',
    )
```

## Decisions
### TYPE_CHECKING imports
**Choice:** Import PromptService, VariableResolver, PipelineEventEmitter, Session under TYPE_CHECKING only; use Any for runtime field types.
**Rationale:** Avoids circular imports. Real types are available for IDE type checking. Matches plan guidance and existing codebase pattern (step.py uses TYPE_CHECKING for PipelineConfig).

### Sync instructions function
**Choice:** Used synchronous `_inject_system_prompt` (not async) for `@agent.instructions`.
**Rationale:** PromptService.get_prompt() and get_system_prompt() are synchronous DB calls via SQLModel session. No async I/O needed. pydantic-ai supports both sync and async instructions -- sync is correct here. Confirmed in Context7 v1.0.5 docs: both patterns work.

### sys_key closure variable
**Choice:** `sys_key = system_instruction_key or step_name` computed once at build time, captured by closure in `_inject_system_prompt`.
**Rationale:** Mirrors create_llm_call() pattern where system_key defaults to self.system_instruction_key. Avoids re-computing on every agent run.

## Verification
[x] File parses without syntax errors (ast.parse)
[x] StepDeps imports successfully with all 8 fields confirmed
[x] build_step_agent constructs Agent with defer_model_check=True (no API key needed)
[x] Agent.name, deps_type, output_type, retries all set correctly
[x] @agent.instructions decorator registered (agent._instructions contains _inject_system_prompt)
[x] Existing test suite passes (583 passed, 1 pre-existing UI test failure unrelated)
[x] Graphiti updated with new file context

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] HIGH: `from pydantic_ai import Agent, RunContext` at line 11 is a runtime import. Since `__init__.py` unconditionally imports from `agent_builders`, any `import llm_pipeline` without pydantic-ai installed raises ImportError. pydantic-ai is an optional dependency.

### Changes Made
#### File: `llm_pipeline/agent_builders.py`
Moved pydantic_ai import behind TYPE_CHECKING guard, added lazy import inside build_step_agent() body, added `from __future__ import annotations` to defer annotation evaluation for return type `Agent[StepDeps, Any]`.

```python
# Before
from pydantic_ai import Agent, RunContext

if TYPE_CHECKING:
    from llm_pipeline.prompts.service import PromptService
    ...

def build_step_agent(...) -> Agent[StepDeps, Any]:
    agent: Agent[StepDeps, Any] = Agent(...)

# After
from __future__ import annotations

if TYPE_CHECKING:
    from pydantic_ai import Agent, RunContext
    from llm_pipeline.prompts.service import PromptService
    ...

def build_step_agent(...) -> Agent[StepDeps, Any]:
    from pydantic_ai import Agent, RunContext
    agent: Agent[StepDeps, Any] = Agent(...)
```

### Verification
[x] StepDeps imports without pydantic_ai being loaded at module level
[x] build_step_agent() still works correctly when pydantic_ai IS available
[x] Agent name, deps_type, output_type, instructions all set correctly
[x] Test suite passes (634 passed, 1 pre-existing UI failure unrelated)
