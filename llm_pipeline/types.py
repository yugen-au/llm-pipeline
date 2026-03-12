"""
Shared type definitions for LLM pipeline.

Contains validation utilities and TypedDict parameter types.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict


@dataclass
class ArrayValidationConfig:
    """
    Configuration for validating LLM array responses.

    Used when the LLM returns an array that should match an input array
    in length and order (e.g., normalizing location strings).
    """
    input_array: List[Any]
    match_field: str = "original"
    filter_empty_inputs: bool = False
    allow_reordering: bool = True
    strip_number_prefix: bool = True


@dataclass
class ValidationContext:
    """
    Context data passed to Pydantic model validators during LLM response validation.

    Allows validators to access external data (e.g., sheet dimensions)
    that aren't part of the LLM response itself.

    Example:
        validation_context = ValidationContext(num_rows=len(df), num_cols=len(df.columns))
    """
    data: Dict[str, Any]

    def __init__(self, **kwargs):
        self.data = kwargs

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def to_dict(self) -> Dict[str, Any]:
        return self.data


class StepCallParams(TypedDict, total=False):
    """
    Parameters provided by step's prepare_calls().

    Required fields:
        variables: PromptVariables instance (User) with template variables

    Optional fields:
        array_validation: Config for array validation
        validation_context: Context data for Pydantic validators
    """
    variables: Any
    array_validation: Optional[Any]
    validation_context: Optional[Any]


__all__ = [
    "ArrayValidationConfig",
    "ValidationContext",
    "StepCallParams",
]
