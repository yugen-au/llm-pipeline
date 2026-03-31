"""Prompt management: serving, variables, and utilities."""

from llm_pipeline.prompts.service import PromptService
from llm_pipeline.prompts.utils import extract_variables_from_content
from llm_pipeline.prompts.variables import (
    PromptVariables,
    VariableResolver,
    RegistryVariableResolver,
    register_prompt_variables,
    get_prompt_variables,
    get_code_prompt_variables,
    get_all_prompt_variables,
    clear_prompt_variables_registry,
    rebuild_from_db,
    register_auto_generate,
    set_auto_generate_base_path,
    clear_auto_generate_registry,
)
from llm_pipeline.prompts.yaml_sync import (
    compare_versions,
    parse_prompt_yaml,
    discover_yaml_prompts,
    sync_yaml_to_db,
    write_prompt_to_yaml,
)

__all__ = [
    "PromptService",
    "PromptVariables",
    "VariableResolver",
    "RegistryVariableResolver",
    "register_prompt_variables",
    "get_prompt_variables",
    "get_all_prompt_variables",
    "clear_prompt_variables_registry",
    "extract_variables_from_content",
    "register_auto_generate",
    "set_auto_generate_base_path",
    "clear_auto_generate_registry",
    "compare_versions",
    "parse_prompt_yaml",
    "discover_yaml_prompts",
    "sync_yaml_to_db",
    "write_prompt_to_yaml",
]
