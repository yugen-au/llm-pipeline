"""
Tests for llm-pipeline.
"""
import pytest
from typing import List, Optional, ClassVar
from unittest.mock import MagicMock, patch
from sqlmodel import SQLModel, Field, Session, create_engine

from llm_pipeline import (
    PipelineConfig,
    LLMStep,
    LLMResultMixin,
    step_definition,
    PipelineStrategy,
    PipelineStrategies,
    StepDefinition,
    PipelineContext,
    PipelineExtraction,
    PipelineDatabaseRegistry,
    PipelineStepState,
    PipelineRunInstance,
    ArrayValidationConfig,
    ValidationContext,
    init_pipeline_db,
)
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.prompts.service import PromptService
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.types import StepCallParams
from llm_pipeline.events import PipelineEventEmitter, PipelineEvent, PipelineStarted


# ---------- Test Domain Models ----------

class Widget(SQLModel, table=True):
    __tablename__ = "widgets"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str


# ---------- Test Step Instructions ----------

class WidgetDetectionInstructions(LLMResultMixin):
    widget_count: int
    category: str

    example: ClassVar[dict] = {
        "widget_count": 5,
        "category": "electronics",
        "notes": "Found 5 widgets",
    }


class WidgetDetectionContext(PipelineContext):
    category: str


# ---------- Test Extraction ----------

class WidgetExtraction(PipelineExtraction, model=Widget):
    def default(self, results):
        instruction = results[0]
        widgets = []
        for i in range(instruction.widget_count):
            widgets.append(Widget(name=f"widget_{i}", category=instruction.category))
        return widgets


# ---------- Test Step ----------

@step_definition(
    instructions=WidgetDetectionInstructions,
    default_system_key="widget_detection.system_instruction",
    default_user_key="widget_detection.user_prompt",
    default_extractions=[WidgetExtraction],
    context=WidgetDetectionContext,
)
class WidgetDetectionStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [{"variables": {"data": self.pipeline.get_sanitized_data()}}]

    def process_instructions(self, instructions):
        instruction = instructions[0]
        return WidgetDetectionContext(category=instruction.category)


# ---------- Test Strategy ----------

class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [WidgetDetectionStep.create_definition()]


# ---------- Test Pipeline ----------

class TestRegistry(PipelineDatabaseRegistry, models=[Widget]):
    pass


class TestAgentRegistry(AgentRegistry, agents={
    "widget_detection": WidgetDetectionInstructions,
}):
    pass


class TestStrategies(PipelineStrategies, strategies=[DefaultStrategy]):
    pass


class TestPipeline(
    PipelineConfig,
    registry=TestRegistry,
    strategies=TestStrategies,
    agent_registry=TestAgentRegistry,
):
    pass


# ---------- Helpers ----------

def _make_widget_run_result(widget_count=3, category="gadgets"):
    """Build a MagicMock mimicking AgentRunResult for WidgetDetectionInstructions."""
    instruction = WidgetDetectionInstructions(
        widget_count=widget_count,
        category=category,
        confidence_score=0.95,
        notes=f"Found {widget_count} {category}",
    )
    mock_result = MagicMock()
    mock_result.output = instruction
    return mock_result


# ---------- Fixtures ----------

