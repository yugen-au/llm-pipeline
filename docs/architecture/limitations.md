# Known Limitations

This document outlines current limitations and known issues in the llm-pipeline framework. These are documented to help users avoid common pitfalls and to track future improvements.

## Database Session Limitations

### clear_cache() Bug with ReadOnlySession

**Issue**: The `clear_cache()` method in `PipelineConfig` attempts to perform write operations using the read-only session wrapper, which will fail at runtime.

**Location**: `llm_pipeline/pipeline.py`, lines 560-574

**Details**:
```python
def clear_cache(self) -> int:
    from llm_pipeline.state import PipelineStepState
    from sqlmodel import select

    states = self.session.exec(
        select(PipelineStepState).where(
            PipelineStepState.run_id == self.run_id
        )
    ).all()
    count = len(states)
    for state in states:
        self.session.delete(state)  # ❌ Fails - self.session is ReadOnlySession
    self.session.commit()           # ❌ Fails - self.session is ReadOnlySession
    logger.info(f"[OK] Cleared {count} cached step(s) for run {self.run_id}")
    return count
```

The problem is that `self.session` is a `ReadOnlySession` wrapper that explicitly blocks all write operations (`delete()`, `commit()`, etc.) to prevent accidental database modifications during step execution. When `clear_cache()` attempts to delete and commit, it raises a `RuntimeError`:

```
RuntimeError: Cannot delete from database during step execution.
Database writes are only allowed in pipeline.save().
```

**Impact**:
- This bug is rarely encountered in practice because `clear_cache()` is seldom called
- The framework defaults to `use_cache=False` in pipeline execution
- When caching is disabled, there are no cached states to clear

**Workaround**:
Currently, there is no safe workaround for calling `clear_cache()` during pipeline execution. Users who need to clear cache should:
1. Avoid calling `clear_cache()` during step execution
2. Clear cache before or after pipeline execution using direct database access
3. Manually delete `PipelineStepState` records using a regular session

**Proper Solution** (requires code fix):
```python
def clear_cache(self) -> int:
    from llm_pipeline.state import PipelineStepState
    from sqlmodel import select

    # Use _real_session instead of self.session
    states = self._real_session.exec(
        select(PipelineStepState).where(
            PipelineStepState.run_id == self.run_id
        )
    ).all()
    count = len(states)
    for state in states:
        self._real_session.delete(state)
    self._real_session.commit()
    logger.info(f"[OK] Cleared {count} cached step(s) for run {self.run_id}")
    return count
```

## Prompt System Limitations

### Vestigial Context Filtering in get_prompt()

**Issue**: The `PromptService.get_prompt()` method includes a `context` parameter intended to filter prompts by context, but the underlying `Prompt` model does not have a `context` field.

**Location**: `llm_pipeline/prompts/service.py`, lines 16-41

**Details**:
```python
def get_prompt(
    self,
    prompt_key: str,
    prompt_type: str = 'system',
    context: Optional[dict] = None,  # ❌ Parameter exists
    fallback: Optional[str] = None
) -> str:
    """Get a prompt by key and type, optionally filtered by context."""
    stmt = select(Prompt).where(
        Prompt.prompt_key == prompt_key,
        Prompt.prompt_type == prompt_type,
        Prompt.is_active == True
    )

    if context:
        # ❌ This would fail - Prompt.context field does not exist
        context_match = self.session.exec(
            stmt.where(Prompt.context.contains(context))
        ).first()
        if context_match:
            return context_match.content

    # ✅ This fallback path works
    base_prompt = self.session.exec(stmt).first()
    if base_prompt:
        return base_prompt.content
```

The `Prompt` model (in `llm_pipeline/db/prompt.py`) has no `context` field. Evidence suggests this field existed in an earlier version but was removed, leaving orphaned code in the service layer.

**Impact**:
- If `get_prompt()` is called with a non-None `context` parameter, it will fail with an `AttributeError`
- The `get_guidance()` method also calls `get_prompt()` with a context parameter, making it potentially broken for context-filtered queries
- However, both methods work correctly when `context` is `None` (the common case)

**Affected Methods**:
- `PromptService.get_prompt(context=...)`
- `PromptService.get_guidance()` (internally passes context)

**Workaround**:
Always call `get_prompt()` without the `context` parameter:

```python
# ❌ Will fail
prompt = prompt_service.get_prompt("my_prompt", "system", context={"foo": "bar"})

# ✅ Works correctly
prompt = prompt_service.get_prompt("my_prompt", "system")
```

For `get_guidance()`, it works only when the fallback path is used (no context match needed):

```python
# Works if guidance prompt has no context requirements
guidance = prompt_service.get_guidance("step_name")
```

**Proper Solution** (requires code fix):
Either remove the `context` parameter from both methods, or add a `context` field to the `Prompt` model with proper JSON column support.

## Inheritance and Naming Validation

