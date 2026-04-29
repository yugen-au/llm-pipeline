"""
Base classes for pipeline strategies.

A strategy defines:
1. What bindings to run (get_bindings)
2. When it applies (can_handle)

Each Bind in the returned list pairs a step class with a SourcesSpec
describing how the step's inputs are assembled, plus an optional list
of nested extraction Binds.

The pipeline orchestrates execution step-by-step, compiling each Bind
into a StepDefinition (internal data carrier) and resolving its inputs
adapter against the pipeline's accumulated output context.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Type, Optional, ClassVar, TYPE_CHECKING
from dataclasses import dataclass, field

from llm_pipeline.naming import to_snake_case
from llm_pipeline.wiring import Bind, SourcesSpec

if TYPE_CHECKING:
    from llm_pipeline.consensus import ConsensusStrategy
    from llm_pipeline.transformation import PipelineTransformation


@dataclass
class StepDefinition:
    """
    Internal data carrier between ``Bind`` (declarative, from strategy)
    and the live step instance (constructed in ``create_step``).

    A Bind is compiled into a StepDefinition at pipeline execution time;
    this dataclass captures everything the executor needs to run the step,
    including the Bind's inputs adapter and nested extraction Binds.

    ``prompt_name`` is the Phoenix prompt this step resolves against. A
    Phoenix CHAT prompt holds both the system + user messages within
    one record, so a single name suffices. Defaults to the step's
    snake_case name; override via ``Bind(step=..., prompt_name=...)``.
    """
    step_class: Type
    instructions: Type
    prompt_name: str | None = None
    action_after: Optional[str] = None
    extraction_binds: List[Bind] = field(default_factory=list)
    transformation: Optional[Type['PipelineTransformation']] = None
    inputs_spec: Optional[SourcesSpec] = None
    tool_binds: List[Bind] = field(default_factory=list)
    agent_name: str | None = None
    model: str | None = None
    not_found_indicators: list[str] | None = None
    consensus_strategy: 'ConsensusStrategy | None' = None
    review: 'StepReview | None' = None
    evaluators: list = field(default_factory=list)

    @property
    def step_name(self) -> str:
        """Derived snake_case name from step_class (e.g. ConstraintExtractionStep -> 'constraint_extraction')."""
        return to_snake_case(self.step_class.__name__, strip_suffix='Step')

    @property
    def resolved_prompt_name(self) -> str:
        """Phoenix prompt name to use at runtime. Falls back to the step's
        snake_case name when no per-Bind override is set."""
        return self.prompt_name or self.step_name

    def create_step(self, pipeline: 'PipelineConfig'):
        """Construct a configured step instance bound to ``pipeline``.

        The Phoenix prompt name is computed from ``self.resolved_prompt_name``
        (Bind override, or the step's snake_case class name). PromptService
        fetches the matching CHAT prompt and pulls the system + user
        messages from it at runtime — no tier-3 DB auto-discovery.
        """
        step = self.step_class(
            prompt_name=self.resolved_prompt_name,
            instructions=self.instructions,
            pipeline=pipeline,
        )
        step._extraction_binds = self.extraction_binds
        step._tool_binds = self.tool_binds
        step._transformation = self.transformation
        step._agent_name = self.agent_name
        step._step_model = self.model
        step._inputs_spec = self.inputs_spec
        return step


class PipelineStrategy(ABC):
    """
    Base class for pipeline strategies.
    
    Each strategy defines:
    1. When it applies (can_handle)
    2. What steps it provides (get_steps)
    
    The pipeline orchestrates execution by looping through step positions
    and finding which strategy can handle each position.
    
    Naming convention: Class must end with 'Strategy' (e.g., LaneBasedStrategy)
    Auto-generated properties:
    - name: snake_case version (LaneBasedStrategy -> "lane_based")
    - display_name: Title case version (LaneBasedStrategy -> "Lane Based")
    """
    
    def __init_subclass__(cls, **kwargs):
        """
        Called when a subclass is defined. Auto-generates name and display_name.
        
        Validates:
        - Class name ends with 'Strategy' suffix
        
        Auto-generates:
        - cls.NAME: snake_case name from class name
        - cls.DISPLAY_NAME: human-readable display name
        
        Raises:
            ValueError: If class name doesn't follow naming convention
        """
        super().__init_subclass__(**kwargs)
        
        # Skip validation for intermediate base classes (start with _)
        if cls.__name__.startswith('_'):
            return
        
        # Only validate concrete strategy classes (direct subclasses of PipelineStrategy)
        if cls.__bases__[0] is not PipelineStrategy:
            return
        
        # Validate naming convention
        if not cls.__name__.endswith('Strategy'):
            raise ValueError(
                f"Strategy class '{cls.__name__}' must end with 'Strategy' suffix. "
                f"Example: {cls.__name__}Strategy"
            )
        
        # Auto-generate name (snake_case)
        strategy_prefix = cls.__name__[:-8]  # Remove 'Strategy' suffix
        import re
        snake_case = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', strategy_prefix)
        snake_case = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', snake_case)
        cls.NAME = snake_case.lower()
        
        # Auto-generate display_name (Title Case with spaces)
        # Insert space before capitals, then title case
        display = re.sub(r'([a-z\d])([A-Z])', r'\1 \2', strategy_prefix)
        display = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', display)
        cls.DISPLAY_NAME = display.strip()
    
    @property
    def name(self) -> str:
        """
        Strategy name (auto-generated from class name).
        
        Example: LaneBasedStrategy -> "lane_based"
        
        Returns:
            Unique identifier for this strategy
        """
        return self.NAME
    
    @property
    def display_name(self) -> str:
        """
        Human-readable strategy name (auto-generated from class name).
        
        Example: LaneBasedStrategy -> "Lane Based"
        
        Returns:
            Display name for UI/logging
        """
        return self.DISPLAY_NAME
    
    @abstractmethod
    def can_handle(self, context: Dict[str, Any]) -> bool:
        """
        Determine if this strategy can handle the current context.
        
        This is checked before each step to see if this strategy should
        provide the step implementation.
        
        Args:
            context: Current pipeline context
        
        Returns:
            True if this strategy should provide steps, False otherwise
        """
        pass
    
    @abstractmethod
    def get_bindings(self) -> List[Bind]:
        """
        Declare the step bindings this strategy runs.

        Each Bind pairs a step class with the ``SourcesSpec`` describing
        how to assemble its inputs, plus optional nested extraction Binds.
        The pipeline compiles each Bind into a StepDefinition at execution
        time and resolves its inputs adapter against the accumulated output
        context.

        Returns:
            Ordered list of ``Bind`` instances.
        """
        pass


class PipelineStrategies(ABC):
    """
    Base class for declaring pipeline strategies.
    
    Similar to PipelineDatabaseRegistry, this provides a declarative way
    to define which strategies a pipeline uses, making configuration
    clear and centralized.
    
    Strategies must be configured at class definition time using class call syntax:
    
    Example:
        class RateCardParserStrategies(PipelineStrategies, strategies=[
            LaneBasedStrategy,
            DestinationBasedStrategy,
            GlobalRatesStrategy,
        ]):
            pass
    
    Usage in pipeline:
        class MyPipeline(PipelineConfig,
                        registry=MyRegistry,
                        strategies=MyStrategies,
                        extractions=MyExtractions):
            pass
    """
    
    STRATEGIES: ClassVar[List[Type[PipelineStrategy]]] = []
    
    def __init_subclass__(cls, strategies=None, **kwargs):
        """
        Called when a subclass is defined. Sets STRATEGIES from class parameter.
        
        Args:
            strategies: List of PipelineStrategy classes (required)
            **kwargs: Additional keyword arguments passed to super().__init_subclass__
        
        Raises:
            ValueError: If strategies not provided for concrete strategies class
        """
        super().__init_subclass__(**kwargs)
        
        # Only enforce strategies for concrete classes (not intermediate base classes)
        if strategies is not None:
            cls.STRATEGIES = strategies
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineStrategies:
            # This is a concrete strategies class without strategies specified
            raise ValueError(
                f"{cls.__name__} must specify strategies parameter when defining the class:\n"
                f"class {cls.__name__}(PipelineStrategies, strategies=[Strategy1, Strategy2, ...])"
            )
    
    @classmethod
    def create_instances(cls) -> List[PipelineStrategy]:
        """
        Create instances of all configured strategies.
        
        Returns:
            List of instantiated strategy objects
        
        Raises:
            ValueError: If STRATEGIES not configured
        """
        if not cls.STRATEGIES:
            raise ValueError(
                f"{cls.__name__} has no strategies configured. "
                f"Use: class {cls.__name__}(PipelineStrategies, strategies=[...])"
            )
        return [strategy_class() for strategy_class in cls.STRATEGIES]
    
    @classmethod
    def get_strategy_names(cls) -> List[str]:
        """
        Get names of all configured strategies.
        
        Returns:
            List of strategy names
        """
        return [strategy_class().name for strategy_class in cls.STRATEGIES]


__all__ = ["StepDefinition", "PipelineStrategy", "PipelineStrategies"]
