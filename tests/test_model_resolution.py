"""Tests for B.6 — model resolution chain.

Two surfaces to pin:

1. ``PromptService.get_model`` — combines Phoenix's
   ``model_provider`` + ``model_name`` into a pydantic-ai-format
   string and returns it.

2. ``LLMStepNode._run_llm`` resolution — ``ctx.deps.model`` wins when
   set; ``PromptService.get_model`` is the fallback; ``RuntimeError``
   when neither produces a value.

The runtime test is end-to-end against a stub Phoenix client so the
full chain (Phoenix lookup → format) is exercised, not mocked.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel, Field
from pydantic_graph import End, GraphRunContext

from llm_pipeline.graph.nodes import LLMStepNode
from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.inputs import StepInputs
from llm_pipeline.prompts.service import PromptService
from llm_pipeline.prompts.variables import PromptVariables


# ---------------------------------------------------------------------------
# PromptService.get_model — direct unit tests
# ---------------------------------------------------------------------------


class _StubPhoenixClient:
    def __init__(self, version: dict[str, Any] | None) -> None:
        self._version = version

    def get_by_tag(self, name: str, tag: str) -> dict[str, Any]:
        if self._version is None:
            from llm_pipeline.prompts.phoenix_client import PromptNotFoundError

            raise PromptNotFoundError(name)
        return self._version

    def get_latest(self, name: str) -> dict[str, Any]:
        return self.get_by_tag(name, "latest")


class TestPromptServiceGetModel:
    def test_returns_pai_format_when_phoenix_has_model(self):
        version = {
            "model_provider": "OPENAI",
            "model_name": "gpt-4o-mini",
            "template": {"type": "chat", "messages": []},
        }
        svc = PromptService(client=_StubPhoenixClient(version))
        assert svc.get_model("any_step") == "openai:gpt-4o-mini"

    def test_returns_none_when_phoenix_lookup_fails(self):
        svc = PromptService(client=_StubPhoenixClient(version=None))
        assert svc.get_model("missing") is None

    def test_fallback_used_when_phoenix_lookup_fails(self):
        svc = PromptService(client=_StubPhoenixClient(version=None))
        assert svc.get_model("missing", fallback="openai:fallback") == (
            "openai:fallback"
        )

    def test_returns_none_when_provider_or_name_missing(self):
        version = {
            "model_provider": None,
            "model_name": "gpt-4o-mini",
            "template": {"type": "chat", "messages": []},
        }
        svc = PromptService(client=_StubPhoenixClient(version))
        assert svc.get_model("partial") is None


# ---------------------------------------------------------------------------
# LLMStepNode._run_llm — model resolution chain
# ---------------------------------------------------------------------------


class _Inputs(StepInputs):
    text: str


class _Instructions(BaseModel):
    label: str = ""


class _ResolvePrompt(PromptVariables):
    """Module-level PromptVariables subclass.

    Lives at module top level so the strict prepare-validator (which
    runs at ``__init_subclass__`` time and uses
    ``typing.get_type_hints``) can resolve the annotation. The tests
    don't register this with the prompt registry — discovery is
    bypassed; ``_run_llm`` only walks the prompt registry to render
    auto_vars, which we don't exercise.
    """

    text: str = Field(description="text payload")


class _CapturingPromptService:
    """Records calls to the surfaces ``_run_llm`` touches.

    Returns canned strings for the rendering surfaces and a
    configurable model for ``get_model``.
    """

    def __init__(self, *, model_value: str | None) -> None:
        self.model_calls: list[str] = []
        self.model_value = model_value

    def get_user_prompt(self, *, prompt_key: str, variables: dict) -> str:
        return "USER"

    def get_system_prompt(self, *, prompt_key: str, variables: dict) -> str:
        return "SYSTEM"

    def get_model(self, prompt_key: str, fallback: str | None = None) -> str | None:
        self.model_calls.append(prompt_key)
        return self.model_value if self.model_value is not None else fallback


def _capture_model_passed_to_agent(ctx, monkeypatch) -> dict[str, Any]:
    """Patch ``agent.run`` (via build_step_agent) to record the model
    kwarg without actually running an LLM. Returns the dict the test
    can inspect after running ``_run_llm``."""
    captured: dict[str, Any] = {}

    class _StubResult:
        def __init__(self, output):
            self.output = output

    class _StubAgent:
        async def run(self, user_prompt, *, deps, model):
            captured["model"] = model
            captured["user_prompt"] = user_prompt
            return _StubResult(_Instructions())

    def _fake_build(**kwargs):
        captured["instructions"] = kwargs.get("instructions")
        return _StubAgent()

    # build_step_agent is imported lazily inside _run_llm; patch the
    # source module so the lookup resolves to the stub.
    monkeypatch.setattr(
        "llm_pipeline.agent_builders.build_step_agent",
        _fake_build,
    )
    return captured


# A minimal LLMStepNode subclass plus the wiring the runtime expects.
class _ResolveStep(LLMStepNode):
    INPUTS = _Inputs
    INSTRUCTIONS = _Instructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _Inputs) -> list[_ResolvePrompt]:
        return [_ResolvePrompt(text=inputs.text)]

    async def run(
        self,
        ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_llm(ctx)
        return End(None)


def _build_full_ctx(*, deps_model: str | None, phoenix_model: str | None):
    """Build a real GraphRunContext-shaped object so ``_run_llm``'s
    wiring lookup + state ops succeed."""
    from llm_pipeline.graph.state import PipelineState
    from llm_pipeline.wiring import FromInput, Step

    state = PipelineState(input_data={"text": "hi"})
    binding = Step(
        _ResolveStep,
        inputs_spec=_Inputs.sources(text=FromInput("text")),
    )
    deps = PipelineDeps(
        session=None,
        prompt_service=_CapturingPromptService(model_value=phoenix_model),
        run_id="r",
        pipeline_name="p",
        model=deps_model,
        input_cls=type(
            "_FakeInput",
            (BaseModel,),
            {"__annotations__": {"text": str}},
        ),
        node_classes={},
        wiring={_ResolveStep: binding},
    )

    class _CtxStub:
        pass

    ctx = _CtxStub()
    ctx.state = state
    ctx.deps = deps
    return ctx


class TestRunLlmModelResolution:
    def test_deps_model_wins_when_set(self, monkeypatch):
        ctx = _build_full_ctx(
            deps_model="openai:override",
            phoenix_model="openai:phoenix",
        )
        captured = _capture_model_passed_to_agent(ctx, monkeypatch)

        asyncio.run(_ResolveStep()._run_llm(ctx))

        assert captured["model"] == "openai:override"
        # Phoenix lookup never fired — deps overrode.
        assert ctx.deps.prompt_service.model_calls == []

    def test_phoenix_fallback_when_deps_model_is_none(self, monkeypatch):
        ctx = _build_full_ctx(
            deps_model=None,
            phoenix_model="openai:phoenix",
        )
        captured = _capture_model_passed_to_agent(ctx, monkeypatch)

        asyncio.run(_ResolveStep()._run_llm(ctx))

        assert captured["model"] == "openai:phoenix"
        # Phoenix lookup fired exactly once.
        assert ctx.deps.prompt_service.model_calls == [_ResolveStep.step_name()]

    def test_runtime_error_when_neither_resolves(self, monkeypatch):
        ctx = _build_full_ctx(
            deps_model=None,
            phoenix_model=None,
        )
        # No need to install the agent stub — the error fires before
        # build_step_agent is reached.
        with pytest.raises(RuntimeError, match="No model resolved"):
            asyncio.run(_ResolveStep()._run_llm(ctx))
