# IMPLEMENTATION - STEP 2: APPLY_INSTRUCTION_DELTA() UTILITY
**Status:** completed

## Summary
Implemented `apply_instruction_delta(base_cls, instructions_delta) -> type` as pure function in new `llm_pipeline/evals/delta.py`. Builds a new pydantic subclass from `LLMResultMixin` (or subclass) + JSON delta via `pydantic.create_model(__base__=...)`. Hard-coded type whitelist, identifier+dunder regex, JSON-only defaults, length caps. Exported via `llm_pipeline/evals/__init__.py`. 55 unit tests in `TestApplyInstructionDelta` class appended to `tests/test_eval_variants.py`; all pass. Pydantic-ai Agent compatibility verified with `TestModel` stub.

## Files
**Created:** `llm_pipeline/evals/delta.py`
**Modified:** `llm_pipeline/evals/__init__.py`, `tests/test_eval_variants.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/evals/delta.py`
New module. Exports `apply_instruction_delta`. Module-level constants: `_TYPE_WHITELIST` (dict), `_FIELD_NAME_RE`, `_DUNDER_RE`, `_MAX_DELTA_ITEMS=50`, `_MAX_STRING_LEN=1000`, `_ALLOWED_OPS={"add","modify"}`, `_SCALAR_TYPES`. Private helpers `_resolve_type`, `_validate_default`, `_validate_field_name`. No eval/exec/importlib.

### File: `llm_pipeline/evals/__init__.py`
Was empty. Now exposes `apply_instruction_delta` as public API.
```
# After
from llm_pipeline.evals.delta import apply_instruction_delta
__all__ = ["apply_instruction_delta"]
```

### File: `tests/test_eval_variants.py`
Appended `_DemoInstructions(LLMResultMixin)` fixture class and `TestApplyInstructionDelta` class with 55 tests covering: add/modify/optional fields, empty delta passthrough, op/type/field/default rejection paths, size caps (50 items, 1000 chars), create_failure inheritance, pydantic-ai Agent construction with TestModel. Added `from typing import ClassVar` and pydantic imports.

## Decisions
### Dunder field rejection
**Choice:** Added `_DUNDER_RE = re.compile(r"^__.*__$")` alongside `_FIELD_NAME_RE` and reject dunders in `_validate_field_name`.
**Rationale:** Plan calls out `field="__class__"` as required security test. The base identifier regex `^[a-z_][a-z0-9_]*$` actually matches dunders (leading underscore, lowercase). Without the dunder check `__class__` / `__init__` / `__dict__` pass the regex but then either collide with pydantic's protocol slots or with Python internals. Separate regex makes the rejection explicit in the error message and keeps the base regex simple.

### Required default on add/modify
**Choice:** Both `op="add"` and `op="modify"` require an explicit `default` key in the delta item. Missing default → ValueError.
**Rationale:** Pydantic's `create_model` API encodes required-no-default as `Ellipsis`, which is not JSON-serialisable and therefore can't survive the delta/delta_snapshot round-trip. Forcing a default keeps delta storage invariant ("JSON only") and prevents the pydantic-ai output validator from demanding LLM-supplied values that a variant author didn't anticipate.

### `modify` without `type_str` inherits annotation
**Choice:** If `op="modify"` and no `type_str` is provided, the existing field's annotation is copied from `base_cls.model_fields[field].annotation`.
**Rationale:** Lets variants change just the default without re-declaring the type. Still enforces whitelist when `type_str` IS supplied. Unknown field + no `type_str` → ValueError.

### Empty-delta passthrough
**Choice:** Return `base_cls` unchanged when delta is empty or None.
**Rationale:** Avoids the overhead (and downstream subclass-identity churn) of creating an empty `VariantInstructions` wrapper when nothing changes. Callers can rely on `result is base_cls` for the no-op case.

### Test class co-location
**Choice:** Appended `TestApplyInstructionDelta` to the existing `tests/test_eval_variants.py` created by Step 1.
**Rationale:** Contract instruction + plan both specify the same test file. Used a distinct test class to avoid any naming collision with Step 1's `TestFreshDbCreation` / `TestMigrationOnExistingDb`.

## Verification
- [x] `uv run pytest tests/test_eval_variants.py::TestApplyInstructionDelta -v` → 55/55 pass
- [x] `uv run pytest tests/test_eval_variants.py -v` → 64/64 pass (9 from Step 1 + 55 from Step 2)
- [x] Full suite `uv run pytest --tb=no -q` → same 15 pre-existing failures as before this step; confirmed via `git stash` + rerun. No new regressions attributable to Step 2.
- [x] Security test cases present: `type_str="__import__('os').system('ls')"` → ValueError; `field="__class__"` → ValueError; `field="items.append"` → ValueError; `op="eval"` → ValueError; `default=lambda: 1` → ValueError; `instructions_delta` length 51 → ValueError; `type_str` of 1001 chars → ValueError.
- [x] `create_failure()` preservation test passes on delta-modified subclass.
- [x] Pydantic-ai compatibility test passes — `pydantic_ai.Agent(TestModel(), output_type=cls)` constructs successfully with a delta-modified `VariantInstructions` class.
- [x] No eval/exec/importlib/get_type_hints in `delta.py` (grep-verified during authoring).
- [x] `apply_instruction_delta` is pure — no I/O, no session, no global mutation.
- [x] Did not touch `pipeline.py`, `runner.py`, or any Step 3+ integration surface.
