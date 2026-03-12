# IMPLEMENTATION - STEP 9: UPDATE PIPELINECONFIG
**Status:** completed

## Summary
Added optional `agent_registry=` class parameter to `PipelineConfig.__init_subclass__` with `{Prefix}AgentRegistry` naming validation, matching existing registry/strategies pattern.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Added TYPE_CHECKING import for AgentRegistry, AGENT_REGISTRY ClassVar, and agent_registry= param to __init_subclass__ with naming validation.

```
# Before (TYPE_CHECKING block)
if TYPE_CHECKING:
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
    from llm_pipeline.registry import PipelineDatabaseRegistry
    from llm_pipeline.state import PipelineStepState

# After
if TYPE_CHECKING:
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
    from llm_pipeline.registry import PipelineDatabaseRegistry
    from llm_pipeline.agent_registry import AgentRegistry
    from llm_pipeline.state import PipelineStepState
```

```
# Before (ClassVars)
REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None
INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None

# After
REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None
AGENT_REGISTRY: ClassVar[Optional[Type["AgentRegistry"]]] = None
INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None
```

```
# Before (__init_subclass__ signature)
def __init_subclass__(cls, registry=None, strategies=None, **kwargs):

# After
def __init_subclass__(cls, registry=None, strategies=None, agent_registry=None, **kwargs):
```

```
# Added (naming validation inside pipeline suffix guard)
if agent_registry is not None:
    expected = f"{pipeline_name_prefix}AgentRegistry"
    if agent_registry.__name__ != expected:
        raise ValueError(
            f"AgentRegistry for {cls.__name__} must be named '{expected}', "
            f"got '{agent_registry.__name__}'"
        )

# Added (assignment after validation block)
if agent_registry is not None:
    cls.AGENT_REGISTRY = agent_registry
```

## Decisions
### Guard condition expansion
**Choice:** Extended existing `if registry is not None or strategies is not None` to also include `or agent_registry is not None`
**Rationale:** agent_registry requires same Pipeline suffix check and pipeline_name_prefix derivation as registry/strategies; reusing the same guard block keeps validation logic unified

### AGENT_REGISTRY placement
**Choice:** Placed between STRATEGIES and INPUT_DATA ClassVars
**Rationale:** Groups all registry-like ClassVars together (REGISTRY, STRATEGIES, AGENT_REGISTRY) before data-related ones (INPUT_DATA)

## Verification
[x] TYPE_CHECKING import added for AgentRegistry
[x] AGENT_REGISTRY ClassVar defaults to None (backward compatible)
[x] __init_subclass__ accepts agent_registry= param defaulting to None
[x] Naming validation uses {Prefix}AgentRegistry pattern
[x] Validation only runs inside Pipeline suffix guard
[x] cls.AGENT_REGISTRY assigned when agent_registry is not None
[x] All existing tests pass (1 pre-existing UI test failure unrelated)
[x] Existing pipelines without agent_registry= param unaffected
