"""Integration tests: PipelineRun write behaviour during execute()."""
import uuid
from typing import Any, ClassVar, Dict, List, Optional, Type
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import SQLModel, Field, Session, create_engine, select

from llm_pipeline import (
    PipelineConfig,
    LLMStep,
    LLMResultMixin,
    step_definition,
    PipelineStrategy,
    PipelineStrategies,
    PipelineContext,
    PipelineExtraction,
    PipelineDatabaseRegistry,
)
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.db import init_pipeline_db
from llm_pipeline.state import PipelineRun
from llm_pipeline.types import StepCallParams
from llm_pipeline.db.prompt import Prompt


# ---------------------------------------------------------------------------
# Minimal domain model
# ---------------------------------------------------------------------------

class Gadget(SQLModel, table=True):
    __tablename__ = "gadgets_tracking"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


# ---------------------------------------------------------------------------
# LLM result / context / extraction
# ---------------------------------------------------------------------------

class GadgetInstructions(LLMResultMixin):
    count: int
    label: str

    example: ClassVar[dict] = {"count": 1, "label": "test", "confidence_score": 1.0}


class GadgetContext(PipelineContext):
    label: str


class GadgetExtraction(PipelineExtraction, model=Gadget):
    def default(self, results):
        instruction = results[0]
        return [Gadget(name=f"{instruction.label}_{i}") for i in range(instruction.count)]


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------

@step_definition(
    instructions=GadgetInstructions,
    default_system_key="gadget.system",
    default_user_key="gadget.user",
    default_extractions=[GadgetExtraction],
    context=GadgetContext,
)
class GadgetStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [{"variables": {"data": self.pipeline.get_sanitized_data()}}]

    def process_instructions(self, instructions):
        return GadgetContext(label=instructions[0].label)


# ---------------------------------------------------------------------------
# Failing step (raises during execute)
# ---------------------------------------------------------------------------

class BrokenInstructions(LLMResultMixin):
    count: int = 0
    label: str = ""


@step_definition(
    instructions=BrokenInstructions,
    default_system_key="gadget.system",
    default_user_key="gadget.user",
)
class BrokenStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        raise RuntimeError("intentional failure for testing")


# ---------------------------------------------------------------------------
# Strategy / pipeline classes
# ---------------------------------------------------------------------------

class GadgetStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [GadgetStep.create_definition()]


class BrokenStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [BrokenStep.create_definition()]


class TrackingRegistry(PipelineDatabaseRegistry, models=[Gadget]):
    pass


class TrackingAgentRegistry(AgentRegistry, agents={
    "gadget": GadgetInstructions,
}):
    pass


class TrackingStrategies(PipelineStrategies, strategies=[GadgetStrategy]):
    pass


class TrackingPipeline(
    PipelineConfig,
    registry=TrackingRegistry,
    strategies=TrackingStrategies,
    agent_registry=TrackingAgentRegistry,
):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_result(count=2, label="widget"):
    """Build a MagicMock mimicking AgentRunResult for GadgetInstructions."""
    instruction = GadgetInstructions(
        count=count,
        label=label,
        confidence_score=0.9,
        notes="ok",
    )
    mock_result = MagicMock()
    mock_result.output = instruction
    usage = MagicMock()
    usage.input_tokens = 10
    usage.output_tokens = 5
    usage.requests = 1
    mock_result.usage.return_value = usage
    return mock_result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tracking_engine():
    engine = create_engine("sqlite:///:memory:")
    init_pipeline_db(engine)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def seeded_tracking_session(tracking_engine):
    with Session(tracking_engine) as session:
        session.add(Prompt(
            prompt_key="gadget.system",
            prompt_name="Gadget System",
            prompt_type="system",
            category="test",
            step_name="gadget",
            content="You detect gadgets.",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="gadget.user",
            prompt_name="Gadget User",
            prompt_type="user",
            category="test",
            step_name="gadget",
            content="Analyze: {data}",
            version="1.0",
        ))
        session.commit()
        yield session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPipelineRunTracking:
    def test_successful_execute_writes_completed_run(self, tracking_engine, seeded_tracking_session):
        pipeline = TrackingPipeline(session=seeded_tracking_session, model="test-model")
        run_id = pipeline.run_id

        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(count=2, label="widget")):
            pipeline.execute(data="raw input", initial_context={})

        with Session(tracking_engine) as session:
            stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
            run = session.exec(stmt).first()

        assert run is not None, "PipelineRun row must exist after execute()"
        assert run.status == "completed"
        assert run.started_at is not None
        assert run.completed_at is not None
        assert run.step_count is not None and run.step_count >= 1
        assert run.total_time_ms is not None and run.total_time_ms >= 0

    def test_failed_execute_writes_failed_run(self, tracking_engine, seeded_tracking_session):
        pipeline = TrackingPipeline(
            session=seeded_tracking_session,
            model="test-model",
            strategies=[BrokenStrategy()],
        )
        run_id = pipeline.run_id

        with pytest.raises(RuntimeError, match="intentional failure"):
            pipeline.execute(data="raw input", initial_context={})

        with Session(tracking_engine) as session:
            stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
            run = session.exec(stmt).first()

        assert run is not None, "PipelineRun row must exist after failed execute()"
        assert run.status == "failed"
        assert run.completed_at is not None

    def test_pre_generated_run_id_preserved(self, tracking_engine, seeded_tracking_session):
        custom_run_id = str(uuid.uuid4())
        pipeline = TrackingPipeline(
            session=seeded_tracking_session,
            model="test-model",
            run_id=custom_run_id,
        )

        assert pipeline.run_id == custom_run_id

        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(count=1, label="x")):
            pipeline.execute(data="input", initial_context={})

        with Session(tracking_engine) as session:
            stmt = select(PipelineRun).where(PipelineRun.run_id == custom_run_id)
            run = session.exec(stmt).first()

        assert run is not None, "PipelineRun must be stored under pre-generated run_id"
        assert run.run_id == custom_run_id

    def test_completed_run_has_pipeline_name(self, tracking_engine, seeded_tracking_session):
        pipeline = TrackingPipeline(session=seeded_tracking_session, model="test-model")

        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(count=1, label="g")):
            pipeline.execute(data="d", initial_context={})

        with Session(tracking_engine) as session:
            run = session.exec(
                select(PipelineRun).where(PipelineRun.run_id == pipeline.run_id)
            ).first()

        assert run.pipeline_name == "tracking"
