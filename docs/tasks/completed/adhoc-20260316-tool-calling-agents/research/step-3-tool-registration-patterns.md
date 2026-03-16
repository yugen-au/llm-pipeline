# Step 3: Tool Registration Patterns for build_step_agent()

## Summary

Constructor-based registration is the recommended pattern. Add `tools: Sequence[Any] | None = None` to `build_step_agent()`, conditionally insert into `agent_kwargs`. ~5 lines changed. Fully backward compatible.

---

## Patterns Evaluated

### Option A: Constructor Registration (RECOMMENDED)

Pass tools directly to `Agent()` via the `tools` kwarg.

```python
def build_step_agent(
    step_name: str,
    output_type: type,
    ...,
    tools: Sequence[Any] | None = None,  # new
) -> Agent[StepDeps, Any]:
    agent_kwargs: dict[str, Any] = dict(
        model=model,
        output_type=output_type,
        deps_type=StepDeps,
        ...
    )
    if tools:
        agent_kwargs["tools"] = tools
    ...
    agent: Agent[StepDeps, Any] = Agent(**agent_kwargs)
```

**Why this wins:**
- pydantic-ai `Agent.__init__` natively accepts `tools: Sequence[Tool[AgentDepsT] | ToolFuncEither[AgentDepsT, ...]]`
- Auto-infers `takes_ctx` from function signature (detects `RunContext` first param)
- Callers can pass plain functions OR `Tool()` wrappers for fine-grained control
- Single construction call; no post-construction mutation needed
- Matches how `instrument` is already conditionally added to `agent_kwargs`

### Option B: Post-Construction Registration

```python
agent = Agent(**agent_kwargs)
for t in (tools or []):
    agent.tool(t)  # or agent.tool_plain(t)
```

**Rejected because:**
- Requires detecting whether each function takes `RunContext` to choose `.tool()` vs `.tool_plain()`
- The constructor already handles this detection automatically
- More verbose for no benefit
- Note: validators use post-construction (`agent.output_validator(v)`) because `output_validator` is NOT a constructor param. `tools` IS a constructor param.

### Option C: Hybrid (Constructor + Post-Construction)

**Rejected:** Unnecessary complexity. No use case requires mixing both patterns for this builder.

---

## Type Signature Decision

### Recommended: `Sequence[Any] | None = None`

Matches existing pattern -- `validators: list[Any] | None = None` and `model_settings: Any | None = None` both use `Any` to avoid runtime pydantic-ai imports.

### Alternative: More Specific Typing

```python
# Under TYPE_CHECKING only:
from pydantic_ai import Tool
from collections.abc import Sequence, Callable

tools: Sequence[Tool[StepDeps] | Callable[..., Any]] | None = None
```

Not recommended: breaks the established pattern, adds import complexity, and `Any` is sufficient since pydantic-ai validates at runtime anyway.

---

## What Callers Pass

Tool functions follow two signatures:

```python
# Plain tool (no context)
def get_current_date() -> str:
    """Return today's date."""
    return str(date.today())

# Context-aware tool (accesses StepDeps)
def read_cell(ctx: RunContext[StepDeps], sheet: str, cell: str) -> str:
    """Read a cell value from the workbook."""
    wb = ctx.deps.extra["workbook_context"]
    return wb.read(sheet, cell)
```

Both are passed as a flat list: `tools=[get_current_date, read_cell]`

---

## Impact on Existing Callers

### pipeline.py (line 745) -- Only Call Site

```python
# Current:
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
    validators=step_validators,
    instrument=self._instrumentation_settings,
)

# After: UNCHANGED (tools defaults to None, no tools key added to agent_kwargs)
```

Zero impact. `tools=None` means the `if tools:` guard skips adding it to `agent_kwargs`. Agent constructed identically to today.

### __init__.py Export

`build_step_agent` already exported. No changes needed.

---

## StepDeps.extra (Related but Separate)

GAP_TOOL_CALLING_AGENTS.md proposes adding `extra: dict[str, Any]` to `StepDeps` for domain-specific deps that tools access via `ctx.deps.extra["key"]`. This is orthogonal to the tool registration pattern but needed for tools to access domain data at runtime.

```python
@dataclass
class StepDeps:
    ...
    extra: dict[str, Any] = field(default_factory=dict)  # new
```

- Backward compatible (default empty dict)
- Pipeline executor populates from prepare_calls() params or pipeline context
- Tools read via `ctx.deps.extra["workbook_context"]` etc.

---

## Exact Change Estimate

### agent_builders.py (~6 lines)

1. Add `from collections.abc import Sequence` to imports (line 10 area)
2. Add `tools: Sequence[Any] | None = None,` parameter (after `validators`)
3. Add docstring line for `tools` param
4. Add `if tools: agent_kwargs["tools"] = tools` (after instrument block)
5. Add `extra: dict[str, Any] = field(default_factory=dict)` to StepDeps

### No changes needed in:
- `pipeline.py` (existing caller unchanged)
- `step.py` (no tool awareness needed)
- `__init__.py` (already exports both symbols)
- `agent_registry.py` (output types only)

---

## Verification: pydantic-ai Constructor Signature (v1.0.5+)

From Context7 docs, the relevant Agent.__init__ param:

```python
tools: Sequence[
    Tool[AgentDepsT] | ToolFuncEither[AgentDepsT, ...]
] = (),
```

Default is empty tuple `()`. Our builder omits the key entirely when no tools (same effect). When tools provided, pydantic-ai handles type validation and `takes_ctx` inference internally.
