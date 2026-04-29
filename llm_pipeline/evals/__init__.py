"""Evaluation system public API.

Phase 3 of the pydantic-evals migration: Phoenix is the source of
truth for datasets/examples/experiments/runs/case results, the
framework keeps only the ``EvaluationAcceptance`` audit table,
and ``accept_experiment`` walks variant deltas across the three
production surfaces (``StepModelConfig`` / Phoenix prompt /
INSTRUCTIONS source files).
"""
from llm_pipeline.evals.acceptance import AcceptanceError, accept_experiment
from llm_pipeline.evals.evaluators import (
    FieldMatchEvaluator,
    build_auto_evaluators,
    build_case_evaluators,
    clear_evaluator_registry,
    get_evaluator,
    list_evaluators,
    register_evaluator,
)
from llm_pipeline.evals.phoenix_client import (
    DatasetNotFoundError,
    ExperimentNotFoundError,
    PhoenixDatasetClient,
    PhoenixDatasetError,
    PhoenixDatasetNotConfiguredError,
    PhoenixDatasetUnavailableError,
)
from llm_pipeline.evals.runner import EvalTargetError, run_dataset
from llm_pipeline.evals.runtime import build_pipeline_task, build_step_task
from llm_pipeline.evals.variants import (
    DeltaOp,
    Variant,
    apply_instruction_delta,
    get_type_whitelist,
    merge_variable_definitions,
)

__all__ = [
    # variants + delta
    "Variant",
    "DeltaOp",
    "apply_instruction_delta",
    "merge_variable_definitions",
    "get_type_whitelist",
    # evaluators
    "FieldMatchEvaluator",
    "build_auto_evaluators",
    "build_case_evaluators",
    "register_evaluator",
    "get_evaluator",
    "list_evaluators",
    "clear_evaluator_registry",
    # task wrappers
    "build_step_task",
    "build_pipeline_task",
    # runner
    "run_dataset",
    "EvalTargetError",
    # acceptance
    "accept_experiment",
    "AcceptanceError",
    # phoenix client
    "PhoenixDatasetClient",
    "PhoenixDatasetError",
    "PhoenixDatasetNotConfiguredError",
    "PhoenixDatasetUnavailableError",
    "DatasetNotFoundError",
    "ExperimentNotFoundError",
]
