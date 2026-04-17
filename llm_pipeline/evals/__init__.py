"""Evaluation system public API."""
from llm_pipeline.evals.delta import (
    apply_instruction_delta,
    merge_variable_definitions,
)

__all__ = ["apply_instruction_delta", "merge_variable_definitions"]
