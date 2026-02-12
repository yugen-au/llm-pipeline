"""
Abstract base class for LLM providers.

Defines the interface that all LLM provider implementations must follow.
"""
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Type
from pydantic import BaseModel

from llm_pipeline.llm.result import LLMCallResult


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implementations handle the actual LLM API calls, including:
    - API authentication
    - Request formatting
    - Response parsing
    - Rate limiting
    - Retry logic

    Example:
        class GeminiProvider(LLMProvider):
            def call_structured(self, prompt, system_instruction, result_class, **kwargs):
                # Call Gemini API and return validated dict
                ...
    """

    @abstractmethod
    def call_structured(
        self,
        prompt: str,
        system_instruction: str,
        result_class: Type[BaseModel],
        max_retries: int = 3,
        not_found_indicators: Optional[List[str]] = None,
        strict_types: bool = True,
        array_validation: Optional[Any] = None,
        validation_context: Optional[Any] = None,
        **kwargs,
    ) -> LLMCallResult:
        """
        Call the LLM with structured output validation and retry logic.

        Args:
            prompt: User prompt text
            system_instruction: System instruction text
            result_class: Pydantic model class for validation
            max_retries: Maximum retry attempts
            not_found_indicators: Phrases indicating LLM couldn't find info
            strict_types: Whether to validate field types strictly
            array_validation: Optional ArrayValidationConfig
            validation_context: Optional ValidationContext for Pydantic validators

        Returns:
            LLMCallResult containing parsed output, raw response, model
            metadata, attempt count, and any validation errors.
        """
        ...


__all__ = ["LLMProvider"]
