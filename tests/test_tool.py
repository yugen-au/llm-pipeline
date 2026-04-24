"""Tests for the PipelineTool base class.

Covers class-creation validation of the Inputs/Args contract. Runtime
dispatch is exercised once tools are wired into strategy Binds.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from llm_pipeline.inputs import StepInputs
from llm_pipeline.resources import PipelineResource, Resource
from llm_pipeline.tool import PipelineTool


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


class _ToolWithResource(PipelineTool):
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
        class FetchDocs(PipelineTool):
            class Inputs(StepInputs):
                library_id: str

            class Args(BaseModel):
                topic: str

            @classmethod
            def run(cls, inputs, args, ctx):
                return f"{inputs.library_id}/{args.topic}"

        assert FetchDocs.Inputs.__name__ == "Inputs"
        assert FetchDocs.Args.__name__ == "Args"
        assert FetchDocs.run.__func__ is not PipelineTool.run.__func__

    def test_tool_inputs_can_declare_resource_dependency(self) -> None:
        # Module-scope classes dodge pydantic's forward-ref resolution
        # quirks for resource-typed fields declared inside a function.
        specs = _ToolWithResource.Inputs.resource_specs()
        assert set(specs) == {"cache"}
        assert specs["cache"].resource_cls is _DocCacheStub

    def test_run_invokable_via_classmethod(self) -> None:
        class Echo(PipelineTool):
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


class TestToolValidationFailures:
    def test_missing_inputs_raises(self) -> None:
        with pytest.raises(TypeError, match="must declare both an Inputs"):
            class _Bad(PipelineTool):
                class Args(BaseModel):
                    topic: str

                @classmethod
                def run(cls, inputs, args, ctx):  # pragma: no cover
                    return None

    def test_missing_args_raises(self) -> None:
        with pytest.raises(TypeError, match="must declare both an Inputs"):
            class _Bad(PipelineTool):
                class Inputs(StepInputs):
                    x: str

                @classmethod
                def run(cls, inputs, args, ctx):  # pragma: no cover
                    return None

    def test_inputs_not_stepinputs_subclass_raises(self) -> None:
        with pytest.raises(TypeError, match="must be a StepInputs subclass"):
            class _Bad(PipelineTool):
                class Inputs(BaseModel):  # plain BaseModel, not StepInputs
                    x: str

                class Args(BaseModel):
                    topic: str

                @classmethod
                def run(cls, inputs, args, ctx):  # pragma: no cover
                    return None

    def test_args_not_basemodel_subclass_raises(self) -> None:
        with pytest.raises(TypeError, match="must be a pydantic BaseModel"):
            class _Bad(PipelineTool):
                class Inputs(StepInputs):
                    x: str

                Args = dict  # not a BaseModel

                @classmethod
                def run(cls, inputs, args, ctx):  # pragma: no cover
                    return None

    def test_intermediate_base_without_inputs_or_args_is_allowed(self) -> None:
        # Authors can write abstract intermediate bases that don't set
        # Inputs/Args yet. Validation only fires when at least one is set.
        class AbstractMiddle(PipelineTool):
            pass

        class Concrete(AbstractMiddle):
            class Inputs(StepInputs):
                x: str

            class Args(BaseModel):
                y: str

            @classmethod
            def run(cls, inputs, args, ctx):
                return ""

        assert Concrete.Inputs.__name__ == "Inputs"
