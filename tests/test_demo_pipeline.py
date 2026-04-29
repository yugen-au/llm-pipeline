"""
Tests for llm_pipelines: TextAnalyzerPipeline and supporting classes.

Covers under the Bind-based contract:
- Import verification for all public classes
- Model field validation (TopicItem, Topic, Instructions, Inputs)
- Strategy behavior (can_handle, get_bindings)
- TopicExtraction pathway dispatch (from_topic_extraction)
- YAML prompt discovery
"""
from types import SimpleNamespace
from typing import ClassVar, Optional

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from llm_pipeline.inputs import PipelineInputData, StepInputs
from llm_pipeline.step import LLMResultMixin


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
    """All public classes importable from llm_pipelines and submodules."""

    def test_import_text_analyzer_pipeline(self):
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        assert TextAnalyzerPipeline is not None

    def test_import_all_classes_from_convention_modules(self):
        from llm_pipelines.schemas.text_analyzer import (
            SentimentAnalysisInputs,
            SentimentAnalysisInstructions,
            SummaryInputs,
            SummaryInstructions,
            TextAnalyzerInputData,
            Topic,
            TopicExtractionInputs,
            TopicExtractionInstructions,
            TopicItem,
        )
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
        from llm_pipelines.steps.topic_extraction import TopicExtractionStep
        from llm_pipelines.steps.summary import SummaryStep
        from llm_pipelines.pipelines.text_analyzer import (
            DefaultStrategy,
            TextAnalyzerPipeline,
            TextAnalyzerRegistry,
            TextAnalyzerStrategies,
        )
        for cls in [
            TextAnalyzerInputData, TopicItem, Topic, TextAnalyzerRegistry,
            SentimentAnalysisInstructions, TopicExtractionInstructions, SummaryInstructions,
            SentimentAnalysisInputs, TopicExtractionInputs, SummaryInputs,
            TopicExtraction, SentimentAnalysisStep, TopicExtractionStep, SummaryStep,
            DefaultStrategy, TextAnalyzerStrategies,
            TextAnalyzerPipeline,
        ]:
            assert cls is not None

    def test_pipeline_importable_from_convention_dir(self):
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        assert TextAnalyzerPipeline is not None


# ---------------------------------------------------------------------------
# TextAnalyzerInputData
# ---------------------------------------------------------------------------

class TestTextAnalyzerInputData:
    def test_is_pipeline_input_data_subclass(self):
        from llm_pipelines.schemas.text_analyzer import TextAnalyzerInputData
        assert issubclass(TextAnalyzerInputData, PipelineInputData)

    def test_has_text_field(self):
        from llm_pipelines.schemas.text_analyzer import TextAnalyzerInputData
        obj = TextAnalyzerInputData(text="hello world")
        assert obj.text == "hello world"

    def test_missing_text_raises(self):
        from llm_pipelines.schemas.text_analyzer import TextAnalyzerInputData
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TextAnalyzerInputData()


# ---------------------------------------------------------------------------
# TopicItem model
# ---------------------------------------------------------------------------

class TestTopicItem:
    def test_has_name_and_relevance(self):
        from llm_pipelines.schemas.text_analyzer import TopicItem
        ti = TopicItem(name="machine learning", relevance=0.95)
        assert ti.name == "machine learning"
        assert ti.relevance == 0.95

    def test_relevance_is_float(self):
        from llm_pipelines.schemas.text_analyzer import TopicItem
        ti = TopicItem(name="ai", relevance=0.5)
        assert isinstance(ti.relevance, float)

    def test_missing_fields_raises(self):
        from llm_pipelines.schemas.text_analyzer import TopicItem
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TopicItem(name="topic_only")


# ---------------------------------------------------------------------------
# Topic SQLModel table
# ---------------------------------------------------------------------------

