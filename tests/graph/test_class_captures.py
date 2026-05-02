"""Class-property captures land on ``cls._init_subclass_errors``.

After the validator hoist, every check that's a property of the
node CLASS (naming convention, INPUTS / INSTRUCTIONS / MODEL /
OUTPUT type and naming, INSTRUCTIONS-not-LLMResultMixin) lives on
the relevant base class's ``__init_subclass__``. The class is the
source of truth — a broken step shows its issues on
``cls._init_subclass_errors`` regardless of whether any pipeline
references it.

This module asserts that contract: define a class, immediately
inspect its captures. No ``Pipeline`` subclass anywhere.

``location.field`` is set to a constant from the per-kind fields
class (``StepSpec.INPUTS`` etc.) so
:meth:`ArtifactField.attach_class_captures` can localise each issue
onto the matching ``ArtifactField`` sub-component when builders
call ``.attach_class_captures(cls)``.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel
from pydantic_graph import End

from llm_pipeline.graph import (
    ExtractionNode,
    LLMResultMixin,
    LLMStepNode,
    ReviewNode,
    StepInputs,
)
from llm_pipeline.prompts import PromptVariables


# ---------------------------------------------------------------------------
# LLMStepNode
# ---------------------------------------------------------------------------


class TestLLMStepNodeCaptures:
    def test_missing_inputs_lands_on_inputs_field(self):
        class _GoodInstr(LLMResultMixin):
            example: ClassVar[dict] = {"confidence_score": 0.0}

        class _BrokenStep(LLMStepNode):
            INSTRUCTIONS = _GoodInstr

            def prepare(self, inputs):
                return []

            async def run(self, ctx) -> End[None]:
                return End(None)

        codes = {e.code for e in _BrokenStep._init_subclass_errors}
        assert "missing_inputs" in codes
        # ``location.field`` uses the spec field name
        for issue in _BrokenStep._init_subclass_errors:
            if issue.code == "missing_inputs":
                assert issue.location.field == "inputs"

    def test_missing_instructions_lands_on_instructions_field(self):
        class _MyInputs(StepInputs):
            text: str

        class _NoInstrStep(LLMStepNode):
            INPUTS = _MyInputs

            def prepare(self, inputs: _MyInputs):
                return []

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in _NoInstrStep._init_subclass_errors:
            if issue.code == "missing_instructions":
                assert issue.location.field == "instructions"

    def test_name_suffix_top_level(self):
        # No "Step" suffix — top-level issue (no spec field hosts it).
        class _MyInputs(StepInputs):
            text: str

        class _MyInstr(LLMResultMixin):
            example: ClassVar[dict] = {"confidence_score": 0.0}

        class _MyPrompt(PromptVariables):
            text: str

        class BadlyNamed(LLMStepNode):
            INPUTS = _MyInputs
            INSTRUCTIONS = _MyInstr

            def prepare(self, inputs: _MyInputs) -> list[_MyPrompt]:
                return [_MyPrompt(text=inputs.text)]

            async def run(self, ctx) -> End[None]:
                return End(None)

        suffix_issues = [
            e for e in BadlyNamed._init_subclass_errors
            if e.code == "step_name_suffix"
        ]
        assert len(suffix_issues) == 1
        # top-level — no field set (nothing on the spec hosts the
        # class name itself).
        assert suffix_issues[0].location.field is None
        assert suffix_issues[0].location.node == "BadlyNamed"

    def test_instructions_not_llm_result_mixin_lands_on_instructions(self):
        class _MyInputs(StepInputs):
            text: str

        class _BareModel(BaseModel):  # NOT LLMResultMixin
            label: str = ""

        class _Step(LLMStepNode):
            INPUTS = _MyInputs
            INSTRUCTIONS = _BareModel

            def prepare(self, inputs: _MyInputs):
                return []

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in _Step._init_subclass_errors:
            if issue.code == "step_instructions_not_llm_result_mixin":
                assert issue.location.field == "instructions"
                break
        else:
            raise AssertionError("expected step_instructions_not_llm_result_mixin")

    def test_inputs_name_mismatch_lands_on_inputs(self):
        # Step suffix present + INPUTS class name doesn't match prefix.
        class _NotMatchingNameInputs(StepInputs):  # should be "AlphaInputs"
            text: str

        class _AlphaInstructions(LLMResultMixin):
            example: ClassVar[dict] = {"confidence_score": 0.0}

        class _AlphaPrompt(PromptVariables):
            text: str

        class AlphaStep(LLMStepNode):
            INPUTS = _NotMatchingNameInputs
            INSTRUCTIONS = _AlphaInstructions

            def prepare(
                self, inputs: _NotMatchingNameInputs,
            ) -> list[_AlphaPrompt]:
                return [_AlphaPrompt(text=inputs.text)]

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in AlphaStep._init_subclass_errors:
            if issue.code == "step_inputs_name_mismatch":
                assert issue.location.field == "inputs"
                break
        else:
            raise AssertionError("expected step_inputs_name_mismatch")


# ---------------------------------------------------------------------------
# ExtractionNode
# ---------------------------------------------------------------------------


class TestExtractionNodeCaptures:
    def test_missing_model_top_level(self):
        # MODEL captures use ``field=None`` because ExtractionSpec.table_name
        # is a primitive — not routable. They live on top-level ExtractionSpec.issues.
        class _ExtInputs(StepInputs):
            x: int

        class _NoModelExtraction(ExtractionNode):
            INPUTS = _ExtInputs

            def extract(self, inputs):
                return []

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in _NoModelExtraction._init_subclass_errors:
            if issue.code == "missing_model":
                assert issue.location.field is None
                break
        else:
            raise AssertionError("expected missing_model")

    def test_name_suffix_top_level(self):
        class _ExtInputs(StepInputs):
            x: int

        from sqlmodel import Field as SQLField, SQLModel

        class _Row(SQLModel, table=True):
            __tablename__ = "test_class_captures_rows"
            __table_args__ = {"extend_existing": True}
            id: int | None = SQLField(default=None, primary_key=True)

        class BadlyNamedExtractor(ExtractionNode):
            INPUTS = _ExtInputs
            MODEL = _Row

            def extract(self, inputs):
                return []

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in BadlyNamedExtractor._init_subclass_errors:
            if issue.code == "extraction_name_suffix":
                assert issue.location.field is None
                break
        else:
            raise AssertionError("expected extraction_name_suffix")

    def test_model_not_sqlmodel_top_level(self):
        class _ExtInputs(StepInputs):
            x: int

        class _NotSqlModel(BaseModel):  # plain BaseModel, not SQLModel
            x: int = 0

        class _Extraction(ExtractionNode):
            INPUTS = _ExtInputs
            MODEL = _NotSqlModel

            def extract(self, inputs):
                return []

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in _Extraction._init_subclass_errors:
            if issue.code == "extraction_model_not_sqlmodel":
                assert issue.location.field is None
                break
        else:
            raise AssertionError("expected extraction_model_not_sqlmodel")


# ---------------------------------------------------------------------------
# ReviewNode
# ---------------------------------------------------------------------------


class TestReviewNodeCaptures:
    def test_missing_output_lands_on_output(self):
        class _RevInputs(StepInputs):
            x: int

        class _NoOutputReview(ReviewNode):
            INPUTS = _RevInputs

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in _NoOutputReview._init_subclass_errors:
            if issue.code == "missing_output":
                assert issue.location.field == "output"
                break
        else:
            raise AssertionError("expected missing_output")

    def test_name_suffix_top_level(self):
        class _RevInputs(StepInputs):
            x: int

        class _RevOut(BaseModel):
            ok: bool

        class BadlyNamedReviewer(ReviewNode):
            INPUTS = _RevInputs
            OUTPUT = _RevOut

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in BadlyNamedReviewer._init_subclass_errors:
            if issue.code == "review_name_suffix":
                assert issue.location.field is None
                break
        else:
            raise AssertionError("expected review_name_suffix")

    def test_output_not_basemodel_lands_on_output(self):
        class _RevInputs(StepInputs):
            x: int

        class _Review(ReviewNode):
            INPUTS = _RevInputs
            OUTPUT = "not a class"  # type: ignore[assignment]

            async def run(self, ctx) -> End[None]:
                return End(None)

        for issue in _Review._init_subclass_errors:
            if issue.code == "review_output_not_basemodel":
                assert issue.location.field == "output"
                break
        else:
            raise AssertionError("expected review_output_not_basemodel")


# ---------------------------------------------------------------------------
# Routing via ArtifactField.attach_class_captures(source_cls)
# ---------------------------------------------------------------------------


class TestAttachClassCaptures:
    """Captures land on the matching ArtifactField sub-component
    when builders call ``.attach_class_captures(cls)``."""

    def test_inputs_capture_routes_to_step_spec_inputs(self):
        from llm_pipeline.artifacts import (
            JsonSchemaWithRefs,
            KIND_STEP,
            StepSpec,
        )

        class _MyInputs(StepInputs):
            text: str

        class _BareInstr(BaseModel):  # not LLMResultMixin → routes to .instructions
            label: str = ""

        class _RoutingStep(LLMStepNode):
            INPUTS = _MyInputs
            INSTRUCTIONS = _BareInstr

            def prepare(self, inputs: _MyInputs):
                return []

            async def run(self, ctx) -> End[None]:
                return End(None)

        spec = StepSpec(
            kind=KIND_STEP,
            name="routing",
            cls="m._RoutingStep",
            source_path="/x.py",
            inputs=JsonSchemaWithRefs(json_schema={"type": "object"}),
            instructions=JsonSchemaWithRefs(json_schema={"type": "object"}),
        ).attach_class_captures(_RoutingStep)

        instr_codes = {i.code for i in spec.instructions.issues}
        # The bareness routes to instructions; both not-LLMResultMixin
        # and the name-mismatch (not "_RoutingStepInstructions") land
        # on the .instructions sub-component.
        assert "step_instructions_not_llm_result_mixin" in instr_codes
        # The naming-convention top-level issue (step_name_suffix) is
        # NOT here because _RoutingStep ends with "Step" — fine.
        # The class-name-prefix-mismatch checks DO fire because INPUTS
        # / INSTRUCTIONS class names don't follow the prefix:
        inputs_codes = {i.code for i in spec.inputs.issues}
        assert "step_inputs_name_mismatch" in inputs_codes

    def test_prompt_variables_captures_route_to_prompt_data_variables(self):
        """PromptVariables captures use field=PromptData.VARIABLES
        and route onto PromptData.variables.issues (the unified
        PromptVariableDefs sub-component). Single home for both
        Pydantic-fields and auto_vars problems."""
        from llm_pipeline.artifacts import (
            PromptData,
            PromptVariableDefs,
        )

        class _BadPrompt(PromptVariables):
            text: str = ""  # missing Field(description=...)

        prompt = PromptData(
            variables=PromptVariableDefs(json_schema={"type": "object"}),
            yaml_path="/tmp/x.yaml",
        ).attach_class_captures(_BadPrompt)

        # Issue routes structurally onto the variables sub-component,
        # not top-level — single canonical home.
        assert prompt.issues == []
        var_codes = {i.code for i in prompt.variables.issues}
        assert "missing_field_description" in var_codes

    def test_top_level_issue_lands_on_spec_issues(self):
        from llm_pipeline.artifacts import (
            JsonSchemaWithRefs,
            KIND_STEP,
            StepSpec,
        )

        class _Inputs(StepInputs):
            text: str

        class _Instr(LLMResultMixin):
            example: ClassVar[dict] = {"confidence_score": 0.0}

        class _Prompt(PromptVariables):
            text: str

        # No "Step" suffix → step_name_suffix at top-level.
        class TopLevelIssueClass(LLMStepNode):
            INPUTS = _Inputs
            INSTRUCTIONS = _Instr

            def prepare(self, inputs: _Inputs) -> list[_Prompt]:
                return [_Prompt(text=inputs.text)]

            async def run(self, ctx) -> End[None]:
                return End(None)

        spec = StepSpec(
            kind=KIND_STEP,
            name="top_level_issue_class",
            cls="m.TopLevelIssueClass",
            source_path="/x.py",
            inputs=JsonSchemaWithRefs(json_schema={"type": "object"}),
            instructions=JsonSchemaWithRefs(json_schema={"type": "object"}),
        ).attach_class_captures(TopLevelIssueClass)

        top_codes = {i.code for i in spec.issues}
        assert "step_name_suffix" in top_codes
