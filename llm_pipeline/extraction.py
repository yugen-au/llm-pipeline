"""
Base classes for pipeline data extractions.

Extractions handle the conversion of LLM results into database models.
Each extraction is responsible for one model type and has access to the
pipeline's context and state.

Extractions are defined in the same file as their step (next to the result schema)
and configured at the step level using default_extractions:

    @step_definition(
        result_class=SemanticMappingInstructions,
        default_extractions=[LaneExtraction],
    )
    class SemanticMappingStep(LLMStep):
        pass

Extraction methods can be:
- Single method (any name) → auto-detected
- Explicit 'default' method → always used  
- Multiple methods (lane_based, destination_based) → specified in strategy
"""
from abc import ABC, abstractmethod
from typing import List, Type, ClassVar, TYPE_CHECKING
from sqlmodel import SQLModel
from decimal import Decimal
from pydantic import ValidationError

if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig


class PipelineExtraction(ABC):
    """
    Base class for data extraction logic.
    
    Each extraction is responsible for creating instances of one database model
    from LLM results and pipeline context.
    
    Extractions have access to:
    - self.pipeline.context: All step results, DataFrame, etc.
    - self.pipeline.get_extractions(Model): Previously extracted models
    - self.pipeline.session: Database session
    
    Model must be configured at class definition time using class call syntax:
    
    Example:
        class LaneExtraction(PipelineExtraction, model=Lane):
            def extract(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
                result = results[0]
                df = self.pipeline.context['df']
                rate_card_id = self.pipeline.context['rate_card_id']
                # ... extraction logic
                return lanes
    """
    
    MODEL: ClassVar[Type[SQLModel]] = None
    
    def __init_subclass__(cls, model=None, **kwargs):
        """
        Called when a subclass is defined. Sets MODEL from class parameter.
        
        Args:
            model: SQLModel class this extraction produces (required)
            **kwargs: Additional keyword arguments passed to super().__init_subclass__
        
        Raises:
            ValueError: If model not provided for concrete extraction
            ValueError: If class name doesn't follow naming convention
        """
        super().__init_subclass__(**kwargs)
        
        # Only enforce model for concrete extractions (not intermediate base classes)
        if model is not None:
            cls.MODEL = model
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineExtraction:
            # This is a concrete extraction without model specified
            raise ValueError(
                f"{cls.__name__} must specify model parameter when defining the class:\n"
                f"class {cls.__name__}(PipelineExtraction, model=YourModel)"
            )
        
        # Enforce naming convention: must end with 'Extraction'
        if not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineExtraction:
            if not cls.__name__.endswith('Extraction'):
                raise ValueError(
                    f"{cls.__name__} must follow naming convention: {{ModelName}}Extraction\n"
                    f"Example: LaneExtraction, RateExtraction"
                )
    
    def __init__(self, pipeline: 'PipelineConfig'):
        """
        Initialize extraction with pipeline reference.
        
        Validates that the extraction's MODEL is in the pipeline's registry.
        
        Args:
            pipeline: Reference to the pipeline instance
        
        Raises:
            ValueError: If MODEL is not in pipeline's registry
        """
        # Validate that this extraction's model is in the pipeline's registry
        if self.MODEL not in pipeline.REGISTRY.get_models():
            raise ValueError(
                f"{self.__class__.__name__}.MODEL ({self.MODEL.__name__}) "
                f"is not in {pipeline.REGISTRY.__name__}. "
                f"Valid models: {[m.__name__ for m in pipeline.REGISTRY.get_models()]}"
            )
        
        self.pipeline = pipeline
        self._tracked_updates: list[tuple[SQLModel, dict]] = []

    def begin_update(self, instance: SQLModel) -> None:
        """Snapshot instance state before mutation for before/after diffing."""
        self._tracked_updates.append((instance, instance.model_dump()))
    
    def _validate_instance(self, instance: SQLModel, index: int) -> None:
        """
        Validate a single model instance before database insertion.
        
        This catches validation issues that SQLModel with table=True doesn't catch,
        ensuring errors happen at extraction time rather than database insertion time.
        
        Validates:
        - Decimal fields for NaN/Infinity (prevents silent failures)
        - Required fields for NULL (prevents NOT NULL constraint violations)
        - Foreign key fields for NULL (prevents FK constraint violations)
        
        Args:
            instance: Model instance to validate
            index: Index in the list (for error messages)
        
        Raises:
            ValueError: If instance contains invalid data (NaN, Infinity, NULL in required fields)
        """
        from typing import get_origin, get_args
        
        model_name = self.MODEL.__name__
        
        # Get SQLAlchemy table metadata if available (for FK detection)
        foreign_key_fields = set()
        if hasattr(self.MODEL, '__table__'):
            for column in self.MODEL.__table__.columns:
                if column.foreign_keys:
                    foreign_key_fields.add(column.name)
        
        # Validate all fields
        for field_name, field_info in type(instance).model_fields.items():
            value = getattr(instance, field_name, None)
            
            # Check if field is required (not Optional, no default)
            is_required = field_info.is_required()
            is_foreign_key = field_name in foreign_key_fields
            
            # Validate required fields (NOT NULL constraint)
            if is_required and value is None:
                raise ValueError(
                    f"Invalid {model_name} at index {index}: "
                    f"Required field '{field_name}' cannot be None. "
                    f"This would violate NOT NULL constraint on database insertion. "
                    f"Check extraction logic to ensure all required fields are populated."
                )
            
            # Validate foreign key fields (even if Optional, should not be None if set)
            # Special case: primary keys named 'id' are auto-generated, so None is OK
            if is_foreign_key and value is None and field_name != 'id':
                # Only warn if this isn't an optional FK
                if is_required:
                    raise ValueError(
                        f"Invalid {model_name} at index {index}: "
                        f"Foreign key field '{field_name}' cannot be None. "
                        f"This would violate foreign key constraint on database insertion. "
                        f"Check extraction logic to ensure foreign key references are valid."
                    )
            
            # Skip None values for remaining checks
            if value is None:
                continue
                
            # Validate Decimal fields for NaN and Infinity
            if isinstance(value, Decimal):
                if value.is_nan():
                    raise ValueError(
                        f"Invalid {model_name} at index {index}: "
                        f"Field '{field_name}' cannot be NaN. "
                        f"Check extraction logic to filter out NaN values."
                    )
                if value.is_infinite():
                    raise ValueError(
                        f"Invalid {model_name} at index {index}: "
                        f"Field '{field_name}' cannot be Infinity. "
                        f"Check extraction logic to filter out Infinity values."
                    )
    
    def _validate_instances(self, instances: List[SQLModel]) -> List[SQLModel]:
        """
        Validate all extracted instances before returning to pipeline.
        
        SQLModel with table=True doesn't run Pydantic validation, so we manually
        validate critical constraints here to catch errors at extraction time
        rather than at database insertion time.
        
        Args:
            instances: List of model instances from extraction method
        
        Returns:
            Same list of instances (validation raises on error)
        
        Raises:
            ValueError: If any instance contains invalid data
        """
        for i, instance in enumerate(instances):
            self._validate_instance(instance, i)
        
        return instances
    
    def extract(self, results: List[any]) -> List[SQLModel]:
        """
        Auto-detect and call the appropriate extraction method.
        
        This method implements smart method detection:
        1. If subclass defines a 'default' method → use it
        2. If current strategy has matching method name → use that
        3. If subclass has exactly ONE custom method (not extract) → use that
        4. Otherwise → raise error (ambiguous, must specify method in strategy)
        
        This allows extraction classes to define:
        - Single method with any name → auto-detected
        - Explicit 'default' method → always used
        - Multiple strategy-specific methods (lane_based, destination_based, etc.) → auto-routed by strategy name
        
        Args:
            results: List of LLM result objects from pipeline execution
        
        Returns:
            List of model instances ready for database insertion
        
        Raises:
            NotImplementedError: If multiple methods exist and none match current strategy or default
        """
        # Get all public methods except 'extract' itself and inherited methods
        all_methods = set(dir(self))
        base_methods = set(dir(PipelineExtraction))
        custom_methods = [
            m for m in (all_methods - base_methods)
            if callable(getattr(self, m))
            and not m.startswith('_')
            and m != 'extract'
        ]
        
        # Priority 1: explicit 'default' method
        if 'default' in custom_methods:
            instances = self.default(results)
            return self._validate_instances(instances)
        
        # Priority 2: strategy-specific method matching current strategy name
        if hasattr(self.pipeline, '_current_strategy') and self.pipeline._current_strategy:
            strategy_name = self.pipeline._current_strategy.name
            if strategy_name in custom_methods:
                method = getattr(self, strategy_name)
                instances = method(results)
                return self._validate_instances(instances)
        
        # Priority 3: exactly one custom method
        if len(custom_methods) == 1:
            method = getattr(self, custom_methods[0])
            instances = method(results)
            return self._validate_instances(instances)
        
        # Priority 4: no custom methods - must be abstract base or error
        if len(custom_methods) == 0:
            raise NotImplementedError(
                f"{self.__class__.__name__} has no extraction methods defined. "
                f"Add a 'default' method or a custom extraction method."
            )
        
        # Ambiguous - multiple methods but no 'default' or strategy match
        strategy_name = self.pipeline._current_strategy.name if hasattr(self.pipeline, '_current_strategy') and self.pipeline._current_strategy else None
        raise NotImplementedError(
            f"{self.__class__.__name__} has multiple extraction methods {custom_methods} "
            f"but no matching method for current strategy '{strategy_name}' and no 'default' method. Either:\n"
            f"  1. Add a method named '{strategy_name}' to match the current strategy, or\n"
            f"  2. Add a 'default' method to handle all strategies"
        )


__all__ = ["PipelineExtraction"]
