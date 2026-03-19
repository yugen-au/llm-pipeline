# IMPLEMENTATION - STEP 12: PACKAGE WIRING
**Status:** completed

## Summary
Created `llm_pipeline/creator/__init__.py` with jinja2 ImportError guard and StepCreatorPipeline re-export. Added `creator` optional-dependency and `step_creator` entry-point to pyproject.toml. Added guarded optional import of StepCreatorPipeline to `llm_pipeline/__init__.py`.

## Files
**Created:** `llm_pipeline/creator/__init__.py`
**Modified:** `pyproject.toml`, `llm_pipeline/__init__.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/__init__.py`
New file - ImportError guard for jinja2, re-exports StepCreatorPipeline.
```
# Before
(did not exist)

# After
try:
    import jinja2
except ImportError:
    raise ImportError("llm_pipeline.creator requires jinja2. Install with: pip install llm-pipeline[creator]")

from llm_pipeline.creator.pipeline import StepCreatorPipeline

__all__ = ["StepCreatorPipeline"]
```

### File: `pyproject.toml`
Added creator optional-dep and entry-point.
```
# Before
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"

[project.optional-dependencies]
ui = ...

# After
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
step_creator = "llm_pipeline.creator:StepCreatorPipeline"

[project.optional-dependencies]
creator = ["jinja2>=3.0"]
ui = ...
```

### File: `llm_pipeline/__init__.py`
Added guarded optional import and conditional __all__ extension.
```
# Before
from llm_pipeline.validators import not_found_validator, ...

__version__ = "0.1.0"
__all__ = [...]

# After
from llm_pipeline.validators import not_found_validator, ...

try:
    from llm_pipeline.creator import StepCreatorPipeline
    _has_creator = True
except ImportError:
    _has_creator = False

__version__ = "0.1.0"
__all__ = [...]

if _has_creator:
    __all__ += ["StepCreatorPipeline"]
```

## Decisions
### ImportError guard placement
**Choice:** Guard in `creator/__init__.py` re-raises ImportError on jinja2 absence; top-level `__init__.py` catches it silently.
**Rationale:** Matches plan spec. Users importing `llm_pipeline.creator` directly get a clear actionable message. Users importing `llm_pipeline` directly just don't get StepCreatorPipeline in namespace (no error).

### __all__ conditional extension
**Choice:** `if _has_creator: __all__ += ["StepCreatorPipeline"]` after the static __all__ list.
**Rationale:** Keeps the static list readable; conditional append is idiomatic for optional extras.

## Verification
- [x] `llm_pipeline/creator/__init__.py` created with jinja2 guard and StepCreatorPipeline export
- [x] `pyproject.toml` has `creator = ["jinja2>=3.0"]` in optional-dependencies
- [x] `pyproject.toml` has `step_creator = "llm_pipeline.creator:StepCreatorPipeline"` entry-point
- [x] `llm_pipeline/__init__.py` has guarded import and conditional __all__ extension
- [x] pytest: 1049 passed, 6 pre-existing failures (unrelated to this step)
- [x] committed: 72270c3f
