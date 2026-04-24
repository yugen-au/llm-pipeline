"""Tests for evaluators= param on step_definition and auto FieldMatch evaluators."""
import pytest
from unittest.mock import MagicMock
from pydantic import BaseModel, Field

from llm_pipeline.evals.evaluators import FieldMatchEvaluator, build_auto_evaluators


# -- helpers --


class FakeOutput:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_ctx(output, expected_output):
    """Build a minimal EvaluatorContext-like mock."""
    ctx = MagicMock()
    ctx.output = output
    ctx.expected_output = expected_output
    return ctx


# -- FieldMatchEvaluator tests --


class TestFieldMatchEvaluator:
    def test_skip_when_expected_none(self):
        ev = FieldMatchEvaluator(field_name="sentiment")
        result = ev.evaluate(_make_ctx(FakeOutput(sentiment="positive"), None))
        assert result == {}

    def test_skip_when_field_missing_from_expected_dict(self):
        ev = FieldMatchEvaluator(field_name="sentiment")
        result = ev.evaluate(_make_ctx(FakeOutput(sentiment="positive"), {"score": 0.9}))
        assert result == {}

    def test_true_when_match(self):
        ev = FieldMatchEvaluator(field_name="sentiment")
        result = ev.evaluate(_make_ctx(FakeOutput(sentiment="positive"), {"sentiment": "positive"}))
        assert result is True

    def test_false_when_mismatch(self):
        ev = FieldMatchEvaluator(field_name="sentiment")
        result = ev.evaluate(_make_ctx(FakeOutput(sentiment="positive"), {"sentiment": "negative"}))
        assert result is False

    def test_match_with_numeric_field(self):
        ev = FieldMatchEvaluator(field_name="score")
        assert ev.evaluate(_make_ctx(FakeOutput(score=0.8), {"score": 0.8})) is True
        assert ev.evaluate(_make_ctx(FakeOutput(score=0.8), {"score": 0.9})) is False

    def test_output_missing_field_returns_false(self):
        ev = FieldMatchEvaluator(field_name="missing_field")
        result = ev.evaluate(_make_ctx(FakeOutput(), {"missing_field": "value"}))
        assert result is False

    def test_repr_contains_field_name(self):
        ev = FieldMatchEvaluator(field_name="sentiment")
        assert "sentiment" in repr(ev)


# -- build_auto_evaluators tests --


class SampleInstructions(BaseModel):
    sentiment: str = Field(description="Sentiment label")
    score: float = Field(description="Confidence score")
    notes: str | None = Field(default=None, description="Notes")


class TestBuildAutoEvaluators:
    def test_returns_one_per_field(self):
        evaluators = build_auto_evaluators(SampleInstructions)
        field_names = [ev.field_name for ev in evaluators]
        assert field_names == ["sentiment", "score", "notes"]

    def test_all_are_field_match_evaluators(self):
        evaluators = build_auto_evaluators(SampleInstructions)
        assert all(isinstance(ev, FieldMatchEvaluator) for ev in evaluators)

    def test_empty_model(self):
        class EmptyInstructions(BaseModel):
            pass

        evaluators = build_auto_evaluators(EmptyInstructions)
        assert evaluators == []


# -- step_definition evaluators= param tests --


class TestStepDefinitionEvaluatorsParam:
    """Test that @step_definition(evaluators=[...]) stores evaluators on StepDefinition."""

    def test_evaluators_stored_on_class(self):
        from llm_pipeline.step import step_definition, LLMStep

        class MockEval:
            pass

        class MockInstructions(BaseModel):
            value: str = ""

        MockInstructions.__name__ = "EvalTestInstructions"

        @step_definition(instructions=MockInstructions, evaluators=[MockEval])
        class EvalTestStep(LLMStep):
            def prepare_calls(self):
                return []

        assert EvalTestStep._step_evaluators == [MockEval]

    def test_evaluators_passed_to_step_definition(self):
        from llm_pipeline.step import step_definition, LLMStep

        class MockEval:
            pass

        class MockInstructions(BaseModel):
            value: str = ""

        MockInstructions.__name__ = "EvalDefInstructions"

        @step_definition(instructions=MockInstructions, evaluators=[MockEval])
        class EvalDefStep(LLMStep):
            def prepare_calls(self):
                return []

        step_def = EvalDefStep.create_definition()
        assert step_def.evaluators == [MockEval]

    def test_no_evaluators_default_empty(self):
        from llm_pipeline.step import step_definition, LLMStep

        class NoEvalInstructions(BaseModel):
            value: str = ""

        NoEvalInstructions.__name__ = "NoEvalInstructions"

        @step_definition(instructions=NoEvalInstructions)
        class NoEvalStep(LLMStep):
            def prepare_calls(self):
                return []

        assert NoEvalStep._step_evaluators == []
        step_def = NoEvalStep.create_definition()
        assert step_def.evaluators == []
