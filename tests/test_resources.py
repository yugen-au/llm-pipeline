"""Tests for PipelineResource / Resource(...) declaration + runtime resolution."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from unittest.mock import MagicMock

from llm_pipeline.inputs import StepInputs
from llm_pipeline.resources import PipelineResource, Resource, resolve_resources
from llm_pipeline.runtime import PipelineContext


# ---------------------------------------------------------------------------
# Minimal resource used across tests
# ---------------------------------------------------------------------------


class WorkbookContextStub(PipelineResource):
    """Minimal resource stub that records its build args."""

    class Inputs(BaseModel):
        vendor_id: str
        input_2: bool

    def __init__(self, vendor_id: str, input_2: bool) -> None:
        self.vendor_id = vendor_id
        self.input_2 = input_2

    @classmethod
    def build(cls, inputs, ctx):
        return cls(vendor_id=inputs.vendor_id, input_2=inputs.input_2)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestResourceAcceptance:
    def test_valid_explicit_mapping_creates_class(self) -> None:
        class ChargeAuditInputs(StepInputs):
            vendor_id: str
            input_2: bool
            workbook_context: WorkbookContextStub = Resource(
                vendor_id="vendor_id",
                input_2="input_2",
            )

        specs = ChargeAuditInputs.resource_specs()
        assert set(specs) == {"workbook_context"}
        assert specs["workbook_context"].resource_cls is WorkbookContextStub
        assert specs["workbook_context"].mapping == {
            "vendor_id": "vendor_id",
            "input_2": "input_2",
        }

    def test_mapping_can_rename(self) -> None:
        class ChargeAuditInputs(StepInputs):
            our_vendor_id: str
            some_flag: bool
            workbook_context: WorkbookContextStub = Resource(
                vendor_id="our_vendor_id",
                input_2="some_flag",
            )

        specs = ChargeAuditInputs.resource_specs()
        assert specs["workbook_context"].mapping == {
            "vendor_id": "our_vendor_id",
            "input_2": "some_flag",
        }

    def test_resource_field_excluded_from_sources_companion(self) -> None:
        class ChargeAuditInputs(StepInputs):
            vendor_id: str
            input_2: bool
            workbook_context: WorkbookContextStub = Resource(
                vendor_id="vendor_id",
                input_2="input_2",
            )

        sources_cls = ChargeAuditInputs._sources_cls
        assert sources_cls is not None
        assert set(sources_cls.model_fields) == {"vendor_id", "input_2"}
        assert "workbook_context" not in sources_cls.model_fields

    def test_sources_rejects_resource_field_as_kwarg(self) -> None:
        from llm_pipeline.wiring import FromInput

        class ChargeAuditInputs(StepInputs):
            vendor_id: str
            input_2: bool
            workbook_context: WorkbookContextStub = Resource(
                vendor_id="vendor_id",
                input_2="input_2",
            )

        # Supplying workbook_context to .sources() should fail (extra='forbid')
        with pytest.raises(Exception):  # pydantic.ValidationError
            ChargeAuditInputs.sources(
                vendor_id=FromInput("v"),
                input_2=FromInput("i"),
                workbook_context=FromInput("w"),
            )


# ---------------------------------------------------------------------------
# Strict validation — class creation should raise
# ---------------------------------------------------------------------------


class TestResourceValidationFailures:
    def test_missing_mapping_entry_raises(self) -> None:
        with pytest.raises(TypeError, match="missing required input"):
            class _Bad(StepInputs):
                vendor_id: str
                input_2: bool
                workbook_context: WorkbookContextStub = Resource(
                    vendor_id="vendor_id",
                    # input_2 missing from mapping
                )

    def test_extraneous_mapping_entry_raises(self) -> None:
        with pytest.raises(TypeError, match="unknown input"):
            class _Bad(StepInputs):
                vendor_id: str
                input_2: bool
                workbook_context: WorkbookContextStub = Resource(
                    vendor_id="vendor_id",
                    input_2="input_2",
                    bogus="vendor_id",
                )

    def test_mapping_target_missing_on_stepinputs_raises(self) -> None:
        with pytest.raises(TypeError, match="has no field named 'nonexistent'"):
            class _Bad(StepInputs):
                vendor_id: str
                input_2: bool
                workbook_context: WorkbookContextStub = Resource(
                    vendor_id="nonexistent",
                    input_2="input_2",
                )

    def test_resource_without_inputs_class_raises(self) -> None:
        class Broken(PipelineResource):
            # No Inputs class defined
            @classmethod
            def build(cls, inputs, ctx):  # pragma: no cover
                return cls()

        with pytest.raises(TypeError, match="does not define an Inputs"):
            class _Bad(StepInputs):
                some_field: str
                broken: Broken = Resource(
                    whatever="some_field",
                )

    def test_resource_inputs_not_basemodel_subclass_raises(self) -> None:
        with pytest.raises(TypeError, match="must be a pydantic BaseModel"):
            class Broken(PipelineResource):
                Inputs = dict  # not a BaseModel

                @classmethod
                def build(cls, inputs, ctx):  # pragma: no cover
                    return cls()

    def test_annotation_not_piperesource_raises(self) -> None:
        # Field has Resource(...) default but annotated as a non-resource type
        with pytest.raises(TypeError, match="is not a PipelineResource subclass"):
            class _Bad(StepInputs):
                vendor_id: str
                wrongly_typed: str = Resource(
                    vendor_id="vendor_id",
                )

    def test_mapping_target_is_resource_field_raises(self) -> None:
        class OtherResource(PipelineResource):
            class Inputs(BaseModel):
                vendor_id: str

            @classmethod
            def build(cls, inputs, ctx):  # pragma: no cover
                return cls()

        with pytest.raises(TypeError, match="is itself a resource field"):
            class _Bad(StepInputs):
                vendor_id: str
                other_resource: OtherResource = Resource(
                    vendor_id="vendor_id",
                )
                workbook_context: WorkbookContextStub = Resource(
                    vendor_id="other_resource",  # pointing at another resource
                    input_2="vendor_id",
                )

    def test_mapping_target_is_self_raises(self) -> None:
        with pytest.raises(TypeError, match="points at the resource field itself"):
            class _Bad(StepInputs):
                vendor_id: str
                input_2: bool
                workbook_context: WorkbookContextStub = Resource(
                    vendor_id="workbook_context",  # self-reference
                    input_2="input_2",
                )


# ---------------------------------------------------------------------------
# Runtime resolution
# ---------------------------------------------------------------------------


# Module-scope StepInputs so pydantic resolves resource annotations.
class _ResolvableInputs(StepInputs):
    vendor_id: str
    flag: bool
    workbook: WorkbookContextStub = Resource(
        vendor_id="vendor_id",
        input_2="flag",
    )


class TestResolveResources:
    @staticmethod
    def _make_ctx() -> PipelineContext:
        return PipelineContext(
            session=MagicMock(),
            logger=MagicMock(),
            run_id="test-run",
        )

    def test_resolve_populates_resource_field(self) -> None:
        inputs = _ResolvableInputs(vendor_id="ACME", flag=True)
        assert inputs.workbook is None  # default before resolution
        resolve_resources(inputs, self._make_ctx())
        assert inputs.workbook is not None
        assert isinstance(inputs.workbook, WorkbookContextStub)
        assert inputs.workbook.vendor_id == "ACME"
        assert inputs.workbook.input_2 is True

    def test_resolve_with_renamed_mapping(self) -> None:
        class _Renamed(StepInputs):
            my_vendor: str
            my_flag: bool
            wb: WorkbookContextStub = Resource(
                vendor_id="my_vendor",
                input_2="my_flag",
            )

        inputs = _Renamed(my_vendor="X", my_flag=False)
        resolve_resources(inputs, self._make_ctx())
        assert inputs.wb.vendor_id == "X"
        assert inputs.wb.input_2 is False

    def test_resolve_passes_ctx_to_build(self) -> None:
        class CtxCapture(PipelineResource):
            class Inputs(BaseModel):
                x: str

            captured_ctx = None

            def __init__(self) -> None:
                pass

            @classmethod
            def build(cls, inputs, ctx):
                cls.captured_ctx = ctx
                return cls()

        class _Inputs(StepInputs):
            x: str
            cap: CtxCapture = Resource(x="x")

        ctx = self._make_ctx()
        inputs = _Inputs(x="hello")
        resolve_resources(inputs, ctx)
        assert CtxCapture.captured_ctx is ctx

    def test_resolve_noop_when_no_resource_fields(self) -> None:
        class _Plain(StepInputs):
            x: str

        inputs = _Plain(x="hi")
        resolve_resources(inputs, self._make_ctx())  # should not raise
        assert inputs.x == "hi"
