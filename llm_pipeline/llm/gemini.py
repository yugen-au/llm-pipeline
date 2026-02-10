"""
Google Gemini LLM provider implementation.

Requires: pip install llm-pipeline[gemini]
"""
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.rate_limiter import RateLimiter
from llm_pipeline.llm.schema import format_schema_for_llm
from llm_pipeline.llm.validation import (
    validate_structured_output,
    validate_array_response,
    check_not_found_response,
    extract_retry_delay_from_error,
)

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    Google Gemini LLM provider.

    Uses google-generativeai SDK for structured output with validation.

    Args:
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
        model_name: Model to use (default: gemini-2.0-flash-lite).
        rate_limiter: Optional RateLimiter instance. Creates default if None.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.0-flash-lite",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=8, time_window_seconds=60
        )
        self._configured = False

    def _ensure_configured(self):
        if self._configured:
            return
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai not installed. "
                "Install with: pip install llm-pipeline[gemini]"
            )
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set and no api_key provided")
        genai.configure(api_key=self.api_key)
        self._configured = True

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
    ) -> Optional[Dict[str, Any]]:
        """Call Gemini with structured output validation and retry logic."""
        self._ensure_configured()
        import google.generativeai as genai

        expected_schema = result_class.model_json_schema()

        for attempt in range(max_retries):
            try:
                self.rate_limiter.wait_if_needed()

                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=system_instruction,
                )

                formatted_schema = format_schema_for_llm(result_class)
                prompt_with_schema = prompt + f"\n\n{formatted_schema}"

                response = model.generate_content(prompt_with_schema)

                if not response or not response.text:
                    logger.warning(
                        f"  Attempt {attempt + 1}/{max_retries}: No response from Gemini"
                    )
                    continue

                response_text = response.text

                if not_found_indicators and check_not_found_response(
                    response_text, not_found_indicators
                ):
                    logger.info(
                        f"  LLM indicated information not found: {response_text[:100]}..."
                    )
                    return None

                # Extract JSON from response
                cleaned_text = response_text.strip()
                json_match = re.search(
                    r"```(?:json)?\s*(\{.*?\})\s*```", cleaned_text, re.DOTALL
                )
                if json_match:
                    cleaned_text = json_match.group(1).strip()
                elif "{" in cleaned_text:
                    start = cleaned_text.find("{")
                    end = cleaned_text.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        cleaned_text = cleaned_text[start : end + 1]

                try:
                    response_json = json.loads(cleaned_text)
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"  Attempt {attempt + 1}/{max_retries}: JSON parse error: {e}"
                    )
                    continue

                # Validate structure
                is_valid, errors = validate_structured_output(
                    response_json, expected_schema, strict_types
                )
                if not is_valid:
                    logger.warning(
                        f"  Attempt {attempt + 1}/{max_retries}: Validation failed"
                    )
                    for error in errors:
                        logger.warning(f"    - {error}")
                    if attempt < max_retries - 1:
                        continue
                    continue

                # Array validation
                if array_validation:
                    array_valid, array_errors = validate_array_response(
                        response_json, array_validation, attempt
                    )
                    if not array_valid:
                        logger.warning(
                            f"  Attempt {attempt + 1}/{max_retries}: Array validation failed"
                        )
                        for error in array_errors:
                            logger.warning(f"    - {error}")
                        if attempt < max_retries - 1:
                            continue
                        continue

                # Pydantic validation
                try:
                    if validation_context:
                        result_class.model_validate(
                            response_json, context=validation_context.to_dict()
                        )
                    else:
                        result_class(**response_json)
                except Exception as pydantic_error:
                    logger.warning(
                        f"  Attempt {attempt + 1}/{max_retries}: "
                        f"Pydantic validation failed: {pydantic_error}"
                    )
                    if attempt < max_retries - 1:
                        continue
                    continue

                logger.info(f"  [OK] Validation passed on attempt {attempt + 1}")
                return response_json

            except Exception as e:
                error_str = str(e)
                is_rate_limit = (
                    "429" in error_str
                    or "quota" in error_str.lower()
                    or "rate limit" in error_str.lower()
                )

                if is_rate_limit and attempt < max_retries - 1:
                    retry_delay = extract_retry_delay_from_error(e)
                    if retry_delay:
                        logger.info(
                            f"  API suggested waiting {retry_delay:.1f}s, waiting..."
                        )
                        time.sleep(retry_delay)
                    else:
                        wait_time = 2**attempt
                        logger.info(
                            f"  Waiting {wait_time}s (exponential backoff)..."
                        )
                        time.sleep(wait_time)
                    continue
                else:
                    logger.warning(
                        f"  Attempt {attempt + 1}/{max_retries}: Error: {e}"
                    )
                    if attempt < max_retries - 1:
                        continue

        logger.error(f"  [ERROR] All {max_retries} attempts failed")
        return None


__all__ = ["GeminiProvider"]
