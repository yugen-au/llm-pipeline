"""
Validation utilities for LLM structured output responses.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from llm_pipeline.types import ArrayValidationConfig

logger = logging.getLogger(__name__)


def validate_field_value(value: Any, expected_type: str) -> bool:
    """Validate that a value matches the expected type."""
    type_checks = {
        "string": lambda v: isinstance(v, str),
        "number": lambda v: isinstance(v, (int, float)),
        "integer": lambda v: isinstance(v, int),
        "boolean": lambda v: isinstance(v, bool),
    }
    checker = type_checks.get(expected_type)
    if not checker:
        return True
    return checker(value)


def _validate_field_type(
    field_name: str, value: Any, field_schema: Dict[str, Any]
) -> List[str]:
    """Validate a field's value matches its schema type definition."""
    errors = []

    if "anyOf" in field_schema:
        any_valid = False
        for type_option in field_schema["anyOf"]:
            if type_option.get("type") == "null" and value is None:
                any_valid = True
                break
            option_errors = _validate_against_type(field_name, value, type_option)
            if not option_errors:
                any_valid = True
                break
        if not any_valid:
            type_names = [opt.get("type", "unknown") for opt in field_schema["anyOf"]]
            errors.append(
                f"Field '{field_name}' doesn't match any allowed types: {type_names}"
            )
        return errors

    return _validate_against_type(field_name, value, field_schema)


def _validate_against_type(
    field_name: str, value: Any, type_schema: Dict[str, Any]
) -> List[str]:
    """Validate value against a single type schema."""
    errors = []
    expected_type = type_schema.get("type")
    if not expected_type:
        return errors

    if expected_type == "string":
        if not isinstance(value, str):
            errors.append(
                f"Field '{field_name}' should be string, got {type(value).__name__}"
            )
    elif expected_type == "number":
        if not isinstance(value, (int, float)):
            errors.append(
                f"Field '{field_name}' should be number, got {type(value).__name__}"
            )
    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            if isinstance(value, str) and value.isdigit():
                errors.append(
                    f"Field '{field_name}' should be integer, got string '{value}' "
                    f"(hint: use numeric value {int(value)} instead)"
                )
            else:
                errors.append(
                    f"Field '{field_name}' should be integer, got {type(value).__name__}"
                )
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            errors.append(
                f"Field '{field_name}' should be boolean, got {type(value).__name__}"
            )
    elif expected_type == "array":
        if not isinstance(value, list):
            errors.append(
                f"Field '{field_name}' should be array, got {type(value).__name__}"
            )
        else:
            items_schema = type_schema.get("items")
            if items_schema:
                for i, item in enumerate(value):
                    item_errors = _validate_against_type(
                        f"{field_name}[{i}]", item, items_schema
                    )
                    errors.extend(item_errors)
    elif expected_type == "object":
        if not isinstance(value, dict):
            errors.append(
                f"Field '{field_name}' should be object, got {type(value).__name__}"
            )

    return errors


