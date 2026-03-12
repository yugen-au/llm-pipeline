"""Unit tests for llm_pipeline.consensus module.

Covers:
1. instructions_match() and _smart_compare() utility functions
2. MajorityVoteStrategy: should_continue, select
3. ConfidenceWeightedStrategy: confidence_score usage, fallback, division-by-zero guard
4. AdaptiveStrategy: threshold lowering at 70%, select returns largest group first member
5. SoftVoteStrategy: picks highest avg confidence group, confidence equals avg
6. Integration smoke test: import works without circular imports
"""
import pytest
from typing import ClassVar, Optional
from pydantic import BaseModel

from llm_pipeline import LLMResultMixin
from llm_pipeline.consensus import (
    ConsensusResult,
    ConsensusStrategy,
    MajorityVoteStrategy,
    ConfidenceWeightedStrategy,
    AdaptiveStrategy,
    SoftVoteStrategy,
    instructions_match,
    _smart_compare,
)


# ---------------------------------------------------------------------------
# Mock instruction models
# ---------------------------------------------------------------------------


class NumericInstr(LLMResultMixin):
    """Instruction with a numeric content field for consensus grouping tests."""
    count: int
    example: ClassVar[dict] = {"count": 1, "notes": "test"}


class MultiFieldInstr(LLMResultMixin):
    """Instruction with multiple content fields."""
    count: int
    category: str
    example: ClassVar[dict] = {"count": 1, "category": "a", "notes": "ok"}


class PlainModel(BaseModel):
    """Non-mixin model for testing plain BaseModel comparisons."""
    value: int


class ConfidentInstr(LLMResultMixin):
    """Instruction where confidence_score is meaningful."""
    count: int
    example: ClassVar[dict] = {"count": 1, "confidence_score": 0.9, "notes": "test"}


def _make_instr(count: int, confidence: float = 0.9, notes: str = "test") -> NumericInstr:
    return NumericInstr(count=count, confidence_score=confidence, notes=notes)


def _make_confident(count: int, confidence: float) -> ConfidentInstr:
    return ConfidentInstr(count=count, confidence_score=confidence, notes="ok")


# ---------------------------------------------------------------------------
# instructions_match / _smart_compare
# ---------------------------------------------------------------------------


class TestSmartCompare:
    """Unit tests for _smart_compare() standalone function."""

    def test_same_int_matches(self):
        assert _smart_compare(5, 5) is True

    def test_different_int_does_not_match(self):
        assert _smart_compare(5, 6) is False

    def test_same_float_matches(self):
        assert _smart_compare(1.5, 1.5) is True

    def test_different_float_does_not_match(self):
        assert _smart_compare(1.5, 2.5) is False

    def test_string_always_matches(self):
        # String fields are lenient - any string value is considered matching
        assert _smart_compare("hello", "world") is True

    def test_none_always_matches(self):
        assert _smart_compare(None, None) is True
        assert _smart_compare(None, 5) is True
        assert _smart_compare(5, None) is True

    def test_mixin_field_always_matches(self):
        # mixin_fields set causes field to be ignored regardless of value
        assert _smart_compare(0.1, 0.9, field_name="confidence_score", mixin_fields={"confidence_score", "notes"}) is True

    def test_non_mixin_numeric_field_compares_value(self):
        assert _smart_compare(3, 3, field_name="count", mixin_fields={"confidence_score", "notes"}) is True
        assert _smart_compare(3, 4, field_name="count", mixin_fields={"confidence_score", "notes"}) is False

    def test_list_same_length_same_values(self):
        assert _smart_compare([1, 2], [1, 2]) is True

    def test_list_different_length(self):
        assert _smart_compare([1, 2], [1, 2, 3]) is False

    def test_list_different_values(self):
        assert _smart_compare([1, 2], [1, 3]) is False

    def test_dict_same_keys_same_values(self):
        assert _smart_compare({"a": 1}, {"a": 1}) is True

    def test_dict_different_values(self):
        assert _smart_compare({"a": 1}, {"a": 2}) is False

    def test_dict_different_keys(self):
        assert _smart_compare({"a": 1}, {"b": 1}) is False


