"""
Tests for PipelineInputData base class, INPUT_DATA type guard, and execute() validation.
"""
import json
from typing import Any, ClassVar, Dict, List, Optional, Type

import pytest
from pydantic import BaseModel, ValidationError
from sqlmodel import SQLModel, Field, Session, create_engine

from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
from llm_pipeline.registry import PipelineDatabaseRegistry


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


# ---------- Execute validation test infrastructure ----------

class OrderInput(PipelineInputData):
    order_id: str
    quantity: int


class EmptyStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_bindings(self):
        return []


class _DummyModel(SQLModel, table=True):
    __tablename__ = "input_data_test_dummy"
    id: Optional[int] = Field(default=None, primary_key=True)


class ValidateRegistry(PipelineDatabaseRegistry, models=[_DummyModel]):
    pass


class ValidateStrategies(PipelineStrategies, strategies=[EmptyStrategy]):
    pass


class ValidatePipeline(
    PipelineConfig,
    registry=ValidateRegistry,
    strategies=ValidateStrategies,
):
    INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]] = OrderInput


class NoInputRegistry(PipelineDatabaseRegistry, models=[_DummyModel]):
    pass


class NoInputStrategies(PipelineStrategies, strategies=[EmptyStrategy]):
    pass


class NoInputPipeline(
    PipelineConfig,
    registry=NoInputRegistry,
    strategies=NoInputStrategies,
):
    """Pipeline without INPUT_DATA -- no validation enforced."""
    pass


@pytest.fixture
def input_engine():
    eng = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def input_session(input_engine):
    with Session(input_engine) as sess:
        yield sess


# ---------- Execute validation tests ----------

class TestExecuteInputDataValidation:
    """execute() validates input_data against INPUT_DATA schema."""

    def test_raises_when_input_data_none(self, input_session):
        """ValueError when INPUT_DATA declared but input_data not provided."""
        pipeline = ValidatePipeline(session=input_session, model="test-model")
        with pytest.raises(ValueError, match="requires input_data"):
            pipeline.execute(data="x")

    def test_raises_when_input_data_empty_dict(self, input_session):
        """ValueError when INPUT_DATA declared and input_data is empty dict."""
        pipeline = ValidatePipeline(session=input_session, model="test-model")
        with pytest.raises(ValueError, match="requires input_data"):
            pipeline.execute(data="x", input_data={})

    def test_valid_input_succeeds(self, input_session):
        """Valid input_data passes validation and execute completes."""
        pipeline = ValidatePipeline(session=input_session, model="test-model")
        result = pipeline.execute(
            data="x", input_data={"order_id": "ORD-1", "quantity": 5}
        )
        assert result is pipeline

    def test_raises_on_schema_mismatch(self, input_session):
        """ValueError on input_data that doesn't match INPUT_DATA schema."""
        pipeline = ValidatePipeline(session=input_session, model="test-model")
        with pytest.raises(ValueError, match="input_data validation failed"):
            pipeline.execute(data="x", input_data={"order_id": "ORD-1", "quantity": "bad"})

    def test_raises_on_missing_required_field(self, input_session):
        """ValueError when required field missing from input_data."""
        pipeline = ValidatePipeline(session=input_session, model="test-model")
        with pytest.raises(ValueError, match="input_data validation failed"):
            pipeline.execute(data="x", input_data={"order_id": "ORD-1"})

    def test_error_includes_pipeline_name(self, input_session):
        """Error message includes pipeline name for debugging."""
        pipeline = ValidatePipeline(session=input_session, model="test-model")
        with pytest.raises(ValueError, match="validate"):
            pipeline.execute(data="x", input_data={})

    def test_no_input_data_pipeline_skips_validation(self, input_session):
        """Pipeline without INPUT_DATA executes fine without input_data."""
        pipeline = NoInputPipeline(session=input_session, model="test-model")
        result = pipeline.execute(data="x")
        assert result is pipeline

    def test_no_input_data_pipeline_accepts_raw_dict(self, input_session):
        """Pipeline without INPUT_DATA stores raw dict as validated_input."""
        pipeline = NoInputPipeline(session=input_session, model="test-model")
        pipeline.execute(data="x", input_data={"arbitrary": "data"})
        assert pipeline.validated_input == {"arbitrary": "data"}


class TestValidatedInputProperty:
    """validated_input property exposes validated data to steps."""

    def test_returns_pydantic_model_after_execute(self, input_session):
        """validated_input returns PipelineInputData instance after valid execute."""
        pipeline = ValidatePipeline(session=input_session, model="test-model")
        pipeline.execute(data="x", input_data={"order_id": "ORD-1", "quantity": 5})
        result = pipeline.validated_input
        assert isinstance(result, OrderInput)
        assert result.order_id == "ORD-1"
        assert result.quantity == 5

    def test_returns_none_before_execute(self, input_session):
        """validated_input is None before execute() is called."""
        pipeline = ValidatePipeline(session=input_session, model="test-model")
        assert pipeline.validated_input is None

    def test_returns_none_when_no_input_data_and_no_schema(self, input_session):
        """validated_input is None when no INPUT_DATA and no input_data provided."""
        pipeline = NoInputPipeline(session=input_session, model="test-model")
        pipeline.execute(data="x")
        assert pipeline.validated_input is None

    def test_returns_raw_dict_when_no_schema(self, input_session):
        """validated_input returns raw dict when INPUT_DATA not declared."""
        pipeline = NoInputPipeline(session=input_session, model="test-model")
        pipeline.execute(data="x", input_data={"key": "val"})
        assert pipeline.validated_input == {"key": "val"}
