"""Tests for the AgentTool base class.

Covers class-creation validation of the Inputs/Args contract.
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
# Module-scope fixtures (needed for pydantic forward-ref resolution on
# resource-typed fields — function-local classes aren't visible to
# pydantic's model-rebuild phase).
# ---------------------------------------------------------------------------


class _DocCacheStub(PipelineResource):
    class Inputs(BaseModel):
        library_id: str

    @classmethod
    def build(cls, inputs, ctx):  # pragma: no cover — not exercised here
        return cls()


class _ToolWithResource(AgentTool):
    class Inputs(StepInputs):
        library_id: str
        cache: _DocCacheStub = Resource(library_id="library_id")

    class Args(BaseModel):
        topic: str

    @classmethod
    def run(cls, inputs, args, ctx):  # pragma: no cover
        return ""


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestToolAcceptance:
    def test_minimal_tool_class_creates(self) -> None:
        class FetchDocs(AgentTool):
            class Inputs(StepInputs):
                library_id: str

            class Args(BaseModel):
                topic: str

            @classmethod
            def run(cls, inputs, args, ctx):
                return f"{inputs.library_id}/{args.topic}"

        assert FetchDocs.Inputs.__name__ == "Inputs"
        assert FetchDocs.Args.__name__ == "Args"
        assert FetchDocs.run.__func__ is not AgentTool.run.__func__

    def test_tool_inputs_can_declare_resource_dependency(self) -> None:
        # Module-scope classes dodge pydantic's forward-ref resolution
        # quirks for resource-typed fields declared inside a function.
        specs = _ToolWithResource.Inputs.resource_specs()
        assert set(specs) == {"cache"}
        assert specs["cache"].resource_cls is _DocCacheStub

    def test_run_invokable_via_classmethod(self) -> None:
        class Echo(AgentTool):
            class Inputs(StepInputs):
                prefix: str

            class Args(BaseModel):
                body: str

            @classmethod
            def run(cls, inputs, args, ctx):
                return f"{inputs.prefix}: {args.body}"

        inputs = Echo.Inputs(prefix="hi")
        args = Echo.Args(body="there")
        # ctx is not touched by Echo; pass None-ish placeholder that
        # still satisfies the type hint on the signature.
        result = Echo.run(inputs, args, ctx=None)  # type: ignore[arg-type]
        assert result == "hi: there"


# ---------------------------------------------------------------------------
# Class-creation validation failures
# ---------------------------------------------------------------------------


class TestToolValidationCaptures:
    def test_missing_inputs_captured(self) -> None:
        class _Bad(AgentTool):
            class Args(BaseModel):
                topic: str

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in _Bad._init_subclass_errors}
        assert "missing_inputs" in codes

    def test_missing_args_captured(self) -> None:
        class _Bad(AgentTool):
            class Inputs(StepInputs):
                x: str

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in _Bad._init_subclass_errors}
        assert "missing_args" in codes

    def test_inputs_not_stepinputs_subclass_captured(self) -> None:
        class _Bad(AgentTool):
            class Inputs(BaseModel):  # plain BaseModel, not StepInputs
                x: str

            class Args(BaseModel):
                topic: str

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in _Bad._init_subclass_errors}
        assert "tool_inputs_not_stepinputs" in codes

    def test_args_not_basemodel_subclass_captured(self) -> None:
        class _Bad(AgentTool):
            class Inputs(StepInputs):
                x: str

            Args = dict  # not a BaseModel

            @classmethod
            def run(cls, inputs, args, ctx):  # pragma: no cover
                return None

        codes = {i.code for i in _Bad._init_subclass_errors}
        assert "tool_args_not_basemodel" in codes

    def test_intermediate_base_without_inputs_or_args_is_clean(self) -> None:
        # Abstract intermediates without Inputs/Args produce no captures.
        class AbstractMiddle(AgentTool):
            pass

        assert AbstractMiddle._init_subclass_errors == []

        class Concrete(AbstractMiddle):
            class Inputs(StepInputs):
                x: str

            class Args(BaseModel):
                y: str

            @classmethod
            def run(cls, inputs, args, ctx):
                return ""

        assert Concrete._init_subclass_errors == []
        assert Concrete.Inputs.__name__ == "Inputs"
