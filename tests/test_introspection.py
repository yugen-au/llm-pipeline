"""
Tests for PipelineIntrospector - class-level pipeline metadata extraction.
No DB, no LLM, no FastAPI required.
"""
import pytest
from typing import ClassVar, List, Optional

from pydantic import BaseModel
from sqlmodel import SQLModel, Field

from llm_pipeline import (
    PipelineConfig,
    LLMStep,
    LLMResultMixin,
    step_definition,
    PipelineStrategy,
    PipelineStrategies,
    PipelineContext,
    PipelineExtraction,
    PipelineDatabaseRegistry,
)
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.transformation import PipelineTransformation
from llm_pipeline.agent_registry import AgentRegistry, AgentSpec


# ---------- Domain classes (minimal WidgetPipeline pattern) ----------

class WidgetModel(SQLModel, table=True):
    __tablename__ = "introspection_test_widgets"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str


class WidgetDetectionInstructions(LLMResultMixin):
    widget_count: int
    category: str

    example: ClassVar[dict] = {
        "widget_count": 2,
        "category": "test",
        "notes": "test",
    }


class WidgetDetectionContext(PipelineContext):
    category: str


class WidgetExtraction(PipelineExtraction, model=WidgetModel):
    def default(self, results):
        return [WidgetModel(name=f"w_{i}", category=results[0].category)
                for i in range(results[0].widget_count)]


@step_definition(
    instructions=WidgetDetectionInstructions,
    default_system_key="widget.system",
    default_user_key="widget.user",
    default_extractions=[WidgetExtraction],
    context=WidgetDetectionContext,
)
class WidgetDetectionStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {"data": self.pipeline.get_sanitized_data()}}]

    def process_instructions(self, instructions):
        return WidgetDetectionContext(category=instructions[0].category)


# ---------- Transformation domain classes (Pydantic input/output) ----------

class TransformInput(BaseModel):
    raw: str


class TransformOutput(BaseModel):
    processed: str


class ScanDetectionInstructions(LLMResultMixin):
    count: int
    example: ClassVar[dict] = {"count": 1, "notes": "scan"}


class ScanDetectionTransformation(PipelineTransformation,
                                  input_type=TransformInput,
                                  output_type=TransformOutput):
    def default(self, data, instructions):
        return TransformOutput(processed=data.raw.upper())


@step_definition(
    instructions=ScanDetectionInstructions,
    default_system_key="scan.system",
    default_user_key="scan.user",
    default_transformation=ScanDetectionTransformation,
)
class ScanDetectionStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {}}]

    def process_instructions(self, instructions):
        return None


class ScanStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [ScanDetectionStep.create_definition()]


class ScanRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
    pass


class ScanStrategies(PipelineStrategies, strategies=[ScanStrategy]):
    pass


class ScanPipeline(PipelineConfig, registry=ScanRegistry, strategies=ScanStrategies):
    pass


# ---------- Transformation domain classes (non-Pydantic input/output) ----------

class PlainInput:
    pass


class PlainOutput:
    pass


class GadgetDetectionInstructions(LLMResultMixin):
    count: int
    example: ClassVar[dict] = {"count": 1, "notes": "gadget"}


class GadgetDetectionTransformation(PipelineTransformation,
                                    input_type=PlainInput,
                                    output_type=PlainOutput):
    def default(self, data, instructions):
        return PlainOutput()


@step_definition(
    instructions=GadgetDetectionInstructions,
    default_system_key="gadget.system",
    default_user_key="gadget.user",
    default_transformation=GadgetDetectionTransformation,
)
class GadgetDetectionStep(LLMStep):
    def prepare_calls(self):
        return [{"variables": {}}]

    def process_instructions(self, instructions):
        return None


class GadgetStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [GadgetDetectionStep.create_definition()]


class GadgetRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
    pass


class GadgetStrategies(PipelineStrategies, strategies=[GadgetStrategy]):
    pass


class GadgetPipeline(PipelineConfig, registry=GadgetRegistry, strategies=GadgetStrategies):
    pass


# ---------- Primary strategy (no transformation) ----------

class PrimaryStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [WidgetDetectionStep.create_definition()]


class WidgetRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
    pass


class WidgetStrategies(PipelineStrategies, strategies=[PrimaryStrategy]):
    pass


