"""
Tests for llm_pipeline/demo package: TextAnalyzerPipeline and supporting classes.

Covers:
- Import verification for all public classes
- Model field validation (TopicItem, Topic, Instructions)
- Context class instantiation and PipelineContext inheritance
- Strategy behavior (can_handle, get_steps)
- TopicExtraction.default() bridging TopicItem -> Topic
- seed_prompts idempotency and table creation
"""
import pytest
from typing import ClassVar, Optional
from sqlmodel import SQLModel, Session, create_engine, select

from llm_pipeline.context import PipelineContext, PipelineInputData
from llm_pipeline.step import LLMResultMixin
from llm_pipeline.db.prompt import Prompt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as sess:
        yield sess


# ---------------------------------------------------------------------------
# Import verification
# ---------------------------------------------------------------------------

class TestDemoImports:
    """All public classes importable from llm_pipeline.demo and submodules."""

    def test_import_text_analyzer_pipeline_from_demo(self):
        from llm_pipeline.demo import TextAnalyzerPipeline
        assert TextAnalyzerPipeline is not None

    def test_import_all_classes_from_pipeline_module(self):
        from llm_pipeline.demo.pipeline import (
            TextAnalyzerInputData,
            TopicItem,
            Topic,
            TextAnalyzerRegistry,
            SentimentAnalysisInstructions,
            TopicExtractionInstructions,
            SummaryInstructions,
            SentimentAnalysisContext,
            TopicExtractionContext,
            SummaryContext,
            TopicExtraction,
            SentimentAnalysisStep,
            TopicExtractionStep,
            SummaryStep,
            DefaultStrategy,
            TextAnalyzerStrategies,
            TextAnalyzerPipeline,
        )
        for cls in [
            TextAnalyzerInputData, TopicItem, Topic, TextAnalyzerRegistry,
            SentimentAnalysisInstructions, TopicExtractionInstructions, SummaryInstructions,
            SentimentAnalysisContext, TopicExtractionContext, SummaryContext,
            TopicExtraction, SentimentAnalysisStep, TopicExtractionStep, SummaryStep,
            DefaultStrategy, TextAnalyzerStrategies,
            TextAnalyzerPipeline,
        ]:
            assert cls is not None

    def test_import_seed_prompts_from_prompts_module(self):
        from llm_pipeline.demo.prompts import seed_prompts, ALL_PROMPTS
        assert callable(seed_prompts)
        assert isinstance(ALL_PROMPTS, list)

    def test_demo_init_exports_text_analyzer_pipeline(self):
        import llm_pipeline.demo as demo_pkg
        assert hasattr(demo_pkg, "TextAnalyzerPipeline")
        assert hasattr(demo_pkg, "__all__")
        assert "TextAnalyzerPipeline" in demo_pkg.__all__


# ---------------------------------------------------------------------------
# TextAnalyzerInputData
# ---------------------------------------------------------------------------

class TestTextAnalyzerInputData:
    def test_is_pipeline_input_data_subclass(self):
        from llm_pipeline.demo.pipeline import TextAnalyzerInputData
        assert issubclass(TextAnalyzerInputData, PipelineInputData)

    def test_has_text_field(self):
        from llm_pipeline.demo.pipeline import TextAnalyzerInputData
        obj = TextAnalyzerInputData(text="hello world")
        assert obj.text == "hello world"

    def test_missing_text_raises(self):
        from llm_pipeline.demo.pipeline import TextAnalyzerInputData
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TextAnalyzerInputData()


# ---------------------------------------------------------------------------
# TopicItem model
# ---------------------------------------------------------------------------

class TestTopicItem:
    def test_has_name_and_relevance(self):
        from llm_pipeline.demo.pipeline import TopicItem
        ti = TopicItem(name="machine learning", relevance=0.95)
        assert ti.name == "machine learning"
        assert ti.relevance == 0.95

    def test_relevance_is_float(self):
        from llm_pipeline.demo.pipeline import TopicItem
        ti = TopicItem(name="ai", relevance=0.5)
        assert isinstance(ti.relevance, float)

    def test_missing_fields_raises(self):
        from llm_pipeline.demo.pipeline import TopicItem
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TopicItem(name="topic_only")


# ---------------------------------------------------------------------------
# Topic SQLModel table
# ---------------------------------------------------------------------------

