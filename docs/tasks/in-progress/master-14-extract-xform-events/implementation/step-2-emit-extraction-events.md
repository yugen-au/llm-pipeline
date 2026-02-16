# IMPLEMENTATION - STEP 2: EMIT EXTRACTION EVENTS
**Status:** completed

## Summary
Added ExtractionStarting, ExtractionCompleted, and ExtractionError event emissions to extract_data() in step.py, following established guard+emit pattern from pipeline.py.

## Files
**Created:** none
**Modified:** llm_pipeline/step.py
**Deleted:** none

## Changes
### File: `llm_pipeline/step.py`
Added imports for datetime/timezone, ValidationError, and three extraction event types. Restructured extract_data() try block to add except clause for ExtractionError emission before re-raise.

```python
# Before - imports (L1-17)
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, List, Dict, TYPE_CHECKING, Type, Optional, ClassVar, Tuple

from pydantic import BaseModel, Field
from sqlmodel import SQLModel

from llm_pipeline.types import StepCallParams

# After
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, List, Dict, TYPE_CHECKING, Type, Optional, ClassVar, Tuple

from pydantic import BaseModel, Field, ValidationError
from sqlmodel import SQLModel

from llm_pipeline.events.types import (
    ExtractionCompleted,
    ExtractionError,
    ExtractionStarting,
)
from llm_pipeline.types import StepCallParams
```

```python
# Before - extract_data() (L315-332)
def extract_data(self, instructions: List[Any]) -> None:
    extraction_classes = getattr(self, '_extractions', [])
    for extraction_class in extraction_classes:
        extraction = extraction_class(self.pipeline)
        self.pipeline._current_extraction = extraction_class
        try:
            instances = extraction.extract(instructions)
            self.store_extractions(extraction.MODEL, instances)
            for instance in instances:
                self.pipeline._real_session.add(instance)
            self.pipeline._real_session.flush()
        finally:
            self.pipeline._current_extraction = None

# After
def extract_data(self, instructions: List[Any]) -> None:
    extraction_classes = getattr(self, '_extractions', [])
    for extraction_class in extraction_classes:
        extraction = extraction_class(self.pipeline)
        self.pipeline._current_extraction = extraction_class

        if self.pipeline._event_emitter:
            self.pipeline._emit(ExtractionStarting(
                run_id=self.pipeline.run_id,
                pipeline_name=self.pipeline.pipeline_name,
                step_name=self.step_name,
                extraction_class=extraction_class.__name__,
                model_class=extraction.MODEL.__name__,
                timestamp=datetime.now(timezone.utc),
            ))

        try:
            extract_start = datetime.now(timezone.utc)
            instances = extraction.extract(instructions)
            self.store_extractions(extraction.MODEL, instances)
            for instance in instances:
                self.pipeline._real_session.add(instance)
            self.pipeline._real_session.flush()

            if self.pipeline._event_emitter:
                self.pipeline._emit(ExtractionCompleted(
                    run_id=self.pipeline.run_id,
                    pipeline_name=self.pipeline.pipeline_name,
                    step_name=self.step_name,
                    extraction_class=extraction_class.__name__,
                    model_class=extraction.MODEL.__name__,
                    instance_count=len(instances),
                    execution_time_ms=(
                        datetime.now(timezone.utc) - extract_start
                    ).total_seconds() * 1000,
                    timestamp=datetime.now(timezone.utc),
                ))
        except Exception as e:
            if self.pipeline._event_emitter:
                validation_errors = (
                    e.errors() if isinstance(e, ValidationError) else []
                )
                self.pipeline._emit(ExtractionError(
                    run_id=self.pipeline.run_id,
                    pipeline_name=self.pipeline.pipeline_name,
                    step_name=self.step_name,
                    extraction_class=extraction_class.__name__,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    validation_errors=validation_errors,
                    timestamp=datetime.now(timezone.utc),
                ))
            raise
        finally:
            self.pipeline._current_extraction = None
```

## Decisions
None -- all emission patterns follow established conventions from pipeline.py consensus events.

## Verification
- [x] All 225 tests pass (pytest tests/ -x -q)
- [x] ExtractionStarting emits before try block, after _current_extraction set
- [x] ExtractionCompleted emits after flush with instance_count and execution_time_ms
- [x] ExtractionError emits in except block then re-raises (preserves PipelineError double-emit)
- [x] ValidationError isinstance check populates validation_errors; empty list for other exceptions
- [x] Guard pattern `if self.pipeline._event_emitter:` matches codebase convention
- [x] All three events use kw_only construction matching event type definitions
