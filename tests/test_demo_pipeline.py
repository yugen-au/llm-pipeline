"""Tests for ``llm_pipelines``: ``TextAnalyzerPipeline`` and supporting classes.

Updated for the pydantic-graph-native shape:
- pipeline declares ``INPUT_DATA`` + ``nodes = [...]`` instead of
  ``PipelineConfig`` + strategies + registry
- steps subclass ``LLMStepNode``, extractions subclass ``ExtractionNode``
- the framework's compile-time validator runs at class-definition
  time and asserts edge resolution, naming conventions, etc.
"""
from typing import ClassVar

import pytest
from pydantic import ValidationError

from llm_pipeline.graph import (
    ExtractionNode,
    LLMStepNode,
    Pipeline,
    PipelineInputData,
    StepInputs,
)
from llm_pipeline.graph import LLMResultMixin


# ---------------------------------------------------------------------------
# Import verification
# ---------------------------------------------------------------------------


class TestDemoImports:
    """All public classes importable from ``llm_pipelines`` and submodules."""

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
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline

        for cls in [
            TextAnalyzerInputData, TopicItem, Topic,
            SentimentAnalysisInstructions, TopicExtractionInstructions,
            SummaryInstructions,
            SentimentAnalysisInputs, TopicExtractionInputs, SummaryInputs,
            TopicExtraction, SentimentAnalysisStep, TopicExtractionStep,
            SummaryStep,
            TextAnalyzerPipeline,
        ]:
            assert cls is not None


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
# Step + extraction node shape
# ---------------------------------------------------------------------------


class TestStepNodes:
    """Each step is an ``LLMStepNode`` subclass with the expected shape."""

    def test_sentiment_step_subclasses_llmstepnode(self):
        from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
        from llm_pipelines.schemas.text_analyzer import (
            SentimentAnalysisInputs,
            SentimentAnalysisInstructions,
        )
        assert issubclass(SentimentAnalysisStep, LLMStepNode)
        assert SentimentAnalysisStep.INPUTS is SentimentAnalysisInputs
        assert SentimentAnalysisStep.INSTRUCTIONS is SentimentAnalysisInstructions
        assert SentimentAnalysisStep.inputs_spec is not None

    def test_topic_step_subclasses_llmstepnode(self):
        from llm_pipelines.steps.topic_extraction import TopicExtractionStep
        from llm_pipelines.schemas.text_analyzer import (
            TopicExtractionInputs,
            TopicExtractionInstructions,
        )
        assert issubclass(TopicExtractionStep, LLMStepNode)
        assert TopicExtractionStep.INPUTS is TopicExtractionInputs
        assert TopicExtractionStep.INSTRUCTIONS is TopicExtractionInstructions

    def test_summary_step_subclasses_llmstepnode(self):
        from llm_pipelines.steps.summary import SummaryStep
        from llm_pipelines.schemas.text_analyzer import (
            SummaryInputs,
            SummaryInstructions,
        )
        assert issubclass(SummaryStep, LLMStepNode)
        assert SummaryStep.INPUTS is SummaryInputs
        assert SummaryStep.INSTRUCTIONS is SummaryInstructions


class TestTopicExtractionNode:
    """``TopicExtraction`` is an ``ExtractionNode`` that produces ``Topic`` rows."""

    def test_subclasses_extraction_node(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        assert issubclass(TopicExtraction, ExtractionNode)

    def test_model_is_topic(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.schemas.text_analyzer import Topic
        assert TopicExtraction.MODEL is Topic

    def test_source_step_is_topic_extraction_step(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.steps.topic_extraction import TopicExtractionStep
        assert TopicExtraction.source_step is TopicExtractionStep

    def test_extract_converts_topic_items_to_topics(self):
        from llm_pipelines.extractions.text_analyzer import (
            FromTopicExtractionInputs,
            TopicExtraction,
        )
        from llm_pipelines.schemas.text_analyzer import Topic, TopicItem

        node = TopicExtraction()
        rows = node.extract(FromTopicExtractionInputs(
            topics=[TopicItem(name="ml", relevance=0.9)],
            run_id="run-abc",
        ))
        assert len(rows) == 1
        assert isinstance(rows[0], Topic)
        assert rows[0].name == "ml"
        assert rows[0].relevance == 0.9
        assert rows[0].run_id == "run-abc"

    def test_extract_empty_returns_empty_list(self):
        from llm_pipelines.extractions.text_analyzer import (
            FromTopicExtractionInputs,
            TopicExtraction,
        )
        node = TopicExtraction()
        rows = node.extract(FromTopicExtractionInputs(topics=[], run_id="r1"))
        assert rows == []


# ---------------------------------------------------------------------------
# YAML prompt discovery (legacy artifact)
# ---------------------------------------------------------------------------


class TestYamlPrompts:
    """Demo prompts live in ``llm-pipeline-prompts/*.yaml`` as historical
    artifacts — they're no longer loaded at startup (Phoenix owns
    prompts), but the files remain as a bootstrap source for
    ``migrate_prompts_to_phoenix.py``."""

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
        value = eps["text_analyzer"].value
        assert value in (
            "llm_pipelines.pipelines.text_analyzer:TextAnalyzerPipeline",
            "llm_pipeline.demo:TextAnalyzerPipeline",  # stale backport cache
        )


# ---------------------------------------------------------------------------
# TextAnalyzerPipeline class-level attributes
# ---------------------------------------------------------------------------


class TestTextAnalyzerPipelineConfig:
    def test_subclasses_pipeline(self):
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        assert issubclass(TextAnalyzerPipeline, Pipeline)

    def test_has_input_data_class_var(self):
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        from llm_pipelines.schemas.text_analyzer import TextAnalyzerInputData
        assert TextAnalyzerPipeline.INPUT_DATA is TextAnalyzerInputData

    def test_nodes_list_in_topological_order(self):
        from llm_pipelines.extractions.text_analyzer import TopicExtraction
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
        from llm_pipelines.steps.summary import SummaryStep
        from llm_pipelines.steps.topic_extraction import TopicExtractionStep

        assert TextAnalyzerPipeline.nodes == [
            SentimentAnalysisStep,
            TopicExtractionStep,
            TopicExtraction,
            SummaryStep,
        ]

    def test_start_node_defaults_to_first(self):
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
        assert TextAnalyzerPipeline.start_node is SentimentAnalysisStep

    def test_graph_compiles(self):
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        graph = TextAnalyzerPipeline.graph()
        assert graph is not None
        assert "SentimentAnalysisStep" in graph.node_defs
        assert "TopicExtractionStep" in graph.node_defs
        assert "TopicExtraction" in graph.node_defs
        assert "SummaryStep" in graph.node_defs

    def test_pipeline_name_is_snake_case(self):
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        assert TextAnalyzerPipeline.pipeline_name() == "text_analyzer"

    def test_no_legacy_attrs(self):
        """``REGISTRY`` / ``STRATEGIES`` are gone in the graph-native shape."""
        from llm_pipelines.pipelines.text_analyzer import TextAnalyzerPipeline
        # Sanity: legacy attributes shouldn't leak from the old shape.
        assert not hasattr(TextAnalyzerPipeline, "STRATEGIES")
        assert not hasattr(TextAnalyzerPipeline, "REGISTRY")
