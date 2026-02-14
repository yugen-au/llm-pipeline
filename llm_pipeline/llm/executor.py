"""
Provider-agnostic LLM step executor.

Handles prompt retrieval, variable formatting, and dispatching to LLM providers.
"""
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.result import LLMCallResult
from llm_pipeline.types import ArrayValidationConfig, ValidationContext

if TYPE_CHECKING:
    from llm_pipeline.events.emitter import PipelineEventEmitter

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def execute_llm_step(
    system_instruction_key: str,
    user_prompt_key: str,
    variables: Any,
    result_class: Type[T],
    provider: Optional[LLMProvider] = None,
    prompt_service: Any = None,
    context: Optional[Dict[str, Any]] = None,
    array_validation: Optional[ArrayValidationConfig] = None,
    system_variables: Optional[Any] = None,
    validation_context: Optional[ValidationContext] = None,
    event_emitter: Optional["PipelineEventEmitter"] = None,
    run_id: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    step_name: Optional[str] = None,
    call_index: int = 0,
) -> T:
    """
    Generic executor for LLM-based pipeline steps.

    Handles the common pattern of:
    1. Retrieving prompts from database via prompt_service
    2. Calling LLM via provider with structured output (returns LLMCallResult)
    3. Validating response with Pydantic
    4. Returning result or calling create_failure()

    Args:
        system_instruction_key: Key for system instruction prompt
        user_prompt_key: Key for user prompt template
        variables: PromptVariables instance or dict
        result_class: Pydantic model class for the result
        provider: LLMProvider instance for making LLM calls
        prompt_service: PromptService instance for prompt retrieval
        context: Optional context for prompt retrieval
        array_validation: Optional array validation configuration
        system_variables: Optional system prompt variables
        validation_context: Optional ValidationContext for Pydantic validators

    Returns:
        Validated Pydantic result object
    """
    if provider is None:
        raise ValueError(
            "provider is required. Pass an LLMProvider instance "
            "(e.g., GeminiProvider()) to execute_llm_step() or pipeline."
        )
    if prompt_service is None:
        raise ValueError(
            "prompt_service is required. Pass a PromptService instance "
            "to execute_llm_step() or pipeline."
        )

    # Convert PromptVariables instances to dicts if needed
    if hasattr(variables, "model_dump"):
        variables_dict = variables.model_dump()
    else:
        variables_dict = variables

    system_variables_dict = None
    if system_variables is not None:
        if hasattr(system_variables, "model_dump"):
            system_variables_dict = system_variables.model_dump()
        else:
            system_variables_dict = system_variables

    # Get system instruction
    if system_variables_dict:
        system_instruction = prompt_service.get_system_prompt(
            system_instruction_key,
            variables=system_variables_dict,
            variable_instance=system_variables,
            context=context,
        )
    else:
        system_instruction = prompt_service.get_prompt(
            system_instruction_key,
            prompt_type="system",
            context=context,
        )

    # Get user prompt
    user_prompt = prompt_service.get_user_prompt(
        user_prompt_key,
        variables=variables_dict,
        variable_instance=variables,
        context=context,
    )

    # Emit LLMCallStarting before provider call
    if event_emitter:
        from llm_pipeline.events.types import LLMCallStarting

        event_emitter.emit(
            LLMCallStarting(
                run_id=run_id,
                pipeline_name=pipeline_name,
                step_name=step_name,
                call_index=call_index,
                rendered_system_prompt=system_instruction,
                rendered_user_prompt=user_prompt,
            )
        )

    # Call LLM via provider
    try:
        result: LLMCallResult = provider.call_structured(
            prompt=user_prompt,
            system_instruction=system_instruction,
            result_class=result_class,
            array_validation=array_validation,
            validation_context=validation_context,
        )
    except Exception as exc:
        if event_emitter:
            from llm_pipeline.events.types import LLMCallCompleted

            event_emitter.emit(
                LLMCallCompleted(
                    run_id=run_id,
                    pipeline_name=pipeline_name,
                    step_name=step_name,
                    call_index=call_index,
                    raw_response=None,
                    parsed_result=None,
                    model_name=None,
                    attempt_count=1,
                    validation_errors=[str(exc)],
                )
            )
        raise

    # Emit LLMCallCompleted after successful provider call
    if event_emitter:
        from llm_pipeline.events.types import LLMCallCompleted

        event_emitter.emit(
            LLMCallCompleted(
                run_id=run_id,
                pipeline_name=pipeline_name,
                step_name=step_name,
                call_index=call_index,
                raw_response=result.raw_response,
                parsed_result=result.parsed,
                model_name=result.model_name,
                attempt_count=result.attempt_count,
                validation_errors=result.validation_errors,
            )
        )

    if result.parsed is None:
        if result.validation_errors:
            failure_msg = f"LLM call failed: {'; '.join(result.validation_errors)}"
        else:
            failure_msg = "LLM call failed"
        return result_class.create_failure(failure_msg)

    # Validate with Pydantic
    try:
        if validation_context:
            return result_class.model_validate(
                result.parsed, context=validation_context.to_dict()
            )
        else:
            return result_class(**result.parsed)
    except Exception as e:
        logger.error(f"[ERROR] Pydantic validation failed: {e}")
        return result_class.create_failure(f"Validation failed: {str(e)}")


def save_step_yaml(save_dir: "Path", step_name: str, data: dict) -> "Path":
    """Save a pipeline step result to YAML."""
    import yaml
    from pathlib import Path as P

    if not isinstance(save_dir, P):
        save_dir = P(save_dir)
    step_path = save_dir / f"{step_name}.yaml"
    with open(step_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return step_path


__all__ = ["execute_llm_step", "save_step_yaml"]
