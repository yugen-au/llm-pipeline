"""Shared fixtures and test helpers for event emission tests.

Provides common instruction models, steps, strategies, pipelines,
and pytest fixtures used across event test modules.
"""
import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import SQLModel, Field, Session, create_engine
from typing import Any, Dict, List, Optional, ClassVar

from llm_pipeline import (
    PipelineConfig,
    LLMStep,
    LLMResultMixin,
    step_definition,
    PipelineStrategy,
    PipelineStrategies,
    PipelineDatabaseRegistry,
)
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.transformation import PipelineTransformation
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.inputs import StepInputs
from llm_pipeline.types import StepCallParams
from llm_pipeline.wiring import Bind, FromOutput
from llm_pipeline.events.handlers import InMemoryEventHandler


# -- Test Domain ---------------------------------------------------------------


class SimpleInstructions(LLMResultMixin):
    """Minimal instruction model for test pipeline."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


class FailingInstructions(LLMResultMixin):
    """Instruction model for failing step."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


class SkippableInstructions(LLMResultMixin):
    """Instruction model for skippable step."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


# -- Extraction Domain (for CacheReconstruction tests) -------------------------


class Item(SQLModel, table=True):
    """Minimal DB model for extraction tests."""
    __tablename__ = "items"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    value: int


class ItemDetectionInstructions(LLMResultMixin):
    """Instruction model for extraction step."""
    item_count: int
    category: str

    example: ClassVar[dict] = {"item_count": 2, "category": "test", "notes": "ok"}


class ItemExtraction(PipelineExtraction, model=Item):
    """Extraction that creates Item instances from step output."""
    class FromItemDetectionInputs(StepInputs):
        item_count: int

    def from_item_detection(self, inputs: FromItemDetectionInputs) -> list[Item]:
        return [
            Item(name=f"item_{i}", value=i)
            for i in range(inputs.item_count)
        ]


# -- Transformation Domain (for transformation event tests) -------------------


class TransformationTransformation(PipelineTransformation, input_type=dict, output_type=dict):
    """Transformation that adds a transformed_key to input dict."""
    def transform(self, data: dict, instructions) -> dict:
        """Add transformed_key to demonstrate transformation."""
        result = data.copy()
        result["transformed_key"] = "transformed_value"
        result["original_count"] = instructions.count if hasattr(instructions, 'count') else 0
        return result


class TransformationInstructions(LLMResultMixin):
    """Instruction model for transformation step."""
    count: int
    operation: str

    example: ClassVar[dict] = {"count": 5, "operation": "transform", "notes": "test"}


# -- Test Steps ----------------------------------------------------------------


@step_definition(
    instructions=SimpleInstructions,
    default_system_key="simple.system",
    default_user_key="simple.user",
)
class SimpleStep(LLMStep):
    """Step that succeeds."""
    def prepare_calls(self) -> List[StepCallParams]:
        return [{"variables": {"data": "test"}}]


@step_definition(
    instructions=FailingInstructions,
    default_system_key="failing.system",
    default_user_key="failing.user",
)
class FailingStep(LLMStep):
    """Step that raises ValueError during execution."""
    def prepare_calls(self) -> List[StepCallParams]:
        raise ValueError("Intentional test failure")


@step_definition(
    instructions=SkippableInstructions,
    default_system_key="skippable.system",
    default_user_key="skippable.user",
)
class SkippableStep(LLMStep):
    """Step that is skipped (should_skip returns True)."""
    def should_skip(self) -> bool:
        return True

    def prepare_calls(self) -> List[StepCallParams]:
        return [{"variables": {"data": "test"}}]


@step_definition(
    instructions=ItemDetectionInstructions,
    default_system_key="item_detection.system",
    default_user_key="item_detection.user",
)
class ItemDetectionStep(LLMStep):
    """Step with extractions for CacheReconstruction tests."""
    def prepare_calls(self) -> List[StepCallParams]:
        return [{"variables": {"data": "test"}}]


@step_definition(
    instructions=TransformationInstructions,
    default_system_key="transformation.system",
    default_user_key="transformation.user",
    default_transformation=TransformationTransformation,
)
class TransformationStep(LLMStep):
    """Step with transformation for transformation event tests."""
    def prepare_calls(self) -> List[StepCallParams]:
        return [{"variables": {"data": "test"}}]


# -- Test Strategies -----------------------------------------------------------


class SuccessStrategy(PipelineStrategy):
    """Strategy with 2 successful steps."""
    def can_handle(self, context):
        return True

    def get_bindings(self):
        return [
            Bind(step=SimpleStep),
            Bind(step=SimpleStep),
        ]


class FailureStrategy(PipelineStrategy):
    """Strategy with failing step."""
    def can_handle(self, context):
        return True

    def get_bindings(self):
        return [Bind(step=FailingStep)]


class SkipStrategy(PipelineStrategy):
    """Strategy with skippable step."""
    def can_handle(self, context):
        return True

    def get_bindings(self):
        return [Bind(step=SkippableStep)]


# -- Test Pipelines ------------------------------------------------------------


class SuccessRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class FailureRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class SkipRegistry(PipelineDatabaseRegistry, models=[]):
    pass



class SuccessStrategies(PipelineStrategies, strategies=[SuccessStrategy]):
    pass


class FailureStrategies(PipelineStrategies, strategies=[FailureStrategy]):
    pass


class SkipStrategies(PipelineStrategies, strategies=[SkipStrategy]):
    pass


class SuccessPipeline(
    PipelineConfig,
    registry=SuccessRegistry,
    strategies=SuccessStrategies,
):
    pass


class FailurePipeline(
    PipelineConfig,
    registry=FailureRegistry,
    strategies=FailureStrategies,
):
    pass


class SkipPipeline(
    PipelineConfig,
    registry=SkipRegistry,
    strategies=SkipStrategies,
):
    pass


class ExtractionStrategy(PipelineStrategy):
    """Strategy with a single extraction step."""
    def can_handle(self, context):
        return True

    def get_bindings(self):
        return [
            Bind(
                step=ItemDetectionStep,
                extractions=[
                    Bind(
                        extraction=ItemExtraction,
                        inputs=ItemExtraction.FromItemDetectionInputs.sources(
                            item_count=FromOutput(ItemDetectionStep, field="item_count"),
                        ),
                    ),
                ],
            ),
        ]


class ExtractionRegistry(PipelineDatabaseRegistry, models=[Item]):
    pass


class ExtractionStrategies(PipelineStrategies, strategies=[ExtractionStrategy]):
    pass


class ExtractionPipeline(
    PipelineConfig,
    registry=ExtractionRegistry,
    strategies=ExtractionStrategies,
):
    pass


class TransformationStrategy(PipelineStrategy):
    """Strategy with a single transformation step."""
    def can_handle(self, context):
        return True

    def get_bindings(self):
        return [Bind(step=TransformationStep)]


class TransformationRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class TransformationStrategies(PipelineStrategies, strategies=[TransformationStrategy]):
    pass


class TransformationPipeline(
    PipelineConfig,
    registry=TransformationRegistry,
    strategies=TransformationStrategies,
):
    pass


# -- Mock run_result builders --------------------------------------------------


from tests.conftest import _mock_usage  # shared helper from root tests/conftest.py


def make_simple_run_result(count=1):
    """Build MagicMock mimicking AgentRunResult for SimpleInstructions."""
    instruction = SimpleInstructions(count=count, confidence_score=1.0, notes="test")
    mock_result = MagicMock()
    mock_result.output = instruction
    mock_result.usage.return_value = _mock_usage()
    return mock_result


def make_item_detection_run_result(item_count=2, category="test"):
    """Build MagicMock mimicking AgentRunResult for ItemDetectionInstructions."""
    instruction = ItemDetectionInstructions(
        item_count=item_count, category=category, confidence_score=1.0, notes="ok"
    )
    mock_result = MagicMock()
    mock_result.output = instruction
    mock_result.usage.return_value = _mock_usage()
    return mock_result


def make_transformation_run_result(count=5, operation="transform"):
    """Build MagicMock mimicking AgentRunResult for TransformationInstructions."""
    instruction = TransformationInstructions(
        count=count, operation=operation, confidence_score=1.0, notes="test"
    )
    mock_result = MagicMock()
    mock_result.output = instruction
    mock_result.usage.return_value = _mock_usage()
    return mock_result


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def engine():
    """In-memory SQLite engine with tables."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def seeded_session(engine):
    """Session with prompts for test steps."""
    with Session(engine) as session:
        session.add(Prompt(
            prompt_key="simple.system",
            prompt_name="Simple System",
            prompt_type="system",
            category="test",
            step_name="simple",
            content="You are a test assistant.",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="simple.user",
            prompt_name="Simple User",
            prompt_type="user",
            category="test",
            step_name="simple",
            content="Process: {data}",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="failing.system",
            prompt_name="Failing System",
            prompt_type="system",
            category="test",
            step_name="failing",
            content="You are a test assistant.",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="failing.user",
            prompt_name="Failing User",
            prompt_type="user",
            category="test",
            step_name="failing",
            content="Process: {data}",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="skippable.system",
            prompt_name="Skippable System",
            prompt_type="system",
            category="test",
            step_name="skippable",
            content="You are a test assistant.",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="skippable.user",
            prompt_name="Skippable User",
            prompt_type="user",
            category="test",
            step_name="skippable",
            content="Process: {data}",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="item_detection.system",
            prompt_name="Item Detection System",
            prompt_type="system",
            category="test",
            step_name="item_detection",
            content="You are an item detector.",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="item_detection.user",
            prompt_name="Item Detection User",
            prompt_type="user",
            category="test",
            step_name="item_detection",
            content="Detect items: {data}",
            version="1.0",
        ))
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

    # Return a new session for test use
    return Session(engine)


@pytest.fixture
def in_memory_handler():
    """Fresh InMemoryEventHandler for each test."""
    return InMemoryEventHandler()


@pytest.fixture
def mock_simple_run_result():
    """Default AgentRunResult mock for SimpleInstructions (count=1)."""
    return make_simple_run_result(count=1)


@pytest.fixture
def agent_run_sync_patch():
    """Patch Agent.run_sync to return SimpleInstructions result by default.

    Tests that need custom return values can override via monkeypatch or
    call patch() directly within the test body.
    """
    with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=1)) as mock:
        yield mock
