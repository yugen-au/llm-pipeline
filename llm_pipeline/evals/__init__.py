"""Evaluation system public API.

Phase 1 of the pydantic-evals migration: ``Variant`` + delta machinery
+ Phoenix datasets/experiments client. Runner / evaluators / acceptance
helpers land in Phases 2 and 3.
"""
from llm_pipeline.evals.phoenix_client import (
    DatasetNotFoundError,
    ExperimentNotFoundError,
    PhoenixDatasetClient,
    PhoenixDatasetError,
    PhoenixDatasetNotConfiguredError,
    PhoenixDatasetUnavailableError,
)
from llm_pipeline.evals.variants import (
    DeltaOp,
    Variant,
    apply_instruction_delta,
    get_type_whitelist,
    merge_variable_definitions,
)

__all__ = [
    "Variant",
    "DeltaOp",
    "apply_instruction_delta",
    "merge_variable_definitions",
    "get_type_whitelist",
    "PhoenixDatasetClient",
    "PhoenixDatasetError",
    "PhoenixDatasetNotConfiguredError",
    "PhoenixDatasetUnavailableError",
    "DatasetNotFoundError",
    "ExperimentNotFoundError",
]
