"""Tests for the AgentTool base class.

Covers class-creation validation of the INPUTS/ARGS contract.
``__init_subclass__`` no longer raises — contract violations land on
``cls._init_subclass_errors`` so the class always constructs and the
walker can register a partial spec.
"""
from __future__ import annotations

from pydantic import BaseModel

from llm_pipeline.agent_tool import AgentTool
from llm_pipeline.inputs import StepInputs
from llm_pipeline.resources import PipelineResource, Resource


# ---------------------------------------------------------------------------
# Module-scope fixtures
# ---------------------------------------------------------------------------


class _DocCacheStub(PipelineResource):
    class Inputs(BaseModel):
        library_id: str

    @classmethod
    def build(cls, inputs, ctx):  # pragma: no cover — not exercised here
        return cls()


class _ToolWithResourceInputs(StepInputs):
    library_id: str
    cache: _DocCacheStub = Resource(library_id="library_id")


class _ToolWithResourceArgs(BaseModel):
    topic: str


class _ToolWithResourceTool(AgentTool):
    INPUTS = _ToolWithResourceInputs
    ARGS = _ToolWithResourceArgs

    @classmethod
    def run(cls, inputs, args, ctx):  # pragma: no cover
        return ""


class FetchDocsInputs(StepInputs):
    library_id: str


class FetchDocsArgs(BaseModel):
    topic: str


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestToolAcceptance:
    def test_minimal_tool_class_creates(self) -> None:
        class FetchDocsTool(AgentTool):
            INPUTS = FetchDocsInputs
            ARGS = FetchDocsArgs

            @classmethod
            def run(cls, inputs, args, ctx):
                return f"{inputs.library_id}/{args.topic}"

        assert FetchDocsTool.INPUTS is FetchDocsInputs
        assert FetchDocsTool.ARGS is FetchDocsArgs
        assert FetchDocsTool.run.__func__ is not AgentTool.run.__func__
        assert FetchDocsTool._init_subclass_errors == []

    def test_tool_inputs_can_declare_resource_dependency(self) -> None:
        specs = _ToolWithResourceTool.INPUTS.resource_specs()
        assert set(specs) == {"cache"}
        assert specs["cache"].resource_cls is _DocCacheStub

    def test_run_invokable_via_classmethod(self) -> None:
        class EchoInputs(StepInputs):
            prefix: str

        class EchoArgs(BaseModel):
            body: str

        class EchoTool(AgentTool):
            INPUTS = EchoInputs
            ARGS = EchoArgs

            @classmethod
            def run(cls, inputs, args, ctx):
                return f"{inputs.prefix}: {args.body}"

        inputs = EchoTool.INPUTS(prefix="hi")
        args = EchoTool.ARGS(body="there")
        result = EchoTool.run(inputs, args, ctx=None)  # type: ignore[arg-type]
        assert result == "hi: there"


# ---------------------------------------------------------------------------
# Class-creation validation captures
# ---------------------------------------------------------------------------


class _BadMissingInputsArgs(BaseModel):
    topic: str


class _BadInputsTypeInputs(BaseModel):  # plain BaseModel, not StepInputs
    x: str


class _BadInputsTypeArgs(BaseModel):
    topic: str


class _MismatchInputs(StepInputs):
    x: str


class _MismatchArgs(BaseModel):
    y: str


class TestToolValidationCaptures:
    def test_missing_inputs_captured(self) -> None:
        class _BadTool(AgentTool):
            ARGS = _BadMissingInputsArgs

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in _BadTool._init_subclass_errors}
        assert "missing_inputs" in codes

    def test_missing_args_captured(self) -> None:
        class _BadTool(AgentTool):
            INPUTS = _MismatchInputs

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in _BadTool._init_subclass_errors}
        assert "missing_args" in codes

    def test_inputs_not_stepinputs_subclass_captured(self) -> None:
        class _BadTool(AgentTool):
            INPUTS = _BadInputsTypeInputs  # plain BaseModel
            ARGS = _BadInputsTypeArgs

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in _BadTool._init_subclass_errors}
        assert "tool_inputs_not_stepinputs" in codes

    def test_args_not_basemodel_subclass_captured(self) -> None:
        class _BadTool(AgentTool):
            INPUTS = _MismatchInputs
            ARGS = dict  # type: ignore[assignment]  # not a BaseModel

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in _BadTool._init_subclass_errors}
        assert "tool_args_not_basemodel" in codes

    def test_inputs_name_mismatch_captured(self) -> None:
        class FooTool(AgentTool):
            INPUTS = _MismatchInputs  # named _MismatchInputs, not FooInputs
            ARGS = _MismatchArgs

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in FooTool._init_subclass_errors}
        assert "tool_inputs_name_mismatch" in codes
        assert "tool_args_name_mismatch" in codes

    def test_tool_suffix_required(self) -> None:
        class FooThing(AgentTool):  # no Tool suffix
            INPUTS = _MismatchInputs
            ARGS = _MismatchArgs

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in FooThing._init_subclass_errors}
        assert "tool_name_suffix" in codes
