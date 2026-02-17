"""
Base classes for LLM pipeline steps.

This module defines the foundation for implementing LLM-powered pipeline steps:
- LLMStep: Abstract base class for step implementations
- LLMResultMixin: Standardized result structure for all LLM outputs
- step_definition: Decorator for auto-generating step definition factories
"""
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, List, Dict, TYPE_CHECKING, Type, Optional, ClassVar, Tuple

from pydantic import BaseModel, Field, ValidationError
from sqlmodel import SQLModel

from llm_pipeline.events.types import (
    ExtractionCompleted,
    ExtractionError,
    ExtractionStarting,
)
from llm_pipeline.types import StepCallParams

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig
    from llm_pipeline.types import ExecuteLLMStepParams
    from llm_pipeline.context import PipelineContext


def _query_prompt_keys(
    step_name: str,
    session: Any,
    strategy_name: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Query database for prompt keys using the provided session.

    Args:
        step_name: Name of the step (e.g., 'constraint_extraction')
        session: Database session to query prompts
        strategy_name: Optional strategy name (e.g., 'lane_based')

    Returns:
        Tuple of (system_key, user_key) or (None, None) if not found
    """
    from sqlmodel import select
    from llm_pipeline.db.prompt import Prompt

    if strategy_name:
        search_key = f"{step_name}.{strategy_name}"
    else:
        search_key = step_name

    system_key = None
    user_key = None

    system_prompt = session.exec(select(Prompt).where(
        Prompt.prompt_key == search_key,
        Prompt.prompt_type == 'system',
        Prompt.is_active == True
    )).first()
    if system_prompt:
        system_key = system_prompt.prompt_key

    user_prompt = session.exec(select(Prompt).where(
        Prompt.prompt_key == search_key,
        Prompt.prompt_type == 'user',
        Prompt.is_active == True
    )).first()
    if user_prompt:
        user_key = user_prompt.prompt_key

    return system_key, user_key


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
        name = class_name[:-4]
        snake_case = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
        return snake_case

    def store_extractions(self, model_class: Type[SQLModel], instances: List[SQLModel]) -> None:
        """Store extracted database models on the pipeline."""
        self.pipeline.store_extractions(model_class, instances)

    def create_llm_call(
        self,
        variables: Dict[str, Any],
        system_instruction_key: Optional[str] = None,
        user_prompt_key: Optional[str] = None,
        instructions: Optional[Type[BaseModel]] = None,
        **extra_params
    ) -> 'ExecuteLLMStepParams':
        """
        Create an ExecuteLLMStepParams dict with defaults from step config.

        Automatically instantiates System variables if the step has a
        variable_resolver configured on the pipeline.
        """
        system_key = system_instruction_key or self.system_instruction_key

        # Auto-instantiate System variables via variable_resolver if available
        system_variables = None
        if system_key and hasattr(self.pipeline, '_variable_resolver') and self.pipeline._variable_resolver:
            try:
                system_var_class = self.pipeline._variable_resolver.resolve(system_key, 'system')
                if system_var_class:
                    system_variables = system_var_class()
            except (AttributeError, ImportError):
                pass

        params = {
            "system_instruction_key": system_key,
            "user_prompt_key": user_prompt_key or self.user_prompt_key,
            "variables": variables,
            "result_class": instructions or self.instructions,
            "system_variables": system_variables,
        }
        params.update(extra_params)
        return params

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
