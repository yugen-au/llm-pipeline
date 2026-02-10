"""
Base class for pipeline context contributions.

Context represents derived values that steps extract from their instructions
and make available to other steps via pipeline.context.
"""
from pydantic import BaseModel


class PipelineContext(BaseModel):
    """
    Base class for step context contributions.
    
    Steps that add values to pipeline context should define a Context class
    that inherits from this base class.
    
    Context classes follow the naming convention: {StepName}Context
    
    Example:
        class TableTypeDetectionContext(PipelineContext):
            table_type: str
        
        @step_definition(
            instructions=TableTypeDetectionInstructions,
            context=TableTypeDetectionContext
        )
        class TableTypeDetectionStep(LLMStep):
            def process_instructions(self, instructions) -> TableTypeDetectionContext:
                return TableTypeDetectionContext(
                    table_type=instructions[0].table_type.value
                )
    """
    pass


__all__ = ["PipelineContext"]