class TestTopicModel:
    def test_tablename(self):
        from llm_pipeline.demo.pipeline import Topic
        assert Topic.__tablename__ == "demo_topics"

    def test_columns(self):
        from llm_pipeline.demo.pipeline import Topic
        cols = {c.name for c in Topic.__table__.columns}
        assert cols == {"id", "name", "relevance", "run_id"}

    def test_id_is_primary_key(self):
        from llm_pipeline.demo.pipeline import Topic
        id_col = Topic.__table__.c["id"]
        assert id_col.primary_key

    def test_id_default_none(self):
        from llm_pipeline.demo.pipeline import Topic
        t = Topic(name="ml", relevance=0.8, run_id="run-1")
        assert t.id is None

    def test_instantiation(self):
        from llm_pipeline.demo.pipeline import Topic
        t = Topic(name="data science", relevance=0.75, run_id="abc-123")
        assert t.name == "data science"
        assert t.relevance == 0.75
        assert t.run_id == "abc-123"


# ---------------------------------------------------------------------------
# Instructions classes
# ---------------------------------------------------------------------------

class TestSentimentAnalysisInstructions:
    def test_inherits_llm_result_mixin(self):
        from llm_pipeline.demo.pipeline import SentimentAnalysisInstructions
        assert issubclass(SentimentAnalysisInstructions, LLMResultMixin)

    def test_safe_defaults(self):
        from llm_pipeline.demo.pipeline import SentimentAnalysisInstructions
        obj = SentimentAnalysisInstructions()
        assert obj.sentiment == ""
        assert obj.explanation == ""

    def test_has_example(self):
        from llm_pipeline.demo.pipeline import SentimentAnalysisInstructions
        ex = SentimentAnalysisInstructions.get_example()
        assert ex is not None
        assert ex.sentiment == "positive"

    def test_class_name_matches_convention(self):
        from llm_pipeline.demo.pipeline import SentimentAnalysisInstructions
        assert SentimentAnalysisInstructions.__name__ == "SentimentAnalysisInstructions"


class TestTopicExtractionInstructions:
    def test_inherits_llm_result_mixin(self):
        from llm_pipeline.demo.pipeline import TopicExtractionInstructions
        assert issubclass(TopicExtractionInstructions, LLMResultMixin)

    def test_safe_defaults(self):
        from llm_pipeline.demo.pipeline import TopicExtractionInstructions
        obj = TopicExtractionInstructions()
        assert obj.topics == []
        assert obj.primary_topic == ""

    def test_has_example(self):
        from llm_pipeline.demo.pipeline import TopicExtractionInstructions
        ex = TopicExtractionInstructions.get_example()
        assert ex is not None
        assert ex.primary_topic == "machine learning"

    def test_class_name_matches_convention(self):
        from llm_pipeline.demo.pipeline import TopicExtractionInstructions
        assert TopicExtractionInstructions.__name__ == "TopicExtractionInstructions"


class TestSummaryInstructions:
    def test_inherits_llm_result_mixin(self):
        from llm_pipeline.demo.pipeline import SummaryInstructions
        assert issubclass(SummaryInstructions, LLMResultMixin)

    def test_safe_defaults(self):
        from llm_pipeline.demo.pipeline import SummaryInstructions
        obj = SummaryInstructions()
        assert obj.summary == ""

    def test_has_example(self):
        from llm_pipeline.demo.pipeline import SummaryInstructions
        ex = SummaryInstructions.get_example()
        assert ex is not None
        assert "summary" in ex.model_dump()

    def test_class_name_matches_convention(self):
        from llm_pipeline.demo.pipeline import SummaryInstructions
        assert SummaryInstructions.__name__ == "SummaryInstructions"


# ---------------------------------------------------------------------------
# Context classes
# ---------------------------------------------------------------------------

class TestSentimentAnalysisContext:
    def test_is_pipeline_context_subclass(self):
        from llm_pipeline.demo.pipeline import SentimentAnalysisContext
        assert issubclass(SentimentAnalysisContext, PipelineContext)

    def test_instantiation(self):
        from llm_pipeline.demo.pipeline import SentimentAnalysisContext
        ctx = SentimentAnalysisContext(sentiment="positive")
        assert ctx.sentiment == "positive"

    def test_class_name_matches_convention(self):
        from llm_pipeline.demo.pipeline import SentimentAnalysisContext
        assert SentimentAnalysisContext.__name__ == "SentimentAnalysisContext"


