# IMPLEMENTATION - STEP 3: PIPELINE WIRING & ENTRY POINT
**Status:** completed

## Summary
Assembled TextAnalyzerPipeline with agent registry, default strategy, strategies container, seed_prompts classmethod, 6 prompt constants in prompts.py, and entry point registration in pyproject.toml. Demo pipeline is now fully wired and discoverable.

## Files
**Created:** `docs/tasks/in-progress/pipeline-discovery-3-textanalyzer-demo/implementation/step-3-pipeline-wiring-entry-point.md`
**Modified:** `llm_pipeline/demo/pipeline.py`, `llm_pipeline/demo/prompts.py`, `llm_pipeline/demo/__init__.py`, `pyproject.toml`
**Deleted:** none

## Changes
### File: `llm_pipeline/demo/pipeline.py`
Added imports for AgentRegistry, PipelineConfig, PipelineStrategy, PipelineStrategies, Engine, Any, Dict. Added 5 classes after step definitions:

```python
# Before: file ended at SummaryStep.process_instructions

# After: added TextAnalyzerAgentRegistry, DefaultStrategy, TextAnalyzerStrategies, TextAnalyzerPipeline

class TextAnalyzerAgentRegistry(AgentRegistry, agents={
    "sentiment_analysis": SentimentAnalysisInstructions,
    "topic_extraction": TopicExtractionInstructions,
    "summary": SummaryInstructions,
}):
    pass

class DefaultStrategy(PipelineStrategy):
    NAME = "default"
    def can_handle(self, context): return True
    def get_steps(self): return [SentimentAnalysisStep.create_definition(), ...]

class TextAnalyzerStrategies(PipelineStrategies, strategies=[DefaultStrategy]):
    pass

class TextAnalyzerPipeline(PipelineConfig, registry=TextAnalyzerRegistry,
    strategies=TextAnalyzerStrategies, agent_registry=TextAnalyzerAgentRegistry):
    INPUT_DATA: ClassVar[type] = TextAnalyzerInputData
    @classmethod
    def seed_prompts(cls, engine): ...  # delegates to prompts.seed_prompts
```

### File: `llm_pipeline/demo/prompts.py`
Was a single docstring. Now contains 6 prompt constant dicts (3 system + 3 user) for keys sentiment_analysis, topic_extraction, summary. Each dict has prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables, description. User prompts use template variables: {text} (sentiment), {text}+{sentiment} (topic), {text}+{sentiment}+{primary_topic} (summary). `seed_prompts(cls, engine)` creates demo_topics table via `SQLModel.metadata.create_all(engine, tables=[Topic.__table__])` then idempotently inserts prompts using `select(Prompt).where(key, type)` check.

### File: `llm_pipeline/demo/__init__.py`
Changed from TYPE_CHECKING-only import to real import so TextAnalyzerPipeline is properly exported at runtime.

```python
# Before
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm_pipeline.demo.pipeline import TextAnalyzerPipeline

# After
from llm_pipeline.demo.pipeline import TextAnalyzerPipeline
```

### File: `pyproject.toml`
Added entry point section after `[project.scripts]`.

```toml
# Before: no entry-points section

# After
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
```

## Decisions
### DefaultStrategy NAME override
**Choice:** Explicitly set `NAME = "default"` on DefaultStrategy class
**Rationale:** Auto-generated NAME from class name would also be "default" (DefaultStrategy -> strip Strategy -> Default -> snake_case -> default), but explicit is clearer for a reference demo

### seed_prompts delegation pattern
**Choice:** TextAnalyzerPipeline.seed_prompts classmethod delegates to prompts.seed_prompts function
**Rationale:** Keeps prompt content/DB logic in prompts.py while maintaining the classmethod interface expected by _discover_pipelines in app.py

### Prompt content style
**Choice:** Concise role-based system prompts; user prompts with minimal template wrapping
**Rationale:** Demo prompts should be clear and readable, not production-optimized; exact wording is implementation detail per VALIDATED_RESEARCH

## Verification
[x] `from llm_pipeline.demo import TextAnalyzerPipeline` succeeds
[x] TextAnalyzerAgentRegistry.AGENTS has 3 correct entries
[x] DefaultStrategy.NAME == "default" and can_handle returns True
[x] DefaultStrategy.get_steps() returns 3 StepDefinitions
[x] TextAnalyzerStrategies.STRATEGIES == [DefaultStrategy]
[x] TextAnalyzerPipeline.INPUT_DATA is TextAnalyzerInputData
[x] seed_prompts creates demo_topics table
[x] seed_prompts inserts 6 prompts (3 system + 3 user)
[x] seed_prompts is idempotent (second call doesn't duplicate)
[x] Entry point configured in pyproject.toml
[x] pytest: 953 passed, 6 skipped, 0 failures

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] (MEDIUM) Redundant NAME override on DefaultStrategy -- added comment explaining auto-generation, kept explicit for demo clarity
[x] (LOW) Uppercase List/Dict imports used inconsistently -- replaced `List[...]` with `list[...]`, `Dict[str, Any]` with `dict[str, Any]`, removed `List` and `Dict` from typing import

### Changes Made
#### File: `llm_pipeline/demo/pipeline.py`
Removed `List` and `Dict` from typing import, replaced uppercase generic usage with Python 3.11+ lowercase builtins, added explanatory comment above `NAME = "default"`.

```python
# Before
from typing import Any, ClassVar, Dict, List, Optional
    def default(self, results: List[TopicExtractionInstructions]) -> List[Topic]:
    def can_handle(self, context: Dict[str, Any]) -> bool:
    NAME = "default"

# After
from typing import Any, ClassVar, Optional
    def default(self, results: list[TopicExtractionInstructions]) -> list[Topic]:
    def can_handle(self, context: dict[str, Any]) -> bool:
    # Redundant: auto-generated from class name "Default" -> "default".
    # Kept explicit for demo clarity.
    NAME = "default"
```

### Verification
[x] `from llm_pipeline.demo import TextAnalyzerPipeline` succeeds
[x] pytest: 1008 passed, 6 skipped, 0 failures (1 deselected: pre-existing WAL test-ordering issue unrelated to changes)