@pytest.fixture
def engine():
    """Create in-memory SQLite engine with all tables."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as sess:
        yield sess


@pytest.fixture
def seeded_session(session):
    """Session with prompts seeded."""
    session.add(Prompt(
        prompt_key="widget_detection.system_instruction",
        prompt_name="Widget Detection System",
        prompt_type="system",
        category="test",
        step_name="widget_detection",
        content="You are a widget detector.",
        version="1.0",
    ))
    session.add(Prompt(
        prompt_key="widget_detection.user_prompt",
        prompt_name="Widget Detection User",
        prompt_type="user",
        category="test",
        step_name="widget_detection",
        content="Analyze this data: {data}",
        version="1.0",
    ))
    session.commit()
    return session


# ---------- Tests ----------

class TestImports:
    """Verify all public API imports work."""

    def test_core_imports(self):
        from llm_pipeline import PipelineConfig, LLMStep, LLMResultMixin, step_definition
        assert PipelineConfig is not None
        assert LLMStep is not None

    def test_db_imports(self):
        from llm_pipeline.db import init_pipeline_db, Prompt
        assert Prompt is not None

    def test_prompts_imports(self):
        from llm_pipeline.prompts import PromptService, VariableResolver
        assert PromptService is not None


class TestLLMResultMixin:
    def test_create_failure(self):
        result = WidgetDetectionInstructions.create_failure(
            "test error", widget_count=0, category=""
        )
        assert result.confidence_score == 0.0
        assert "Failed: test error" in result.notes

    def test_get_example(self):
        example = WidgetDetectionInstructions.get_example()
        assert example is not None
        assert example.widget_count == 5
        assert example.category == "electronics"

    def test_example_not_required(self):
        """LLMResultMixin works without example defined."""
        class SimpleInstructions(LLMResultMixin):
            value: int
        assert SimpleInstructions.get_example() is None


class TestArrayValidationConfig:
    def test_defaults(self):
        config = ArrayValidationConfig(input_array=["a", "b"])
        assert config.match_field == "original"
        assert config.allow_reordering is True


class TestValidationContext:
    def test_access(self):
        ctx = ValidationContext(num_rows=10, num_cols=5)
        assert ctx["num_rows"] == 10
        assert ctx.get("num_cols") == 5
        assert "num_rows" in ctx
        assert ctx.to_dict() == {"num_rows": 10, "num_cols": 5}


class TestPipelineNaming:
    def test_valid_pipeline_naming(self):
        """Pipeline, Registry, and Strategies must follow naming conventions."""
        pipeline = TestPipeline(
            session=Session(create_engine("sqlite:///:memory:")),
            model="test-model",
        )
        assert pipeline.pipeline_name == "test"

    def test_invalid_pipeline_name(self):
        with pytest.raises(ValueError, match="must end with 'Pipeline'"):
            class BadName(PipelineConfig, registry=TestRegistry, strategies=TestStrategies):
                pass


class TestPipelineInit:
    def test_auto_sqlite(self, tmp_path, monkeypatch):
        """Pipeline auto-creates SQLite when no engine/session provided."""
        monkeypatch.setenv("LLM_PIPELINE_DB", str(tmp_path / "test.db"))
        pipeline = TestPipeline(model="test-model")
        assert pipeline._real_session is not None
        assert pipeline._owns_session is True
        pipeline.close()

    def test_explicit_session(self, session):
        pipeline = TestPipeline(session=session, model="test-model")
        assert pipeline._owns_session is False
        assert pipeline._real_session is session

    def test_explicit_engine(self, engine):
        pipeline = TestPipeline(engine=engine, model="test-model")
        assert pipeline._owns_session is True
        pipeline.close()

    def test_requires_agent_registry_for_execute(self, session):
        """Pipeline without AGENT_REGISTRY raises on execute."""
        class NoAgentRegistry(PipelineDatabaseRegistry, models=[Widget]):
            pass

        class NoAgentStrategies(PipelineStrategies, strategies=[DefaultStrategy]):
            pass

        class NoAgentPipeline(PipelineConfig, registry=NoAgentRegistry, strategies=NoAgentStrategies):
            pass

        pipeline = NoAgentPipeline(session=session, model="test-model")
        with pytest.raises(ValueError, match="agent_registry"):
            pipeline.execute(data="test", initial_context={})


class TestPipelineExecution:
    def test_full_execution(self, engine, seeded_session):
        """Full pipeline: execute with mocked agent, verify extractions and state."""
        pipeline = TestPipeline(session=seeded_session, model="test-model")

        with patch("pydantic_ai.Agent.run_sync", return_value=_make_widget_run_result(widget_count=3, category="gadgets")):
            result = pipeline.execute(data="some raw data", initial_context={})

        # Verify chaining
        assert result is pipeline

        # Verify context was set
        assert pipeline.context["category"] == "gadgets"

        # Verify extractions
        widgets = pipeline.get_extractions(Widget)
        assert len(widgets) == 3
        assert all(w.category == "gadgets" for w in widgets)
        assert widgets[0].name == "widget_0"

        # Verify instructions stored
        assert "widget_detection" in pipeline._instructions

    def test_save_persists_to_db(self, engine, seeded_session):
        pipeline = TestPipeline(session=seeded_session, model="test-model")

        with patch("pydantic_ai.Agent.run_sync", return_value=_make_widget_run_result(widget_count=2, category="tools")):
            pipeline.execute(data="data", initial_context={})

        results = pipeline.save()

        assert results["widgets_saved"] == 2

        # Verify persisted
        from sqlmodel import select
        widgets = seeded_session.exec(select(Widget)).all()
        assert len(widgets) == 2

    def test_step_state_saved(self, engine, seeded_session):
        """Verify PipelineStepState is created after execution."""
        pipeline = TestPipeline(session=seeded_session, model="test-model")

        with patch("pydantic_ai.Agent.run_sync", return_value=_make_widget_run_result(widget_count=1, category="test")):
            pipeline.execute(data="data", initial_context={})

        from sqlmodel import select
        states = seeded_session.exec(select(PipelineStepState)).all()
        assert len(states) == 1
        assert states[0].pipeline_name == "test"
        assert states[0].step_name == "widget_detection"


class TestPromptService:
    def test_get_prompt(self, seeded_session):
        service = PromptService(seeded_session)
        content = service.get_prompt(
            "widget_detection.system_instruction", prompt_type="system"
        )
        assert "widget detector" in content

    def test_prompt_not_found(self, session):
        service = PromptService(session)
        with pytest.raises(ValueError, match="Prompt not found"):
            service.get_prompt("nonexistent")

    def test_prompt_fallback(self, session):
        service = PromptService(session)
        content = service.get_prompt("nonexistent", fallback="default text")
        assert content == "default text"

    def test_format_user_prompt(self, seeded_session):
        service = PromptService(seeded_session)
        result = service.get_user_prompt(
            "widget_detection.user_prompt",
            variables={"data": "hello world"},
        )
        assert "hello world" in result


class TestPromptLoader:
    def test_extract_variables(self):
        from llm_pipeline.prompts.loader import extract_variables_from_content
        vars = extract_variables_from_content("Hello {name}, your {item} is ready")
        assert vars == ["name", "item"]

    def test_extract_no_variables(self):
        from llm_pipeline.prompts.loader import extract_variables_from_content
        vars = extract_variables_from_content("No variables here")
        assert vars == []


class TestInitPipelineDb:
    def test_creates_tables(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_PIPELINE_DB", str(tmp_path / "test.db"))
        engine = init_pipeline_db()
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "pipeline_step_states" in tables
        assert "pipeline_run_instances" in tables
        assert "prompts" in tables


# ---------- Mock Event Emitter ----------

class MockEmitter:
    """Captures emitted events for test assertions."""

    def __init__(self):
        self.events: List[PipelineEvent] = []

    def emit(self, event: PipelineEvent) -> None:
        self.events.append(event)


# ---------- Event Emitter Tests ----------

class TestEventEmitter:
    """Tests for event_emitter parameter and _emit() on PipelineConfig."""

    def test_no_emitter_defaults_to_none(self):
        """PipelineConfig without event_emitter -> _event_emitter is None."""
        pipeline = TestPipeline(
            session=Session(create_engine("sqlite:///:memory:")),
            model="test-model",
        )
        assert pipeline._event_emitter is None

    def test_emitter_stored(self):
        """PipelineConfig with mock emitter -> _event_emitter is the mock."""
        emitter = MockEmitter()
        pipeline = TestPipeline(
            session=Session(create_engine("sqlite:///:memory:")),
            model="test-model",
            event_emitter=emitter,
        )
        assert pipeline._event_emitter is emitter

    def test_emit_noop_when_none(self):
        """_emit() with no emitter configured does not raise."""
        pipeline = TestPipeline(
            session=Session(create_engine("sqlite:///:memory:")),
            model="test-model",
        )
        event = PipelineStarted(run_id="test-run", pipeline_name="test")
        pipeline._emit(event)  # should not raise

    def test_emit_forwards_to_emitter(self):
        """_emit() forwards event to mock emitter's emit()."""
        emitter = MockEmitter()
        pipeline = TestPipeline(
            session=Session(create_engine("sqlite:///:memory:")),
            model="test-model",
            event_emitter=emitter,
        )
        event = PipelineStarted(run_id="test-run", pipeline_name="test")
        pipeline._emit(event)

        assert len(emitter.events) == 1
        assert emitter.events[0] is event

    def test_mock_emitter_satisfies_protocol(self):
        """MockEmitter satisfies PipelineEventEmitter protocol (runtime_checkable)."""
        emitter = MockEmitter()
        assert isinstance(emitter, PipelineEventEmitter)
