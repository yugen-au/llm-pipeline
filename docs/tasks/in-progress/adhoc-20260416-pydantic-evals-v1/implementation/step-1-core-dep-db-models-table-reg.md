# IMPLEMENTATION - STEP 1: CORE DEP + DB MODELS + TABLE REG
**Status:** completed

## Summary
Added pydantic-evals as core dependency, created 4 eval DB models in new evals package, registered tables in init_pipeline_db().

## Files
**Created:** llm_pipeline/evals/__init__.py, llm_pipeline/evals/models.py
**Modified:** pyproject.toml, llm_pipeline/db/__init__.py
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added pydantic-evals to core dependencies.
```
# Before
    "pydantic-ai>=1.0.5",
    "python-dotenv>=1.0",

# After
    "pydantic-ai>=1.0.5",
    "pydantic-evals",
    "python-dotenv>=1.0",
```

### File: `llm_pipeline/evals/__init__.py`
Empty file marking evals as a Python package.

### File: `llm_pipeline/evals/models.py`
4 SQLModel table classes: EvaluationDataset (eval_datasets), EvaluationCase (eval_cases), EvaluationRun (eval_runs), EvaluationCaseResult (eval_case_results). Follows state.py patterns: sa_column=Column(JSON) for dict fields, Field(default_factory=utc_now) for timestamps, Index() in __table_args__.

### File: `llm_pipeline/db/__init__.py`
Imported 4 eval models, added their .__table__ entries to create_all() call.
```
# Before (imports)
from llm_pipeline.events.models import PipelineEventRecord

# After (imports)
from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.evals.models import EvaluationDataset, EvaluationCase, EvaluationRun, EvaluationCaseResult

# Before (create_all)
            PipelineReview.__table__,
        ],

# After (create_all)
            PipelineReview.__table__,
            EvaluationDataset.__table__,
            EvaluationCase.__table__,
            EvaluationRun.__table__,
            EvaluationCaseResult.__table__,
        ],
```

## Decisions
None - all decisions pre-made in PLAN.md.

## Verification
[x] uv sync completes without conflicts
[x] `from pydantic_evals import Dataset, Case` imports cleanly
[x] All 4 eval models import from llm_pipeline.evals.models
[x] init_pipeline_db() creates all 4 tables in fresh SQLite DB
[x] Table names verified: eval_datasets, eval_cases, eval_runs, eval_case_results
