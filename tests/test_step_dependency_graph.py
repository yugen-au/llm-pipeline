"""Tests for the unified step dependency graph.

The graph aggregates two sources of step-level dependencies into one:

1. ``FromOutput(StepCls)`` references in step / extraction / tool inputs.
2. Extraction FK chains: a step extracting a model whose FK column
   targets another model depends on whichever step extracts that
   target.

Validator (``_validate_step_dependency_graph``) asserts:

- Every referenced step class is present in the pipeline.
- The graph is acyclic.
- The user-declared positional binding order is a valid topo sort
  (every dependency at a lower index than its dependent).
"""
from __future__ import annotations

from typing import ClassVar, List, Optional

import pytest
from sqlmodel import Field, SQLModel

from llm_pipeline import (
    LLMResultMixin,
    LLMStep,
    PipelineConfig,
    PipelineDatabaseRegistry,
    PipelineExtraction,
    PipelineStrategies,
    PipelineStrategy,
    step_definition,
)
from llm_pipeline.inputs import PipelineInputData, StepInputs
from llm_pipeline.types import StepCallParams
from llm_pipeline.wiring import Bind, FromInput, FromOutput


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Widget(SQLModel, table=True):
    __tablename__ = "depgraph_widgets"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class WidgetReview(SQLModel, table=True):
    """FKs into Widget — extracts in a later step."""
    __tablename__ = "depgraph_widget_reviews"
    id: Optional[int] = Field(default=None, primary_key=True)
    widget_id: int = Field(foreign_key="depgraph_widgets.id")
    decision: str


# ---------------------------------------------------------------------------
# Pipeline / step inputs
# ---------------------------------------------------------------------------


class _Input(PipelineInputData):
    data: str


class _AInputs(StepInputs):
    data: str


class _BInputs(StepInputs):
    """Carries a step-level FromOutput dep on StepA."""
    data: str
    upstream_count: int


class _CInputs(StepInputs):
    data: str


# ---------------------------------------------------------------------------
# LLM outputs
# ---------------------------------------------------------------------------


class _AInstructions(LLMResultMixin):
    widget_count: int
    example: ClassVar[dict] = {"widget_count": 5}


class _BInstructions(LLMResultMixin):
    decision: str
    example: ClassVar[dict] = {"decision": "ok"}


class _CInstructions(LLMResultMixin):
    note: str
    example: ClassVar[dict] = {"note": "n/a"}


# ---------------------------------------------------------------------------
# Extractions
# ---------------------------------------------------------------------------


class _ExtWidget(PipelineExtraction, model=Widget):
    class FromAInputs(StepInputs):
        widget_count: int

    def from_a(self, inputs: FromAInputs) -> list[Widget]:
        return [Widget(name=f"w{i}") for i in range(inputs.widget_count)]


class _ExtWidgetReview(PipelineExtraction, model=WidgetReview):
    class FromBInputs(StepInputs):
        decision: str
        widget_id: int

    def from_b(self, inputs: FromBInputs) -> list[WidgetReview]:
        return [WidgetReview(widget_id=inputs.widget_id, decision=inputs.decision)]


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


@step_definition(
    inputs=_AInputs,
    instructions=_AInstructions,
)
class _AStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [StepCallParams(variables={"data": self.inputs.data})]


@step_definition(
    inputs=_BInputs,
    instructions=_BInstructions,
)
class _BStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [StepCallParams(variables={"data": self.inputs.data})]


@step_definition(
    inputs=_CInputs,
    instructions=_CInstructions,
)
class _CStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [StepCallParams(variables={"data": self.inputs.data})]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _bind_a() -> Bind:
    return Bind(
        step=_AStep,
        inputs=_AInputs.sources(data=FromInput("data")),
        extractions=[
            Bind(
                extraction=_ExtWidget,
                inputs=_ExtWidget.FromAInputs.sources(
                    widget_count=FromOutput(_AStep, field="widget_count"),
                ),
            ),
        ],
    )


def _bind_b_with_fromoutput_dep_on_a() -> Bind:
    return Bind(
        step=_BStep,
        inputs=_BInputs.sources(
            data=FromInput("data"),
            upstream_count=FromOutput(_AStep, field="widget_count"),
        ),
    )


def _bind_b_with_fk_extraction() -> Bind:
    """B extracts WidgetReview which FKs into Widget; B depends on A via FK."""
    return Bind(
        step=_BStep,
        inputs=_BInputs.sources(
            data=FromInput("data"),
            upstream_count=FromOutput(_AStep, field="widget_count"),
        ),
        extractions=[
            Bind(
                extraction=_ExtWidgetReview,
                inputs=_ExtWidgetReview.FromBInputs.sources(
                    decision=FromOutput(_BStep, field="decision"),
                    widget_id=FromOutput(_AStep, field="widget_count"),
                ),
            ),
        ],
    )


def _bind_c_no_deps() -> Bind:
    return Bind(
        step=_CStep,
        inputs=_CInputs.sources(data=FromInput("data")),
    )


def _bind_c_dep_on_b() -> Bind:
    return Bind(
        step=_CStep,
        inputs=_CInputs.sources(data=FromOutput(_BStep, field="decision")),
    )


