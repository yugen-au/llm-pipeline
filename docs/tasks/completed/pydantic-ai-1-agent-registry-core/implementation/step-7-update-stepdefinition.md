# IMPLEMENTATION - STEP 7: UPDATE STEPDEFINITION
**Status:** completed

## Summary
Added `agent_name` field, `step_name` property, and `_agent_name` propagation to StepDefinition in strategy.py.

## Files
**Created:** none
**Modified:** llm_pipeline/strategy.py
**Deleted:** none

## Changes
### File: `llm_pipeline/strategy.py`
Added `agent_name: str | None = None` field after `context`, `step_name` property using `to_snake_case`, and `step._agent_name = self.agent_name` in `create_step()`.

```
# Before
    context: Optional[Type] = None  # Type is PipelineContext but avoid circular import

    def create_step(self, pipeline: 'PipelineConfig'):
        ...
        step._extractions = self.extractions
        step._transformation = self.transformation
        step._context = self.context
        return step

# After
    context: Optional[Type] = None  # Type is PipelineContext but avoid circular import
    agent_name: str | None = None

    @property
    def step_name(self) -> str:
        """Derived snake_case name from step_class (e.g. ConstraintExtractionStep -> 'constraint_extraction')."""
        return to_snake_case(self.step_class.__name__, strip_suffix='Step')

    def create_step(self, pipeline: 'PipelineConfig'):
        ...
        step._extractions = self.extractions
        step._transformation = self.transformation
        step._context = self.context
        step._agent_name = self.agent_name
        return step
```

## Decisions
None

## Verification
[x] agent_name defaults to None
[x] agent_name accepts string override
[x] step_name returns correct snake_case (ConstraintExtractionStep -> constraint_extraction)
[x] step_name handles consecutive capitals (HTMLParserStep -> html_parser)
[x] create_step() sets step._agent_name from self.agent_name
[x] All existing tests pass (583 passed, 1 pre-existing UI failure unrelated)

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] `test_create_step_sets_agent_name_on_instance` creates in-memory SQLite engine/Session but never closes them, producing `ResourceWarning: unclosed database`

### Changes Made
#### File: `tests/test_agent_registry_core.py`
Added `session.close()` and `engine.dispose()` at end of test to prevent resource leak.

```
# Before
        step = sd.create_step(fake_pipeline)
        assert step._agent_name == "override_name"

# After
        step = sd.create_step(fake_pipeline)
        assert step._agent_name == "override_name"

        session.close()
        engine.dispose()
```

### Verification
[x] Test passes with `-W error::ResourceWarning` (no unclosed database warning)
[x] No regressions in test suite
