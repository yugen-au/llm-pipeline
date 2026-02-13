# IMPLEMENTATION - STEP 1: MODIFY PIPELINECONFIG
**Status:** completed

## Summary
Added optional `event_emitter` parameter to `PipelineConfig.__init__()` with zero-overhead `_emit()` helper method. Follows existing DI pattern (provider, variable_resolver). Fully backwards-compatible -- all 71 existing tests pass.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

**1. TYPE_CHECKING imports (lines 41-42):** Added imports for `PipelineEventEmitter` and `PipelineEvent` under existing TYPE_CHECKING guard.
```
# Before
if TYPE_CHECKING:
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
    from llm_pipeline.registry import PipelineDatabaseRegistry
    from llm_pipeline.state import PipelineStepState
    from llm_pipeline.llm.provider import LLMProvider
    from llm_pipeline.prompts.variables import VariableResolver

# After
if TYPE_CHECKING:
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
    from llm_pipeline.registry import PipelineDatabaseRegistry
    from llm_pipeline.state import PipelineStepState
    from llm_pipeline.llm.provider import LLMProvider
    from llm_pipeline.prompts.variables import VariableResolver
    from llm_pipeline.events.emitter import PipelineEventEmitter
    from llm_pipeline.events.types import PipelineEvent
```

**2. __init__ signature (line 136):** Added `event_emitter` as last parameter with `None` default.
```
# Before
        variable_resolver: Optional["VariableResolver"] = None,
    ):

# After
        variable_resolver: Optional["VariableResolver"] = None,
        event_emitter: Optional["PipelineEventEmitter"] = None,
    ):
```

**3. __init__ docstring (line 147):** Added event_emitter description to Args section.

**4. Attribute storage (line 154):** Added `self._event_emitter = event_emitter` after `self._variable_resolver`.

**5. _emit() method (lines 206-213):** Added zero-overhead helper between __init__ and @property methods.
```
# After (new method)
    def _emit(self, event: "PipelineEvent") -> None:
        """Forward event to emitter if configured.

        Args:
            event: PipelineEvent instance to emit.
        """
        if self._event_emitter is not None:
            self._event_emitter.emit(event)
```

## Decisions
None -- all decisions were pre-made in PLAN.md and followed exactly.

## Verification
[x] TYPE_CHECKING imports match existing pattern (specific submodule imports)
[x] Parameter placed last in __init__ signature after variable_resolver
[x] String annotations used for forward references ("PipelineEventEmitter", "PipelineEvent")
[x] self._event_emitter stored after self._variable_resolver
[x] _emit() placed after __init__, before @property methods
[x] _emit() contains None guard for zero-overhead when disabled
[x] All 71 existing tests pass (backwards compatibility confirmed)
[x] No circular import errors (TYPE_CHECKING guard prevents runtime import)
