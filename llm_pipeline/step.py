"""
Base classes for LLM pipeline steps.

This module defines the foundation for implementing LLM-powered pipeline steps:
- LLMStep: Abstract base class for step implementations
- LLMResultMixin: Standardized result structure for all LLM outputs
- step_definition: Decorator for auto-generating step definition factories
"""
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, List, Dict, TYPE_CHECKING, Type, Optional, ClassVar

from pydantic import BaseModel, Field, ValidationError
from sqlmodel import SQLModel

from llm_pipeline.events.types import (
    ExtractionCompleted,
    ExtractionError,
    ExtractionStarting,
)
from llm_pipeline.naming import to_snake_case
from llm_pipeline.types import StepCallParams

logger = logging.getLogger(__name__)


def _safe_dump(instance: SQLModel) -> dict:
    """model_dump() with JSON-safe coercion for Decimals, datetimes, etc."""
    return json.loads(json.dumps(instance.model_dump(), default=str))


if TYPE_CHECKING:
    from pydantic_ai import Agent
    from llm_pipeline.agent_registry import AgentRegistry
    from llm_pipeline.pipeline import PipelineConfig
    from llm_pipeline.context import PipelineContext


def step_definition(
    instructions: Type[BaseModel],
    default_system_key: Optional[str] = None,
    default_user_key: Optional[str] = None,
    default_extractions: Optional[List] = None,
    default_transformation=None,
    context: Optional[Type] = None,
):
    """
    Decorator that auto-generates a factory function for creating step definitions.

    Stores configuration on the class and provides a create_definition() method.

    Args:
        instructions: The Pydantic instruction class for this step
        default_system_key: Default system instruction prompt key
        default_user_key: Default user prompt template key
        default_extractions: Default extraction classes
        default_transformation: Default transformation class
        context: Context class this step produces
    """
    def decorator(step_class):
        if not step_class.__name__.endswith('Step'):
            raise ValueError(
                f"{step_class.__name__} must follow naming convention: {{StepName}}Step"
            )

        step_name_prefix = step_class.__name__[:-4]

        expected_instruction_name = f"{step_name_prefix}Instructions"
        if instructions.__name__ != expected_instruction_name:
            raise ValueError(
                f"Instruction class for {step_class.__name__} must be named "
                f"'{expected_instruction_name}', got '{instructions.__name__}'"
            )

        if default_transformation:
            expected_transformation_name = f"{step_name_prefix}Transformation"
            if default_transformation.__name__ != expected_transformation_name:
                raise ValueError(
                    f"Transformation class for {step_class.__name__} must be named "
                    f"'{expected_transformation_name}', got '{default_transformation.__name__}'"
                )

        if context:
            expected_context_name = f"{step_name_prefix}Context"
            if context.__name__ != expected_context_name:
                raise ValueError(
                    f"Context class for {step_class.__name__} must be named "
                    f"'{expected_context_name}', got '{context.__name__}'"
                )

        step_class.INSTRUCTIONS = instructions
        step_class.DEFAULT_SYSTEM_KEY = default_system_key
        step_class.DEFAULT_USER_KEY = default_user_key
        step_class.DEFAULT_EXTRACTIONS = default_extractions or []
        step_class.DEFAULT_TRANSFORMATION = default_transformation
        step_class.CONTEXT = context

        @classmethod
        def create_definition(
            cls,
            system_instruction_key: Optional[str] = None,
            user_prompt_key: Optional[str] = None,
            extractions: Optional[List] = None,
            transformation=None,
            **kwargs
        ):
            from llm_pipeline.strategy import StepDefinition

            if extractions is None:
                extractions = cls.DEFAULT_EXTRACTIONS
            if 'transformation' not in kwargs and transformation is None:
                transformation = cls.DEFAULT_TRANSFORMATION

            return StepDefinition(
                step_class=cls,
                system_instruction_key=(
                    system_instruction_key
                    if system_instruction_key is not None
                    else cls.DEFAULT_SYSTEM_KEY
                ),
                user_prompt_key=(
                    user_prompt_key
                    if user_prompt_key is not None
                    else cls.DEFAULT_USER_KEY
                ),
                instructions=cls.INSTRUCTIONS,
                extractions=extractions,
                transformation=transformation,
                context=cls.CONTEXT,
                **kwargs
            )

        step_class.create_definition = create_definition
        return step_class

    return decorator


class LLMResultMixin(BaseModel):
    """
    Mixin for standardized LLM result fields.

    All LLM step result schemas should inherit from this mixin to ensure
    they include confidence scoring and notes fields.
    """

    confidence_score: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence in this analysis (0-1)"
    )
    notes: str | None = Field(
        default=None,
        description="General observations, reasoning, or additional context"
    )

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, 'example'):
            return
        if not isinstance(cls.example, dict):
            raise ValueError(
                f"{cls.__name__}.example must be a dict, got {type(cls.example).__name__}"
            )
        try:
            cls(**cls.example)
        except Exception as e:
            raise ValueError(
                f"{cls.__name__}.example validation failed: {str(e)}\n"
                f"Example dict must match class fields exactly."
            )

    @classmethod
    def get_example(cls):
        """Get an example instance for this instruction class."""
        if hasattr(cls, 'example') and isinstance(cls.example, dict):
            return cls(**cls.example)
        return None

    @classmethod
    def create_failure(cls, reason: str, **safe_defaults):
        """Create a failure result with confidence=0.0 and failure note."""
        return cls(
            confidence_score=0.0,
            notes=f"Failed: {reason}",
            **safe_defaults
        )


