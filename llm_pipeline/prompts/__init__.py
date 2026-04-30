"""Prompt management: Phoenix-backed service + PromptVariables + auto_generate."""

from llm_pipeline.prompts.discovery import discover_prompt_variables
from llm_pipeline.prompts.service import PromptService
from llm_pipeline.prompts.utils import extract_variables_from_content
from llm_pipeline.prompts.variables import (
    PromptVariables,
    build_auto_generate_factory,
    clear_auto_generate_registry,
    clear_prompt_variables_registry,
    get_all_prompt_variables,
    get_prompt_variables,
    register_auto_generate,
    register_prompt_variables,
    set_auto_generate_base_path,
)
from llm_pipeline.utils.versioning import compare_versions

__all__ = [
    "PromptService",
    "PromptVariables",
    "build_auto_generate_factory",
    "clear_auto_generate_registry",
    "clear_prompt_variables_registry",
    "compare_versions",
    "discover_prompt_variables",
    "extract_variables_from_content",
    "get_all_prompt_variables",
    "get_prompt_variables",
    "register_auto_generate",
    "register_prompt_variables",
    "set_auto_generate_base_path",
]
