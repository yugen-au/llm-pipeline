"""Shared fixtures and test helpers for event emission tests.

Provides common mock providers, instruction models, context classes, steps,
strategies, pipelines, and pytest fixtures used across event test modules.
"""
import pytest
from sqlmodel import SQLModel, Session, create_engine
from typing import Any, Dict, List, Optional, ClassVar

from llm_pipeline import (
    PipelineConfig,
    LLMStep,
    LLMResultMixin,
    step_definition,
    PipelineStrategy,
    PipelineStrategies,
    PipelineDatabaseRegistry,
    PipelineContext,
)
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.result import LLMCallResult
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.types import StepCallParams
from llm_pipeline.events.handlers import InMemoryEventHandler


# -- Mock Provider -------------------------------------------------------------


class MockProvider(LLMProvider):
    """Mock LLM provider that returns predefined responses."""

    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None, should_fail: bool = False):
        self._responses = responses or []
        self._call_count = 0
        self._should_fail = should_fail

    def call_structured(self, prompt, system_instruction, result_class, **kwargs):
        if self._should_fail:
            raise ValueError("Mock provider failure")
        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
            self._call_count += 1
            return LLMCallResult.success(
                parsed=response,
                raw_response="mock response",
                model_name="mock-model",
                attempt_count=1,
            )
        return LLMCallResult(
            parsed=None,
            raw_response="",
            model_name="mock-model",
            attempt_count=1,
            validation_errors=[],
        )


# -- Test Domain ---------------------------------------------------------------


class SimpleInstructions(LLMResultMixin):
    """Minimal instruction model for test pipeline."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


class SimpleContext(PipelineContext):
    """Minimal context for test pipeline."""
    total: int


class FailingInstructions(LLMResultMixin):
    """Instruction model for failing step."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


class SkippableInstructions(LLMResultMixin):
    """Instruction model for skippable step."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


class SkippableContext(PipelineContext):
    """Minimal context for skippable step."""
    total: int


# -- Test Steps ----------------------------------------------------------------


@step_definition(
    instructions=SimpleInstructions,
    default_system_key="simple.system",
    default_user_key="simple.user",
    context=SimpleContext,
)
class SimpleStep(LLMStep):
    """Step that succeeds."""
    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={"data": "test"})]

    def process_instructions(self, instructions):
        return SimpleContext(total=instructions[0].count)


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
    context=SkippableContext,
)
class SkippableStep(LLMStep):
    """Step that is skipped (should_skip returns True)."""
    def should_skip(self) -> bool:
        return True

    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={"data": "test"})]

    def process_instructions(self, instructions):
        return SkippableContext(total=instructions[0].count)


# -- Test Strategies -----------------------------------------------------------


class SuccessStrategy(PipelineStrategy):
    """Strategy with 2 successful steps."""
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [
            SimpleStep.create_definition(),
            SimpleStep.create_definition(),
        ]


class FailureStrategy(PipelineStrategy):
    """Strategy with failing step."""
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [FailingStep.create_definition()]


class SkipStrategy(PipelineStrategy):
    """Strategy with skippable step."""
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [SkippableStep.create_definition()]


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


class SuccessPipeline(PipelineConfig, registry=SuccessRegistry, strategies=SuccessStrategies):
    pass


class FailurePipeline(PipelineConfig, registry=FailureRegistry, strategies=FailureStrategies):
    pass


class SkipPipeline(PipelineConfig, registry=SkipRegistry, strategies=SkipStrategies):
    pass


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
        session.commit()

    # Return a new session for test use
    return Session(engine)


@pytest.fixture
def in_memory_handler():
    """Fresh InMemoryEventHandler for each test."""
    return InMemoryEventHandler()
