"""
Pluggable consensus strategies for LLM pipeline step execution.

Provides ConsensusStrategy ABC, ConsensusResult model, and four concrete
strategy implementations: MajorityVote, ConfidenceWeighted, Adaptive,
and SoftVote.

Utility functions for structural comparison of LLM results are also
defined here (extracted from PipelineConfig).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConsensusResult",
    "ConsensusStrategy",
    "MajorityVoteStrategy",
    "ConfidenceWeightedStrategy",
    "AdaptiveStrategy",
    "SoftVoteStrategy",
    "instructions_match",
]


# ---------------------------------------------------------------------------
# Utility functions (extracted from PipelineConfig)
# ---------------------------------------------------------------------------

def _get_mixin_fields(model_class: type[BaseModel]) -> set[str]:
    """Return field names contributed by LLMResultMixin, or empty set."""
    # Lazy import to avoid circular dependency (step -> pipeline -> consensus)
    from llm_pipeline.step import LLMResultMixin

    if not issubclass(model_class, LLMResultMixin):
        return set()
    return set(LLMResultMixin.model_fields.keys())


def _smart_compare(value1: Any, value2: Any, field_name: str = "", mixin_fields: set[str] | None = None) -> bool:
    """Structurally compare two values, treating strings and mixin fields as always matching."""
    if mixin_fields and field_name in mixin_fields:
        return True
    if isinstance(value1, str) or isinstance(value2, str):
        return True
    if value1 is None or value2 is None:
        return True
    if isinstance(value1, (int, float, bool)) and isinstance(value2, (int, float, bool)):
        return value1 == value2
    if isinstance(value1, list) and isinstance(value2, list):
        if len(value1) != len(value2):
            return False
        return all(
            _smart_compare(v1, v2, "", mixin_fields)
            for v1, v2 in zip(value1, value2)
        )
    if isinstance(value1, dict) and isinstance(value2, dict):
        if set(value1.keys()) != set(value2.keys()):
            return False
        return all(
            _smart_compare(value1[k], value2[k], k, mixin_fields)
            for k in value1
        )
    return True


def instructions_match(instr1: BaseModel, instr2: BaseModel) -> bool:
    """Check whether two LLM result instructions are structurally equivalent.

    Mixin fields (confidence_score, notes) and string values are treated as
    always matching so that consensus grouping focuses on the deterministic
    content fields.
    """
    mixin_fields = _get_mixin_fields(type(instr1))
    dict1 = instr1.model_dump()
    dict2 = instr2.model_dump()
    return _smart_compare(dict1, dict2, mixin_fields=mixin_fields)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class ConsensusResult(BaseModel):
    """Immutable result of a consensus strategy selection."""

    model_config = ConfigDict(frozen=True)

    result: Any
    confidence: float = Field(ge=0.0, le=1.0)
    strategy_name: str
    agreement_ratio: float = Field(ge=0.0, le=1.0)
    total_attempts: int
    group_count: int
    consensus_reached: bool


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------

class ConsensusStrategy(ABC):
    """Abstract base for consensus strategies.

    Concrete subclasses must implement ``name``, ``max_attempts``,
    ``should_continue``, and ``select``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this strategy (e.g. 'majority_vote')."""

    @property
    @abstractmethod
    def max_attempts(self) -> int:
        """Maximum number of LLM calls the orchestrator should make."""

    @property
    @abstractmethod
    def threshold(self) -> float:
        """Strategy-specific threshold used for event reporting."""

    @abstractmethod
    def should_continue(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
        attempt: int,
        max_attempts: int,
    ) -> bool:
        """Return True if the orchestrator should keep polling."""

    @abstractmethod
    def select(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
    ) -> ConsensusResult:
        """Pick a winner from the collected results and groups."""


# ---------------------------------------------------------------------------
# Concrete strategies
# ---------------------------------------------------------------------------

class MajorityVoteStrategy(ConsensusStrategy):
    """Simple threshold-based majority vote.

    Reproduces the original ``_execute_with_consensus`` behaviour: stop as
    soon as any result group reaches *threshold* members, otherwise pick
    the largest group after exhausting all attempts.
    """

    def __init__(self, threshold: int = 3, max_attempts: int = 5) -> None:
        self._threshold = threshold
        self._max_attempts = max_attempts

    @property
    def name(self) -> str:
        return "majority_vote"

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def threshold(self) -> float:
        return float(self._threshold)

    def should_continue(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
        attempt: int,
        max_attempts: int,
    ) -> bool:
        if attempt >= max_attempts:
            return False
        for group in result_groups:
            if len(group) >= self._threshold:
                return False
        return True

    def select(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
    ) -> ConsensusResult:
        largest = max(result_groups, key=len)
        total = max(len(results), 1)
        agreement_ratio = len(largest) / total
        return ConsensusResult(
            result=largest[0],
            confidence=agreement_ratio,
            strategy_name=self.name,
            agreement_ratio=agreement_ratio,
            total_attempts=len(results),
            group_count=len(result_groups),
            consensus_reached=len(largest) >= self._threshold,
        )


class ConfidenceWeightedStrategy(ConsensusStrategy):
    """Weight groups by their members' ``confidence_score`` attributes.

    Falls back to ``0.5`` when a result has no ``confidence_score``.
    Guards against division-by-zero when all scores are zero.
    """

    def __init__(
        self,
        threshold: float = 0.8,
        min_samples: int = 3,
        max_attempts: int = 5,
    ) -> None:
        self._threshold = threshold
        self._min_samples = min_samples
        self._max_attempts = max_attempts

    @property
    def name(self) -> str:
        return "confidence_weighted"

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def threshold(self) -> float:
        return self._threshold

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score(result: Any) -> float:
        return float(getattr(result, "confidence_score", 0.5))

    def _group_weighted_score(self, group: list[Any]) -> float:
        return sum(self._score(r) for r in group)

    # ------------------------------------------------------------------
    # interface
    # ------------------------------------------------------------------

    def should_continue(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
        attempt: int,
        max_attempts: int,
    ) -> bool:
        if attempt >= max_attempts:
            return False
        if len(results) < self._min_samples:
            return True
        total_score = sum(self._group_weighted_score(g) for g in result_groups)
        if total_score == 0:
            return True
        best = max(self._group_weighted_score(g) for g in result_groups)
        return (best / total_score) < self._threshold

    def select(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
    ) -> ConsensusResult:
        best_group = max(result_groups, key=self._group_weighted_score)
        best_score = self._group_weighted_score(best_group)
        total_score = sum(self._group_weighted_score(g) for g in result_groups)

        # Guard against division-by-zero
        if total_score == 0:
            agreement_ratio = len(best_group) / max(len(results), 1)
            confidence = agreement_ratio
        else:
            confidence = best_score / total_score
            agreement_ratio = len(best_group) / max(len(results), 1)

        # Pick member with highest individual score
        best_member = max(best_group, key=self._score)

        return ConsensusResult(
            result=best_member,
            confidence=confidence,
            strategy_name=self.name,
            agreement_ratio=agreement_ratio,
            total_attempts=len(results),
            group_count=len(result_groups),
            consensus_reached=confidence >= self._threshold,
        )


class AdaptiveStrategy(ConsensusStrategy):
    """Lowers the agreement threshold as attempts progress.

    After 70 % of ``max_attempts`` are consumed the effective threshold
    drops from ``initial_threshold`` to ``min_threshold``.
    """

    def __init__(
        self,
        initial_threshold: int = 3,
        min_threshold: int = 2,
        max_attempts: int = 5,
    ) -> None:
        self._initial_threshold = initial_threshold
        self._min_threshold = min_threshold
        self._max_attempts = max_attempts

    @property
    def name(self) -> str:
        return "adaptive"

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def threshold(self) -> float:
        return float(self._initial_threshold)

    def _effective_threshold(self, attempt: int, max_attempts: int) -> int:
        progress = attempt / max(max_attempts, 1)
        if progress > 0.7:
            return self._min_threshold
        return self._initial_threshold

    def should_continue(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
        attempt: int,
        max_attempts: int,
    ) -> bool:
        if attempt >= max_attempts:
            return False
        effective = self._effective_threshold(attempt, max_attempts)
        for group in result_groups:
            if len(group) >= effective:
                return False
        return True

    def select(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
    ) -> ConsensusResult:
        largest = max(result_groups, key=len)
        total = max(len(results), 1)
        confidence = len(largest) / total
        effective = self._effective_threshold(len(results), self._max_attempts)
        return ConsensusResult(
            result=largest[0],
            confidence=confidence,
            strategy_name=self.name,
            agreement_ratio=confidence,
            total_attempts=len(results),
            group_count=len(result_groups),
            consensus_reached=len(largest) >= effective,
        )


class SoftVoteStrategy(ConsensusStrategy):
    """Pick the group whose members have the highest average ``confidence_score``."""

    def __init__(
        self,
        min_samples: int = 3,
        confidence_floor: float = 0.7,
        max_attempts: int = 5,
    ) -> None:
        self._min_samples = min_samples
        self._confidence_floor = confidence_floor
        self._max_attempts = max_attempts

    @property
    def name(self) -> str:
        return "soft_vote"

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def threshold(self) -> float:
        return self._confidence_floor

    @staticmethod
    def _avg_confidence(group: list[Any]) -> float:
        scores = [float(getattr(r, "confidence_score", 0.5)) for r in group]
        return sum(scores) / max(len(scores), 1)

    def should_continue(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
        attempt: int,
        max_attempts: int,
    ) -> bool:
        if attempt >= max_attempts:
            return False
        if len(results) < self._min_samples:
            return True
        best_avg = max(self._avg_confidence(g) for g in result_groups)
        return best_avg < self._confidence_floor

    def select(
        self,
        results: list[Any],
        result_groups: list[list[Any]],
    ) -> ConsensusResult:
        best_group = max(result_groups, key=self._avg_confidence)
        avg_conf = self._avg_confidence(best_group)
        total = max(len(results), 1)
        return ConsensusResult(
            result=best_group[0],
            confidence=avg_conf,
            strategy_name=self.name,
            agreement_ratio=len(best_group) / total,
            total_attempts=len(results),
            group_count=len(result_groups),
            consensus_reached=avg_conf >= self._confidence_floor,
        )
