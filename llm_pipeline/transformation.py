"""
Base class for pipeline data transformations.

Transformations handle data structure changes (unpivoting, normalizing, etc.)
with type validation and strategy-specific logic support.

Transformations are defined in the same file as their step (next to the result schema)
and configured at the step level using default_transformations:

    @step_definition(
        result_class=UnpivotInstructions,
        default_transformations=[UnpivotTransformation],
    )
    class UnpivotDetectionStep(LLMStep):
        pass

Transformation methods can be:
- No methods defined → returns data unchanged (passthrough)
- Single method (any name) → auto-detected
- Explicit 'default' method → always used
- Multiple methods (lane_based, destination_based) → specified in strategy
"""
from abc import ABC
from typing import Any, ClassVar, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig


class PipelineTransformation(ABC):
    """
    Base class for data transformation logic.
    
    Each transformation validates input/output types and applies data structure
    changes based on LLM instructions.
    
    Transformations have access to:
    - self.pipeline.context: Derived values and metadata
    - self.pipeline.instructions: LLM instructions from other steps
    - self.pipeline.get_data(): Access to current and previous data states
    
    Types must be configured at class definition time:
    
    Example:
        class UnpivotDetectionTransformation(PipelineTransformation, 
                                             input_type=pd.DataFrame,
                                             output_type=pd.DataFrame):
            def default(self, data: pd.DataFrame, instructions: UnpivotDetectionInstructions) -> pd.DataFrame:
                # Transformation logic
                return transformed_df
    """
    
    INPUT_TYPE: ClassVar[Type] = None
    OUTPUT_TYPE: ClassVar[Type] = None
    
    def __init_subclass__(cls, input_type=None, output_type=None, **kwargs):
        """
        Called when a subclass is defined. Sets INPUT_TYPE and OUTPUT_TYPE from class parameters.
        
        Args:
            input_type: Expected type of input data (required for concrete transformations)
            output_type: Expected type of output data (required for concrete transformations)
            **kwargs: Additional keyword arguments passed to super().__init_subclass__
        
        Raises:
            ValueError: If input_type or output_type not provided for concrete transformation
        """
        super().__init_subclass__(**kwargs)
        
        # Only enforce types for concrete transformations (not intermediate base classes)
        if input_type is not None and output_type is not None:
            cls.INPUT_TYPE = input_type
            cls.OUTPUT_TYPE = output_type
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineTransformation:
            # This is a concrete transformation without types specified
            raise ValueError(
                f"{cls.__name__} must specify input_type and output_type parameters:\n"
                f"class {cls.__name__}(PipelineTransformation, input_type=YourType, output_type=YourType)"
            )
    
    def __init__(self, pipeline: 'PipelineConfig'):
        """
        Initialize transformation with pipeline reference.
        
        Args:
            pipeline: Reference to the pipeline instance
        """
        self.pipeline = pipeline
    
    def _validate_input(self, data: Any) -> None:
        """
        Validate input data matches expected INPUT_TYPE.
        
        Args:
            data: Input data to validate
        
        Raises:
            TypeError: If data doesn't match INPUT_TYPE
        """
        if self.INPUT_TYPE is not None and not isinstance(data, self.INPUT_TYPE):
            raise TypeError(
                f"{self.__class__.__name__} expects input type {self.INPUT_TYPE.__name__} "
                f"but got {type(data).__name__}"
            )
    
    def _validate_output(self, data: Any) -> None:
        """
        Validate output data matches expected OUTPUT_TYPE.
        
        Args:
            data: Output data to validate
        
        Raises:
            TypeError: If data doesn't match OUTPUT_TYPE
        """
        if self.OUTPUT_TYPE is not None and not isinstance(data, self.OUTPUT_TYPE):
            raise TypeError(
                f"{self.__class__.__name__} must return type {self.OUTPUT_TYPE.__name__} "
                f"but returned {type(data).__name__}"
            )
    
    def transform(self, data: Any, instructions: Any) -> Any:
        """
        Auto-detect and call the appropriate transformation method.
        
        This method implements smart method detection:
        1. Validates input data type
        2. If subclass defines a 'default' method → use it
        3. If subclass has exactly ONE custom method (not transform) → use that
        4. Otherwise → return data unchanged (passthrough)
        
        This allows transformation classes to define:
        - No methods → passthrough (returns data unchanged)
        - Single method with any name → auto-detected
        - Explicit 'default' method → always used
        - Multiple methods (lane_based, destination_based, etc.) → specified in strategy
        
        Args:
            data: Input data to transform
            instructions: LLM instructions for how to transform
        
        Returns:
            Transformed data (or original data if no transformation defined)
        
        Raises:
            TypeError: If input/output data doesn't match expected types
            NotImplementedError: If multiple methods exist and none named 'default'
        """
        # Validate input type
        self._validate_input(data)
        
        # Get all public methods except 'transform' itself and inherited methods
        all_methods = set(dir(self))
        base_methods = set(dir(PipelineTransformation))
        custom_methods = [
            m for m in (all_methods - base_methods)
            if callable(getattr(self, m))
            and not m.startswith('_')
            and m != 'transform'
        ]
        
        # Priority 1: explicit 'default' method
        if 'default' in custom_methods:
            result = self.default(data, instructions)
        # Priority 2: exactly one custom method
        elif len(custom_methods) == 1:
            method = getattr(self, custom_methods[0])
            result = method(data, instructions)
        # Priority 3: no custom methods - passthrough (return data unchanged)
        elif len(custom_methods) == 0:
            result = data
        # Ambiguous - multiple methods but no 'default'
        else:
            raise NotImplementedError(
                f"{self.__class__.__name__} has multiple transformation methods {custom_methods} "
                f"but no 'default' method. Either:\n"
                f"  1. Rename one method to 'default', or\n"
                f"  2. Specify the method name explicitly in the strategy"
            )
        
        # Validate output type
        self._validate_output(result)
        
        return result


__all__ = ["PipelineTransformation"]
