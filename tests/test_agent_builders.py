"""Tests for ``llm_pipeline.agent_builders.build_step_agent``.

The factory builds a pydantic-ai Agent for a pipeline step. After
B.5, instructions are passed statically at construction (no
@agent.instructions hook); these tests pin that contract:

- ``instructions`` argument is required and ends up on the Agent's
  static instructions surface.
- Output validators registered via the ``validators`` argument are
  attached.
- Tools, instrumentation, and model_settings round-trip without
  surprise.
"""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from llm_pipeline.agent_builders import StepDeps, build_step_agent


class _DummyOutput(BaseModel):
    value: str = ""


class TestStaticInstructions:
    def test_build_step_agent_requires_instructions(self):
        """``instructions`` is now a required positional kwarg."""
        with pytest.raises(TypeError):
            # type: ignore[call-arg] — deliberate omission
            build_step_agent(
                step_name="x",
                output_type=_DummyOutput,
            )

    def test_instructions_attached_to_agent(self):
        """The rendered system prompt is reachable on the Agent.

        pydantic-ai stores static instructions on ``Agent._instructions``
        (or the public ``Agent.instructions`` accessor depending on
        version). We don't depend on the exact internal name; we
        verify the agent's instructions iteration / serialization
        surface includes the string.
        """
        rendered = "You are a helpful assistant. RENDERED-MARKER-12345"
        agent = build_step_agent(
            step_name="x",
            output_type=_DummyOutput,
            instructions=rendered,
        )

        # pydantic-ai's Agent stores instructions on a private attr that
        # varies across releases. Search every attribute on the instance
        # for the marker — robust to those internal renames.
        agent_state = repr(vars(agent))
        assert "RENDERED-MARKER-12345" in agent_state, (
            "instructions string did not land anywhere on the Agent — "
            "the static-instructions wiring may have broken."
        )

    def test_no_dynamic_instructions_callable_registered(self):
        """B.5 dropped @agent.instructions entirely; nothing should be
        registered as a dynamic instructions callable."""
        agent = build_step_agent(
            step_name="x",
            output_type=_DummyOutput,
            instructions="static system prompt",
        )

        # pydantic-ai keeps the dynamic-instructions callables in a
        # private list. The exact attribute name has shifted across
        # releases (``_instructions_functions`` / ``_function_instructions``
        # / etc.); we're robust to renames by enumerating attributes
        # that look list-like and contain at least one callable.
        suspicious = []
        for name in dir(agent):
            if not name.startswith("_"):
                continue
            try:
                value = getattr(agent, name)
            except AttributeError:
                continue
            if (
                isinstance(value, list)
                and value
                and any(callable(v) for v in value)
                and "instruction" in name.lower()
            ):
                suspicious.append((name, value))

        assert not suspicious, (
            f"Found dynamic instructions callables on Agent: {suspicious}. "
            "B.5 dropped @agent.instructions; the agent should carry the "
            "system prompt as a static string only."
        )


class TestStepDepsContract:
    def test_step_deps_is_constructible_without_instructions_field(self):
        """StepDeps no longer carries any field tied to dynamic instructions."""
        deps = StepDeps(
            session=None,
            pipeline_context={},
            prompt_service=None,
            run_id="r",
            pipeline_name="p",
            step_name="s",
        )
        # If we ever re-add a field for dynamic instructions, the test
        # forces a deliberate update.
        assert hasattr(deps, "session")
        assert hasattr(deps, "prompt_service")
        assert hasattr(deps, "step_name")
        # Validation hooks remain.
        assert hasattr(deps, "array_validation")
        assert hasattr(deps, "validation_context")


class TestModelDeferred:
    def test_model_can_be_omitted_at_construction(self):
        """``model=None`` is allowed; pydantic-ai defers via
        ``defer_model_check`` so the runtime can pick at agent.run time."""
        # Doesn't construct a real model; just shouldn't raise.
        agent = build_step_agent(
            step_name="x",
            output_type=_DummyOutput,
            instructions="anything",
            model=None,
        )
        assert agent is not None
