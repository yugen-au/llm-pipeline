"""Unit tests for llm_pipeline.prompts.resolver."""
from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from llm_pipeline import init_pipeline_db
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.prompts.resolver import (
    resolve_from_step_def,
    resolve_with_auto_discovery,
)
from llm_pipeline.step import LLMResultMixin, step_definition
from llm_pipeline.step import LLMStep


# ---------------------------------------------------------------------------
# Test step classes (class-based so StepDefinition has a real step_class)
# ---------------------------------------------------------------------------


class WidgetCountInstructions(LLMResultMixin):
    count: int = 0

    example: ClassVar[dict] = {"count": 1, "notes": "ok"}


@step_definition(instructions=WidgetCountInstructions)
class WidgetCountStep(LLMStep):
    def prepare_calls(self):  # pragma: no cover - not exercised
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


def _step_def(
    system_key: str | None = None, user_key: str | None = None
):
    """Build a StepDefinition pointing at WidgetCountStep."""
    # Use create_definition so tier-2 defaults flow correctly.
    return WidgetCountStep.create_definition(
        system_instruction_key=system_key,
        user_prompt_key=user_key,
    )


# ---------------------------------------------------------------------------
# resolve_from_step_def
# ---------------------------------------------------------------------------


class TestResolveFromStepDef:
    def test_both_keys_set_returned_as_is(self):
        sd = _step_def(system_key="sys_k", user_key="usr_k")
        assert resolve_from_step_def(sd) == ("sys_k", "usr_k")

    def test_both_keys_none_returns_none_pair(self):
        sd = _step_def()
        assert resolve_from_step_def(sd) == (None, None)

    def test_only_system_preserved(self):
        sd = _step_def(system_key="sys_k", user_key=None)
        assert resolve_from_step_def(sd) == ("sys_k", None)


# ---------------------------------------------------------------------------
# resolve_with_auto_discovery
# ---------------------------------------------------------------------------


class TestResolveWithAutoDiscovery:
    def test_both_declared_no_db_query(self):
        """Both keys declared → no DB roundtrip."""
        sd = _step_def(system_key="sys_declared", user_key="usr_declared")
        mock_session = MagicMock(spec=Session)
        sys_k, usr_k = resolve_with_auto_discovery(sd, mock_session, "my_strategy")
        assert sys_k == "sys_declared"
        assert usr_k == "usr_declared"
        mock_session.exec.assert_not_called()

    def test_strategy_level_hit(self, session):
        """Both keys None + strategy-level Prompt → returns {step}.{strategy} key."""
        sd = _step_def()
        session.add(
            Prompt(
                prompt_key="widget_count.lane_based",
                prompt_name="widget count lane",
                prompt_type="system",
                content="sys",
                is_active=True,
            )
        )
        session.add(
            Prompt(
                prompt_key="widget_count.lane_based",
                prompt_name="widget count lane usr",
                prompt_type="user",
                content="usr",
                is_active=True,
            )
        )
        session.commit()

        sys_k, usr_k = resolve_with_auto_discovery(sd, session, "lane_based")
        assert sys_k == "widget_count.lane_based"
        assert usr_k == "widget_count.lane_based"

    def test_step_level_fallback(self, session):
        """Strategy-level missing, step-level hit → returns {step}."""
        sd = _step_def()
        session.add(
            Prompt(
                prompt_key="widget_count",
                prompt_name="widget count sys",
                prompt_type="system",
                content="sys",
                is_active=True,
            )
        )
        session.add(
            Prompt(
                prompt_key="widget_count",
                prompt_name="widget count usr",
                prompt_type="user",
                content="usr",
                is_active=True,
            )
        )
        session.commit()

        sys_k, usr_k = resolve_with_auto_discovery(sd, session, "some_strategy")
        assert sys_k == "widget_count"
        assert usr_k == "widget_count"

    def test_no_match_returns_none_pair(self, session):
        """Both None + no matching Prompts → (None, None)."""
        sd = _step_def()
        sys_k, usr_k = resolve_with_auto_discovery(sd, session, "my_strategy")
        assert (sys_k, usr_k) == (None, None)

    def test_strategy_name_none_skips_strategy_attempt(self, session):
        """strategy_name=None → only step-level queried."""
        sd = _step_def()
        # seed a strategy-level prompt that should be ignored
        session.add(
            Prompt(
                prompt_key="widget_count.foo",
                prompt_name="strat level",
                prompt_type="system",
                content="sys",
                is_active=True,
            )
        )
        session.add(
            Prompt(
                prompt_key="widget_count",
                prompt_name="step level",
                prompt_type="system",
                content="sys2",
                is_active=True,
            )
        )
        session.commit()

        sys_k, usr_k = resolve_with_auto_discovery(sd, session, None)
        assert sys_k == "widget_count"
        assert usr_k is None  # no user-typed prompt seeded

    def test_partial_declared_auto_discovers_other_side(self, session):
        """Only system_key declared → preserve system, auto-discover user."""
        sd = _step_def(system_key="explicit_sys", user_key=None)
        session.add(
            Prompt(
                prompt_key="widget_count",
                prompt_name="user step level",
                prompt_type="user",
                content="usr",
                is_active=True,
            )
        )
        session.commit()

        sys_k, usr_k = resolve_with_auto_discovery(sd, session, None)
        assert sys_k == "explicit_sys"
        assert usr_k == "widget_count"

    def test_strategy_level_system_step_level_user(self, session):
        """Mixed: strategy-level system exists but no strategy-level user;
        falls back to step-level for user only."""
        sd = _step_def()
        session.add(
            Prompt(
                prompt_key="widget_count.lane_based",
                prompt_name="strat sys",
                prompt_type="system",
                content="sys",
                is_active=True,
            )
        )
        session.add(
            Prompt(
                prompt_key="widget_count",
                prompt_name="step usr",
                prompt_type="user",
                content="usr",
                is_active=True,
            )
        )
        session.commit()

        sys_k, usr_k = resolve_with_auto_discovery(sd, session, "lane_based")
        assert sys_k == "widget_count.lane_based"
        assert usr_k == "widget_count"

    def test_inactive_prompt_skipped(self, session):
        """Inactive prompts are not considered a match."""
        sd = _step_def()
        session.add(
            Prompt(
                prompt_key="widget_count",
                prompt_name="inactive",
                prompt_type="system",
                content="sys",
                is_active=False,
            )
        )
        session.commit()

        sys_k, usr_k = resolve_with_auto_discovery(sd, session, None)
        assert (sys_k, usr_k) == (None, None)