class TestTopicExtractionContext:
    def test_is_pipeline_context_subclass(self):
        from llm_pipeline.demo.pipeline import TopicExtractionContext
        assert issubclass(TopicExtractionContext, PipelineContext)

    def test_instantiation(self):
        from llm_pipeline.demo.pipeline import TopicExtractionContext
        ctx = TopicExtractionContext(primary_topic="ml", topics=["ml", "ai"])
        assert ctx.primary_topic == "ml"
        assert ctx.topics == ["ml", "ai"]

    def test_topics_is_list_of_strings(self):
        from llm_pipeline.demo.pipeline import TopicExtractionContext
        ctx = TopicExtractionContext(primary_topic="x", topics=["a", "b", "c"])
        assert all(isinstance(t, str) for t in ctx.topics)


class TestSummaryContext:
    def test_is_pipeline_context_subclass(self):
        from llm_pipeline.demo.pipeline import SummaryContext
        assert issubclass(SummaryContext, PipelineContext)

    def test_instantiation(self):
        from llm_pipeline.demo.pipeline import SummaryContext
        ctx = SummaryContext(summary="A concise summary.")
        assert ctx.summary == "A concise summary."


# ---------------------------------------------------------------------------
# DefaultStrategy
# ---------------------------------------------------------------------------

class TestDefaultStrategy:
    def test_name_is_default(self):
        from llm_pipeline.demo.pipeline import DefaultStrategy
        assert DefaultStrategy.NAME == "default"

    def test_can_handle_always_returns_true(self):
        from llm_pipeline.demo.pipeline import DefaultStrategy
        s = DefaultStrategy()
        assert s.can_handle({}) is True
        assert s.can_handle({"sentiment": "positive"}) is True
        assert s.can_handle({"any": "value"}) is True

    def test_get_steps_returns_three_steps(self):
        from llm_pipeline.demo.pipeline import DefaultStrategy
        s = DefaultStrategy()
        steps = s.get_steps()
        assert len(steps) == 3

    def test_step_names_ordered(self):
        from llm_pipeline.demo.pipeline import DefaultStrategy
        s = DefaultStrategy()
        steps = s.get_steps()
        names = [st.step_name for st in steps]
        assert names == ["sentiment_analysis", "topic_extraction", "summary"]

    def test_steps_are_step_definitions(self):
        from llm_pipeline.demo.pipeline import DefaultStrategy
        from llm_pipeline.strategy import StepDefinition
        s = DefaultStrategy()
        steps = s.get_steps()
        for step in steps:
            assert isinstance(step, StepDefinition)


# ---------------------------------------------------------------------------
# TopicExtraction.default()
# ---------------------------------------------------------------------------

class TestTopicExtraction:
    def _make_extraction(self, run_id="test-run"):
        from llm_pipeline.demo.pipeline import TopicExtraction

        mock = type("MockPipeline", (), {"run_id": run_id})()
        extraction = object.__new__(TopicExtraction)
        extraction.pipeline = mock
        return extraction

    def test_converts_topic_items_to_topics(self):
        from llm_pipeline.demo.pipeline import TopicItem, TopicExtractionInstructions, Topic
        extraction = self._make_extraction()
        instructions = [TopicExtractionInstructions(
            topics=[TopicItem(name="ml", relevance=0.9)],
            primary_topic="ml",
        )]
        result = extraction.default(instructions)
        assert len(result) == 1
        assert isinstance(result[0], Topic)

    def test_sets_run_id(self):
        from llm_pipeline.demo.pipeline import TopicItem, TopicExtractionInstructions
        extraction = self._make_extraction(run_id="run-abc-123")
        instructions = [TopicExtractionInstructions(
            topics=[TopicItem(name="ai", relevance=0.8)],
            primary_topic="ai",
        )]
        result = extraction.default(instructions)
        assert result[0].run_id == "run-abc-123"

    def test_preserves_name_and_relevance(self):
        from llm_pipeline.demo.pipeline import TopicItem, TopicExtractionInstructions
        extraction = self._make_extraction()
        instructions = [TopicExtractionInstructions(
            topics=[
                TopicItem(name="data science", relevance=0.75),
                TopicItem(name="statistics", relevance=0.6),
            ],
            primary_topic="data science",
        )]
        result = extraction.default(instructions)
        assert len(result) == 2
        assert result[0].name == "data science"
        assert result[0].relevance == 0.75
        assert result[1].name == "statistics"
        assert result[1].relevance == 0.6

    def test_empty_topics_returns_empty_list(self):
        from llm_pipeline.demo.pipeline import TopicExtractionInstructions
        extraction = self._make_extraction()
        instructions = [TopicExtractionInstructions(topics=[], primary_topic="")]
        result = extraction.default(instructions)
        assert result == []

    def test_does_not_override_extract(self):
        from llm_pipeline.demo.pipeline import TopicExtraction
        from llm_pipeline.extraction import PipelineExtraction
        # default() must be defined; extract() must not be overridden
        assert "default" in TopicExtraction.__dict__
        assert "extract" not in TopicExtraction.__dict__


