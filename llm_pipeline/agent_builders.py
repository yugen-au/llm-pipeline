"""
Factory for building pydantic-ai Agent instances for pipeline steps.

Provides StepDeps (dependency injection container) and build_step_agent()
(factory function) for constructing agents with dynamic system prompt
resolution via PromptService.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai import Agent, InstrumentationSettings, RunContext
    from llm_pipeline.prompts.service import PromptService
    from sqlmodel import Session


@dataclass
class StepDeps:
    """Dependencies injected into pydantic-ai agents for pipeline steps.

    Compatible with RunContext[StepDeps] for use in @agent.instructions,
    @agent.tool, and @agent.output_validator decorators.

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
    model: str | None = None,
    prompt_name: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
    instrument: Any | None = None,
    tools: Sequence[Any] | None = None,
) -> Agent[StepDeps, Any]:
    """Build a pydantic-ai Agent configured for a pipeline step.

    Constructs an Agent with dynamic system prompt injection via
    @agent.instructions. The system prompt is resolved at runtime
    through deps.prompt_service against ``prompt_name`` (a Phoenix
    CHAT prompt holding both system and user messages). The system
    message is the one extracted here.

    Args:
        step_name: Unique step identifier (e.g. 'constraint_extraction').
        output_type: Pydantic model for validated output.
        model: Model string. None defers selection via defer_model_check.
        prompt_name: Phoenix prompt name to fetch the system message
            from. Defaults to ``step_name`` when omitted.
        retries: Max retries for output validation failures.
        model_settings: ModelSettings for temperature, max_tokens, etc.
        validators: Output validators registered via
            ``agent.output_validator``. None = no validators.
        instrument: Optional InstrumentationSettings for OTel tracing.
        tools: Optional sequence of tool callables to register on the
            agent. None or empty = no tools registered.

    Returns:
        Configured Agent[StepDeps, Any] with dynamic instructions and
        output validators registered.
    """
    from pydantic_ai import Agent, RunContext

    agent_kwargs: dict[str, Any] = dict(
        model=model,
        output_type=output_type,
        deps_type=StepDeps,
        name=step_name,
        retries=retries,
        model_settings=model_settings,
        defer_model_check=True,
        validation_context=lambda ctx: ctx.deps.validation_context,
    )
    if instrument is not None:
        agent_kwargs["instrument"] = instrument

    if tools:
        from pydantic_ai.toolsets import FunctionToolset

        agent_kwargs["toolsets"] = [FunctionToolset(tools=list(tools))]

    agent: Agent[StepDeps, Any] = Agent(**agent_kwargs)

    resolved_prompt_name = prompt_name or step_name

    @agent.instructions
    def _inject_system_prompt(ctx: RunContext[StepDeps]) -> str:
        """Resolve the system message from the Phoenix CHAT prompt."""
        return ctx.deps.prompt_service.get_prompt(
            prompt_key=resolved_prompt_name,
            prompt_type='system',
        )

    # Register output validators (from validator factories)
    for v in (validators or []):
        agent.output_validator(v)

    return agent


__all__ = ["StepDeps", "build_step_agent"]
