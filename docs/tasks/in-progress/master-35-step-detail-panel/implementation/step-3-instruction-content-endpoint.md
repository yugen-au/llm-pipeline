# IMPLEMENTATION - STEP 3: INSTRUCTION CONTENT ENDPOINT
**Status:** completed

## Summary
Added GET /{name}/steps/{step_name}/prompts endpoint to pipelines router, returning prompt/instruction content for a pipeline step from the Prompt DB table.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/pipelines.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/pipelines.py`
Added imports for `select`, `Prompt`, and `DBSession`. Added `StepPromptItem` and `StepPromptsResponse` Pydantic models. Added `get_step_prompts` endpoint.

```
# Before
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from llm_pipeline.introspection import PipelineIntrospector

# After
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.ui.deps import DBSession
```

```
# Before (no prompt models or endpoint)

# After
class StepPromptItem(BaseModel):
    prompt_key: str
    prompt_type: str
    content: str
    required_variables: Optional[List[str]] = None
    version: str

class StepPromptsResponse(BaseModel):
    pipeline_name: str
    step_name: str
    prompts: List[StepPromptItem]

@router.get("/{name}/steps/{step_name}/prompts", response_model=StepPromptsResponse)
def get_step_prompts(name, step_name, request, db: DBSession) -> StepPromptsResponse:
    # validates pipeline in registry (404), queries Prompt table by step_name,
    # returns empty prompts list if none found
```

## Decisions
### Query filter uses step_name only (no pipeline_name filter)
**Choice:** Filter Prompt table by step_name only, not by pipeline_name
**Rationale:** Prompt table has no pipeline_name column. step_name is sufficient since step names are unique within a pipeline's context. Pipeline existence is validated via introspection registry before querying.

## Verification
[x] Import check passes: `from llm_pipeline.ui.routes.pipelines import router, StepPromptItem, StepPromptsResponse`
[x] 766 tests pass (1 pre-existing failure in test_events_router_prefix unrelated)
[x] Endpoint returns 404 when pipeline not in registry
[x] Endpoint returns empty prompts list when no prompts found (not 404)
[x] Response model matches spec: pipeline_name, step_name, prompts[]

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] HIGH: Cross-pipeline prompt leakage -- endpoint queried Prompt table by step_name only, without scoping to the pipeline. Two pipelines sharing a step_name would return prompts from the wrong pipeline.

### Changes Made
#### File: `llm_pipeline/ui/routes/pipelines.py`
Replaced step_name-only Prompt query with introspection-based prompt_key scoping. The endpoint now introspects the pipeline class to collect declared prompt keys (system_key, user_key) for the matching step, then queries Prompt by those specific keys via `Prompt.prompt_key.in_(declared_keys)`. Returns empty list if no keys declared.

```
# Before
stmt = select(Prompt).where(Prompt.step_name == step_name)
prompts = db.exec(stmt).all()

# After
pipeline_cls = registry[name]
metadata = PipelineIntrospector(pipeline_cls).get_metadata()
declared_keys: set[str] = set()
for strategy in metadata.get("strategies", []):
    for step in strategy.get("steps", []):
        if step.get("step_name") == step_name:
            if step.get("system_key"):
                declared_keys.add(step["system_key"])
            if step.get("user_key"):
                declared_keys.add(step["user_key"])

if not declared_keys:
    return StepPromptsResponse(pipeline_name=name, step_name=step_name, prompts=[])

stmt = select(Prompt).where(Prompt.prompt_key.in_(declared_keys))
prompts = db.exec(stmt).all()
```

### Verification
[x] Import check passes
[x] 766 tests pass (1 pre-existing failure unrelated)
[x] Prompt query now scoped to pipeline's declared prompt keys via introspection
