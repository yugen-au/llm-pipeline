"""
Tests for PipelineIntrospector - class-level pipeline metadata extraction.
No DB, no LLM, no FastAPI required.
"""
from typing import ClassVar, List, Optional

import pytest
from pydantic import BaseModel
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
from llm_pipeline.agent_registry import clear_agent_registry, register_agent
from llm_pipeline.inputs import PipelineInputData, StepInputs
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.transformation import PipelineTransformation
from llm_pipeline.wiring import Bind, FromInput, FromOutput


# ---------- Domain classes (minimal WidgetPipeline pattern) ----------

class WidgetModel(SQLModel, table=True):
    __tablename__ = "introspection_test_widgets"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str


class WidgetPipelineInput(PipelineInputData):
    data: str


class WidgetDetectionInputs(StepInputs):
    data: str


class WidgetDetectionInstructions(LLMResultMixin):
    widget_count: int
    category: str

    example: ClassVar[dict] = {
        "widget_count": 2,
        "category": "test",
        "notes": "test",
    }


class WidgetExtraction(PipelineExtraction, model=WidgetModel):
    class FromWidgetDetectionInputs(StepInputs):
        widget_count: int
        category: str

    def from_widget_detection(
        self, inputs: FromWidgetDetectionInputs
    ) -> list[WidgetModel]:
        return [
            WidgetModel(name=f"w_{i}", category=inputs.category)
            for i in range(inputs.widget_count)
        ]


@step_definition(
    inputs=WidgetDetectionInputs,
    instructions=WidgetDetectionInstructions,
)
class WidgetDetectionStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {"data": self.inputs.data}}]


def _widget_extraction_bind() -> Bind:
    return Bind(
        extraction=WidgetExtraction,
        inputs=WidgetExtraction.FromWidgetDetectionInputs.sources(
            widget_count=FromOutput(WidgetDetectionStep, field="widget_count"),
            category=FromOutput(WidgetDetectionStep, field="category"),
        ),
    )


def _widget_step_bind() -> Bind:
    return Bind(
        step=WidgetDetectionStep,
        inputs=WidgetDetectionInputs.sources(data=FromInput("data")),
        extractions=[_widget_extraction_bind()],
    )


# ---------- Transformation domain classes (Pydantic input/output) ----------

class TransformInput(BaseModel):
    raw: str


class TransformOutput(BaseModel):
    processed: str


class ScanDetectionInputs(StepInputs):
    data: str


class ScanDetectionInstructions(LLMResultMixin):
    count: int
    example: ClassVar[dict] = {"count": 1, "notes": "scan"}


class ScanDetectionTransformation(PipelineTransformation,
                                  input_type=TransformInput,
                                  output_type=TransformOutput):
    def default(self, data, instructions):
        return TransformOutput(processed=data.raw.upper())


@step_definition(
    inputs=ScanDetectionInputs,
    instructions=ScanDetectionInstructions,
    default_transformation=ScanDetectionTransformation,
)
class ScanDetectionStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {}}]


class ScanStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_bindings(self) -> List[Bind]:
        return [
            Bind(
                step=ScanDetectionStep,
                inputs=ScanDetectionInputs.sources(data=FromInput("data")),
            ),
        ]


class ScanRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
    pass


class ScanStrategies(PipelineStrategies, strategies=[ScanStrategy]):
    pass


class ScanPipeline(PipelineConfig, registry=ScanRegistry, strategies=ScanStrategies):
    INPUT_DATA = WidgetPipelineInput


# ---------- Transformation domain classes (non-Pydantic input/output) ----------

class PlainInput:
    pass


class PlainOutput:
    pass


class GadgetDetectionInputs(StepInputs):
    data: str


class GadgetDetectionInstructions(LLMResultMixin):
    count: int
    example: ClassVar[dict] = {"count": 1, "notes": "gadget"}


class GadgetDetectionTransformation(PipelineTransformation,
                                    input_type=PlainInput,
                                    output_type=PlainOutput):
    def default(self, data, instructions):
        return PlainOutput()


@step_definition(
    inputs=GadgetDetectionInputs,
    instructions=GadgetDetectionInstructions,
    default_transformation=GadgetDetectionTransformation,
)
class GadgetDetectionStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {}}]


class GadgetStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_bindings(self) -> List[Bind]:
        return [
            Bind(
                step=GadgetDetectionStep,
                inputs=GadgetDetectionInputs.sources(data=FromInput("data")),
            ),
        ]


class GadgetRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
    pass


class GadgetStrategies(PipelineStrategies, strategies=[GadgetStrategy]):
    pass


class GadgetPipeline(PipelineConfig, registry=GadgetRegistry, strategies=GadgetStrategies):
    INPUT_DATA = WidgetPipelineInput


