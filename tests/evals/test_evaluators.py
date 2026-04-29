"""Tests for the auto-evaluator builder + custom evaluator registry."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import ClassVar

import pytest
from pydantic_evals.evaluators import Evaluator

from llm_pipeline.evals.evaluators import (
    FieldMatchEvaluator,
    build_auto_evaluators,
    build_case_evaluators,
    clear_evaluator_registry,
    get_evaluator,
    list_evaluators,
    register_evaluator,
)
from llm_pipeline.graph.instructions import LLMResultMixin


# ---------------------------------------------------------------------------
# Sample instructions class
# ---------------------------------------------------------------------------


class _SentimentInstructions(LLMResultMixin):
    label: str = ""
    score: float = 0.0

    example: ClassVar[dict] = {"label": "positive", "score": 0.9}


# ---------------------------------------------------------------------------
# build_auto_evaluators
# ---------------------------------------------------------------------------


class TestBuildAutoEvaluators:
    def test_emits_one_per_declared_field(self):
        evaluators = build_auto_evaluators(_SentimentInstructions)
        names = sorted(e.field_name for e in evaluators)
        # confidence_score + notes are skipped (LLMResultMixin operational
        # fields, not ground-truth comparable).
        assert names == ["label", "score"]

    def test_skips_confidence_and_notes(self):
        evaluators = build_auto_evaluators(_SentimentInstructions)
        names = {e.field_name for e in evaluators}
        assert "confidence_score" not in names
        assert "notes" not in names

    def test_empty_model_returns_empty_list(self):
        class _Empty(LLMResultMixin):
            pass

        evaluators = build_auto_evaluators(_Empty)
        assert evaluators == []


# ---------------------------------------------------------------------------
# FieldMatchEvaluator
# ---------------------------------------------------------------------------


def _make_ctx(*, output, expected_output):
    """Build a minimal EvaluatorContext-shaped object for FieldMatch evals."""
    return SimpleNamespace(output=output, expected_output=expected_output)


class TestFieldMatchEvaluator:
    def test_match_returns_true_keyed_by_field_name(self):
        ev = FieldMatchEvaluator(field_name="label")
        ctx = _make_ctx(output={"label": "x"}, expected_output={"label": "x"})
        assert ev.evaluate(ctx) == {"label": True}

    def test_mismatch_returns_false(self):
        ev = FieldMatchEvaluator(field_name="label")
        ctx = _make_ctx(output={"label": "x"}, expected_output={"label": "y"})
        assert ev.evaluate(ctx) == {"label": False}

    def test_skips_when_expected_output_missing(self):
        ev = FieldMatchEvaluator(field_name="label")
        ctx = _make_ctx(output={"label": "x"}, expected_output=None)
        assert ev.evaluate(ctx) == {}

    def test_skips_when_field_absent_on_expected(self):
        ev = FieldMatchEvaluator(field_name="label")
        ctx = _make_ctx(output={"label": "x"}, expected_output={"other": "y"})
        assert ev.evaluate(ctx) == {}

    def test_label_override_swaps_result_key(self):
        ev = FieldMatchEvaluator(field_name="label", label="sentiment_match")
        ctx = _make_ctx(output={"label": "x"}, expected_output={"label": "x"})
        result = ev.evaluate(ctx)
        assert "sentiment_match" in result
        assert "label" not in result

    def test_works_with_pydantic_models(self):
        class _Out(LLMResultMixin):
            label: str = ""

        ev = FieldMatchEvaluator(field_name="label")
        ctx = _make_ctx(
            output=_Out(label="x"),
            expected_output=_Out(label="x"),
        )
        assert ev.evaluate(ctx) == {"label": True}


# ---------------------------------------------------------------------------
# Custom evaluator registry
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_evaluator_registry()
    yield
    clear_evaluator_registry()


class TestEvaluatorRegistry:
    def test_register_and_lookup(self):
        @register_evaluator(name="length_under_280")
        @dataclass
        class _LengthEval(Evaluator):
            def evaluate(self, ctx):
                return len(str(ctx.output)) <= 280

        assert get_evaluator("length_under_280") is _LengthEval
        assert "length_under_280" in list_evaluators()

    def test_default_name_is_class_name(self):
        @register_evaluator()
        @dataclass
        class _NamedEval(Evaluator):
            def evaluate(self, ctx):
                return True

        assert get_evaluator("_NamedEval") is _NamedEval

    def test_duplicate_name_rejected(self):
        @register_evaluator(name="dup")
        @dataclass
        class _A(Evaluator):
            def evaluate(self, ctx):
                return True

        with pytest.raises(ValueError, match="already registered"):
            @register_evaluator(name="dup")
            @dataclass
            class _B(Evaluator):
                def evaluate(self, ctx):
                    return False

    def test_re_registering_same_class_is_idempotent(self):
        @dataclass
        class _Idem(Evaluator):
            def evaluate(self, ctx):
                return True

        register_evaluator(name="idem")(_Idem)
        # Second call with same class -> no error, still resolves.
        register_evaluator(name="idem")(_Idem)
        assert get_evaluator("idem") is _Idem

    def test_get_evaluator_missing_raises_keyerror(self):
        with pytest.raises(KeyError):
            get_evaluator("missing")

    def test_register_rejects_non_evaluator(self):
        class _NotAnEvaluator:
            pass

        with pytest.raises(TypeError):
            register_evaluator(name="x")(_NotAnEvaluator)


# ---------------------------------------------------------------------------
# build_case_evaluators
# ---------------------------------------------------------------------------


class TestBuildCaseEvaluators:
    def test_auto_only(self):
        evaluators = build_case_evaluators(_SentimentInstructions, None)
        names = sorted(e.field_name for e in evaluators)
        assert names == ["label", "score"]

    def test_auto_plus_custom(self):
        @register_evaluator(name="custom_check")
        @dataclass
        class _Custom(Evaluator):
            def evaluate(self, ctx):
                return True

        evaluators = build_case_evaluators(
            _SentimentInstructions, ["custom_check"],
        )
        # 2 auto + 1 custom
        assert len(evaluators) == 3
        assert any(isinstance(e, _Custom) for e in evaluators)

    def test_no_instructions_class_returns_custom_only(self):
        @register_evaluator(name="solo")
        @dataclass
        class _Solo(Evaluator):
            def evaluate(self, ctx):
                return True

        evaluators = build_case_evaluators(None, ["solo"])
        assert len(evaluators) == 1
        assert isinstance(evaluators[0], _Solo)

    def test_unknown_custom_raises(self):
        with pytest.raises(KeyError):
            build_case_evaluators(_SentimentInstructions, ["missing"])