class TestTopicModel:
    def test_tablename(self):
        from llm_pipelines.schemas.text_analyzer import Topic
        assert Topic.__tablename__ == "demo_topics"

    def test_columns(self):
        from llm_pipelines.schemas.text_analyzer import Topic
        cols = {c.name for c in Topic.__table__.columns}
        assert cols == {"id", "name", "relevance", "run_id"}

    def test_id_is_primary_key(self):
        from llm_pipelines.schemas.text_analyzer import Topic
        id_col = Topic.__table__.c["id"]
        assert id_col.primary_key

    def test_id_default_none(self):
        from llm_pipelines.schemas.text_analyzer import Topic
        t = Topic(name="ml", relevance=0.8, run_id="run-1")
        assert t.id is None

    def test_instantiation(self):
        from llm_pipelines.schemas.text_analyzer import Topic
        t = Topic(name="data science", relevance=0.75, run_id="abc-123")
        assert t.name == "data science"
        assert t.relevance == 0.75
        assert t.run_id == "abc-123"


# ---------------------------------------------------------------------------
# Instructions classes
# ---------------------------------------------------------------------------

class TestSentimentAnalysisInstructions:
    def test_inherits_llm_result_mixin(self):
        from llm_pipelines.schemas.text_analyzer import SentimentAnalysisInstructions
        assert issubclass(SentimentAnalysisInstructions, LLMResultMixin)

    def test_safe_defaults(self):
        from llm_pipelines.schemas.text_analyzer import SentimentAnalysisInstructions
        obj = SentimentAnalysisInstructions()
        assert obj.sentiment == ""
        assert obj.explanation == ""

    def test_has_example(self):
        from llm_pipelines.schemas.text_analyzer import SentimentAnalysisInstructions
        ex = SentimentAnalysisInstructions.get_example()
        assert ex is not None
        assert ex.sentiment == "positive"

    def test_class_name_matches_convention(self):
        from llm_pipelines.schemas.text_analyzer import SentimentAnalysisInstructions
        assert SentimentAnalysisInstructions.__name__ == "SentimentAnalysisInstructions"


class TestTopicExtractionInstructions:
    def test_inherits_llm_result_mixin(self):
        from llm_pipelines.schemas.text_analyzer import TopicExtractionInstructions
        assert issubclass(TopicExtractionInstructions, LLMResultMixin)

    def test_safe_defaults(self):
        from llm_pipelines.schemas.text_analyzer import TopicExtractionInstructions
        obj = TopicExtractionInstructions()
        assert obj.topics == []
        assert obj.primary_topic == ""

    def test_has_example(self):
        from llm_pipelines.schemas.text_analyzer import TopicExtractionInstructions
        ex = TopicExtractionInstructions.get_example()
        assert ex is not None
        assert ex.primary_topic == "machine learning"

    def test_class_name_matches_convention(self):
        from llm_pipelines.schemas.text_analyzer import TopicExtractionInstructions
        assert TopicExtractionInstructions.__name__ == "TopicExtractionInstructions"


class TestSummaryInstructions:
    def test_inherits_llm_result_mixin(self):
        from llm_pipelines.schemas.text_analyzer import SummaryInstructions
        assert issubclass(SummaryInstructions, LLMResultMixin)

    def test_safe_defaults(self):
        from llm_pipelines.schemas.text_analyzer import SummaryInstructions
        obj = SummaryInstructions()
        assert obj.summary == ""

    def test_has_example(self):
        from llm_pipelines.schemas.text_analyzer import SummaryInstructions
        ex = SummaryInstructions.get_example()
        assert ex is not None
        assert "summary" in ex.model_dump()

    def test_class_name_matches_convention(self):
        from llm_pipelines.schemas.text_analyzer import SummaryInstructions
        assert SummaryInstructions.__name__ == "SummaryInstructions"


# ---------------------------------------------------------------------------
# StepInputs classes
# ---------------------------------------------------------------------------

class TestSentimentAnalysisInputs:
    def test_is_stepinputs_subclass(self):
        from llm_pipelines.schemas.text_analyzer import SentimentAnalysisInputs
        assert issubclass(SentimentAnalysisInputs, StepInputs)

    def test_has_text_field(self):
        from llm_pipelines.schemas.text_analyzer import SentimentAnalysisInputs
        obj = SentimentAnalysisInputs(text="hello")
        assert obj.text == "hello"

    def test_class_name_matches_convention(self):
        from llm_pipelines.schemas.text_analyzer import SentimentAnalysisInputs
        assert SentimentAnalysisInputs.__name__ == "SentimentAnalysisInputs"