class WidgetPipeline(PipelineConfig, registry=WidgetRegistry, strategies=WidgetStrategies):
    pass


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
                    "instructions_class", "instructions_schema", "extractions"):
            assert key in step, f"step missing key: {key}"

    def test_step_name_correct(self):
        assert self._step()["step_name"] == "widget_detection"

    def test_system_key_correct(self):
        assert self._step()["system_key"] == "widget.system"

    def test_user_key_correct(self):
        assert self._step()["user_key"] == "widget.user"

    def test_instructions_class_name(self):
        assert self._step()["instructions_class"] == "WidgetDetectionInstructions"

    def test_instructions_schema_is_valid_json_schema(self):
        schema = self._step()["instructions_schema"]
        assert isinstance(schema, dict)
        # Valid JSON Schema for a Pydantic model has 'type' and 'properties'
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

    def test_extraction_methods_contains_default(self):
        # 'default' is a custom method on WidgetExtraction not present on PipelineExtraction
        assert "default" in self._extraction()["methods"]


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

            def get_steps(self):
                return [WidgetDetectionStep.create_definition()]

        class BetaStrategy(PipelineStrategy):
            def can_handle(self, ctx):
                return False

            def get_steps(self):
                return [WidgetDetectionStep.create_definition()]

        class DedupeStrategies(PipelineStrategies, strategies=[AlphaStrategy, BetaStrategy]):
            pass

        class DedupeRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
            pass

        class DedupePipeline(PipelineConfig, registry=DedupeRegistry, strategies=DedupeStrategies):
            pass

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

            def get_steps(self):
                return []

        class ErroringStrategies(PipelineStrategies, strategies=[ErroringStrategy]):
            pass

        class ErroringRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
            pass

        class ErroringPipeline(PipelineConfig, registry=ErroringRegistry, strategies=ErroringStrategies):
            pass

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

            def get_steps(self):
                return []

        class ComboStrategies(PipelineStrategies, strategies=[FailingStrategy, PrimaryStrategy]):
            pass

        class ComboRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
            pass

        class ComboPipeline(PipelineConfig, registry=ComboRegistry, strategies=ComboStrategies):
            pass

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


class TooledAgentRegistry(AgentRegistry, agents={
    "widget_detection": AgentSpec(
        instructions=WidgetDetectionInstructions,
        tools=[_dummy_tool_alpha, _dummy_tool_beta],
    ),
}):
    pass


class TooledStrategies(PipelineStrategies, strategies=[PrimaryStrategy]):
    pass


class TooledRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
    pass


class TooledPipeline(PipelineConfig,
                      registry=TooledRegistry,
                      strategies=TooledStrategies,
                      agent_registry=TooledAgentRegistry):
    pass


class TestToolsMetadata:
    def test_tools_key_present_in_step(self):
        """Every step_entry has a 'tools' key."""
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert "tools" in step

    def test_tools_empty_when_no_agent_registry(self):
        """Pipeline without AGENT_REGISTRY -> tools=[]."""
        meta = PipelineIntrospector(WidgetPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert step["tools"] == []

    def test_tools_populated_from_agent_registry(self):
        """Pipeline with AGENT_REGISTRY + AgentSpec -> tool names listed."""
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

    def test_tools_empty_for_bare_type_in_registry(self):
        """AgentRegistry with bare Type (no AgentSpec) -> tools=[]."""

        class BareAgentRegistry(AgentRegistry, agents={
            "widget_detection": WidgetDetectionInstructions,
        }):
            pass

        class BareRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
            pass

        class BareStrategies(PipelineStrategies, strategies=[PrimaryStrategy]):
            pass

        class BarePipeline(PipelineConfig,
                           registry=BareRegistry,
                           strategies=BareStrategies,
                           agent_registry=BareAgentRegistry):
            pass

        meta = PipelineIntrospector(BarePipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        assert step["tools"] == []

    def test_tools_graceful_when_step_not_in_registry(self):
        """If step_name not in AGENT_REGISTRY.AGENTS, tools stays []."""

        class MismatchAgentRegistry(AgentRegistry, agents={
            "nonexistent_step": WidgetDetectionInstructions,
        }):
            pass

        class MismatchRegistry(PipelineDatabaseRegistry, models=[WidgetModel]):
            pass

        class MismatchStrategies(PipelineStrategies, strategies=[PrimaryStrategy]):
            pass

        class MismatchPipeline(PipelineConfig,
                               registry=MismatchRegistry,
                               strategies=MismatchStrategies,
                               agent_registry=MismatchAgentRegistry):
            pass

        meta = PipelineIntrospector(MismatchPipeline).get_metadata()
        step = meta["strategies"][0]["steps"][0]
        # get_tools raises KeyError for missing step; caught by try/except
        assert step["tools"] == []
