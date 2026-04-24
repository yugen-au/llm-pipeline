"""Tests for llm_pipeline.wiring: Source types, AdapterContext, SourcesSpec, Bind,
and validate_bindings static analysis.
"""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from llm_pipeline.wiring import (
    AdapterContext,
    Bind,
    Computed,
    FromInput,
    FromOutput,
    FromPipeline,
    SourcesSpec,
    validate_bindings,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


class _Nested(BaseModel):
    value: str


class _PipelineInput(BaseModel):
    name: str
    count: int
    nested: _Nested | None = None


class _Instructions(BaseModel):
    confidence: float
    label: str


class _StepA:
    """Placeholder step class; only identity matters for FromOutput keying."""


class _MyInputs(BaseModel):
    name: str
    count: int


def _ctx(
    *,
    input: BaseModel | None = None,
    outputs: dict | None = None,
    pipeline: object | None = None,
) -> AdapterContext:
    return AdapterContext(
        input=input if input is not None else _PipelineInput(name="hello", count=3),
        outputs=outputs if outputs is not None else {},
        pipeline=pipeline if pipeline is not None else SimpleNamespace(),
    )


# ---------------------------------------------------------------------------
# FromInput
# ---------------------------------------------------------------------------


class TestFromInput:
    def test_resolves_top_level_attr(self):
        ctx = _ctx(input=_PipelineInput(name="alpha", count=7))
        assert FromInput("name").resolve(ctx) == "alpha"
        assert FromInput("count").resolve(ctx) == 7

    def test_resolves_dotted_path(self):
        nested = _Nested(value="x")
        ctx = _ctx(input=_PipelineInput(name="a", count=1, nested=nested))
        assert FromInput("nested.value").resolve(ctx) == "x"

    def test_raises_on_missing_attr(self):
        ctx = _ctx()
        with pytest.raises(AttributeError):
            FromInput("missing").resolve(ctx)

    def test_is_frozen(self):
        src = FromInput("x")
        with pytest.raises(FrozenInstanceError):
            src.path = "y"  # type: ignore[misc]

    def test_equality_and_hash(self):
        assert FromInput("x") == FromInput("x")
        assert FromInput("x") != FromInput("y")
        assert hash(FromInput("x")) == hash(FromInput("x"))


# ---------------------------------------------------------------------------
# FromOutput
# ---------------------------------------------------------------------------


class TestFromOutput:
    def test_resolves_whole_instruction(self):
        inst = _Instructions(confidence=0.9, label="cat")
        ctx = _ctx(outputs={_StepA: [inst]})
        assert FromOutput(_StepA).resolve(ctx) is inst

    def test_resolves_field(self):
        inst = _Instructions(confidence=0.8, label="dog")
        ctx = _ctx(outputs={_StepA: [inst]})
        assert FromOutput(_StepA, field="label").resolve(ctx) == "dog"
        assert FromOutput(_StepA, field="confidence").resolve(ctx) == 0.8

    def test_resolves_nth_call(self):
        insts = [
            _Instructions(confidence=0.1, label="a"),
            _Instructions(confidence=0.9, label="b"),
        ]
        ctx = _ctx(outputs={_StepA: insts})
        assert FromOutput(_StepA, index=1).resolve(ctx) is insts[1]
        assert FromOutput(_StepA, index=1, field="label").resolve(ctx) == "b"

    def test_raises_on_missing_step(self):
        ctx = _ctx()
        with pytest.raises(KeyError, match="_StepA"):
            FromOutput(_StepA).resolve(ctx)

    def test_raises_on_empty_outputs_list(self):
        ctx = _ctx(outputs={_StepA: []})
        with pytest.raises(KeyError, match="_StepA"):
            FromOutput(_StepA).resolve(ctx)

    def test_raises_on_out_of_range_index(self):
        ctx = _ctx(outputs={_StepA: [_Instructions(confidence=0.5, label="x")]})
        with pytest.raises(IndexError, match="out of range"):
            FromOutput(_StepA, index=5).resolve(ctx)

    def test_is_frozen(self):
        src = FromOutput(_StepA)
        with pytest.raises(FrozenInstanceError):
            src.index = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FromPipeline
# ---------------------------------------------------------------------------


class TestFromPipeline:
    def test_resolves_attr(self):
        pipe = SimpleNamespace(session="db-session", logger="logger-obj")
        ctx = _ctx(pipeline=pipe)
        assert FromPipeline("session").resolve(ctx) == "db-session"
        assert FromPipeline("logger").resolve(ctx) == "logger-obj"

    def test_raises_on_missing_attr(self):
        ctx = _ctx(pipeline=SimpleNamespace())
        with pytest.raises(AttributeError):
            FromPipeline("missing").resolve(ctx)

    def test_is_frozen(self):
        src = FromPipeline("session")
        with pytest.raises(FrozenInstanceError):
            src.attr = "logger"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Computed
# ---------------------------------------------------------------------------


def _sum(*vals):
    return sum(vals)


def _join(a, b):
    return f"{a}:{b}"


class TestComputed:
    def test_resolves_via_nested_sources(self):
        ctx = _ctx(input=_PipelineInput(name="a", count=3))
        src = Computed(_join, FromInput("name"), FromInput("count"))
        assert src.resolve(ctx) == "a:3"

    def test_works_with_stdlib_fn(self):
        insts = [
            _Instructions(confidence=0.1, label="x"),
            _Instructions(confidence=0.2, label="y"),
            _Instructions(confidence=0.3, label="z"),
        ]
        ctx = _ctx(outputs={_StepA: insts})
        src = Computed(
            _sum,
            FromOutput(_StepA, index=0, field="confidence"),
            FromOutput(_StepA, index=1, field="confidence"),
            FromOutput(_StepA, index=2, field="confidence"),
        )
        assert src.resolve(ctx) == pytest.approx(0.6)

    def test_propagates_nested_failures(self):
        ctx = _ctx()
        src = Computed(len, FromOutput(_StepA))
        with pytest.raises(KeyError):
            src.resolve(ctx)

    def test_equality_and_hash(self):
        a = Computed(_join, FromInput("name"), FromInput("count"))
        b = Computed(_join, FromInput("name"), FromInput("count"))
        c = Computed(_join, FromInput("name"), FromInput("other"))
        assert a == b
        assert a != c
        assert hash(a) == hash(b)

    def test_repr_includes_fn_name_and_sources(self):
        src = Computed(_sum, FromInput("count"))
        text = repr(src)
        assert "_sum" in text
        assert "FromInput" in text


# ---------------------------------------------------------------------------
# SourcesSpec
# ---------------------------------------------------------------------------


class TestSourcesSpec:
    def test_resolve_constructs_inputs_instance(self):
        ctx = _ctx(input=_PipelineInput(name="alpha", count=5))
        spec = SourcesSpec(
            inputs_cls=_MyInputs,
            field_sources={
                "name": FromInput("name"),
                "count": FromInput("count"),
            },
        )
        result = spec.resolve(ctx)
        assert isinstance(result, _MyInputs)
        assert result.name == "alpha"
        assert result.count == 5

    def test_resolve_runs_pydantic_validation(self):
        ctx = _ctx(input=_PipelineInput(name="alpha", count=5))
        spec = SourcesSpec(
            inputs_cls=_MyInputs,
            field_sources={"name": FromInput("name")},  # count missing
        )
        with pytest.raises(ValidationError):
            spec.resolve(ctx)


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------


class _FakeStep:
    pass


class _FakeExtraction:
    pass


def _spec() -> SourcesSpec:
    return SourcesSpec(
        inputs_cls=_MyInputs,
        field_sources={
            "name": FromInput("name"),
            "count": FromInput("count"),
        },
    )


class TestBind:
    def test_step_bind_valid(self):
        b = Bind(step=_FakeStep, inputs=_spec())
        assert b.step is _FakeStep
        assert b.extraction is None
        assert b.extractions == []

    def test_extraction_bind_valid(self):
        b = Bind(extraction=_FakeExtraction, inputs=_spec())
        assert b.extraction is _FakeExtraction
        assert b.step is None

    def test_rejects_both_step_and_extraction(self):
        with pytest.raises(ValueError, match="exactly one"):
            Bind(step=_FakeStep, extraction=_FakeExtraction, inputs=_spec())

    def test_rejects_neither_step_nor_extraction(self):
        with pytest.raises(ValueError, match="exactly one"):
            Bind(inputs=_spec())

    def test_step_bind_allows_no_inputs(self):
        # Steps without a declared INPUTS class can omit inputs=
        b = Bind(step=_FakeStep)
        assert b.inputs is None

    def test_extraction_bind_requires_inputs(self):
        with pytest.raises(ValueError, match="inputs="):
            Bind(extraction=_FakeExtraction)

    def test_nested_extractions_under_step_ok(self):
        child = Bind(extraction=_FakeExtraction, inputs=_spec())
        b = Bind(step=_FakeStep, inputs=_spec(), extractions=[child])
        assert b.extractions == [child]

    def test_nested_extractions_under_extraction_rejected(self):
        child = Bind(extraction=_FakeExtraction, inputs=_spec())
        with pytest.raises(ValueError, match="Nested extractions"):
            Bind(extraction=_FakeExtraction, inputs=_spec(), extractions=[child])

    def test_nested_step_under_step_rejected(self):
        child = Bind(step=_FakeStep, inputs=_spec())
        with pytest.raises(ValueError, match="extraction="):
            Bind(step=_FakeStep, inputs=_spec(), extractions=[child])


# ---------------------------------------------------------------------------
# validate_bindings — static analysis
# ---------------------------------------------------------------------------


class _InnerInput(BaseModel):
    email: str


class _ValidateInput(BaseModel):
    """INPUT_DATA fixture for validate_bindings tests."""
    name: str
    count: int
    user: _InnerInput | None = None


class _StepOneInstructions(BaseModel):
    confidence: float
    label: str


class _StepOne:
    INSTRUCTIONS = _StepOneInstructions


class _StepTwoInstructions(BaseModel):
    summary: str


class _StepTwo:
    INSTRUCTIONS = _StepTwoInstructions


class _StepWithoutInstructions:
    """Step-like class without INSTRUCTIONS — validate_bindings should skip
    field-existence checks for FromOutput(..., field=X) gracefully."""


class _ExtractionA:
    pass


def _mk_spec(inputs_cls: type[BaseModel], **field_sources) -> SourcesSpec:
    """Construct a SourcesSpec directly for tests (bypasses .sources() validation
    to let us build deliberately invalid specs)."""
    return SourcesSpec(inputs_cls=inputs_cls, field_sources=field_sources)


class _StepInputs(BaseModel):
    """Minimal target inputs class used to satisfy SourcesSpec construction."""
    x: str


class TestValidateBindingsHappyPath:
    def test_empty_bindings(self):
        validate_bindings([], input_cls=_ValidateInput)

    def test_single_step_from_input(self):
        spec = _mk_spec(_StepInputs, x=FromInput("name"))
        validate_bindings(
            [Bind(step=_StepOne, inputs=spec)],
            input_cls=_ValidateInput,
        )

    def test_dotted_from_input_through_nested_basemodel(self):
        spec = _mk_spec(_StepInputs, x=FromInput("user.email"))
        validate_bindings(
            [Bind(step=_StepOne, inputs=spec)],
            input_cls=_ValidateInput,
        )

    def test_step_reads_prior_step_output(self):
        spec_a = _mk_spec(_StepInputs, x=FromInput("name"))
        spec_b = _mk_spec(_StepInputs, x=FromOutput(_StepOne, field="label"))
        validate_bindings(
            [
                Bind(step=_StepOne, inputs=spec_a),
                Bind(step=_StepTwo, inputs=spec_b),
            ],
            input_cls=_ValidateInput,
        )

    def test_nested_extraction_reads_owning_step(self):
        step_spec = _mk_spec(_StepInputs, x=FromInput("name"))
        ext_spec = _mk_spec(_StepInputs, x=FromOutput(_StepOne, field="label"))
        validate_bindings(
            [
                Bind(
                    step=_StepOne,
                    inputs=step_spec,
                    extractions=[
                        Bind(extraction=_ExtractionA, inputs=ext_spec),
                    ],
                ),
            ],
            input_cls=_ValidateInput,
        )

    def test_from_pipeline_always_passes(self):
        spec = _mk_spec(_StepInputs, x=FromPipeline("session"))
        validate_bindings(
            [Bind(step=_StepOne, inputs=spec)],
            input_cls=_ValidateInput,
        )

    def test_computed_with_valid_nested_sources(self):
        spec = _mk_spec(
            _StepInputs,
            x=Computed(
                lambda a, b: f"{a}:{b}",
                FromInput("name"),
                FromInput("count"),
            ),
        )
        validate_bindings(
            [Bind(step=_StepOne, inputs=spec)],
            input_cls=_ValidateInput,
        )

    def test_from_output_whole_instruction_no_field(self):
        spec_a = _mk_spec(_StepInputs, x=FromInput("name"))
        spec_b = _mk_spec(_StepInputs, x=FromOutput(_StepOne))  # no field
        validate_bindings(
            [
                Bind(step=_StepOne, inputs=spec_a),
                Bind(step=_StepTwo, inputs=spec_b),
            ],
            input_cls=_ValidateInput,
        )

    def test_step_without_instructions_attr_skips_field_check(self):
        spec_a = _mk_spec(_StepInputs, x=FromInput("name"))
        # FromOutput with field=X on a step that has no INSTRUCTIONS — no raise.
        spec_b = _mk_spec(
            _StepInputs,
            x=FromOutput(_StepWithoutInstructions, field="anything"),
        )
        validate_bindings(
            [
                Bind(step=_StepWithoutInstructions, inputs=spec_a),
                Bind(step=_StepOne, inputs=spec_b),
            ],
            input_cls=_ValidateInput,
        )


class TestValidateBindingsFailures:
    def test_top_level_extraction_rejected(self):
        spec = _mk_spec(_StepInputs, x=FromInput("name"))
        with pytest.raises(ValueError, match="no step"):
            validate_bindings(
                [Bind(extraction=_ExtractionA, inputs=spec)],
                input_cls=_ValidateInput,
            )

    def test_from_input_missing_field(self):
        spec = _mk_spec(_StepInputs, x=FromInput("missing"))
        with pytest.raises(ValueError, match="missing"):
            validate_bindings(
                [Bind(step=_StepOne, inputs=spec)],
                input_cls=_ValidateInput,
            )

    def test_from_input_dotted_path_missing_intermediate(self):
        spec = _mk_spec(_StepInputs, x=FromInput("user.missing"))
        with pytest.raises(ValueError, match="missing"):
            validate_bindings(
                [Bind(step=_StepOne, inputs=spec)],
                input_cls=_ValidateInput,
            )

    def test_from_output_unknown_step(self):
        spec = _mk_spec(_StepInputs, x=FromOutput(_StepTwo, field="summary"))
        with pytest.raises(ValueError, match="_StepTwo"):
            validate_bindings(
                [Bind(step=_StepOne, inputs=spec)],
                input_cls=_ValidateInput,
            )

    def test_from_output_later_step_rejected(self):
        # Step one tries to read from step two (which runs later)
        spec_a = _mk_spec(_StepInputs, x=FromOutput(_StepTwo, field="summary"))
        spec_b = _mk_spec(_StepInputs, x=FromInput("name"))
        with pytest.raises(ValueError, match="_StepTwo"):
            validate_bindings(
                [
                    Bind(step=_StepOne, inputs=spec_a),
                    Bind(step=_StepTwo, inputs=spec_b),
                ],
                input_cls=_ValidateInput,
            )

    def test_step_cannot_reference_itself(self):
        # Step one's own inputs adapter references step one's output (not allowed
        # — the step hasn't run at the time its inputs are resolved).
        spec = _mk_spec(_StepInputs, x=FromOutput(_StepOne, field="label"))
        with pytest.raises(ValueError, match="_StepOne"):
            validate_bindings(
                [Bind(step=_StepOne, inputs=spec)],
                input_cls=_ValidateInput,
            )

    def test_from_output_bad_instructions_field(self):
        spec_a = _mk_spec(_StepInputs, x=FromInput("name"))
        spec_b = _mk_spec(
            _StepInputs, x=FromOutput(_StepOne, field="nonexistent_field")
        )
        with pytest.raises(ValueError, match="nonexistent_field"):
            validate_bindings(
                [
                    Bind(step=_StepOne, inputs=spec_a),
                    Bind(step=_StepTwo, inputs=spec_b),
                ],
                input_cls=_ValidateInput,
            )

    def test_computed_with_bad_nested_source(self):
        spec = _mk_spec(
            _StepInputs,
            x=Computed(
                lambda a: a,
                FromInput("missing"),
            ),
        )
        with pytest.raises(ValueError, match="missing"):
            validate_bindings(
                [Bind(step=_StepOne, inputs=spec)],
                input_cls=_ValidateInput,
            )

    def test_nested_extraction_bad_source(self):
        step_spec = _mk_spec(_StepInputs, x=FromInput("name"))
        ext_spec = _mk_spec(_StepInputs, x=FromInput("bogus"))
        with pytest.raises(ValueError, match="bogus"):
            validate_bindings(
                [
                    Bind(
                        step=_StepOne,
                        inputs=step_spec,
                        extractions=[
                            Bind(extraction=_ExtractionA, inputs=ext_spec),
                        ],
                    ),
                ],
                input_cls=_ValidateInput,
            )

    def test_error_message_includes_location(self):
        spec = _mk_spec(_StepInputs, x=FromInput("missing"))
        with pytest.raises(ValueError) as exc_info:
            validate_bindings(
                [Bind(step=_StepOne, inputs=spec)],
                input_cls=_ValidateInput,
            )
        msg = str(exc_info.value)
        assert "binding[0]" in msg
        assert "_StepOne" in msg
        assert "field=x" in msg
