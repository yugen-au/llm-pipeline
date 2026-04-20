"""Unit tests for llm_pipeline.model.resolver."""
from __future__ import annotations

from typing import ClassVar

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from llm_pipeline import init_pipeline_db
from llm_pipeline.db.step_config import StepModelConfig
from llm_pipeline.model.resolver import (
    resolve_model_from_step_def,
    resolve_model_with_fallbacks,
)
from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition


# ---------------------------------------------------------------------------
# Test step classes
# ---------------------------------------------------------------------------


class WidgetInstructions(LLMResultMixin):
    count: int = 0

    example: ClassVar[dict] = {"count": 1, "notes": "ok"}


@step_definition(instructions=WidgetInstructions)
class WidgetStep(LLMStep):
    def prepare_calls(self):  # pragma: no cover — not exercised
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(engine)
    with Session(engine) as s:
        yield s


def _step_def(*, model: str | None = None):
    """Build a StepDefinition pointing at WidgetStep."""
    return WidgetStep.create_definition(model=model)


# ---------------------------------------------------------------------------
# resolve_model_from_step_def
# ---------------------------------------------------------------------------


class TestResolveModelFromStepDef:
    def test_model_set_returned(self):
        sd = _step_def(model="gpt-5")
        assert resolve_model_from_step_def(sd) == "gpt-5"

    def test_model_none_returns_none(self):
        sd = _step_def(model=None)
        assert resolve_model_from_step_def(sd) is None


# ---------------------------------------------------------------------------
# resolve_model_with_fallbacks
# ---------------------------------------------------------------------------


class TestResolveModelWithFallbacks:
    def test_tier_2_db_hit_wins(self, session):
        """DB StepModelConfig row for (pipeline, step) wins over tier 1 + 3."""
        sd = _step_def(model="step-def-model")
        session.add(
            StepModelConfig(
                pipeline_name="p1",
                step_name="widget",
                model="db-model",
            )
        )
        session.commit()

        model, source = resolve_model_with_fallbacks(
            sd, session, "p1", "pipeline-default"
        )
        assert model == "db-model"
        assert source == "db"

    def test_tier_2_miss_tier_1_hit(self, session):
        """No DB row → falls back to step_def.model."""
        sd = _step_def(model="step-def-model")

        model, source = resolve_model_with_fallbacks(
            sd, session, "p1", "pipeline-default"
        )
        assert model == "step-def-model"
        assert source == "step_definition"

    def test_tier_2_miss_tier_1_none_tier_3_hit(self, session):
        """No DB row + no step_def model → pipeline default."""
        sd = _step_def(model=None)

        model, source = resolve_model_with_fallbacks(
            sd, session, "p1", "pipeline-default"
        )
        assert model == "pipeline-default"
        assert source == "pipeline_default"

    def test_all_tiers_miss(self, session):
        """Nothing configured anywhere → (None, 'none')."""
        sd = _step_def(model=None)

        model, source = resolve_model_with_fallbacks(
            sd, session, "p1", None
        )
        assert model is None
        assert source == "none"

    def test_tier_2_for_different_pipeline_not_matched(self, session):
        """StepModelConfig keyed to pipeline X must not leak into pipeline Y."""
        sd = _step_def(model="step-def-model")
        session.add(
            StepModelConfig(
                pipeline_name="other_pipeline",
                step_name="widget",
                model="other-db-model",
            )
        )
        session.commit()

        model, source = resolve_model_with_fallbacks(
            sd, session, "p1", "pipeline-default"
        )
        # Tier 2 skipped (wrong pipeline) → tier 1 hit
        assert model == "step-def-model"
        assert source == "step_definition"

    def test_tier_2_for_different_step_not_matched(self, session):
        """StepModelConfig keyed to a different step_name must not match."""
        sd = _step_def(model=None)
        session.add(
            StepModelConfig(
                pipeline_name="p1",
                step_name="some_other_step",
                model="wrong-model",
            )
        )
        session.commit()

        model, source = resolve_model_with_fallbacks(
            sd, session, "p1", "pipeline-default"
        )
        assert model == "pipeline-default"
        assert source == "pipeline_default"

    def test_tier_2_wins_over_tier_3(self, session):
        """DB row beats pipeline default when both exist (and no tier 1)."""
        sd = _step_def(model=None)
        session.add(
            StepModelConfig(
                pipeline_name="p1",
                step_name="widget",
                model="db-model",
            )
        )
        session.commit()

        model, source = resolve_model_with_fallbacks(
            sd, session, "p1", "pipeline-default"
        )
        assert model == "db-model"
        assert source == "db"

    def test_tier_1_wins_over_tier_3(self, session):
        """step_def.model beats pipeline default when no DB row."""
        sd = _step_def(model="step-def-model")

        model, source = resolve_model_with_fallbacks(
            sd, session, "p1", "pipeline-default"
        )
        assert model == "step-def-model"
        assert source == "step_definition"
