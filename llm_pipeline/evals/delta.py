"""Backwards-compat shim — canonical home is :mod:`llm_pipeline.evals.variants`.

Phase 3 of the pydantic-evals migration deletes this module entirely
along with the legacy ``ui/routes/evals.py`` route handler. Until
then, this shim keeps the existing route handler working while new
code imports from ``variants`` directly.
"""
from llm_pipeline.evals.variants import (
    apply_instruction_delta,
    get_type_whitelist,
    merge_variable_definitions,
)

__all__ = [
    "apply_instruction_delta",
    "merge_variable_definitions",
    "get_type_whitelist",
]
