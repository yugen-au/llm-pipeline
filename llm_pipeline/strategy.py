"""
Base classes for pipeline strategies.

A strategy defines:
1. What steps to run (get_steps)
2. When it applies (can_handle)

The pipeline orchestrates execution step-by-step, selecting the appropriate
strategy for each step based on context.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Type, Optional, ClassVar, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from llm_pipeline.extraction import PipelineExtraction
    from llm_pipeline.transformation import PipelineTransformation


@dataclass
class StepDefinition:
    """
    Definition of a pipeline step with its configuration.
    
    This connects a step class with its prompts, configuration, extractions, transformation,
    and context, making it clear what each step will do and what data it produces.
    """
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type
    action_after: Optional[str] = None
    extractions: List[Type['PipelineExtraction']] = field(default_factory=list)
    transformation: Optional[Type['PipelineTransformation']] = None
    context: Optional[Type] = None  # Type is PipelineContext but avoid circular import
    
    def create_step(self, pipeline: 'PipelineConfig'):
        """
        Create a configured step instance with pipeline reference.
        
        Auto-discovers prompt keys if not provided:
        1. Strategy-level: step_name.strategy_name (e.g., 'constraint_extraction.lane_based')
        2. Step-level: step_name (e.g., 'constraint_extraction')
        3. Error if none found
        
        Args:
            pipeline: Reference to the pipeline instance
        
        Returns:
            Instantiated step with prompts configured and pipeline reference
        """
        from sqlmodel import select
        from llm_pipeline.db.prompt import Prompt

        # Get step name for auto-discovery
        import re
        step_class_name = self.step_class.__name__
        step_name_prefix = step_class_name[:-4]  # Remove 'Step' suffix
        snake_case = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', step_name_prefix)
        snake_case = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', snake_case)
        step_name = snake_case.lower()
        
        # Determine final prompt keys with auto-discovery
        final_system_key = self.system_instruction_key
        final_user_key = self.user_prompt_key
        
        # Auto-discover if keys are None
        if final_system_key is None or final_user_key is None:
            # Get current strategy name from pipeline
            strategy_name = None
            if hasattr(pipeline, '_current_strategy') and pipeline._current_strategy:
                strategy_name = pipeline._current_strategy.name
            
            # Try strategy-level first (step_name.strategy_name)
            if strategy_name:
                if final_system_key is None:
                    strategy_key = f"{step_name}.{strategy_name}"
                    system_prompt = pipeline.session.exec(select(Prompt).where(
                        Prompt.prompt_key == strategy_key,
                        Prompt.prompt_type == 'system',
                        Prompt.is_active == True
                    )).first()
                    if system_prompt:
                        final_system_key = system_prompt.prompt_key
                
                if final_user_key is None:
                    strategy_key = f"{step_name}.{strategy_name}"
                    user_prompt = pipeline.session.exec(select(Prompt).where(
                        Prompt.prompt_key == strategy_key,
                        Prompt.prompt_type == 'user',
                        Prompt.is_active == True
                    )).first()
                    if user_prompt:
                        final_user_key = user_prompt.prompt_key
            
            # Fall back to step-level (step_name)
            if final_system_key is None:
                system_prompt = pipeline.session.exec(select(Prompt).where(
                    Prompt.prompt_key == step_name,
                    Prompt.prompt_type == 'system',
                    Prompt.is_active == True
                )).first()
                if system_prompt:
                    final_system_key = system_prompt.prompt_key

            if final_user_key is None:
                user_prompt = pipeline.session.exec(select(Prompt).where(
                    Prompt.prompt_key == step_name,
                    Prompt.prompt_type == 'user',
                    Prompt.is_active == True
                )).first()
                if user_prompt:
                    final_user_key = user_prompt.prompt_key
        
        # Validate that we have at least one key
        if final_system_key is None and final_user_key is None:
            raise ValueError(
                f"No prompts found for {step_class_name}. "
                f"Searched for:\n"
                f"  - {step_name}.{strategy_name if strategy_name else '[no strategy]'}\n"
                f"  - {step_name}\n"
                f"Please provide explicit keys or ensure prompts exist in database."
            )
        
        step = self.step_class(
            system_instruction_key=final_system_key,
            user_prompt_key=final_user_key,
            instructions=self.instructions,
            pipeline=pipeline  # Pass pipeline to step
        )
        # Store extractions, transformation, and context on the step instance
        step._extractions = self.extractions
        step._transformation = self.transformation
        step._context = self.context
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
    def get_steps(self) -> List[StepDefinition]:
        """
        Define all steps for this strategy.
        
        Returns:
            List of StepDefinition objects in order
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