# ---------- Primary strategy (no transformation) ----------

class PrimaryStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_bindings(self) -> List[Bind]:
        return [_widget_step_bind()]


class WidgetRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
    pass


class WidgetStrategies(PipelineStrategies, strategies=[PrimaryStrategy]):
    pass


class WidgetPipeline(PipelineConfig, registry=WidgetRegistry, strategies=WidgetStrategies):
    INPUT_DATA = WidgetPipelineInput


# ---------- Helper: clear cache between tests ----------

@pytest.fixture(autouse=True)
def clear_introspector_cache():
    """Ensure _cache is empty before each test to avoid cross-test pollution."""
    PipelineIntrospector._cache.clear()
    yield
    PipelineIntrospector._cache.clear()


# ---------- Tests ----------

class TestGetMetadataTopLevel:
    def test_returns_dict(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        assert isinstance(meta, dict)

    def test_pipeline_name_correct(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        assert meta["pipeline_name"] == "widget"

    def test_required_top_level_keys_present(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        for key in ("pipeline_name", "registry_models", "strategies", "execution_order"):
            assert key in meta, f"missing key: {key}"


class TestStrategiesList:
    def test_strategies_length_matches_definition(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        assert len(meta["strategies"]) == len(WidgetStrategies.STRATEGIES)

    def test_each_strategy_has_required_keys(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        for strategy in meta["strategies"]:
            for key in ("name", "display_name", "class_name", "steps"):
                assert key in strategy, f"strategy missing key: {key}"

    def test_strategy_class_name_correct(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        class_names = [s["class_name"] for s in meta["strategies"]]
        assert "PrimaryStrategy" in class_names

    def test_strategy_name_is_snake_case(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        assert meta["strategies"][0]["name"] == "primary"


class TestStepEntries:
    def _step(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        return meta["strategies"][0]["steps"][0]

    def test_step_has_required_keys(self):
        step = self._step()
        for key in ("step_name", "system_key", "user_key",
                    "instructions_class", "instructions_schema",
                    "inputs_class", "inputs_schema", "extractions"):
            assert key in step, f"step missing key: {key}"

    def test_step_name_correct(self):
        assert self._step()["step_name"] == "widget_detection"

    def test_system_key_correct(self):
        # Phase C: introspection emits ``<prompt_name>.system_instruction``
        # derived from the step's snake_case class name.
        assert self._step()["system_key"] == "widget_detection.system_instruction"

    def test_user_key_correct(self):
        assert self._step()["user_key"] == "widget_detection.user_prompt"

    def test_instructions_class_name(self):
        assert self._step()["instructions_class"] == "WidgetDetectionInstructions"

    def test_instructions_schema_is_valid_json_schema(self):
        schema = self._step()["instructions_schema"]
        assert isinstance(schema, dict)
        # Valid JSON Schema for a Pydantic model has 'type' and 'properties'
        assert "type" in schema or "properties" in schema

    def test_inputs_class_name(self):
        assert self._step()["inputs_class"] == "WidgetDetectionInputs"

    def test_inputs_schema_is_valid_json_schema(self):
        schema = self._step()["inputs_schema"]
        assert isinstance(schema, dict)
        assert "type" in schema or "properties" in schema


class TestExtractionEntries:
    def _extraction(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        return meta["strategies"][0]["steps"][0]["extractions"][0]

    def test_extraction_has_required_keys(self):
        ext = self._extraction()
        for key in ("class_name", "model_class", "methods"):
            assert key in ext, f"extraction missing key: {key}"

    def test_extraction_class_name(self):
        assert self._extraction()["class_name"] == "WidgetExtraction"

    def test_extraction_model_class(self):
        assert self._extraction()["model_class"] == "WidgetModel"

    def test_extraction_methods_is_list(self):
        assert isinstance(self._extraction()["methods"], list)

    def test_extraction_methods_contains_pathway_method(self):
        # Under the new contract, extractions dispatch per pathway inputs
        # class; the method name is whatever the author chose, e.g.
        # from_widget_detection for FromWidgetDetectionInputs.
        assert "from_widget_detection" in self._extraction()["methods"]


class TestExecutionOrder:
    def test_execution_order_is_list(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        assert isinstance(meta["execution_order"], list)

    def test_execution_order_contains_step_names(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        assert "widget_detection" in meta["execution_order"]

    def test_execution_order_deduplicated(self):
        """When same step class appears in multiple strategies, listed only once."""

        class AlphaStrategy(PipelineStrategy):
            def can_handle(self, ctx):
                return True

            def get_bindings(self) -> List[Bind]:
                return [_widget_step_bind()]

        class BetaStrategy(PipelineStrategy):
            def can_handle(self, ctx):
                return False

            def get_bindings(self) -> List[Bind]:
                return [_widget_step_bind()]

        class DedupeStrategies(PipelineStrategies, strategies=[AlphaStrategy, BetaStrategy]):
            pass

        class DedupeRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
            pass

        class DedupePipeline(PipelineConfig, registry=DedupeRegistry, strategies=DedupeStrategies):
            INPUT_DATA = WidgetPipelineInput

        meta = PipelineIntrospector(DedupePipeline).get_metadata()
        order = meta["execution_order"]
        assert order.count("widget_detection") == 1

    def test_execution_order_items_are_strings(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        for item in meta["execution_order"]:
            assert isinstance(item, str)


class TestRegistryModels:
    def test_registry_models_is_list(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        assert isinstance(meta["registry_models"], list)

    def test_registry_models_contains_model_class_names(self):
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        assert "WidgetModel" in meta["registry_models"]


class TestCaching:
    def test_get_metadata_twice_returns_same_object(self):
        introspector = PipelineIntrospector(WidgetPipeline)
        first = introspector.get_metadata()
        second = introspector.get_metadata()
        assert first is second

    def test_different_introspector_instances_same_pipeline_share_cache(self):
        """Two separate PipelineIntrospector instances for the same class hit the same cache."""
        a = PipelineIntrospector(WidgetPipeline)
        b = PipelineIntrospector(WidgetPipeline)
        first = a.get_metadata()
        second = b.get_metadata()
        assert first is second


class TestGetSchemaNonPydantic:
    def test_non_pydantic_type_returns_type_dict(self):
        """_get_schema() with a non-Pydantic class returns {"type": class_name}."""

        class PlainClass:
            pass

        result = PipelineIntrospector._get_schema(PlainClass)
        assert result == {"type": "PlainClass"}

    def test_non_pydantic_type_does_not_raise(self):
        class AnotherPlain:
            pass

        try:
            PipelineIntrospector._get_schema(AnotherPlain)
        except Exception as exc:
            pytest.fail(f"_get_schema raised unexpectedly: {exc}")

    def test_pydantic_type_returns_full_schema(self):
        class SampleModel(BaseModel):
            value: int

        result = PipelineIntrospector._get_schema(SampleModel)
        assert isinstance(result, dict)
        assert "properties" in result

    def test_none_returns_none(self):
        assert PipelineIntrospector._get_schema(None) is None


class TestBrokenStrategy:
    def test_broken_strategy_init_returns_error_dict_not_exception(self):
        """A strategy whose __init__ raises is captured in 'error' key, no exception raised."""

        class ErroringStrategy(PipelineStrategy):
            def __init__(self):
                raise RuntimeError("cannot init")

            def can_handle(self, ctx):
                return True

            def get_bindings(self) -> List[Bind]:
                return []

        class ErroringStrategies(PipelineStrategies, strategies=[ErroringStrategy]):
            pass

        class ErroringRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
            pass

        class ErroringPipeline(PipelineConfig, registry=ErroringRegistry, strategies=ErroringStrategies):
            INPUT_DATA = WidgetPipelineInput

        # Must not raise
        meta = PipelineIntrospector(ErroringPipeline).get_metadata()

        strategies = meta["strategies"]
        assert len(strategies) == 1
        broken = strategies[0]
        assert "error" in broken
        assert "RuntimeError" in broken["error"]

    def test_broken_strategy_does_not_affect_other_strategies(self):
        """A broken strategy entry still returns name/display_name/class_name."""

        class FailingStrategy(PipelineStrategy):
            def __init__(self):
                raise ValueError("boom")

            def can_handle(self, ctx):
                return True

            def get_bindings(self) -> List[Bind]:
                return []

        class ComboStrategies(PipelineStrategies, strategies=[FailingStrategy, PrimaryStrategy]):
            pass

        class ComboRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
            pass

        class ComboPipeline(PipelineConfig, registry=ComboRegistry, strategies=ComboStrategies):
            INPUT_DATA = WidgetPipelineInput

        meta = PipelineIntrospector(ComboPipeline).get_metadata()
        strategies = meta["strategies"]
        assert len(strategies) == 2

        broken = strategies[0]
        assert "error" in broken
        assert broken["class_name"] == "FailingStrategy"

        ok = strategies[1]
        assert "error" not in ok
        assert ok["class_name"] == "PrimaryStrategy"
        assert len(ok["steps"]) == 1


class TestTransformation:
    def _step(self, pipeline_cls):
        meta = PipelineIntrospector(pipeline_cls).get_metadata()
        return meta["strategies"][0]["steps"][0]

    def test_transformation_key_present_in_step(self):
        step = self._step(ScanPipeline)
        assert "transformation" in step

    def test_transformation_is_not_none_when_configured(self):
        step = self._step(ScanPipeline)
        assert step["transformation"] is not None

    def test_transformation_class_name(self):
        t = self._step(ScanPipeline)["transformation"]
        assert t["class_name"] == "ScanDetectionTransformation"

    def test_transformation_pydantic_input_type_name(self):
        t = self._step(ScanPipeline)["transformation"]
        assert t["input_type"] == "TransformInput"

    def test_transformation_pydantic_output_type_name(self):
        t = self._step(ScanPipeline)["transformation"]
        assert t["output_type"] == "TransformOutput"

    def test_transformation_pydantic_input_schema_has_properties(self):
        t = self._step(ScanPipeline)["transformation"]
        assert isinstance(t["input_schema"], dict)
        assert "properties" in t["input_schema"]

    def test_transformation_pydantic_output_schema_has_properties(self):
        t = self._step(ScanPipeline)["transformation"]
        assert isinstance(t["output_schema"], dict)
        assert "properties" in t["output_schema"]

    def test_transformation_non_pydantic_input_schema_is_type_dict(self):
        t = self._step(GadgetPipeline)["transformation"]
        assert t["input_schema"] == {"type": "PlainInput"}

    def test_transformation_non_pydantic_output_schema_is_type_dict(self):
        t = self._step(GadgetPipeline)["transformation"]
        assert t["output_schema"] == {"type": "PlainOutput"}

    def test_transformation_non_pydantic_type_names(self):
        t = self._step(GadgetPipeline)["transformation"]
        assert t["input_type"] == "PlainInput"
        assert t["output_type"] == "PlainOutput"

    def test_no_transformation_is_none(self):
        """Step without transformation has transformation=None."""
        step = self._step(WidgetPipeline)
        assert step["transformation"] is None


# ---------- Tools metadata ----------

def _dummy_tool_alpha(x: int) -> str:
    """Dummy tool for testing introspection."""
    return str(x)


def _dummy_tool_beta(y: str) -> bool:
    """Another dummy tool."""
    return bool(y)


class TooledInputs(StepInputs):
    data: str


class TooledInstructions(LLMResultMixin):
    widget_count: int
    category: str

    example: ClassVar[dict] = {
        "widget_count": 2,
        "category": "test",
        "notes": "test",
    }


@step_definition(
    inputs=TooledInputs,
    instructions=TooledInstructions,
    agent="tooled",
)
class TooledStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {"data": self.inputs.data}}]


class TooledStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_bindings(self) -> List[Bind]:
        return [
            Bind(
                step=TooledStep,
                inputs=TooledInputs.sources(data=FromInput("data")),
                extractions=[
                    Bind(
                        extraction=WidgetExtraction,
                        inputs=WidgetExtraction.FromWidgetDetectionInputs.sources(
                            widget_count=FromOutput(TooledStep, field="widget_count"),
                            category=FromOutput(TooledStep, field="category"),
                        ),
                    ),
                ],
            ),
        ]


class TooledStrategies(PipelineStrategies, strategies=[TooledStrategy]):
    pass


class TooledRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
    pass


class TooledPipeline(PipelineConfig,
                      registry=TooledRegistry,
                      strategies=TooledStrategies):
    INPUT_DATA = WidgetPipelineInput


class TestToolsMetadata:

    def setup_method(self):
        register_agent("tooled", [_dummy_tool_alpha, _dummy_tool_beta])

    def teardown_method(self):
        clear_agent_registry()

    def test_tools_key_present_in_step(self):
        """Every step_entry has a 'tools' key."""
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert "tools" in step

    def test_tools_empty_when_no_agent_registered(self):
        """Step without agent= -> tools=[]."""
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert step["tools"] == []

    def test_tools_populated_from_registered_agent(self):
        """Step with agent= + registered tools -> tool names listed."""
        meta = PipelineIntrospector(TooledPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert "_dummy_tool_alpha" in step["tools"]
        assert "_dummy_tool_beta" in step["tools"]
        assert len(step["tools"]) == 2

    def test_tools_is_list_of_strings(self):
        meta = PipelineIntrospector(TooledPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert isinstance(step["tools"], list)
        for name in step["tools"]:
            assert isinstance(name, str)

    def test_tools_empty_when_agent_not_registered(self):
        """Step with agent= but no matching register_agent() -> tools=[]."""
        clear_agent_registry()
        meta = PipelineIntrospector(TooledPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert step["tools"] == []

    def test_tools_empty_when_no_agent_on_step(self):
        """Step without agent= always has tools=[] regardless of registry."""
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert step["tools"] == []
