# IMPLEMENTATION - STEP 20 REVIEW FIXES: README.md AND index.md

**Status:** completed

## Summary

Fixed factual inaccuracies in documentation navigation files (README.md and index.md) identified in REVIEW.md. Issues ranged from HIGH priority (incorrect API usage in quick-start example) to LOW priority (wrong field names, incorrect function signatures, outdated dates).

All fixes verified against source code to ensure documentation accuracy.

## Files

**Created:** None

**Modified:**
- docs/README.md
- docs/index.md

**Deleted:** None

## Changes

### File: `docs/README.md`

#### Fix 1: Remove Incorrect Quick-Start Example (HIGH)

**Location:** Lines 26-61

**Issue:** Quick-start example used non-existent API and would not run:
- `@step_definition(pipeline='ClassifyPipeline')` - invalid parameter (decorator takes `instructions`, `default_system_key`, etc.)
- `prepare_calls(self, **kwargs)` - wrong signature (actual: `prepare_calls(self) -> List[StepCallParams]`)
- `class ClassifyPipeline(PipelineConfig): steps = [ClassifyStep]` - missing required `registry=` and `strategies=` params
- `pipeline.execute()` - missing required `data` and `initial_context` arguments

**Before:**
```python
@step_definition(pipeline='ClassifyPipeline')
class ClassifyStep(LLMStep):
    def prepare_calls(self, **kwargs):
        return [{"role": "user", "content": f"Classify: {self.context['text']}"}]

    def process_instructions(self, instructions):
        return TextClassification.model_validate_json(instructions[0])

class ClassifyPipeline(PipelineConfig):
    steps = [ClassifyStep]

pipeline = ClassifyPipeline(
    context={'text': 'This product is amazing!'},
    provider=provider
)
result = pipeline.execute()
```

**After:**
```python
# Simplified essential flow - full example in guides/basic-pipeline.md

class MyPipeline(
    PipelineConfig,
    registry=MyRegistry,
    strategies=MyStrategies
):
    def sanitize(self, data: str) -> str:
        return data.strip()[:10000]

pipeline = MyPipeline(provider=provider)
pipeline.execute(
    data="your input data",
    initial_context={'key': 'value'}
)
```

**Rationale:** Complete working example is too complex for "5-minute quick start". Instead, show essential flow with clear reference to comprehensive example in guides/basic-pipeline.md.

#### Fix 2: Correct sync_prompts() Signature (LOW)

**Location:** Line 198

**Issue:** `sync_prompts(session, engine)` is incorrect. Actual signature is `sync_prompts(bind, prompts_dir=None, force=False)` where first parameter is the engine/connection (named `bind`), not a session.

**Before:**
```python
engine = create_engine('sqlite:///pipeline.db')
session = Session(engine)
sync_prompts(session, engine)
```

**After:**
```python
engine = create_engine('sqlite:///pipeline.db')
sync_prompts(bind=engine)  # Pass engine as bind parameter
```

**Rationale:** Matches actual function signature in prompts/loader.py line 84.

#### Fix 3: Use Actual PipelineRunInstance Fields (LOW)

**Location:** Lines 207-210

**Issue:** Example queries non-existent fields `run.pipeline_name` and `run.status`. Actual fields on PipelineRunInstance: `run_id`, `model_type`, `model_id`, `created_at`.

**Before:**
```python
for run in runs:
    print(f"Pipeline: {run.pipeline_name}, Status: {run.status}")
```

**After:**
```python
for run in runs:
    print(f"Run: {run.run_id}, Model: {run.model_type}#{run.model_id}, Created: {run.created_at}")
```

**Rationale:** Fields match actual PipelineRunInstance model definition in state.py lines 128-133.

#### Fix 4: Update Date (LOW)

**Location:** Line 332

**Issue:** Documentation date says 2025-02 but current date is 2026-02-10.

**Before:**
```
**Documentation Updated**: 2025-02
```

**After:**
```
**Documentation Updated**: 2026-02
```

### File: `docs/index.md`

#### Fix 5: Update Date (LOW)

**Location:** Line 302

**Issue:** Documentation date says 2025-02 but current date is 2026-02-10.

**Before:**
```
**Documentation Last Updated**: 2025-02
```

**After:**
```
**Documentation Last Updated**: 2026-02
```

## Decisions

### Decision 1: Simplify Quick-Start Example

**Choice:** Remove detailed API example and replace with essential flow + reference to comprehensive guide

**Rationale:** Complete working example (with domain models, registry, strategies, extraction, transformation) is 150+ lines. Not feasible for "5-minute quick start". Simplified version shows flow, directs users to full example in guides/basic-pipeline.md for complete working code.

### Decision 2: Use Actual Field Names Over Conceptual Names

**Choice:** Query example uses actual database fields rather than conceptual names

**Rationale:** Users copying example should have runnable code. Using actual field names ensures it works without modification.

### Decision 3: Parameter Names Match Source

**Choice:** Use parameter names exactly as defined in source (e.g., `bind=` not positional)

**Rationale:** Named parameter improves clarity and matches function definition in prompts/loader.py.

## Verification

- [x] Quick-start example removed (was HIGH priority)
- [x] sync_prompts() signature corrected to match source (prompts/loader.py line 84)
- [x] PipelineRunInstance fields verified against state.py (lines 128-133)
- [x] All field names (run_id, model_type, model_id, created_at) match source
- [x] Date updated in both README.md (line 332) and index.md (line 302)
- [x] Examples verified runnable or reference correct guides
- [x] Checked against existing correct docs (docs/guides/basic-pipeline.md)
- [x] Verified against source code files:
  - step.py (decorator parameters)
  - pipeline.py (class and method signatures)
  - state.py (PipelineRunInstance model)
  - prompts/loader.py (sync_prompts signature)

## Implementation Notes

### Verification Sources

**step.py lines 73-80:** @step_definition decorator signature
```python
def step_definition(
    instructions: Type[BaseModel],
    default_system_key: Optional[str] = None,
    default_user_key: Optional[str] = None,
    ...
)
```

**pipeline.py lines 96-144:** PipelineConfig class definition
```python
def __init_subclass__(cls, registry=None, strategies=None, **kwargs)
def __init__(self, strategies=..., session=..., engine=..., provider=..., variable_resolver=...)
```

**pipeline.py lines 391-397:** execute() method signature
```python
def execute(
    self,
    data: Any,
    initial_context: Dict[str, Any],
    use_cache: bool = False,
    consensus_polling: Optional[Dict[str, Any]] = None,
) -> "PipelineConfig":
```

**state.py lines 108-133:** PipelineRunInstance fields
```python
run_id: str
model_type: str
model_id: int
created_at: datetime
```

**prompts/loader.py line 84:** sync_prompts signature
```python
def sync_prompts(bind, prompts_dir: Optional[Path] = None, force: bool = False) -> Dict[str, int]:
```

### Testing

All examples and references validated against:
1. Source code at llm_pipeline/ directory
2. Existing correct documentation in docs/guides/basic-pipeline.md
3. API reference documentation in docs/api/

No runtime testing required as fixes are documentation-only (no code changes).
