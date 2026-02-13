# PLANNING

## Summary
Add optional `event_emitter` parameter to `PipelineConfig.__init__()` with zero-overhead `_emit()` helper. Stores emitter in `self._event_emitter` attribute following existing DI pattern. When `None`, `_emit()` no-ops with single if-check. Fully backwards-compatible (all existing callers use keyword args).

## Plugin & Agents
**Plugin:** python-development
**Subagents:** python-developer
**Skills:** none

## Phases
1. Implementation - Add parameter, attribute, helper method to pipeline.py
2. Testing - Unit tests for parameter, attribute, and _emit() behavior

## Architecture Decisions

### _emit() Redundant None Check
**Choice:** _emit() contains `if self._event_emitter is not None` check even though call sites will also guard with `if self._event_emitter:`
**Rationale:** Centralizes forwarding for future interception/instrumentation hooks, safety net for call sites that forget guard. Dual-layer pattern documented in VALIDATED_RESEARCH.md. Performance: single attribute lookup + identity comparison (~50ns overhead when None).
**Alternatives:** No _emit() helper (inline emit() calls at every site) - rejected due to no central hook point for future needs.

### Call-Site Gating Convention Docs Location
**Choice:** Defer call-site gating convention (`if self._event_emitter:` before event construction) documentation to Task 8
**Rationale:** Task 7 only adds plumbing (_emit helper + param). Task 8 introduces actual usage pattern in execute() where convention becomes visible. Documenting convention where it's first used improves discoverability.
**Alternatives:** Document in Task 7 _emit() docstring - rejected per VALIDATED_RESEARCH.md Q&A (convention docs belong with usage, not helper).

### TYPE_CHECKING Import Pattern
**Choice:** Import `PipelineEventEmitter` and `PipelineEvent` from specific submodules (`events.emitter`, `events.types`) under TYPE_CHECKING guard
**Rationale:** Matches existing pattern at lines 35-40 in pipeline.py. String annotations prevent circular imports. Specific submodule imports avoid unnecessary package __init__.py loading.
**Alternatives:** Import from events/__init__.py - rejected, not the established codebase convention.

### Parameter Placement
**Choice:** Add `event_emitter: Optional["PipelineEventEmitter"] = None` as last parameter in __init__ signature after `variable_resolver`
**Rationale:** All 8 instantiation sites in tests/test_pipeline.py use keyword arguments exclusively (verified). No positional argument usage anywhere. Adding at end maintains backwards compatibility.
**Alternatives:** Insert before variable_resolver - rejected, unnecessary disruption to parameter order.

## Implementation Steps

### Step 1: Modify PipelineConfig in pipeline.py
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add TYPE_CHECKING imports after line 40:
   - `from llm_pipeline.events.emitter import PipelineEventEmitter`
   - `from llm_pipeline.events.types import PipelineEvent`
2. Add parameter to __init__ signature (after variable_resolver at line 132): `event_emitter: Optional["PipelineEventEmitter"] = None`
3. Update __init__ docstring Args section: add `event_emitter: Optional PipelineEventEmitter for lifecycle/LLM/extraction events. None disables events.`
4. Store attribute after line 149 (after self._variable_resolver): `self._event_emitter = event_emitter`
5. Add _emit() method after __init__ (before @property methods around line 155):
```python
def _emit(self, event: "PipelineEvent") -> None:
    """Forward event to emitter if configured.

    Args:
        event: PipelineEvent instance to emit.
    """
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

### Step 2: Add unit tests to tests/test_pipeline.py
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** /pytest/latest
**Group:** B

1. Add import at top: `from llm_pipeline.events import PipelineEventEmitter, PipelineEvent`
2. Create mock emitter class with captured events list and emit() method
3. Test case: instantiate PipelineConfig subclass without event_emitter, verify self._event_emitter is None
4. Test case: instantiate PipelineConfig subclass with mock emitter, verify self._event_emitter is mock instance
5. Test case: call _emit() when event_emitter is None, verify no error
6. Test case: call _emit() with mock emitter, verify mock's emit() received event
7. Test case: verify mock emitter satisfies PipelineEventEmitter protocol at runtime (isinstance check with @runtime_checkable)

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Circular import when importing PipelineEventEmitter/PipelineEvent | High | Use TYPE_CHECKING guard + string annotations (existing pattern in codebase) |
| Breaking change to existing PipelineConfig instantiation | High | Add parameter at end with None default; all call sites use keyword args (verified in research) |
| _emit() overhead when event_emitter is None | Low | Single if-check with attribute lookup (~50ns); no event construction at call site when guarded |
| Type checker errors with Optional["PipelineEventEmitter"] | Medium | Follow existing Optional["LLMProvider"] pattern at line 131; string annotation defers resolution |

## Success Criteria
- [ ] PipelineConfig.__init__ accepts optional event_emitter parameter
- [ ] self._event_emitter attribute stores emitter or None
- [ ] _emit() method forwards event to emitter when not None
- [ ] _emit() no-ops when event_emitter is None (no exception)
- [ ] All existing tests pass (backward compatibility verified)
- [ ] New tests cover instantiation with/without emitter, _emit forwarding, _emit no-op
- [ ] Type checking passes (mypy/pyright)
- [ ] No circular import errors

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Single file change with well-defined scope. No complex logic. Pattern matches existing DI approach (provider, variable_resolver). All call sites use keyword args. TYPE_CHECKING guard eliminates circular import risk. Task 2 (upstream dependency) completed with zero deviations.
**Suggested Exclusions:** testing, review