class LLMStep(ABC):
    """
    Base class for LLM-powered pipeline steps.

    Each step in an LLM pipeline implements this interface to:
    1. Prepare one or more LLM calls based on context
    2. Process the results from those calls into a final output
    """

    def __init__(
        self,
        system_instruction_key: str,
        user_prompt_key: str,
        instructions: Type[BaseModel],
        pipeline: 'PipelineConfig'
    ):
        self.system_instruction_key = system_instruction_key
        self.user_prompt_key = user_prompt_key
        self.instructions = instructions
        self.pipeline: 'PipelineConfig' = pipeline

    @property
    def step_name(self) -> str:
        """Auto-derived step name from class name (CamelCase -> snake_case, remove 'Step')."""
        class_name = self.__class__.__name__
        if not class_name.endswith('Step'):
            raise ValueError(
                f"Step class '{class_name}' must end with 'Step' suffix."
            )
        return to_snake_case(class_name, strip_suffix='Step')

    def get_agent(self, registry: 'AgentRegistry') -> tuple[type, list]:
        """
        Look up this step's instructions type and tools from the agent registry.

        Uses agent_name override (set by StepDefinition) if available,
        otherwise falls back to the auto-derived step_name.

        Returns (instructions, tools) tuple. instructions is the LLMResultMixin
        class reference; tools is a list of tool callables (empty if none registered).

        Args:
            registry: AgentRegistry subclass to look up from

        Returns:
            Tuple of (instructions LLMResultMixin class, list of tool callables)
        """
        agent_name = getattr(self, '_agent_name', None) or self.step_name
        instructions = registry.get_instructions(agent_name)
        tools = registry.get_tools(agent_name)
        return (instructions, tools)

    def build_user_prompt(
        self,
        variables: dict[str, Any] | Any,
        prompt_service: Any,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Build the user prompt string for this step via the prompt service.

        Extracts prompt building logic for use with pydantic-ai Agent.run().

        Args:
            variables: Template variables dict or Pydantic model instance
            prompt_service: PromptService instance for prompt rendering
            context: Optional additional context dict

        Returns:
            Rendered user prompt string
        """
        variable_instance = variables
        if hasattr(variables, 'model_dump'):
            variables = variables.model_dump()
        return prompt_service.get_user_prompt(
            self.user_prompt_key,
            variables=variables,
            variable_instance=variable_instance,
            context=context,
        )

    def store_extractions(self, model_class: Type[SQLModel], instances: List[SQLModel]) -> None:
        """Store extracted database models on the pipeline."""
        self.pipeline.store_extractions(model_class, instances)

    @abstractmethod
    def prepare_calls(self) -> List[StepCallParams]:
        """Prepare LLM call(s) for this step based on pipeline context."""
        pass

    def process_instructions(self, instructions: List[Any]) -> Dict[str, Any]:
        """Process raw LLM instructions to extract derived context values."""
        return {}

    def should_skip(self) -> bool:
        """Determine if this step should be skipped based on context."""
        return False

    def log_instructions(self, instructions: List[Any]) -> None:
        """Log step instructions to console. Override for custom logging."""
        pass

    def extract_data(self, instructions: List[Any]) -> None:
        """
        Extract database models from LLM instructions using step-level extractions.

        Automatically delegates to extraction classes registered on this step definition.
        """
        extraction_classes = getattr(self, '_extractions', [])
        for extraction_class in extraction_classes:
            extraction = extraction_class(self.pipeline)
            self.pipeline._current_extraction = extraction_class

            if self.pipeline._event_emitter:
                self.pipeline._emit(ExtractionStarting(
                    run_id=self.pipeline.run_id,
                    pipeline_name=self.pipeline.pipeline_name,
                    step_name=self.step_name,
                    extraction_class=extraction_class.__name__,
                    model_class=extraction.MODEL.__name__,
                    timestamp=datetime.now(timezone.utc),
                ))

            try:
                extract_start = datetime.now(timezone.utc)
                instances = extraction.extract(instructions)
                self.store_extractions(extraction.MODEL, instances)
                for instance in instances:
                    self.pipeline._real_session.add(instance)
                self.pipeline._real_session.flush()

                # Build created/updated payloads (post-flush so IDs are assigned)
                created_data = tuple(_safe_dump(inst) for inst in instances)
                updated_data = tuple(
                    {"id": getattr(inst, "id", None), "before": before, "after": _safe_dump(inst)}
                    for inst, before in extraction._tracked_updates
                )

                if self.pipeline._event_emitter:
                    self.pipeline._emit(ExtractionCompleted(
                        run_id=self.pipeline.run_id,
                        pipeline_name=self.pipeline.pipeline_name,
                        step_name=self.step_name,
                        extraction_class=extraction_class.__name__,
                        model_class=extraction.MODEL.__name__,
                        instance_count=len(instances),
                        execution_time_ms=(
                            datetime.now(timezone.utc) - extract_start
                        ).total_seconds() * 1000,
                        timestamp=datetime.now(timezone.utc),
                        created=created_data,
                        updated=updated_data,
                    ))
            except Exception as e:
                if self.pipeline._event_emitter:
                    validation_errors = (
                        [err["msg"] for err in e.errors()]
                        if isinstance(e, ValidationError)
                        else []
                    )
                    self.pipeline._emit(ExtractionError(
                        run_id=self.pipeline.run_id,
                        pipeline_name=self.pipeline.pipeline_name,
                        step_name=self.step_name,
                        extraction_class=extraction_class.__name__,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        validation_errors=validation_errors,
                        timestamp=datetime.now(timezone.utc),
                    ))
                raise
            finally:
                self.pipeline._current_extraction = None


__all__ = ["LLMStep", "LLMResultMixin", "step_definition"]
