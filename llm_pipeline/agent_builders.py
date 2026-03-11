"""
Factory for building pydantic-ai Agent instances for pipeline steps.

Provides StepDeps (dependency injection container) and build_step_agent()
(factory function) for constructing agents with dynamic system prompt
resolution via PromptService.
"""
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from pydantic_ai import Agent, RunContext

if TYPE_CHECKING:
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


def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
) -> Agent[StepDeps, Any]:
    """Build a pydantic-ai Agent configured for a pipeline step.

    Constructs an Agent with dynamic system prompt injection via
    @agent.instructions. The system prompt is resolved at runtime
    through deps.prompt_service, mirroring the existing
    create_llm_call() prompt resolution pattern.

    Args:
        step_name: Unique step identifier (e.g. 'constraint_extraction').
        output_type: Pydantic model for validated output.
        model: Model string (e.g. 'google-gla:gemini-2.0-flash-lite').
            None defers model selection to run-time via defer_model_check.
        system_instruction_key: DB prompt key for system instruction.
            Defaults to step_name if not provided.
        retries: Max retries for output validation failures.
        model_settings: ModelSettings for temperature, max_tokens, etc.

    Returns:
        Configured Agent[StepDeps, Any] with dynamic instructions registered.
    """
    agent: Agent[StepDeps, Any] = Agent(
        model=model,
        output_type=output_type,
        deps_type=StepDeps,
        name=step_name,
        retries=retries,
        model_settings=model_settings,
        defer_model_check=True,
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

    return agent


__all__ = ["StepDeps", "build_step_agent"]
