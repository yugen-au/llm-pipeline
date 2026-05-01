"""
Factory for building pydantic-ai Agent instances for pipeline steps.

Provides StepDeps (dependency injection container) and build_step_agent()
(factory function) for constructing agents with dynamic system prompt
resolution via PromptService.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from llm_pipeline.prompts.service import PromptService
    from sqlmodel import Session


@dataclass
class StepDeps:
    """Dependencies injected into pydantic-ai agents for pipeline steps.

    Compatible with RunContext[StepDeps] for use in @agent.tool and
    @agent.output_validator decorators. (Instructions are passed
    statically at agent construction; they don't need RunContext.)

    Uses Any for runtime types to avoid circular imports; real types
    are declared under TYPE_CHECKING for IDE support.

    Validation fields (array_validation, validation_context) are per-call
    config passed to output validators via ctx.deps. Default to None
    when the step has no validation requirements.
    """

    # Core pipeline deps
    session: Any  # Session
    pipeline_context: dict[str, Any]
    prompt_service: Any  # PromptService

    # Execution metadata
    run_id: str
    pipeline_name: str
    step_name: str

    # Per-call validation config, read by output validators via ctx.deps
    array_validation: Any | None = None  # ArrayValidationConfig
    validation_context: Any | None = None  # ValidationContext for Pydantic field_validators



def build_step_agent(
    step_name: str,
    output_type: type,
    instructions: str,
    model: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
    instrument: Any | None = None,
    tools: Sequence[Any] | None = None,
) -> Agent[StepDeps, Any]:
    """Build a pydantic-ai Agent configured for a pipeline step.

    The system prompt is passed statically at construction time —
    callers are expected to have fetched the Phoenix prompt and
    rendered its ``system`` message with the call's variables before
    invoking this factory. The previous dynamic
    ``@agent.instructions`` indirection (which fetched + rendered at
    every ``agent.run`` call) has been removed; the static path is
    simpler, lets us pre-resolve auto_vars, and matches what
    pydantic-ai treats as the canonical case.

    Args:
        step_name: Unique step identifier (e.g. 'constraint_extraction').
        output_type: Pydantic model for validated output.
        instructions: Fully-rendered system prompt to embed on the
            agent. The caller resolves placeholders via
            ``PromptService.get_system_prompt`` (or equivalent)
            BEFORE calling this factory.
        model: Model string. None defers selection via defer_model_check —
            the runtime path then decides per-call (Phoenix prompt
            model or eval-time override).
        retries: Max retries for output validation failures.
        model_settings: ModelSettings for temperature, max_tokens, etc.
        validators: Output validators registered via
            ``agent.output_validator``. None = no validators.
        instrument: Optional InstrumentationSettings for OTel tracing.
        tools: Optional sequence of tool callables to register on the
            agent. None or empty = no tools registered.

    Returns:
        Configured Agent[StepDeps, Any] with static instructions and
        output validators registered.
    """
    from pydantic_ai import Agent

    agent_kwargs: dict[str, Any] = dict(
        model=model,
        output_type=output_type,
        deps_type=StepDeps,
        name=step_name,
        retries=retries,
        model_settings=model_settings,
        defer_model_check=True,
        validation_context=lambda ctx: ctx.deps.validation_context,
        instructions=instructions,
    )
    if instrument is not None:
        agent_kwargs["instrument"] = instrument

    if tools:
        from pydantic_ai.toolsets import FunctionToolset

        agent_kwargs["toolsets"] = [FunctionToolset(tools=list(tools))]

    agent: Agent[StepDeps, Any] = Agent(**agent_kwargs)

    # Register output validators (from validator factories)
    for v in (validators or []):
        agent.output_validator(v)

    return agent


__all__ = ["StepDeps", "build_step_agent"]
