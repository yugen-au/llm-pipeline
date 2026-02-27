"""
Tests for PipelineInputData base class and INPUT_DATA type guard.
"""
from typing import ClassVar, Optional, Type

import pytest
from pydantic import BaseModel, ValidationError

from llm_pipeline.context import PipelineInputData
from llm_pipeline.pipeline import PipelineConfig


class TestPipelineInputDataBase:
    """PipelineInputData itself is a valid empty BaseModel."""

    def test_is_basemodel_subclass(self):
        assert issubclass(PipelineInputData, BaseModel)

    def test_instantiate_empty(self):
        instance = PipelineInputData()
        assert instance is not None

    def test_model_dump_empty(self):
        assert PipelineInputData().model_dump() == {}

    def test_model_json_schema_empty(self):
        schema = PipelineInputData.model_json_schema()
        assert schema["type"] == "object"
        assert schema["title"] == "PipelineInputData"


class TestPipelineInputDataSubclassing:
    """Subclassing PipelineInputData works with typed fields."""

    def test_subclass_with_fields(self):
        class MyInput(PipelineInputData):
            name: str
            count: int

        obj = MyInput(name="test", count=5)
        assert obj.name == "test"
        assert obj.count == 5

    def test_subclass_is_basemodel(self):
        class MyInput(PipelineInputData):
            value: str

        assert issubclass(MyInput, BaseModel)
        assert issubclass(MyInput, PipelineInputData)

    def test_subclass_with_optional_fields(self):
        class MyInput(PipelineInputData):
            required: str
            optional: Optional[str] = None

        obj = MyInput(required="yes")
        assert obj.required == "yes"
        assert obj.optional is None

    def test_subclass_with_defaults(self):
        class MyInput(PipelineInputData):
            mode: str = "auto"

        obj = MyInput()
        assert obj.mode == "auto"

    def test_subclass_validation_error(self):
        class MyInput(PipelineInputData):
            count: int

        with pytest.raises(ValidationError):
            MyInput(count="not_an_int")


class TestPipelineInputDataSchema:
    """model_json_schema() returns valid JSON schema from subclass."""

    def test_subclass_schema_has_properties(self):
        class MyInput(PipelineInputData):
            name: str
            age: int

        schema = MyInput.model_json_schema()
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "age" in schema["properties"]

    def test_subclass_schema_required_fields(self):
        class MyInput(PipelineInputData):
            required_field: str
            optional_field: Optional[str] = None

        schema = MyInput.model_json_schema()
        assert "required_field" in schema.get("required", [])

    def test_subclass_schema_title(self):
        class ShippingInput(PipelineInputData):
            origin: str

        schema = ShippingInput.model_json_schema()
        assert schema["title"] == "ShippingInput"

    def test_model_validate_from_dict(self):
        class MyInput(PipelineInputData):
            name: str
            count: int

        obj = MyInput.model_validate({"name": "test", "count": 3})
        assert obj.name == "test"
        assert obj.count == 3

    def test_model_validate_rejects_invalid(self):
        class MyInput(PipelineInputData):
            count: int

        with pytest.raises(ValidationError):
            MyInput.model_validate({"count": "bad"})


class TestInputDataTypeGuard:
    """INPUT_DATA ClassVar on PipelineConfig validated at class-definition time."""

    def test_valid_input_data_subclass(self):
        """Subclass with valid PipelineInputData subclass succeeds."""
        class ValidInput(PipelineInputData):
            name: str

        class ValidPipeline(PipelineConfig):
            INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = ValidInput

        assert ValidPipeline.INPUT_DATA is ValidInput

    def test_default_none_succeeds(self):
        """Subclass without INPUT_DATA (default None) succeeds."""
        class DefaultPipeline(PipelineConfig):
            pass

        assert DefaultPipeline.INPUT_DATA is None

    def test_explicit_none_succeeds(self):
        """Subclass with INPUT_DATA=None explicitly succeeds."""
        class ExplicitNonePipeline(PipelineConfig):
            INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = None

        assert ExplicitNonePipeline.INPUT_DATA is None

    def test_bare_base_class_succeeds(self):
        """PipelineInputData itself (not just subclasses) is accepted."""
        class BarePipeline(PipelineConfig):
            INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = PipelineInputData

        assert BarePipeline.INPUT_DATA is PipelineInputData

    def test_invalid_str_raises_type_error(self):
        """INPUT_DATA set to str raises TypeError at class definition."""
        with pytest.raises(TypeError, match="must be a PipelineInputData subclass"):
            class BadPipeline(PipelineConfig):
                INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = str

    def test_invalid_int_raises_type_error(self):
        """INPUT_DATA set to int raises TypeError at class definition."""
        with pytest.raises(TypeError, match="must be a PipelineInputData subclass"):
            class BadPipeline(PipelineConfig):
                INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = int

    def test_invalid_plain_basemodel_raises_type_error(self):
        """INPUT_DATA set to plain BaseModel (not PipelineInputData) raises TypeError."""
        class PlainModel(BaseModel):
            name: str

        with pytest.raises(TypeError, match="must be a PipelineInputData subclass"):
            class BadPipeline(PipelineConfig):
                INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = PlainModel

    def test_invalid_instance_raises_type_error(self):
        """INPUT_DATA set to an instance (not a class) raises TypeError."""
        class ValidInput(PipelineInputData):
            name: str

        with pytest.raises(TypeError, match="must be a PipelineInputData subclass"):
            class BadPipeline(PipelineConfig):
                INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = ValidInput(name="oops")

    def test_error_message_includes_class_name(self):
        """TypeError message includes the offending pipeline class name."""
        with pytest.raises(TypeError, match="NamedBadPipeline"):
            class NamedBadPipeline(PipelineConfig):
                INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = str