class TestInstructionsMatch:
    """Unit tests for instructions_match() public function."""

    def test_same_count_matches(self):
        a = _make_instr(count=5)
        b = _make_instr(count=5)
        assert instructions_match(a, b) is True

    def test_different_count_does_not_match(self):
        a = _make_instr(count=5)
        b = _make_instr(count=6)
        assert instructions_match(a, b) is False

    def test_string_field_lenient(self):
        # category is a string field -> always matches regardless of value
        a = MultiFieldInstr(count=1, category="foo", confidence_score=0.9, notes="x")
        b = MultiFieldInstr(count=1, category="bar", confidence_score=0.8, notes="y")
        assert instructions_match(a, b) is True

    def test_mixin_fields_skipped(self):
        # confidence_score and notes are LLMResultMixin fields -> ignored in comparison
        a = _make_instr(count=3, confidence=0.1, notes="totally different")
        b = _make_instr(count=3, confidence=0.99, notes="also different")
        assert instructions_match(a, b) is True

    def test_mixin_field_diff_does_not_cause_mismatch(self):
        a = _make_instr(count=7, confidence=0.0, notes=None)
        b = _make_instr(count=7, confidence=1.0, notes="something")
        assert instructions_match(a, b) is True

    def test_count_diff_overrides_mixin_match(self):
        # Even if mixin fields match, differing count causes mismatch
        a = _make_instr(count=1, confidence=0.9, notes="ok")
        b = _make_instr(count=2, confidence=0.9, notes="ok")
        assert instructions_match(a, b) is False

    def test_plain_model_compares_by_value(self):
        # PlainModel has no LLMResultMixin -> all fields compared
        a = PlainModel(value=10)
        b = PlainModel(value=10)
        c = PlainModel(value=11)
        assert instructions_match(a, b) is True
        assert instructions_match(a, c) is False

    def test_symmetric(self):
        a = _make_instr(count=4)
        b = _make_instr(count=5)
        assert instructions_match(a, b) == instructions_match(b, a)

    def test_reflexive(self):
        a = _make_instr(count=99)
        assert instructions_match(a, a) is True


# ---------------------------------------------------------------------------
# Helpers: build simple result_groups from instruction lists
# ---------------------------------------------------------------------------


def _build_groups(results):
    """Simple O(n^2) grouper using instructions_match for test purposes."""
    groups = []
    for r in results:
        placed = False
        for group in groups:
            if instructions_match(r, group[0]):
                group.append(r)
                placed = True
                break
        if not placed:
            groups.append([r])
    return groups


# ---------------------------------------------------------------------------
# MajorityVoteStrategy
# ---------------------------------------------------------------------------