def _bind_a_dep_on_c() -> Bind:
    """Used to construct a cycle: A depends on C."""
    return Bind(
        step=_AStep,
        inputs=_AInputs.sources(data=FromOutput(_CStep, field="note")),
        extractions=[
            Bind(
                extraction=_ExtWidget,
                inputs=_ExtWidget.FromAInputs.sources(
                    widget_count=FromOutput(_AStep, field="widget_count"),
                ),
            ),
        ],
    )


# Reference to a step class that will not appear in the pipeline.
class _MissingInputs(StepInputs):
    data: str


class _MissingInstructions(LLMResultMixin):
    widget_count: int
    example: ClassVar[dict] = {"widget_count": 0}


@step_definition(
    inputs=_MissingInputs,
    instructions=_MissingInstructions,
)
class _MissingStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return []


def _bind_b_dep_on_missing() -> Bind:
    return Bind(
        step=_BStep,
        inputs=_BInputs.sources(
            data=FromInput("data"),
            upstream_count=FromOutput(_MissingStep, field="widget_count"),
        ),
    )


# ---------------------------------------------------------------------------
# Strategy / pipeline factory helpers
# ---------------------------------------------------------------------------


def _make_pipeline(*binds: Bind):
    class _Strategy(PipelineStrategy):
        def can_handle(self, context):
            return True

        def get_bindings(self):
            return list(binds)

    class _Strategies(PipelineStrategies, strategies=[_Strategy]):
        pass

    class _Registry(
        PipelineDatabaseRegistry, models=[Widget, WidgetReview],
    ):
        pass

    class _Pipeline(
        PipelineConfig,
        registry=_Registry,
        strategies=_Strategies,
    ):
        INPUT_DATA = _Input

    return _Pipeline(model="test")


# ---------------------------------------------------------------------------
# Build tests
# ---------------------------------------------------------------------------


class TestGraphBuild:
    def test_single_step_no_deps(self):
        p = _make_pipeline(_bind_a())
        assert p._step_deps.get(_AStep, set()) == set()

    def test_fromoutput_creates_step_edge(self):
        p = _make_pipeline(_bind_a(), _bind_b_with_fromoutput_dep_on_a())
        assert _AStep in p._step_deps[_BStep]

    def test_fk_extraction_creates_step_edge(self):
        # B extracts WidgetReview FK->Widget extracted by A => B->A edge.
        p = _make_pipeline(_bind_a(), _bind_b_with_fk_extraction())
        assert _AStep in p._step_deps[_BStep]

    def test_combined_fromoutput_and_fk_collapses_to_single_edge(self):
        # Same edge declared via both mechanisms — set semantics dedupes,
        # but provenance reasons accumulate both.
        p = _make_pipeline(_bind_a(), _bind_b_with_fk_extraction())
        assert p._step_deps[_BStep] == {_AStep}
        reasons = p._step_dep_reasons[(_BStep, _AStep)]
        # Both kinds of reason recorded
        joined = " | ".join(reasons)
        assert "FromOutput" in joined
        assert "FK on" in joined

    def test_self_edges_filtered(self):
        # Step B's extraction declares FromOutput(_BStep) — must not
        # produce a self-edge.
        p = _make_pipeline(_bind_a(), _bind_b_with_fk_extraction())
        assert _BStep not in p._step_deps.get(_BStep, set())


# ---------------------------------------------------------------------------
# Validation: pass cases
# ---------------------------------------------------------------------------


class TestValidationPasses:
    def test_well_ordered_fromoutput(self):
        # A then B (B depends on A) — passes.
        _make_pipeline(_bind_a(), _bind_b_with_fromoutput_dep_on_a())

    def test_well_ordered_fk_chain(self):
        # A extracts Widget, B extracts WidgetReview FK->Widget — passes.
        _make_pipeline(_bind_a(), _bind_b_with_fk_extraction())

    def test_three_step_chain(self):
        # A -> B -> C all properly ordered.
        _make_pipeline(_bind_a(), _bind_b_with_fromoutput_dep_on_a(), _bind_c_dep_on_b())


# ---------------------------------------------------------------------------
# Validation: failure cases
# ---------------------------------------------------------------------------


class TestValidationFailures:
    def test_out_of_order_fromoutput(self):
        # B at position 0 depends on A at position 1 — must fail.
        with pytest.raises(ValueError, match="depends on '_AStep'"):
            _make_pipeline(_bind_b_with_fromoutput_dep_on_a(), _bind_a())

    def test_out_of_order_fk(self):
        # B at position 0 has WidgetReview FK->Widget but A (extractor of
        # Widget) is at position 1 — must fail.
        with pytest.raises(ValueError, match="depends on '_AStep'"):
            _make_pipeline(_bind_b_with_fk_extraction(), _bind_a())

    def test_cycle_detected(self):
        # A depends on C, C depends on B, B depends on A — cycle.
        with pytest.raises(ValueError, match="cycle"):
            _make_pipeline(
                _bind_a_dep_on_c(),
                _bind_b_with_fromoutput_dep_on_a(),
                _bind_c_dep_on_b(),
            )

    def test_dangling_fromoutput_reference(self):
        # B depends on _MissingStep which is not in the pipeline.
        with pytest.raises(ValueError, match="not present in any strategy"):
            _make_pipeline(_bind_a(), _bind_b_dep_on_missing())

    def test_error_message_includes_position_numbers(self):
        with pytest.raises(ValueError, match=r"position \d+"):
            _make_pipeline(_bind_b_with_fromoutput_dep_on_a(), _bind_a())