### Single-Level Inheritance Requirement

**Issue**: The naming validation in `@step_definition` and related decorators only checks the immediate parent class, not the full inheritance chain.

**Location**: Naming validation throughout `llm_pipeline/step.py`

**Details**:
The framework enforces naming conventions at class definition time using `__init_subclass__`:
- Pipeline classes must end with "Pipeline"
- Registry classes must match pipeline name + "Registry"
- Strategy classes must match pipeline name + "Strategies"

However, this validation only examines the direct parent class. Multi-level inheritance can bypass validation:

```python
# ❌ This would bypass validation
class BasePipeline(PipelineConfig):
    """Intermediate abstract base - validation skipped"""
    pass

class MyConcretePipeline(BasePipeline):
    """Validation only checks BasePipeline, not PipelineConfig"""
    # Missing "Pipeline" suffix might not be caught
    pass
```

**Design Intent**:
By design, all concrete pipeline/strategy/extraction classes in the framework directly subclass their base (no multi-level inheritance). The validation is sufficient for the intended usage pattern.

**Escape Hatch**:
Intermediate abstract classes can use underscore prefix to bypass validation:

```python
class _BaseExtraction(PipelineExtraction):
    """Underscore prefix signals: intermediate abstract class"""
    pass

class LaneExtraction(_BaseExtraction):
    """Concrete class - validation applies"""
    pass
```

**Workaround**:
For projects that need multi-level inheritance:
1. Use underscore prefix (`_BaseName`) for all intermediate abstract classes
2. Ensure all concrete classes directly subclass the framework base
3. Manually verify naming conventions for concrete classes

**Impact**: Low - standard usage patterns do not involve multi-level inheritance

## Provider Limitations

### Gemini-Only LLM Provider

**Issue**: The framework currently ships with only one `LLMProvider` implementation: `GeminiProvider`.

**Details**:
- The `LLMProvider` abstract base class is designed to support multiple providers (OpenAI, Anthropic, etc.)
- Currently, only Google's Gemini models are implemented
- Users requiring other LLM providers must implement custom providers

**Creating Custom Providers**:
Extend the `LLMProvider` abstract class and implement the `call_structured()` method:

```python
from llm_pipeline.llm.provider import LLMProvider
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel

class OpenAIProvider(LLMProvider):
    """Custom OpenAI provider implementation."""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model

    def call_structured(
        self,
        prompt: str,
        system_instructions: str,
        result_class: Type[BaseModel],
        retries: int = 3,
        rate_limiter: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Call OpenAI API with structured output."""
        # Implementation details:
        # 1. Format schema from result_class using Pydantic
        # 2. Make API call to OpenAI
        # 3. Parse and validate response
        # 4. Return dict matching result_class schema
        pass
```

Then use the custom provider in your pipeline:

```python
from your_module import OpenAIProvider

provider = OpenAIProvider(api_key="sk-...", model="gpt-4")
pipeline = YourPipeline(provider=provider)
```

**Impact**:
- Low for Gemini users
- Medium for users requiring alternative LLM providers
- Requires custom implementation work for non-Gemini deployments

## Deprecated Features

### save_step_yaml() Function

**Status**: Legacy/Dead Code

**Location**: `llm_pipeline/llm/executor.py`, lines 127-137

**Details**:
This function is a remnant from the pre-Strategy architecture. It was used by the old `execute_pipeline()` function but is never called by the current `PipelineConfig.execute()` implementation.

**Impact**: None - safely ignore this function

**Recommendation**: Do not use `save_step_yaml()` in new code. It may be removed in future versions.

## Summary of Limitations

| Limitation | Severity | Workaround Available |
|-----------|----------|---------------------|
| `clear_cache()` ReadOnlySession bug | Medium | Avoid calling during execution |
| `get_prompt()` context filtering broken | Medium | Don't use context parameter |
| Single-level inheritance requirement | Low | Use underscore prefix for intermediate classes |
| Gemini-only provider | Medium | Implement custom provider |
| `save_step_yaml()` deprecated | None | Don't use |

## Future Improvements

Potential fixes for these limitations (not currently planned):

1. **Fix clear_cache()**: Use `_real_session` instead of `session` for write operations
2. **Fix context filtering**: Either remove `context` parameter or add `context` field to `Prompt` model
3. **Enhance inheritance validation**: Check full inheritance chain, not just immediate parent
4. **Add more providers**: Implement OpenAI, Anthropic, Mistral, etc. providers
5. **Remove deprecated code**: Clean up `save_step_yaml()` and other legacy functions

## Reporting Issues

If you encounter a limitation not documented here, please:
1. Check the GitHub issue tracker for existing reports
2. Create a new issue with reproduction steps
3. Include error messages and stack traces
4. Specify your environment (Python version, dependencies, etc.)

Contributions to address these limitations are welcome via pull requests.
