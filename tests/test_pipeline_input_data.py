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
