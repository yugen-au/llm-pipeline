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
