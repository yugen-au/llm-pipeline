"""Tests for the PipelineResource / Resource(...) declaration machinery.

Covers class-creation validation only — runtime resolution is exercised
by pipeline/sandbox tests once adapter resolution is extended.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from llm_pipeline.inputs import StepInputs
from llm_pipeline.resources import PipelineResource, Resource


# ---------------------------------------------------------------------------
# Minimal resource used across tests
# ---------------------------------------------------------------------------


class WorkbookContextStub(PipelineResource):
    class Inputs(BaseModel):
        vendor_id: str
        input_2: bool

    @classmethod
    def build(cls, inputs, ctx):  # pragma: no cover — not exercised here
        return cls()


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