def validate_structured_output(
    response_json: Any,
    expected_schema: Dict[str, Any],
    strict_types: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Validate response matches expected schema structure.

    Supports both simple schemas and full Pydantic JSON schemas.

    Args:
        response_json: Parsed JSON response from LLM
        expected_schema: Dict defining expected structure
        strict_types: If True, validate field types match schema

    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []
    is_pydantic_schema = "type" in expected_schema and "properties" in expected_schema

    if is_pydantic_schema:
        required_fields = set(expected_schema.get("required", []))
        properties = expected_schema.get("properties", {})
        expected_type = expected_schema.get("type")

        if expected_type == "object":
            if not isinstance(response_json, dict):
                errors.append(
                    f"Response should be object, got {type(response_json).__name__}"
                )
                return False, errors
        elif expected_type == "array":
            if not isinstance(response_json, list):
                errors.append(
                    f"Response should be array, got {type(response_json).__name__}"
                )
                return False, errors

        if expected_type == "object" and isinstance(response_json, dict):
            for field_name in required_fields:
                if field_name not in response_json:
                    errors.append(f"Missing required field: {field_name}")

            for field_name, value in response_json.items():
                if field_name not in properties:
                    continue
                field_schema = properties[field_name]
                is_optional = (
                    "anyOf" in field_schema
                    or "default" in field_schema
                    or field_name not in required_fields
                )
                if value is None:
                    if not is_optional:
                        errors.append(
                            f"Field '{field_name}' is required but got null"
                        )
                    continue
                if strict_types:
                    field_errors = _validate_field_type(field_name, value, field_schema)
                    errors.extend(field_errors)

        return len(errors) == 0, errors

    # Legacy simple schema validation
    if expected_schema.get("type") == "array":
        if not isinstance(response_json, list):
            errors.append(
                f"Response should be array, got {type(response_json).__name__}"
            )
            return False, errors
        min_items = expected_schema.get("min_items", 0)
        if len(response_json) < min_items:
            errors.append(
                f"Array has {len(response_json)} items, minimum is {min_items}"
            )
        items_schema = expected_schema.get("items")
        if items_schema and strict_types:
            for i, item in enumerate(response_json):
                if items_schema.get("type") == "object":
                    if not isinstance(item, dict):
                        errors.append(
                            f"Array item {i} should be object, got {type(item).__name__}"
                        )
                        continue
                    properties = items_schema.get("properties", {})
                    for prop_name, prop_config in properties.items():
                        if prop_name not in item:
                            errors.append(
                                f"Array item {i} missing property: {prop_name}"
                            )
                            continue
                        if prop_config.get("type") == "object":
                            nested_props = prop_config.get("properties", {})
                            if nested_props:
                                for nested_name in nested_props:
                                    if nested_name not in item[prop_name]:
                                        errors.append(
                                            f"Array item {i}.{prop_name} missing property: {nested_name}"
                                        )
        return len(errors) == 0, errors

    if not isinstance(response_json, dict):
        errors.append("Response is not a JSON object")
        return False, errors

    for field_name, field_config in expected_schema.items():
        if field_name not in response_json:
            errors.append(f"Missing required field: {field_name}")
            continue
        value = response_json[field_name]
        if value is None or value == "":
            errors.append(f"Field '{field_name}' is empty")
            continue
        expected_type = (
            field_config.get("type") if isinstance(field_config, dict) else None
        )
        if strict_types and expected_type:
            if expected_type == "object":
                if not isinstance(value, dict):
                    errors.append(
                        f"Field '{field_name}' should be object, got {type(value).__name__}"
                    )
                    continue
                nested_schema = field_config.get("fields", {})
                if nested_schema:
                    is_valid, nested_errors = validate_structured_output(
                        value, nested_schema, strict_types
                    )
                    if not is_valid:
                        errors.extend([f"{field_name}.{e}" for e in nested_errors])
            elif expected_type == "array":
                if not isinstance(value, list):
                    errors.append(
                        f"Field '{field_name}' should be array, got {type(value).__name__}"
                    )
                    continue
                min_items = field_config.get("min_items", 0)
                if len(value) < min_items:
                    errors.append(
                        f"Field '{field_name}' has {len(value)} items, minimum is {min_items}"
                    )
            else:
                if not validate_field_value(value, expected_type):
                    errors.append(
                        f"Field '{field_name}' type mismatch: expected {expected_type}, "
                        f"got {type(value).__name__}"
                    )

    return len(errors) == 0, errors


def check_not_found_response(
    response_text: str, not_found_indicators: List[str]
) -> bool:
    """Check if LLM response indicates it couldn't find the requested information."""
    if not not_found_indicators or not response_text:
        return False
    response_lower = response_text.lower()
    return any(indicator.lower() in response_lower for indicator in not_found_indicators)


def extract_retry_delay_from_error(error: Exception) -> Optional[float]:
    """Extract retry delay from a rate limit error."""
    error_str = str(error)
    match = re.search(r"Please retry in ([\d.]+)s", error_str)
    if match:
        return float(match.group(1))
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", error_str)
    if match:
        return float(match.group(1))
    return None


def strip_number_prefix(text: str) -> str:
    """Strip leading number and dot/parenthesis from text."""
    text = str(text).strip()
    return re.sub(r"^\d+[\.\)\-\s]+", "", text).strip()


def validate_array_response(
    response_json: Dict[str, Any],
    config: ArrayValidationConfig,
    attempt: int,
) -> Tuple[bool, List[str]]:
    """
    Validate that an LLM array response matches the input array.

    Validates length, order, and original values.

    Args:
        response_json: Parsed JSON response from LLM
        config: Array validation configuration
        attempt: Current attempt number

    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []
    response_array = None
    for value in response_json.values():
        if isinstance(value, list) and len(value) > 0:
            if isinstance(value[0], dict) and config.match_field in value[0]:
                response_array = value
                break

    if response_array is None:
        return False, [
            f"No array found in response with match_field '{config.match_field}'"
        ]

    input_array = config.input_array
    if config.filter_empty_inputs:
        non_empty_items = []
        for item in input_array:
            item_str = str(item).strip()
            if item_str:
                non_empty_items.append(item)
        if len(non_empty_items) != len(input_array):
            input_array = non_empty_items

    if len(response_array) != len(input_array):
        return False, [
            f"Length mismatch: got {len(response_array)} items, expected {len(input_array)}"
        ]

    if config.allow_reordering:
        match_field_map = {}
        for i, item in enumerate(response_array):
            if isinstance(item, dict) and config.match_field in item:
                match_value = str(item[config.match_field])
                if config.strip_number_prefix:
                    match_value = strip_number_prefix(match_value)
                match_field_map[match_value] = i

        reordered = [None] * len(input_array)
        for i, expected in enumerate(input_array):
            expected_str = str(expected)
            if config.strip_number_prefix:
                expected_str = strip_number_prefix(expected_str)
            if expected_str in match_field_map:
                llm_idx = match_field_map[expected_str]
                reordered[i] = response_array[llm_idx]
            else:
                errors.append(f"Could not find match for input item '{expected}'")

        if None not in reordered and not errors:
            logger.info("  [OK] Array reordered successfully")
            for key, value in response_json.items():
                if isinstance(value, list) and value == response_array:
                    response_json[key] = reordered
                    break
            return True, []

    for i, (expected, actual) in enumerate(zip(input_array, response_array)):
        expected_str = str(expected)
        if isinstance(actual, dict) and config.match_field in actual:
            actual_str = str(actual[config.match_field])
        else:
            actual_str = str(actual)
        if config.strip_number_prefix:
            expected_str = strip_number_prefix(expected_str)
            actual_str = strip_number_prefix(actual_str)
        if expected_str != actual_str:
            errors.append(f"Position {i+1}: expected '{expected}', got '{actual_str}'")

    if errors:
        return False, errors[:5]
    return True, []


__all__ = [
    "validate_structured_output",
    "validate_array_response",
    "validate_field_value",
    "check_not_found_response",
    "extract_retry_delay_from_error",
    "strip_number_prefix",
]