class TestTopicExtractionInputs:
    def test_is_stepinputs_subclass(self):
        from llm_pipelines.schemas.text_analyzer import TopicExtractionInputs
        assert issubclass(TopicExtractionInputs, StepInputs)

    def test_instantiation(self):
        from llm_pipelines.schemas.text_analyzer import TopicExtractionInputs
        obj = TopicExtractionInputs(text="hello", sentiment="positive")
        assert obj.text == "hello"
        assert obj.sentiment == "positive"


class TestSummaryInputs:
    def test_is_stepinputs_subclass(self):
        from llm_pipelines.schemas.text_analyzer import SummaryInputs
        assert issubclass(SummaryInputs, StepInputs)

    def test_instantiation(self):
        from llm_pipelines.schemas.text_analyzer import SummaryInputs
        obj = SummaryInputs(text="hello", sentiment="positive", primary_topic="ml")
        assert obj.text == "hello"
        assert obj.sentiment == "positive"
        assert obj.primary_topic == "ml"


# ---------------------------------------------------------------------------
# DefaultStrategy
# ---------------------------------------------------------------------------

class TestDefaultStrategy:
    def test_name_is_default(self):
        from llm_pipelines.pipelines.text_analyzer import DefaultStrategy
        assert DefaultStrategy.NAME == "default"

    def test_can_handle_always_returns_true(self):
        from llm_pipelines.pipelines.text_analyzer import DefaultStrategy
        s = DefaultStrategy()
        assert s.can_handle({}) is True
        assert s.can_handle({"sentiment": "positive"}) is True
        assert s.can_handle({"any": "value"}) is True

    def test_get_bindings_returns_three_binds(self):
        from llm_pipelines.pipelines.text_analyzer import DefaultStrategy
        s = DefaultStrategy()
        bindings = s.get_bindings()
        assert len(bindings) == 3

    def test_bindings_are_bind_instances(self):
        from llm_pipeline.wiring import Bind
        from llm_pipelines.pipelines.text_analyzer import DefaultStrategy
        s = DefaultStrategy()
        for bind in s.get_bindings():
            assert isinstance(bind, Bind)

    def test_step_order(self):
        from llm_pipelines.pipelines.text_analyzer import DefaultStrategy
        from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
        from llm_pipelines.steps.summary import SummaryStep
        from llm_pipelines.steps.topic_extraction import TopicExtractionStep
        s = DefaultStrategy()
        bindings = s.get_bindings()
        assert bindings[0].step is SentimentAnalysisStep
        assert bindings[1].step is TopicExtractionStep
        assert bindings[2].step is SummaryStep

    def test_topic_extraction_has_nested_extraction_bind(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.pipelines.text_analyzer import DefaultStrategy
        s = DefaultStrategy()
        topic_bind = s.get_bindings()[1]
        assert len(topic_bind.extractions) == 1
        assert topic_bind.extractions[0].extraction is TopicExtraction

    def test_bindings_validate_statically(self):
        """validate_bindings walks every source and asserts field/step refs resolve."""
        from llm_pipeline.wiring import validate_bindings
        from llm_pipelines.pipelines.text_analyzer import DefaultStrategy
        from llm_pipelines.schemas.text_analyzer import TextAnalyzerInputData
        s = DefaultStrategy()
        # Should not raise.
        validate_bindings(s.get_bindings(), input_cls=TextAnalyzerInputData)


# ---------------------------------------------------------------------------
# TopicExtraction pathway dispatch
# ---------------------------------------------------------------------------

class TestTopicExtraction:
    def _mock_pipeline(self):
        from llm_pipelines.schemas.text_analyzer import Topic
        registry = SimpleNamespace(
            get_models=lambda: [Topic],
            __name__="MockRegistry",
        )
        return SimpleNamespace(REGISTRY=registry)

    def test_has_single_pathway(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        assert len(TopicExtraction._pathway_dispatch) == 1
        assert TopicExtraction.FromTopicExtractionInputs in TopicExtraction._pathway_dispatch

    def test_converts_topic_items_to_topics(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.schemas.text_analyzer import Topic, TopicItem

        extraction = TopicExtraction(self._mock_pipeline())
        inputs = TopicExtraction.FromTopicExtractionInputs(
            topics=[TopicItem(name="ml", relevance=0.9)],
            run_id="test-run",
        )
        result = extraction.from_topic_extraction(inputs)
        assert len(result) == 1
        assert isinstance(result[0], Topic)

    def test_sets_run_id_from_inputs(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.schemas.text_analyzer import TopicItem

        extraction = TopicExtraction(self._mock_pipeline())
        inputs = TopicExtraction.FromTopicExtractionInputs(
            topics=[TopicItem(name="ai", relevance=0.8)],
            run_id="run-abc-123",
        )
        result = extraction.from_topic_extraction(inputs)
        assert result[0].run_id == "run-abc-123"

    def test_preserves_name_and_relevance(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.schemas.text_analyzer import TopicItem

        extraction = TopicExtraction(self._mock_pipeline())
        inputs = TopicExtraction.FromTopicExtractionInputs(
            topics=[
                TopicItem(name="data science", relevance=0.75),
                TopicItem(name="statistics", relevance=0.6),
            ],
            run_id="r1",
        )
        result = extraction.from_topic_extraction(inputs)
        assert len(result) == 2
        assert result[0].name == "data science"
        assert result[0].relevance == 0.75
        assert result[1].name == "statistics"
        assert result[1].relevance == 0.6

    def test_empty_topics_returns_empty_list(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction

        extraction = TopicExtraction(self._mock_pipeline())
        inputs = TopicExtraction.FromTopicExtractionInputs(topics=[], run_id="r1")
        result = extraction.from_topic_extraction(inputs)
        assert result == []

    def test_extract_dispatches_to_from_topic_extraction(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.schemas.text_analyzer import TopicItem

        extraction = TopicExtraction(self._mock_pipeline())
        inputs = TopicExtraction.FromTopicExtractionInputs(
            topics=[TopicItem(name="ai", relevance=0.5)],
            run_id="r1",
        )
        result = extraction.extract(inputs)
        assert len(result) == 1
        assert result[0].name == "ai"


# ---------------------------------------------------------------------------
# YAML prompt discovery
# ---------------------------------------------------------------------------

class TestYamlPrompts:
    """Demo prompts live in llm-pipeline-prompts/*.yaml as historical
    artifacts — they're no longer loaded at startup (Phase E moved
    prompt storage to Phoenix), but the files stay around as a
    bootstrap source for ``migrate_prompts_to_phoenix.py``."""

    def test_yaml_files_exist(self):
        from pathlib import Path
        prompts_dir = Path(__file__).resolve().parent.parent / "llm-pipeline-prompts"
        assert (prompts_dir / "sentiment_analysis.yaml").exists()
        assert (prompts_dir / "topic_extraction.yaml").exists()
        assert (prompts_dir / "summary.yaml").exists()


# ---------------------------------------------------------------------------
# Entry point discovery
# ---------------------------------------------------------------------------

class TestEntryPoint:
    def test_text_analyzer_entry_point_discoverable(self):
        import importlib.metadata
        eps = list(importlib.metadata.entry_points(group="llm_pipeline.pipelines"))
        names = [ep.name for ep in eps]
        assert "text_analyzer" in names

    def test_entry_point_points_to_correct_module(self):
        import importlib.metadata
        eps = {ep.name: ep for ep in importlib.metadata.entry_points(group="llm_pipeline.pipelines")}
        # importlib_metadata backport may return stale metadata from user site-packages
        value = eps["text_analyzer"].value
        assert value in (
            "llm_pipelines.pipelines.text_analyzer:TextAnalyzerPipeline",
            "llm_pipeline.demo:TextAnalyzerPipeline",  # stale backport cache
        )


# ---------------------------------------------------------------------------
# TextAnalyzerPipeline class-level attributes
# ---------------------------------------------------------------------------

class TestTextAnalyzerPipelineConfig:
    def test_has_input_data_class_var(self):
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        from llm_pipelines.schemas.text_analyzer import TextAnalyzerInputData
        assert TextAnalyzerPipeline.INPUT_DATA is TextAnalyzerInputData

    def test_no_seed_prompts_classmethod(self):
        """Demo prompts come from YAML now, no _seed_prompts needed."""
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        assert not hasattr(TextAnalyzerPipeline, "_seed_prompts")