# ---------------------------------------------------------------------------
# seed_prompts idempotency and table creation
# ---------------------------------------------------------------------------

class TestSeedPrompts:
    @pytest.fixture
    def seed_engine(self):
        eng = create_engine("sqlite:///:memory:", echo=False)
        SQLModel.metadata.create_all(eng)
        return eng

    def test_creates_demo_topics_table(self, seed_engine):
        from llm_pipeline.demo.prompts import seed_prompts
        from llm_pipeline.demo.pipeline import TextAnalyzerPipeline
        from sqlalchemy import inspect
        seed_prompts(TextAnalyzerPipeline, seed_engine)
        inspector = inspect(seed_engine)
        assert "demo_topics" in inspector.get_table_names()

    def test_inserts_six_prompts(self, seed_engine):
        from llm_pipeline.demo.prompts import seed_prompts
        from llm_pipeline.demo.pipeline import TextAnalyzerPipeline
        seed_prompts(TextAnalyzerPipeline, seed_engine)
        with Session(seed_engine) as session:
            prompts = session.exec(select(Prompt)).all()
        assert len(prompts) == 6

    def test_idempotent_double_seed(self, seed_engine):
        from llm_pipeline.demo.prompts import seed_prompts
        from llm_pipeline.demo.pipeline import TextAnalyzerPipeline
        seed_prompts(TextAnalyzerPipeline, seed_engine)
        seed_prompts(TextAnalyzerPipeline, seed_engine)
        with Session(seed_engine) as session:
            prompts = session.exec(select(Prompt)).all()
        assert len(prompts) == 6

    def test_seeds_system_and_user_for_each_step(self, seed_engine):
        from llm_pipeline.demo.prompts import seed_prompts
        from llm_pipeline.demo.pipeline import TextAnalyzerPipeline
        seed_prompts(TextAnalyzerPipeline, seed_engine)
        with Session(seed_engine) as session:
            prompts = session.exec(select(Prompt)).all()
        keys_by_type = {
            "system": {p.prompt_key for p in prompts if p.prompt_type == "system"},
            "user": {p.prompt_key for p in prompts if p.prompt_type == "user"},
        }
        expected_keys = {"sentiment_analysis", "topic_extraction", "summary"}
        assert keys_by_type["system"] == expected_keys
        assert keys_by_type["user"] == expected_keys

    def test_all_prompts_constant_has_six_entries(self):
        from llm_pipeline.demo.prompts import ALL_PROMPTS
        assert len(ALL_PROMPTS) == 6


# ---------------------------------------------------------------------------
# Entry point discovery
# ---------------------------------------------------------------------------

class TestEntryPoint:
    def test_text_analyzer_entry_point_discoverable(self):
        import importlib.metadata
        eps = list(importlib.metadata.entry_points(group="llm_pipeline.pipelines"))
        names = [ep.name for ep in eps]
        assert "text_analyzer" in names

    def test_entry_point_loads_text_analyzer_pipeline(self):
        import importlib.metadata
        from llm_pipeline.demo.pipeline import TextAnalyzerPipeline
        eps = {ep.name: ep for ep in importlib.metadata.entry_points(group="llm_pipeline.pipelines")}
        loaded = eps["text_analyzer"].load()
        assert loaded is TextAnalyzerPipeline


# ---------------------------------------------------------------------------
# TextAnalyzerPipeline class-level attributes
# ---------------------------------------------------------------------------

class TestTextAnalyzerPipelineConfig:
    def test_has_input_data_class_var(self):
        from llm_pipeline.demo.pipeline import TextAnalyzerPipeline, TextAnalyzerInputData
        assert TextAnalyzerPipeline.INPUT_DATA is TextAnalyzerInputData

    def test_has_seed_prompts_classmethod(self):
        from llm_pipeline.demo.pipeline import TextAnalyzerPipeline
        assert callable(getattr(TextAnalyzerPipeline, "seed_prompts", None))

