# IMPLEMENTATION - STEP 5: CREATE TRANSFORM TEST INFRA
**Status:** completed

## Summary
Created transformation test infrastructure in tests/events/conftest.py following existing ExtractionPipeline pattern. Added TransformationTransformation class, TransformationStep, TransformationStrategy, TransformationPipeline, prompts, and transformation_pipeline fixture for testing transformation events.

## Files
**Created:** C:/Users/SamSG/Documents/claude_projects/llm-pipeline/docs/tasks/in-progress/master-14-extract-xform-events/implementation/step-5-create-transform-test-infra.md
**Modified:** C:/Users/SamSG/Documents/claude_projects/llm-pipeline/tests/events/conftest.py
**Deleted:** none

## Changes
### File: `tests/events/conftest.py`
Added transformation test infrastructure mirroring ExtractionPipeline pattern:

```python
# Before
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.llm.provider import LLMProvider
# ... only extraction domain existed

# After
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.transformation import PipelineTransformation
from llm_pipeline.llm.provider import LLMProvider
# ... added transformation domain
```

Added TransformationTransformation class (L132-139):
```python
class TransformationTransformation(PipelineTransformation, input_type=dict, output_type=dict):
    """Transformation that adds a transformed_key to input dict."""
    def transform(self, data: dict, instructions) -> dict:
        """Add transformed_key to demonstrate transformation."""
        result = data.copy()
        result["transformed_key"] = "transformed_value"
        result["original_count"] = instructions.count if hasattr(instructions, 'count') else 0
        return result
```

Added TransformationInstructions and TransformationContext (L142-152):
```python
class TransformationInstructions(LLMResultMixin):
    """Instruction model for transformation step."""
    count: int
    operation: str

    example: ClassVar[dict] = {"count": 5, "operation": "transform", "notes": "test"}


class TransformationContext(PipelineContext):
    """Context produced by transformation step."""
    operation: str
```

Added TransformationStep with step_definition decorator (L218-231):
```python
@step_definition(
    instructions=TransformationInstructions,
    default_system_key="transformation.system",
    default_user_key="transformation.user",
    default_transformation=TransformationTransformation,
    context=TransformationContext,
)
class TransformationStep(LLMStep):
    """Step with transformation for transformation event tests."""
    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={"data": "test"})]

    def process_instructions(self, instructions):
        return TransformationContext(operation=instructions[0].operation)
```

Added TransformationStrategy, TransformationRegistry, TransformationStrategies, TransformationPipeline (L327-345):
```python
class TransformationStrategy(PipelineStrategy):
    """Strategy with a single transformation step."""
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [TransformationStep.create_definition()]


class TransformationRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class TransformationStrategies(PipelineStrategies, strategies=[TransformationStrategy]):
    pass


class TransformationPipeline(PipelineConfig, registry=TransformationRegistry, strategies=TransformationStrategies):
    pass
```

Added prompts to seeded_session fixture (L435-452):
```python
# Before - only item_detection prompts
session.add(Prompt(
    prompt_key="item_detection.user",
    ...
))
session.commit()

# After - added transformation prompts
session.add(Prompt(
    prompt_key="transformation.system",
    prompt_name="Transformation System",
    prompt_type="system",
    category="test",
    step_name="transformation",
    content="You are a data transformer.",
    version="1.0",
))
session.add(Prompt(
    prompt_key="transformation.user",
    prompt_name="Transformation User",
    prompt_type="user",
    category="test",
    step_name="transformation",
    content="Transform data: {data}",
    version="1.0",
))
session.commit()
```

Added transformation_pipeline fixture (L465-475):
```python
@pytest.fixture
def transformation_pipeline(seeded_session, in_memory_handler):
    """TransformationPipeline with seeded session and InMemoryEventHandler."""
    pipeline = TransformationPipeline(
        session=seeded_session,
        provider=MockProvider(responses=[
            {"count": 5, "operation": "transform"}
        ]),
        event_handler=in_memory_handler,
    )
    return pipeline
```

## Decisions
### Naming Convention: TransformationTransformation
**Choice:** Named transformation class `TransformationTransformation` instead of `TransformDataTransformation`
**Rationale:** step_definition decorator enforces naming convention: transformation class must be named `{StepName}Transformation`. Since step is `TransformationStep`, transformation must be `TransformationTransformation`. Discovered via error: "Transformation class for TransformationStep must be named 'TransformationTransformation', got 'TransformDataTransformation'"

### Reuse TransformationRegistry with Empty Models
**Choice:** TransformationRegistry has `models=[]` unlike ExtractionRegistry which has `models=[Item]`
**Rationale:** Transformation tests don't need DB models (no extractions). Simplest approach per plan: "reuse ExtractionRegistry for simplicity" rejected in favor of minimal dedicated registry with no models

### Dict Input/Output Types for Transformation
**Choice:** TransformationTransformation uses `input_type=dict, output_type=dict`
**Rationale:** Simplest type that demonstrates transformation logic. Real transformations use DataFrame, but dict is sufficient for event testing and avoids pandas dependency in test fixtures

### Transformation Actually Transforms Data
**Choice:** TransformationTransformation.transform() adds `transformed_key` and `original_count` to result dict
**Rationale:** Per task context: "The transformation needs to actually transform data so events fire (not a no-op)". Ensures transformation execution paths are exercised for event emission tests

## Verification
[x] Import test successful: all classes and fixtures importable
[x] Naming conventions verified: TransformationTransformation matches step_definition requirements
[x] Transformation logic non-trivial: adds keys to demonstrate actual transformation
[x] Follows ExtractionPipeline pattern: Strategy → Strategies → Pipeline → fixture
[x] Prompts added to seeded_session: transformation.system and transformation.user
[x] transformation_pipeline fixture instantiates with MockProvider and InMemoryEventHandler
