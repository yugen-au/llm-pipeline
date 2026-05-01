"""Tests for llm_pipeline.wiring: Source types, AdapterContext, SourcesSpec,
and the per-node binding wrappers (Step / Extraction / Review)."""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from llm_pipeline.wiring import (
    AdapterContext,
    Computed,
    Extraction,
    FromInput,
    FromOutput,
    FromPipeline,
    Review,
    SourcesSpec,
    Step,
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
# Per-node bindings: Step / Extraction / Review
# ---------------------------------------------------------------------------


class _BindingInputs(BaseModel):
    name: str


class _OtherInputs(BaseModel):
    name: str


class _NodeWithInputs:
    INPUTS = _BindingInputs


class _NodeWithoutInputs:
    """Node-like class without an INPUTS ClassVar — Step still constructs."""


def _binding_spec(inputs_cls: type[BaseModel] = _BindingInputs) -> SourcesSpec:
    return SourcesSpec(
        inputs_cls=inputs_cls,
        field_sources={"name": FromInput("name")},
    )


class TestStepBinding:
    def test_valid_construction(self):
        binding = Step(_NodeWithInputs, inputs_spec=_binding_spec())
        assert binding.cls is _NodeWithInputs
        assert binding.inputs_spec.inputs_cls is _BindingInputs

    def test_captures_non_class_cls(self):
        binding = Step("not a class", inputs_spec=_binding_spec())  # type: ignore[arg-type]
        assert any(
            e.code == "binding_cls_not_class"
            for e in binding._init_post_errors
        )

    def test_captures_non_sources_spec(self):
        binding = Step(_NodeWithInputs, inputs_spec="oops")  # type: ignore[arg-type]
        assert any(
            e.code == "binding_inputs_spec_wrong_type"
            for e in binding._init_post_errors
        )

    def test_captures_inputs_cls_mismatch(self):
        spec = _binding_spec(inputs_cls=_OtherInputs)
        binding = Step(_NodeWithInputs, inputs_spec=spec)
        assert any(
            e.code == "binding_inputs_cls_mismatch"
            for e in binding._init_post_errors
        )

    def test_no_inputs_classvar_skips_match_check(self):
        # If the node class has no INPUTS, the binding can't enforce the
        # match — just accepts whatever spec the caller provides.
        binding = Step(_NodeWithoutInputs, inputs_spec=_binding_spec())
        assert binding.cls is _NodeWithoutInputs


class TestExtractionBinding:
    def test_valid_construction(self):
        binding = Extraction(_NodeWithInputs, inputs_spec=_binding_spec())
        assert binding.cls is _NodeWithInputs
        assert binding.inputs_spec.inputs_cls is _BindingInputs

    def test_captures_inputs_cls_mismatch(self):
        spec = _binding_spec(inputs_cls=_OtherInputs)
        binding = Extraction(_NodeWithInputs, inputs_spec=spec)
        assert any(
            e.code == "binding_inputs_cls_mismatch"
            for e in binding._init_post_errors
        )


class TestReviewBinding:
    def test_valid_construction(self):
        binding = Review(_NodeWithInputs, inputs_spec=_binding_spec())
        assert binding.cls is _NodeWithInputs
        assert binding.inputs_spec.inputs_cls is _BindingInputs

    def test_captures_inputs_cls_mismatch(self):
        spec = _binding_spec(inputs_cls=_OtherInputs)
        binding = Review(_NodeWithInputs, inputs_spec=spec)
        assert any(
            e.code == "binding_inputs_cls_mismatch"
            for e in binding._init_post_errors
        )
