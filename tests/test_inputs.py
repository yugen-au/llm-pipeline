"""Tests for llm_pipeline.inputs: StepInputs base + auto-generated sources companion."""
import pytest
from pydantic import BaseModel, ValidationError

from llm_pipeline.inputs import StepInputs
from llm_pipeline.wiring import FromInput, FromOutput, SourcesSpec


class _StepA:
    """Placeholder step class; only identity matters for FromOutput keying."""


# ---------------------------------------------------------------------------
# Base class behaviour
# ---------------------------------------------------------------------------


class TestStepInputsBase:
    def test_is_basemodel_subclass(self):
        assert issubclass(StepInputs, BaseModel)

    def test_base_class_has_no_companion(self):
        assert StepInputs._sources_cls is None

    def test_base_class_sources_raises(self):
        with pytest.raises(TypeError, match="no non-resource fields"):
            StepInputs.sources()


# ---------------------------------------------------------------------------
# Companion generation
# ---------------------------------------------------------------------------


class TestSubclassCompanionGeneration:
    def test_subclass_with_fields_gets_companion(self):
        class MyInputs(StepInputs):
            name: str
            count: int

        assert MyInputs._sources_cls is not None
        assert MyInputs._sources_cls.__name__ == "MyInputs_Sources"

    def test_companion_has_matching_field_names(self):
        class MyInputs(StepInputs):
            alpha: str
            beta: int
            gamma: list[str]

        companion = MyInputs._sources_cls
        assert companion is not None
        assert set(companion.model_fields) == {"alpha", "beta", "gamma"}

    def test_companion_accepts_source_values(self):
        class MyInputs(StepInputs):
            x: str

        companion = MyInputs._sources_cls
        src = FromInput("foo")
        instance = companion(x=src)
        assert instance.x is src

    def test_companion_rejects_non_source_value(self):
        class MyInputs(StepInputs):
            x: str

        companion = MyInputs._sources_cls
        with pytest.raises(ValidationError):
            companion(x="literal-string-not-a-source")

    def test_companion_rejects_missing_required_field(self):
        class MyInputs(StepInputs):
            x: str
            y: int

        companion = MyInputs._sources_cls
        with pytest.raises(ValidationError):
            companion(x=FromInput("foo"))  # y missing

    def test_companion_rejects_unknown_field(self):
        class MyInputs(StepInputs):
            x: str

        companion = MyInputs._sources_cls
        with pytest.raises(ValidationError):
            companion(x=FromInput("foo"), unknown=FromInput("bar"))


# ---------------------------------------------------------------------------
# .sources() classmethod
# ---------------------------------------------------------------------------


class TestSourcesClassmethod:
    def test_returns_sources_spec(self):
        class MyInputs(StepInputs):
            name: str
            count: int

        spec = MyInputs.sources(
            name=FromInput("name"),
            count=FromInput("count"),
        )
        assert isinstance(spec, SourcesSpec)
        assert spec.inputs_cls is MyInputs

    def test_field_sources_mapped_correctly(self):
        class MyInputs(StepInputs):
            x: str
            y: int

        src_x = FromInput("some_field")
        src_y = FromOutput(_StepA, field="val")
        spec = MyInputs.sources(x=src_x, y=src_y)
        assert spec.field_sources["x"] is src_x
        assert spec.field_sources["y"] is src_y

    def test_missing_required_field_rejected(self):
        class MyInputs(StepInputs):
            x: str
            y: int

        with pytest.raises(ValidationError):
            MyInputs.sources(x=FromInput("x"))

    def test_unknown_field_rejected(self):
        class MyInputs(StepInputs):
            x: str

        with pytest.raises(ValidationError):
            MyInputs.sources(x=FromInput("x"), z=FromInput("z"))

    def test_non_source_value_rejected(self):
        class MyInputs(StepInputs):
            x: str

        with pytest.raises(ValidationError):
            MyInputs.sources(x="literal-value")


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------


class TestInheritance:
    def test_subclass_inherits_fields(self):
        class ParentInputs(StepInputs):
            base_field: str

        class ChildInputs(ParentInputs):
            child_field: int

        assert set(ChildInputs.model_fields) == {"base_field", "child_field"}

    def test_child_companion_covers_inherited_fields(self):
        class ParentInputs(StepInputs):
            base_field: str

        class ChildInputs(ParentInputs):
            child_field: int

        spec = ChildInputs.sources(
            base_field=FromInput("a"),
            child_field=FromInput("b"),
        )
        assert set(spec.field_sources) == {"base_field", "child_field"}

    def test_child_companion_rejects_missing_inherited_field(self):
        class ParentInputs(StepInputs):
            base_field: str

        class ChildInputs(ParentInputs):
            child_field: int

        with pytest.raises(ValidationError):
            ChildInputs.sources(child_field=FromInput("b"))  # base_field missing