class TestMajorityVoteStrategyShouldContinue:
    """Tests for MajorityVoteStrategy.should_continue()."""

    def test_continues_when_no_group_reaches_threshold(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        results = [_make_instr(1), _make_instr(2)]
        groups = _build_groups(results)
        assert mv.should_continue(results, groups, attempt=2, max_attempts=5) is True

    def test_stops_when_threshold_reached(self):
        mv = MajorityVoteStrategy(threshold=2, max_attempts=5)
        results = [_make_instr(1), _make_instr(1)]
        groups = _build_groups(results)
        assert mv.should_continue(results, groups, attempt=2, max_attempts=5) is False

    def test_stops_when_attempts_exhausted(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=3)
        results = [_make_instr(1), _make_instr(2), _make_instr(3)]
        groups = _build_groups(results)
        assert mv.should_continue(results, groups, attempt=3, max_attempts=3) is False

    def test_stops_when_attempt_exceeds_max(self):
        mv = MajorityVoteStrategy(threshold=5, max_attempts=3)
        results = []
        groups = []
        assert mv.should_continue(results, groups, attempt=4, max_attempts=3) is False

    def test_continues_when_attempt_below_max_no_threshold(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        results = [_make_instr(1)]
        groups = _build_groups(results)
        assert mv.should_continue(results, groups, attempt=1, max_attempts=5) is True


class TestMajorityVoteStrategySelect:
    """Tests for MajorityVoteStrategy.select()."""

    def test_unanimous_confidence_is_1_0(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        results = [_make_instr(1), _make_instr(1), _make_instr(1)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert cr.confidence == 1.0
        assert cr.agreement_ratio == 1.0
        assert cr.consensus_reached is True
        assert cr.strategy_name == "majority_vote"

    def test_unanimous_result_is_first_group_member(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        first = _make_instr(1)
        results = [first, _make_instr(1), _make_instr(1)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert cr.result.count == 1

    def test_split_confidence_is_fraction_of_largest_group(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        # 2 matching + 1 different = largest group size 2 / total 3
        results = [_make_instr(1), _make_instr(1), _make_instr(2)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert abs(cr.confidence - 2/3) < 1e-9

    def test_split_consensus_not_reached_below_threshold(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        results = [_make_instr(1), _make_instr(1), _make_instr(2)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert cr.consensus_reached is False

    def test_consensus_reached_true_when_group_equals_threshold(self):
        mv = MajorityVoteStrategy(threshold=2, max_attempts=5)
        results = [_make_instr(1), _make_instr(1), _make_instr(2)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert cr.consensus_reached is True

    def test_total_attempts_reflects_result_count(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        results = [_make_instr(1), _make_instr(2), _make_instr(3)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert cr.total_attempts == 3

    def test_group_count_reflects_distinct_groups(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        results = [_make_instr(1), _make_instr(2), _make_instr(3)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert cr.group_count == 3

    def test_name_property(self):
        mv = MajorityVoteStrategy()
        assert mv.name == "majority_vote"

    def test_max_attempts_property(self):
        mv = MajorityVoteStrategy(threshold=2, max_attempts=7)
        assert mv.max_attempts == 7

    def test_threshold_property_is_float(self):
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        assert isinstance(mv.threshold, float)
        assert mv.threshold == 3.0

    def test_consensus_result_is_frozen(self):
        mv = MajorityVoteStrategy(threshold=2, max_attempts=3)
        results = [_make_instr(1), _make_instr(1)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        with pytest.raises(Exception):
            cr.confidence = 0.5


# ---------------------------------------------------------------------------
# ConfidenceWeightedStrategy
# ---------------------------------------------------------------------------


class TestConfidenceWeightedStrategyShouldContinue:
    """Tests for ConfidenceWeightedStrategy.should_continue()."""

    def test_continues_below_min_samples(self):
        cw = ConfidenceWeightedStrategy(threshold=0.8, min_samples=3, max_attempts=5)
        results = [_make_confident(1, 0.9), _make_confident(1, 0.9)]
        groups = _build_groups(results)
        assert cw.should_continue(results, groups, attempt=2, max_attempts=5) is True

    def test_stops_at_max_attempts(self):
        cw = ConfidenceWeightedStrategy(threshold=0.8, min_samples=2, max_attempts=3)
        results = [_make_confident(1, 0.5), _make_confident(2, 0.5), _make_confident(3, 0.5)]
        groups = _build_groups(results)
        assert cw.should_continue(results, groups, attempt=3, max_attempts=3) is False

    def test_stops_when_best_weighted_confidence_meets_threshold(self):
        # One group has very high confidence score -> weighted proportion crosses threshold
        cw = ConfidenceWeightedStrategy(threshold=0.8, min_samples=2, max_attempts=5)
        # Group1: 2 results with confidence 1.0 each = 2.0 weight
        # Group2: 1 result with confidence 0.0 = 0.0 weight
        # best / total = 2.0 / 2.0 = 1.0 >= 0.8 -> stop
        results = [
            _make_confident(1, 1.0),
            _make_confident(1, 1.0),
            _make_confident(2, 0.0),
        ]
        groups = _build_groups(results)
        assert cw.should_continue(results, groups, attempt=3, max_attempts=5) is False


class TestConfidenceWeightedStrategySelect:
    """Tests for ConfidenceWeightedStrategy.select()."""

    def test_uses_confidence_score_attribute(self):
        cw = ConfidenceWeightedStrategy(threshold=0.8, min_samples=2, max_attempts=5)
        # Group1 (count=1): sum score = 0.9 + 0.9 = 1.8
        # Group2 (count=2): sum score = 0.1
        results = [
            _make_confident(1, 0.9),
            _make_confident(1, 0.9),
            _make_confident(2, 0.1),
        ]
        groups = _build_groups(results)
        cr = cw.select(results, groups)
        # Winner is count=1 group
        assert cr.result.count == 1

    def test_fallback_to_0_5_when_no_confidence_score(self):
        cw = ConfidenceWeightedStrategy(threshold=0.8, min_samples=1, max_attempts=5)
        # PlainModel has no confidence_score -> getattr falls back to 0.5
        p1 = PlainModel(value=10)
        p2 = PlainModel(value=10)
        p3 = PlainModel(value=20)
        results = [p1, p2, p3]
        groups = _build_groups(results)
        cr = cw.select(results, groups)
        # All fallback to 0.5, group with 2 members wins (score 1.0 vs 0.5)
        assert cr.result.value == 10

    def test_confidence_normalized_0_to_1(self):
        cw = ConfidenceWeightedStrategy(threshold=0.8, min_samples=1, max_attempts=5)
        results = [_make_confident(1, 0.6), _make_confident(2, 0.4)]
        groups = _build_groups(results)
        cr = cw.select(results, groups)
        assert 0.0 <= cr.confidence <= 1.0

    def test_division_by_zero_guard_all_zero_scores(self):
        # All results have confidence_score=0 -> total_score=0, must not raise ZeroDivisionError
        cw = ConfidenceWeightedStrategy(threshold=0.8, min_samples=1, max_attempts=5)
        r1 = ConfidentInstr(count=1, confidence_score=0.0, notes="x")
        r2 = ConfidentInstr(count=2, confidence_score=0.0, notes="y")
        results = [r1, r2]
        groups = _build_groups(results)
        cr = cw.select(results, groups)
        assert 0.0 <= cr.confidence <= 1.0

    def test_consensus_reached_when_confidence_above_threshold(self):
        cw = ConfidenceWeightedStrategy(threshold=0.6, min_samples=1, max_attempts=5)
        # One group dominates with high scores
        results = [
            _make_confident(1, 0.9),
            _make_confident(1, 0.9),
            _make_confident(2, 0.1),
        ]
        groups = _build_groups(results)
        cr = cw.select(results, groups)
        # confidence = 1.8 / 1.9 ~= 0.947 >= 0.6
        assert cr.consensus_reached is True

    def test_selects_member_with_highest_individual_score(self):
        cw = ConfidenceWeightedStrategy(threshold=0.8, min_samples=1, max_attempts=5)
        # Two members in winning group - highest scorer should be selected
        low = ConfidentInstr(count=1, confidence_score=0.3, notes="low")
        high = ConfidentInstr(count=1, confidence_score=0.95, notes="high")
        other = ConfidentInstr(count=2, confidence_score=0.1, notes="other")
        results = [low, high, other]
        groups = _build_groups(results)
        cr = cw.select(results, groups)
        assert cr.result.confidence_score == 0.95

    def test_name_property(self):
        cw = ConfidenceWeightedStrategy()
        assert cw.name == "confidence_weighted"

    def test_max_attempts_property(self):
        cw = ConfidenceWeightedStrategy(max_attempts=8)
        assert cw.max_attempts == 8


# ---------------------------------------------------------------------------
# AdaptiveStrategy
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyShouldContinue:
    """Tests for AdaptiveStrategy.should_continue() and threshold lowering."""

    def test_uses_initial_threshold_below_70_percent(self):
        # At 60% of attempts, effective threshold = initial_threshold = 3
        ad = AdaptiveStrategy(initial_threshold=3, min_threshold=2, max_attempts=10)
        # attempt=6 / max_attempts=10 = 60% -> uses initial threshold 3
        results = [_make_instr(1), _make_instr(1)]  # group of 2, below threshold of 3
        groups = _build_groups(results)
        assert ad.should_continue(results, groups, attempt=6, max_attempts=10) is True

    def test_uses_min_threshold_above_70_percent(self):
        # At 80% of attempts, effective threshold = min_threshold = 2
        ad = AdaptiveStrategy(initial_threshold=3, min_threshold=2, max_attempts=10)
        # attempt=8 / max_attempts=10 = 80% -> uses min_threshold 2
        results = [_make_instr(1), _make_instr(1)]  # group of 2, meets min_threshold
        groups = _build_groups(results)
        assert ad.should_continue(results, groups, attempt=8, max_attempts=10) is False

    def test_stops_at_max_attempts(self):
        ad = AdaptiveStrategy(initial_threshold=3, min_threshold=2, max_attempts=5)
        results = [_make_instr(1), _make_instr(2), _make_instr(3)]
        groups = _build_groups(results)
        assert ad.should_continue(results, groups, attempt=5, max_attempts=5) is False

    def test_threshold_boundary_exactly_70_percent(self):
        # exactly 70% is NOT > 0.7, so initial threshold applies
        ad = AdaptiveStrategy(initial_threshold=3, min_threshold=2, max_attempts=10)
        # attempt=7 / max_attempts=10 = 70% -> uses initial threshold (> 0.7 is False)
        results = [_make_instr(1), _make_instr(1)]  # group of 2, below initial threshold 3
        groups = _build_groups(results)
        assert ad.should_continue(results, groups, attempt=7, max_attempts=10) is True


class TestAdaptiveStrategySelect:
    """Tests for AdaptiveStrategy.select()."""

    def test_returns_first_member_of_largest_group(self):
        ad = AdaptiveStrategy(initial_threshold=2, min_threshold=1, max_attempts=5)
        a = _make_instr(1)
        b = _make_instr(1)
        c = _make_instr(2)
        results = [a, b, c]
        groups = _build_groups(results)
        cr = ad.select(results, groups)
        assert cr.result.count == 1

    def test_confidence_is_fraction_of_largest_group(self):
        ad = AdaptiveStrategy(initial_threshold=2, min_threshold=1, max_attempts=5)
        results = [_make_instr(1), _make_instr(1), _make_instr(2)]
        groups = _build_groups(results)
        cr = ad.select(results, groups)
        assert abs(cr.confidence - 2/3) < 1e-9

    def test_consensus_reached_when_group_meets_effective_threshold(self):
        # With 2 results out of max_attempts=5, progress = 2/5 = 40% -> initial threshold 2
        ad = AdaptiveStrategy(initial_threshold=2, min_threshold=1, max_attempts=5)
        results = [_make_instr(1), _make_instr(1)]
        groups = _build_groups(results)
        cr = ad.select(results, groups)
        assert cr.consensus_reached is True

    def test_name_property(self):
        ad = AdaptiveStrategy()
        assert ad.name == "adaptive"

    def test_max_attempts_property(self):
        ad = AdaptiveStrategy(max_attempts=6)
        assert ad.max_attempts == 6

    def test_threshold_property_is_float_of_initial(self):
        ad = AdaptiveStrategy(initial_threshold=4, min_threshold=2, max_attempts=5)
        assert isinstance(ad.threshold, float)
        assert ad.threshold == 4.0


# ---------------------------------------------------------------------------
# SoftVoteStrategy
# ---------------------------------------------------------------------------


class TestSoftVoteStrategyShouldContinue:
    """Tests for SoftVoteStrategy.should_continue()."""

    def test_continues_below_min_samples(self):
        sv = SoftVoteStrategy(min_samples=3, confidence_floor=0.7, max_attempts=5)
        results = [_make_confident(1, 0.9)]
        groups = _build_groups(results)
        assert sv.should_continue(results, groups, attempt=1, max_attempts=5) is True

    def test_continues_when_best_avg_below_floor(self):
        sv = SoftVoteStrategy(min_samples=2, confidence_floor=0.8, max_attempts=5)
        results = [_make_confident(1, 0.5), _make_confident(2, 0.5), _make_confident(3, 0.5)]
        groups = _build_groups(results)
        # avg = 0.5 for each group < 0.8
        assert sv.should_continue(results, groups, attempt=3, max_attempts=5) is True

    def test_stops_when_avg_meets_floor(self):
        sv = SoftVoteStrategy(min_samples=2, confidence_floor=0.7, max_attempts=5)
        results = [_make_confident(1, 0.9), _make_confident(1, 0.9), _make_confident(2, 0.1)]
        groups = _build_groups(results)
        # best group avg = (0.9 + 0.9) / 2 = 0.9 >= 0.7 -> stop
        assert sv.should_continue(results, groups, attempt=3, max_attempts=5) is False

    def test_stops_at_max_attempts(self):
        sv = SoftVoteStrategy(min_samples=2, confidence_floor=0.7, max_attempts=3)
        results = [_make_confident(1, 0.1), _make_confident(2, 0.1), _make_confident(3, 0.1)]
        groups = _build_groups(results)
        assert sv.should_continue(results, groups, attempt=3, max_attempts=3) is False


class TestSoftVoteStrategySelect:
    """Tests for SoftVoteStrategy.select()."""

    def test_picks_group_with_highest_avg_confidence(self):
        sv = SoftVoteStrategy(min_samples=2, confidence_floor=0.7, max_attempts=5)
        # Group count=1: avg = (0.9 + 0.9) / 2 = 0.9
        # Group count=2: avg = 0.1
        results = [
            _make_confident(1, 0.9),
            _make_confident(1, 0.9),
            _make_confident(2, 0.1),
        ]
        groups = _build_groups(results)
        cr = sv.select(results, groups)
        assert cr.result.count == 1

    def test_confidence_equals_avg_confidence_of_winning_group(self):
        sv = SoftVoteStrategy(min_samples=1, confidence_floor=0.7, max_attempts=5)
        results = [
            _make_confident(1, 0.8),
            _make_confident(1, 0.6),
            _make_confident(2, 0.3),
        ]
        groups = _build_groups(results)
        cr = sv.select(results, groups)
        # Winning group is count=1: avg = (0.8 + 0.6) / 2 = 0.7
        assert abs(cr.confidence - 0.7) < 1e-9

    def test_confidence_in_0_1_range(self):
        sv = SoftVoteStrategy(min_samples=1, confidence_floor=0.7, max_attempts=5)
        results = [_make_confident(1, 0.5)]
        groups = _build_groups(results)
        cr = sv.select(results, groups)
        assert 0.0 <= cr.confidence <= 1.0

    def test_consensus_reached_when_avg_above_floor(self):
        sv = SoftVoteStrategy(min_samples=1, confidence_floor=0.7, max_attempts=5)
        results = [_make_confident(1, 0.9), _make_confident(1, 0.9)]
        groups = _build_groups(results)
        cr = sv.select(results, groups)
        assert cr.consensus_reached is True

    def test_consensus_not_reached_when_avg_below_floor(self):
        sv = SoftVoteStrategy(min_samples=1, confidence_floor=0.9, max_attempts=5)
        results = [_make_confident(1, 0.5), _make_confident(1, 0.5)]
        groups = _build_groups(results)
        cr = sv.select(results, groups)
        # avg = 0.5 < 0.9
        assert cr.consensus_reached is False

    def test_fallback_to_0_5_when_no_confidence_score(self):
        sv = SoftVoteStrategy(min_samples=1, confidence_floor=0.7, max_attempts=5)
        # PlainModel has no confidence_score attribute -> defaults to 0.5
        p1 = PlainModel(value=10)
        p2 = PlainModel(value=10)
        results = [p1, p2]
        groups = _build_groups(results)
        cr = sv.select(results, groups)
        # avg = 0.5, below floor 0.7
        assert cr.consensus_reached is False
        assert abs(cr.confidence - 0.5) < 1e-9

    def test_result_is_first_member_of_best_group(self):
        sv = SoftVoteStrategy(min_samples=1, confidence_floor=0.5, max_attempts=5)
        first = _make_confident(1, 0.9)
        results = [first, _make_confident(1, 0.8), _make_confident(2, 0.1)]
        groups = _build_groups(results)
        cr = sv.select(results, groups)
        # Both share count=1, first member of that group is 'first'
        assert cr.result.count == 1

    def test_name_property(self):
        sv = SoftVoteStrategy()
        assert sv.name == "soft_vote"

    def test_max_attempts_property(self):
        sv = SoftVoteStrategy(max_attempts=9)
        assert sv.max_attempts == 9

    def test_threshold_property(self):
        sv = SoftVoteStrategy(confidence_floor=0.65)
        assert sv.threshold == 0.65


# ---------------------------------------------------------------------------
# ConsensusResult validation
# ---------------------------------------------------------------------------


class TestConsensusResultValidation:
    """Verify Pydantic bounds enforcement on ConsensusResult."""

    def test_confidence_clamps_at_0(self):
        with pytest.raises(Exception):
            ConsensusResult(
                result=None, confidence=-0.1, strategy_name="x",
                agreement_ratio=0.5, total_attempts=1, group_count=1,
                consensus_reached=False,
            )

    def test_confidence_clamps_at_1(self):
        with pytest.raises(Exception):
            ConsensusResult(
                result=None, confidence=1.1, strategy_name="x",
                agreement_ratio=0.5, total_attempts=1, group_count=1,
                consensus_reached=False,
            )

    def test_agreement_ratio_clamps_below_0(self):
        with pytest.raises(Exception):
            ConsensusResult(
                result=None, confidence=0.5, strategy_name="x",
                agreement_ratio=-0.01, total_attempts=1, group_count=1,
                consensus_reached=False,
            )

    def test_valid_result_created(self):
        cr = ConsensusResult(
            result="ok", confidence=0.75, strategy_name="majority_vote",
            agreement_ratio=0.75, total_attempts=4, group_count=2,
            consensus_reached=True,
        )
        assert cr.confidence == 0.75
        assert cr.consensus_reached is True


# ---------------------------------------------------------------------------
# ConsensusStrategy ABC enforcement
# ---------------------------------------------------------------------------


class TestConsensusStrategyABC:
    """Verify ConsensusStrategy ABC cannot be instantiated without implementation."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            ConsensusStrategy()

    def test_partial_implementation_still_abstract(self):
        class Partial(ConsensusStrategy):
            @property
            def name(self):
                return "partial"
            # missing max_attempts, threshold, should_continue, select

        with pytest.raises(TypeError):
            Partial()


# ---------------------------------------------------------------------------
# Integration smoke test
# ---------------------------------------------------------------------------


class TestIntegration:
    """Smoke tests confirming module imports and basic end-to-end behaviour."""

    def test_import_no_circular(self):
        """llm_pipeline import succeeds without circular import errors."""
        import importlib
        import llm_pipeline
        importlib.reload(llm_pipeline)

    def test_strategies_exported_from_package(self):
        from llm_pipeline import (
            MajorityVoteStrategy,
            ConfidenceWeightedStrategy,
            AdaptiveStrategy,
            SoftVoteStrategy,
            ConsensusResult,
            ConsensusStrategy,
        )
        assert MajorityVoteStrategy
        assert ConfidenceWeightedStrategy
        assert AdaptiveStrategy
        assert SoftVoteStrategy
        assert ConsensusResult
        assert ConsensusStrategy

    def test_majority_vote_end_to_end_unanimous(self):
        """End-to-end: unanimous results produce consensus_reached=True."""
        mv = MajorityVoteStrategy(threshold=3, max_attempts=5)
        results = [_make_instr(1)] * 3
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert cr.consensus_reached is True
        assert cr.confidence == 1.0
        assert cr.group_count == 1

    def test_majority_vote_end_to_end_no_consensus(self):
        """End-to-end: all different results -> consensus_reached=False."""
        mv = MajorityVoteStrategy(threshold=3, max_attempts=3)
        results = [_make_instr(1), _make_instr(2), _make_instr(3)]
        groups = _build_groups(results)
        cr = mv.select(results, groups)
        assert cr.consensus_reached is False
        assert cr.group_count == 3

    def test_step_definition_accepts_consensus_strategy(self):
        """StepDefinition.consensus_strategy field accepts strategy objects."""
        from llm_pipeline.strategy import StepDefinition
        mv = MajorityVoteStrategy(threshold=2, max_attempts=5)
        # Minimal StepDefinition to test field acceptance
        sd = StepDefinition(
            step_class=object,
            system_instruction_key="sys",
            user_prompt_key="usr",
            instructions=object,
            consensus_strategy=mv,
        )
        assert sd.consensus_strategy is mv

    def test_step_definition_consensus_strategy_defaults_none(self):
        """StepDefinition.consensus_strategy defaults to None."""
        from llm_pipeline.strategy import StepDefinition
        sd = StepDefinition(
            step_class=object,
            system_instruction_key="sys",
            user_prompt_key="usr",
            instructions=object,
        )
        assert sd.consensus_strategy is None
