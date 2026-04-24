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
from llm_pipeline.inputs import StepInputs
from llm_pipeline.naming import to_snake_case
from llm_pipeline.types import StepCallParams

logger = logging.getLogger(__name__)


def _safe_dump(instance: SQLModel) -> dict:
    """model_dump() with JSON-safe coercion for Decimals, datetimes, etc."""
    return json.loads(json.dumps(instance.model_dump(), default=str))


if TYPE_CHECKING:
    from pydantic_ai import Agent
    from llm_pipeline.pipeline import PipelineConfig
    from llm_pipeline.wiring import AdapterContext


def step_definition(
    instructions: Type[BaseModel],
    default_system_key: Optional[str] = None,
    default_user_key: Optional[str] = None,
    default_transformation=None,
    agent: Optional[str] = None,
    model: Optional[str] = None,
    review: Optional[Type] = None,
    evaluators: Optional[List[Type]] = None,
    inputs: Optional[Type[StepInputs]] = None,
    consensus_strategy: Optional[Any] = None,
    tools: Optional[List[Type]] = None,
):
    """
    Decorator that auto-generates a factory function for creating step definitions.

    Stores configuration on the class and provides a create_definition() method.
    Extractions are no longer declared on the step (they are attached per-strategy
    via nested ``Bind`` instances).

    Args:
        instructions: The Pydantic instruction class for this step
        default_system_key: Default system instruction prompt key
        default_user_key: Default user prompt template key
        default_transformation: Default transformation class
        agent: Optional agent name for tool lookup from global agent registry
            (legacy — prefer ``tools`` for new steps)
        model: Optional default model for this step (overrides pipeline default)
        review: Optional StepReview subclass for human-in-the-loop review
        inputs: StepInputs subclass declaring this step's typed inputs
            contract. Strategies wire these inputs via Bind + .sources().
            Must be named ``{StepName}Inputs`` and subclass ``StepInputs``.
        consensus_strategy: Optional ``ConsensusStrategy`` instance declaring
            this step's default consensus behaviour (majority vote / adaptive
            / etc.). When set, strategies using this step get consensus by
            default; individual Binds may override with their own
            ``consensus_strategy`` field.
        tools: Optional list of ``PipelineTool`` subclasses this step uses
            by default. Strategy-level ``Bind.tools`` overrides this list.
            Each tool declares its own ``Inputs`` and ``Args``; the framework
            resolves tool inputs at step-execution time.
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

        if review:
            expected_review_name = f"{step_name_prefix}Review"
            if review.__name__ != expected_review_name:
                raise ValueError(
                    f"Review class for {step_class.__name__} must be named "
                    f"'{expected_review_name}', got '{review.__name__}'"
                )

        if inputs is not None:
            if not isinstance(inputs, type) or not issubclass(inputs, StepInputs):
                raise TypeError(
                    f"inputs= for {step_class.__name__} must be a StepInputs "
                    f"subclass, got {inputs!r}"
                )
            expected_inputs_name = f"{step_name_prefix}Inputs"
            if inputs.__name__ != expected_inputs_name:
                raise ValueError(
                    f"Inputs class for {step_class.__name__} must be named "
                    f"'{expected_inputs_name}', got '{inputs.__name__}'"
                )

        # Validate tools are PipelineTool subclasses
        if tools:
            from llm_pipeline.tool import PipelineTool
            for t in tools:
                if not (isinstance(t, type) and issubclass(t, PipelineTool)):
                    raise TypeError(
                        f"tools= for {step_class.__name__}: each entry must be "
                        f"a PipelineTool subclass, got {t!r}"
                    )

        step_class.INSTRUCTIONS = instructions
        step_class.DEFAULT_SYSTEM_KEY = default_system_key
        step_class.DEFAULT_USER_KEY = default_user_key
        step_class.DEFAULT_TRANSFORMATION = default_transformation
        step_class.AGENT = agent
        step_class.MODEL = model
        step_class.REVIEW = review
        step_class.INPUTS = inputs
        step_class.CONSENSUS_STRATEGY = consensus_strategy
        step_class.DEFAULT_TOOLS = tools or []
        step_class._step_evaluators = evaluators or []

        @classmethod
        def create_definition(
            cls,
            system_instruction_key: Optional[str] = None,
            user_prompt_key: Optional[str] = None,
            transformation=None,
            **kwargs
        ):
            from llm_pipeline.strategy import StepDefinition

            if 'transformation' not in kwargs and transformation is None:
                transformation = cls.DEFAULT_TRANSFORMATION

            # Default agent_name from decorator if not overridden in kwargs
            if 'agent_name' not in kwargs and cls.AGENT is not None:
                kwargs['agent_name'] = cls.AGENT

            # Default model from decorator if not overridden in kwargs
            if 'model' not in kwargs and cls.MODEL is not None:
                kwargs['model'] = cls.MODEL

            # Default review from decorator if not overridden in kwargs
            if 'review' not in kwargs and cls.REVIEW is not None:
                kwargs['review'] = cls.REVIEW

            # Default evaluators from decorator if not overridden in kwargs
            if 'evaluators' not in kwargs and cls._step_evaluators:
                kwargs['evaluators'] = cls._step_evaluators

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
                transformation=transformation,
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
        # Populated by the pipeline before prepare_calls() runs:
        # result of resolving the step's SourcesSpec against the current
        # AdapterContext. None until the pipeline assigns it.
        self.inputs: Optional[StepInputs] = None

    @property
    def step_name(self) -> str:
        """Auto-derived step name from class name (CamelCase -> snake_case, remove 'Step')."""
        class_name = self.__class__.__name__
        if not class_name.endswith('Step'):
            raise ValueError(
                f"Step class '{class_name}' must end with 'Step' suffix."
            )
        return to_snake_case(class_name, strip_suffix='Step')

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
        """Prepare LLM call(s) for this step based on self.inputs."""
        pass

    def should_skip(self) -> bool:
        """Determine if this step should be skipped based on context."""
        return False

    def log_instructions(self, instructions: List[Any]) -> None:
        """Log step instructions to console. Override for custom logging."""
        pass

    def extract_data(self, adapter_ctx: "AdapterContext") -> None:
        """Run the step's extraction binds, dispatching each via the Bind's adapter.

        For each nested extraction Bind attached via create_step:
        1. Resolve the Bind's inputs SourcesSpec against ``adapter_ctx``
           to produce a typed pathway inputs instance.
        2. Construct the extraction (validates MODEL in pipeline REGISTRY).
        3. Dispatch via ``extraction.extract(pathway_inputs)`` which routes
           to the method accepting that pathway's inputs class.
        4. Persist returned instances through the existing store_extractions
           + session flush + event emission machinery.
        """
        extraction_binds = getattr(self, '_extraction_binds', [])
        for ext_bind in extraction_binds:
            extraction_class = ext_bind.extraction
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
                pathway_inputs = ext_bind.inputs.resolve(adapter_ctx)
                # Build any resource-typed fields on the pathway inputs.
                from llm_pipeline.resources import resolve_resources
                resolve_resources(
                    pathway_inputs,
                    self.pipeline._build_runtime_ctx(step_name=self.step_name),
                )
                extract_start = datetime.now(timezone.utc)
                instances = extraction.extract(pathway_inputs)
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


    def prepare_review(self, instructions: List[Any]) -> 'ReviewData':
        """Prepare review data for human review. Override for custom display.

        Default: shows raw instruction data with no display_data fields.
        Override to provide human-friendly DisplayField items.
        """
        from llm_pipeline.review import ReviewData
        raw = None
        if instructions and hasattr(instructions[0], 'model_dump'):
            raw = instructions[0].model_dump(mode="json")
        return ReviewData(display_data=[], raw_data=raw)


__all__ = ["LLMStep", "LLMResultMixin", "step_definition"]
