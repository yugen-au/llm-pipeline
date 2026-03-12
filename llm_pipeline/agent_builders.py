"""
Factory for building pydantic-ai Agent instances for pipeline steps.

Provides StepDeps (dependency injection container) and build_step_agent()
(factory function) for constructing agents with dynamic system prompt
resolution via PromptService.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai import Agent, RunContext
    from llm_pipeline.prompts.service import PromptService
    from llm_pipeline.prompts.variables import VariableResolver
    from llm_pipeline.events.emitter import PipelineEventEmitter
    from sqlmodel import Session


@dataclass
class StepDeps:
    """Dependencies injected into pydantic-ai agents for pipeline steps.

    Compatible with RunContext[StepDeps] for use in @agent.instructions,
    @agent.tool, and @agent.output_validator decorators.

    Uses Any for runtime types to avoid circular imports; real types
    are declared under TYPE_CHECKING for IDE support.

    Note: array_validation and validation_context are reserved for
    Task 3 output_validators. Unused in Task 2, default to None.
    """

    # Core pipeline deps
    session: Any  # Session
    pipeline_context: dict[str, Any]
    prompt_service: Any  # PromptService

    # Execution metadata
    run_id: str
    pipeline_name: str
    step_name: str

    # Optional deps
    event_emitter: Any | None = None  # PipelineEventEmitter
    variable_resolver: Any | None = None  # VariableResolver

    # Forward-compat: Task 3 output_validators (unused in Task 2)
    array_validation: Any | None = None
    validation_context: Any | None = None


def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
) -> Agent[StepDeps, Any]:
    """Build a pydantic-ai Agent configured for a pipeline step.

    Constructs an Agent with dynamic system prompt injection via
    @agent.instructions. The system prompt is resolved at runtime
    through deps.prompt_service, mirroring the former
    prompt resolution pattern.

    Validators (from validators.py factories) are registered via
    agent.output_validator() after the instructions block. The
    validation_context lambda wires per-call StepDeps.validation_context
    into Pydantic model validator context at run_sync() time, enabling
    output type field_validators to access ValidationContext via
    info.context.

    Args:
        step_name: Unique step identifier (e.g. 'constraint_extraction').
        output_type: Pydantic model for validated output.
        model: Model string (e.g. 'google-gla:gemini-2.0-flash-lite').
            None defers model selection to run-time via defer_model_check.
        system_instruction_key: DB prompt key for system instruction.
            Defaults to step_name if not provided.
        retries: Max retries for output validation failures.
        model_settings: ModelSettings for temperature, max_tokens, etc.
        validators: List of output validator callables (from validator
            factories like not_found_validator, array_length_validator).
            Each is registered via agent.output_validator(). None = no
            validators.

    Returns:
        Configured Agent[StepDeps, Any] with dynamic instructions and
        output validators registered.
    """
    from pydantic_ai import Agent, RunContext

    agent: Agent[StepDeps, Any] = Agent(
        model=model,
        output_type=output_type,
        deps_type=StepDeps,
        name=step_name,
        retries=retries,
        model_settings=model_settings,
        defer_model_check=True,
        validation_context=lambda ctx: ctx.deps.validation_context,
    )

    sys_key = system_instruction_key or step_name

    @agent.instructions
    def _inject_system_prompt(ctx: RunContext[StepDeps]) -> str:
        """Resolve system prompt from DB via PromptService.

        If a variable_resolver is available, resolves the system variable
        class and instantiates it before fetching the formatted prompt.
        Otherwise falls back to the raw prompt template.
        """
        if ctx.deps.variable_resolver:
            var_class = ctx.deps.variable_resolver.resolve(sys_key, 'system')
            if var_class:
                system_variables = var_class()
                variables_dict = (
                    system_variables.model_dump()
                    if hasattr(system_variables, 'model_dump')
                    else system_variables
                )
                return ctx.deps.prompt_service.get_system_prompt(
                    prompt_key=sys_key,
                    variables=variables_dict,
                    variable_instance=system_variables,
                )

        return ctx.deps.prompt_service.get_prompt(
            prompt_key=sys_key,
            prompt_type='system',
        )

    # Register output validators (from validator factories)
    for v in (validators or []):
        agent.output_validator(v)

    return agent


__all__ = ["StepDeps", "build_step_agent"]
