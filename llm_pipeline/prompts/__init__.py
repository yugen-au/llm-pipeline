"""Prompt management: Phoenix-backed service + auto_generate registry."""

from llm_pipeline.prompts.service import PromptService
from llm_pipeline.prompts.utils import extract_variables_from_content
from llm_pipeline.prompts.variables import (
    build_auto_generate_factory,
    clear_auto_generate_registry,
    register_auto_generate,
    set_auto_generate_base_path,
)
from llm_pipeline.utils.versioning import compare_versions

__all__ = [
    "PromptService",
    "extract_variables_from_content",
    "register_auto_generate",
    "set_auto_generate_base_path",
    "clear_auto_generate_registry",
    "build_auto_generate_factory",
    "compare_versions",
]
