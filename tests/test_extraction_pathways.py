"""Tests for PipelineExtraction pathway dispatch (Phase 3).

The new contract:
- Extraction declares one or more nested ``From{Purpose}Inputs`` classes
  (subclasses of ``StepInputs``).
- For each pathway, a method ``(self, inputs: FromPurposeInputs) -> list[MODEL]``.
- At class creation, the 1:1 pathway/method mapping is validated and a
  dispatch table is built on ``cls._pathway_dispatch``.
- ``extract(self, inputs)`` dispatches on ``type(inputs)``.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import pytest
from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.inputs import StepInputs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class Widget(SQLModel):
    """Plain SQLModel (no table=True) used as the MODEL for test extractions."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    value: int


class Gadget(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str


class _WidgetFromAInstructions(BaseModel):
    name: str
    value: int


class _WidgetFromBInstructions(BaseModel):
    label: str
    amount: int


class _UnrelatedInputs(StepInputs):
    """Module-level StepInputs subclass used to test the 'wrong pathway class'
    rejection path. Must be module-level so ``typing.get_type_hints`` can
    resolve the forward reference."""
    y: str


def _mock_pipeline(models: list[type[SQLModel]]) -> SimpleNamespace:
    """Minimal pipeline stand-in for constructing extractions in tests."""
    registry = SimpleNamespace(
        get_models=lambda: models,
        __name__="_MockRegistry",
    )
    return SimpleNamespace(REGISTRY=registry)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestSinglePathway:
    def test_dispatch_table_built(self):
        class WidgetExtraction(PipelineExtraction, model=Widget):
            class FromSingleInputs(StepInputs):
                instructions: _WidgetFromAInstructions

            def from_single(
                self, inputs: FromSingleInputs
            ) -> list[Widget]:
                return [Widget(name=inputs.instructions.name, value=inputs.instructions.value)]

        assert WidgetExtraction.FromSingleInputs in WidgetExtraction._pathway_dispatch
        assert len(WidgetExtraction._pathway_dispatch) == 1

    def test_extract_dispatches(self):
        class WidgetExtraction(PipelineExtraction, model=Widget):
            class FromSingleInputs(StepInputs):
                instructions: _WidgetFromAInstructions

            def from_single(
                self, inputs: FromSingleInputs
            ) -> list[Widget]:
                return [Widget(name=inputs.instructions.name, value=inputs.instructions.value)]

        pipe = _mock_pipeline([Widget])
        ex = WidgetExtraction(pipe)
        inputs = WidgetExtraction.FromSingleInputs(
            instructions=_WidgetFromAInstructions(name="thing", value=7)
        )
        result = ex.extract(inputs)
        assert len(result) == 1
        assert result[0].name == "thing"
        assert result[0].value == 7


class TestMultiplePathways:
    def test_two_pathways_dispatch_separately(self):
        class WidgetExtraction(PipelineExtraction, model=Widget):
            class FromAInputs(StepInputs):
                instructions: _WidgetFromAInstructions

            class FromBInputs(StepInputs):
                instructions: _WidgetFromBInstructions

            def from_a(self, inputs: FromAInputs) -> list[Widget]:
                return [Widget(name=inputs.instructions.name, value=inputs.instructions.value)]

            def from_b(self, inputs: FromBInputs) -> list[Widget]:
                return [Widget(name=inputs.instructions.label, value=inputs.instructions.amount)]

        assert len(WidgetExtraction._pathway_dispatch) == 2

        pipe = _mock_pipeline([Widget])
        ex = WidgetExtraction(pipe)

        a_inputs = WidgetExtraction.FromAInputs(
            instructions=_WidgetFromAInstructions(name="alpha", value=1)
        )
        b_inputs = WidgetExtraction.FromBInputs(
            instructions=_WidgetFromBInstructions(label="beta", amount=9)
        )
        a_result = ex.extract(a_inputs)
        b_result = ex.extract(b_inputs)

        assert a_result[0].name == "alpha"
        assert b_result[0].name == "beta"
        assert b_result[0].value == 9


# ---------------------------------------------------------------------------
# Validation failures at class creation
# ---------------------------------------------------------------------------


class TestPathwayNamingEnforcement:
    def test_non_from_prefix_rejected(self):
        with pytest.raises(ValueError, match="From\\{Purpose\\}Inputs"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class BadInputs(StepInputs):  # missing From prefix
                    x: str

                def do_thing(self, inputs: BadInputs) -> list[Widget]:
                    return []

    def test_missing_inputs_suffix_rejected(self):
        with pytest.raises(ValueError, match="From\\{Purpose\\}Inputs"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromThing(StepInputs):  # missing Inputs suffix
                    x: str

                def from_thing(self, inputs: FromThing) -> list[Widget]:
                    return []

    def test_lowercase_after_from_rejected(self):
        with pytest.raises(ValueError, match="From\\{Purpose\\}Inputs"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromthingInputs(StepInputs):  # lowercase 't'
                    x: str

                def from_thing(self, inputs: FromthingInputs) -> list[Widget]:
                    return []


class TestMethodSignatureEnforcement:
    def test_method_without_inputs_param_rejected(self):
        with pytest.raises(ValueError, match="inputs parameter"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromThingInputs(StepInputs):
                    x: str

                def from_thing(self) -> list[Widget]:  # missing inputs
                    return []

    def test_method_missing_input_annotation_rejected(self):
        with pytest.raises(ValueError, match="must have a type annotation"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromThingInputs(StepInputs):
                    x: str

                def from_thing(self, inputs) -> list[Widget]:  # unannotated
                    return []

    def test_method_input_annotation_wrong_class_rejected(self):
        # _UnrelatedInputs is declared at module level so get_type_hints
        # can resolve the forward reference. Under the contract, a method
        # annotated with a StepInputs that isn't a nested pathway on the
        # extraction must be rejected.
        with pytest.raises(ValueError, match="nested pathway classes"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromThingInputs(StepInputs):
                    x: str

                def from_thing(self, inputs: _UnrelatedInputs) -> list[Widget]:
                    return []

    def test_method_missing_return_annotation_rejected(self):
        with pytest.raises(ValueError, match="return type annotation"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromThingInputs(StepInputs):
                    x: str

                def from_thing(self, inputs: FromThingInputs):  # no return hint
                    return []

    def test_method_wrong_return_type_rejected(self):
        with pytest.raises(ValueError, match="list"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromThingInputs(StepInputs):
                    x: str

                def from_thing(self, inputs: FromThingInputs) -> list[Gadget]:
                    return []


class TestBijectionEnforcement:
    def test_two_methods_same_inputs_rejected(self):
        with pytest.raises(ValueError, match="two methods accept"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromThingInputs(StepInputs):
                    x: str

                def from_thing(self, inputs: FromThingInputs) -> list[Widget]:
                    return []

                def from_thing_again(self, inputs: FromThingInputs) -> list[Widget]:
                    return []

    def test_orphan_pathway_rejected(self):
        with pytest.raises(ValueError, match="without matching methods"):
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromOrphanInputs(StepInputs):
                    x: str

                # no from_orphan method

    def test_all_orphans_listed_in_error(self):
        with pytest.raises(ValueError) as exc_info:
            class BadExtraction(PipelineExtraction, model=Widget):
                class FromOneInputs(StepInputs):
                    x: str

                class FromTwoInputs(StepInputs):
                    y: str

                # no methods at all

        msg = str(exc_info.value)
        assert "FromOneInputs" in msg
        assert "FromTwoInputs" in msg


# ---------------------------------------------------------------------------
# Preserved existing behavior
# ---------------------------------------------------------------------------


class TestExistingBehaviourPreserved:
    def test_missing_model_kwarg_still_rejected(self):
        with pytest.raises(ValueError, match="model parameter"):
            class NoModelExtraction(PipelineExtraction):  # no model=
                class FromThingInputs(StepInputs):
                    x: str

                def from_thing(self, inputs: FromThingInputs) -> list[Widget]:
                    return []

    def test_non_extraction_suffix_still_rejected(self):
        with pytest.raises(ValueError, match="Extraction"):
            class WrongName(PipelineExtraction, model=Widget):  # no suffix
                class FromThingInputs(StepInputs):
                    x: str

                def from_thing(self, inputs: FromThingInputs) -> list[Widget]:
                    return []

    def test_pipeline_registry_validation_still_runs(self):
        class WidgetExtraction(PipelineExtraction, model=Widget):
            class FromThingInputs(StepInputs):
                x: str

            def from_thing(self, inputs: FromThingInputs) -> list[Widget]:
                return []

        # pipeline has Gadget but not Widget in its registry
        pipe = _mock_pipeline([Gadget])
        with pytest.raises(ValueError, match="is not in _MockRegistry"):
            WidgetExtraction(pipe)


# ---------------------------------------------------------------------------
# Runtime dispatch failures
# ---------------------------------------------------------------------------


class TestExtractRuntime:
    def test_extract_rejects_unknown_inputs_type(self):
        class WidgetExtraction(PipelineExtraction, model=Widget):
            class FromThingInputs(StepInputs):
                x: str

            def from_thing(self, inputs: FromThingInputs) -> list[Widget]:
                return []

        class UnrelatedInputs(StepInputs):
            z: int

        pipe = _mock_pipeline([Widget])
        ex = WidgetExtraction(pipe)
        bad_inputs = UnrelatedInputs(z=1)

        with pytest.raises(TypeError, match="no pathway method"):
            ex.extract(bad_inputs)

    def test_extract_runs_validation_on_returned_instances(self):
        """_validate_instances still runs (existing behavior)."""
        class WidgetExtraction(PipelineExtraction, model=Widget):
            class FromThingInputs(StepInputs):
                x: str

            def from_thing(self, inputs: FromThingInputs) -> list[Widget]:
                # Returns a Widget with name=None, which is required -> validation rejects
                return [Widget.model_construct(id=None, name=None, value=1)]

        pipe = _mock_pipeline([Widget])
        ex = WidgetExtraction(pipe)
        inputs = WidgetExtraction.FromThingInputs(x="anything")

        with pytest.raises(ValueError, match="Required field 'name'"):
            ex.extract(inputs)
