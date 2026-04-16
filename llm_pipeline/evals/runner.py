"""Eval runner: executes pydantic-evals Dataset against pipeline steps/pipelines.

Builds pydantic-evals Dataset from DB cases, runs via evaluate_sync(),
persists results back to EvaluationRun + EvaluationCaseResult rows.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Type

from sqlalchemy import Engine
from sqlmodel import Session, select

from llm_pipeline.evals.models import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationRun,
)

logger = logging.getLogger(__name__)


class EvalRunner:
    """Orchestrates evaluation runs against registered pipelines/steps.

    Args:
        engine: SQLAlchemy engine for DB access.
        pipeline_registry: {name: factory_callable} from app.state.
        introspection_registry: {name: PipelineConfig class} from app.state.
    """

    def __init__(
        self,
        engine: Engine,
        pipeline_registry: dict[str, Callable] | None = None,
        introspection_registry: dict[str, Type] | None = None,
    ):
        self.engine = engine
        self.pipeline_registry = pipeline_registry or {}
        self.introspection_registry = introspection_registry or {}

    def run_dataset(self, dataset_id: int, model: str | None = None) -> int:
        """Run all cases in a dataset, persist results. Returns EvaluationRun.id."""
        from pydantic_evals import Case, Dataset

        # Load dataset + cases
        with Session(self.engine) as session:
            dataset = session.exec(
                select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
            ).first()
            if dataset is None:
                raise ValueError(f"Dataset {dataset_id} not found")

            cases = session.exec(
                select(EvaluationCase)
                .where(EvaluationCase.dataset_id == dataset_id)
                .order_by(EvaluationCase.id)
            ).all()

            if not cases:
                raise ValueError(f"Dataset '{dataset.name}' has no cases")

            # Create run row
            run = EvaluationRun(
                dataset_id=dataset_id,
                status="running",
                total_cases=len(cases),
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

            # Snapshot values needed outside session
            ds_name = dataset.name
            ds_target_type = dataset.target_type
            ds_target_name = dataset.target_name
            case_rows = [
                {
                    "id": c.id,
                    "name": c.name,
                    "inputs": c.inputs,
                    "expected_output": c.expected_output,
                    "metadata_": c.metadata_,
                }
                for c in cases
            ]

        try:
            # Resolve task_fn and evaluators
            task_fn, evaluators = self._resolve_task(
                ds_target_type, ds_target_name, model
            )

            # Build pydantic-evals Dataset
            pe_cases = []
            for cr in case_rows:
                pe_case = Case(
                    name=cr["name"],
                    inputs=cr["inputs"],
                    expected_output=cr["expected_output"],
                    metadata=cr["metadata_"],
                    evaluators=tuple(evaluators) if evaluators else (),
                )
                pe_cases.append(pe_case)

            pe_dataset = Dataset(cases=pe_cases)
            report = pe_dataset.evaluate_sync(task_fn, name=ds_name, progress=False)

            # Map case names to DB case ids
            name_to_id = {cr["name"]: cr["id"] for cr in case_rows}

            # Process results
            passed = 0
            failed = 0
            errored = 0
            case_results: list[EvaluationCaseResult] = []

            for case_result in report.cases:
                # Determine pass/fail from assertions
                assertions = case_result.assertions or {}
                if assertions:
                    case_passed = all(a.value for a in assertions.values())
                else:
                    # No assertions = pass (no evaluators triggered)
                    case_passed = True

                if case_passed:
                    passed += 1
                else:
                    failed += 1

                # Build evaluator scores dict
                scores: dict[str, Any] = {}
                for aname, aval in assertions.items():
                    scores[aname] = {
                        "value": aval.value,
                        "reason": aval.reason,
                    }
                for mname, mval in (case_result.metrics or {}).items():
                    scores[mname] = {"value": mval}

                # Serialize output
                output_data = None
                if case_result.output is not None:
                    if hasattr(case_result.output, "model_dump"):
                        output_data = case_result.output.model_dump()
                    elif isinstance(case_result.output, dict):
                        output_data = case_result.output
                    else:
                        output_data = {"_raw": str(case_result.output)}

                case_db_id = name_to_id.get(case_result.name, 0)
                case_results.append(
                    EvaluationCaseResult(
                        run_id=run_id,
                        case_id=case_db_id,
                        case_name=case_result.name,
                        passed=case_passed,
                        evaluator_scores=scores,
                        output_data=output_data,
                    )
                )

            # Process failures (task_fn errors — pydantic-evals puts these in report.failures, not report.cases)
            for failure in getattr(report, "failures", []):
                errored += 1
                case_db_id = name_to_id.get(failure.name, 0)
                error_msg = getattr(failure, "error_message", None) or str(failure)
                logger.error(
                    "Eval case '%s' errored: %s", failure.name, error_msg,
                )
                case_results.append(
                    EvaluationCaseResult(
                        run_id=run_id,
                        case_id=case_db_id,
                        case_name=failure.name,
                        passed=False,
                        evaluator_scores={},
                        output_data=None,
                        error_message=error_msg,
                    )
                )

            # Serialize report_data
            report_data: dict[str, Any] = {}
            try:
                import json
                report_data = json.loads(report.model_dump_json())
            except Exception:
                # Fallback: store summary only
                report_data = {
                    "total": len(case_rows),
                    "passed": passed,
                    "failed": failed,
                    "errored": errored,
                }

            # Persist results
            with Session(self.engine) as session:
                for cr in case_results:
                    session.add(cr)

                db_run = session.exec(
                    select(EvaluationRun).where(EvaluationRun.id == run_id)
                ).first()
                if db_run:
                    db_run.status = "completed"
                    db_run.passed = passed
                    db_run.failed = failed
                    db_run.errored = errored
                    db_run.report_data = report_data
                    db_run.completed_at = datetime.now(timezone.utc)
                session.commit()

        except Exception as exc:
            logger.error("Eval run %d failed: %s", run_id, exc, exc_info=True)
            with Session(self.engine) as session:
                db_run = session.exec(
                    select(EvaluationRun).where(EvaluationRun.id == run_id)
                ).first()
                if db_run:
                    db_run.status = "failed"
                    db_run.error_message = str(exc)
                    db_run.completed_at = datetime.now(timezone.utc)
                session.commit()
            raise

        return run_id

    def run_dataset_by_name(self, name: str, model: str | None = None) -> int:
        """Lookup dataset by name, delegate to run_dataset."""
        with Session(self.engine) as session:
            dataset = session.exec(
                select(EvaluationDataset).where(EvaluationDataset.name == name)
            ).first()
            if dataset is None:
                raise ValueError(f"Dataset '{name}' not found")
            dataset_id = dataset.id

        return self.run_dataset(dataset_id, model=model)

    # ------------------------------------------------------------------
    # Internal: resolve task function + evaluators from target
    # ------------------------------------------------------------------

    def _resolve_task(
        self,
        target_type: str,
        target_name: str,
        model: str | None,
    ) -> tuple[Callable, list | None]:
        """Return (task_fn, evaluators) for a given target.

        For target_type=step: finds step definition across all registered
        pipelines, builds a task_fn that runs just that step.

        For target_type=pipeline: finds pipeline factory, builds a task_fn
        that runs the full pipeline.
        """
        if target_type == "step":
            return self._resolve_step_task(target_name, model)
        elif target_type == "pipeline":
            return self._resolve_pipeline_task(target_name, model)
        else:
            raise ValueError(f"Unknown target_type: {target_type}")

    def _resolve_step_task(
        self, step_name: str, model: str | None
    ) -> tuple[Callable, list | None]:
        """Build task_fn for a single step evaluation."""
        step_def, input_data_cls, default_model = self._find_step_def(step_name)
        if step_def is None:
            raise ValueError(
                f"Step '{step_name}' not found in any registered pipeline"
            )

        step_model = model or default_model
        if not step_model:
            raise ValueError(
                f"No model configured for step '{step_name}'. "
                "Pass model= to run_dataset() or configure a default model."
            )

        evaluators = self._resolve_evaluators(step_def)
        task_fn = self._build_step_task_fn(step_def, input_data_cls, step_model)
        return task_fn, evaluators

    def _resolve_pipeline_task(
        self, pipeline_name: str, model: str | None
    ) -> tuple[Callable, list | None]:
        """Build task_fn for a full pipeline evaluation."""
        if pipeline_name not in self.pipeline_registry:
            raise ValueError(
                f"Pipeline '{pipeline_name}' not found in registry"
            )
        task_fn = self._build_pipeline_task_fn(pipeline_name, model)
        return task_fn, None  # no evaluators for pipeline-level (uses case-level)

    def _find_step_def(self, step_name: str) -> tuple[Optional[Any], Optional[Type], Optional[str]]:
        """Find StepDefinition + INPUT_DATA cls + default model for a step.

        Returns (step_def, input_data_cls, default_model) or (None, None, None).
        """
        for pipeline_name, pipeline_cls in self.introspection_registry.items():
            try:
                strategies_cls = pipeline_cls.STRATEGIES
                if strategies_cls is None:
                    continue
                for strategy_cls in strategies_cls.STRATEGIES:
                    strategy = strategy_cls()
                    for sd in strategy.get_steps():
                        if sd.step_name == step_name:
                            input_data_cls = getattr(pipeline_cls, "INPUT_DATA", None)
                            default_model = getattr(pipeline_cls, "_default_model", None)
                            return sd, input_data_cls, default_model
            except Exception:
                logger.debug(
                    "Failed to introspect '%s' for step '%s'",
                    pipeline_name, step_name, exc_info=True,
                )
                continue
        return None, None, None

    def _resolve_evaluators(self, step_def: Any) -> list | None:
        """Get evaluators from step_def or auto-generate from instructions."""
        from llm_pipeline.evals.evaluators import build_auto_evaluators

        if step_def.evaluators:
            # Instantiate evaluator classes
            result = []
            for ev in step_def.evaluators:
                if isinstance(ev, type):
                    result.append(ev())
                else:
                    result.append(ev)
            return result

        # Auto-generate from instructions fields
        if step_def.instructions is not None:
            auto = build_auto_evaluators(step_def.instructions)
            if auto:
                return auto

        return None

    def _build_step_task_fn(
        self, step_def: Any, input_data_cls: Optional[Type], step_model: str,
    ) -> Callable:
        """Return callable(inputs) -> output for single step execution.

        Uses sandbox pipeline so the step runs through the identical
        execution path as production (prompt rendering, model resolution, etc).
        """
        prod_engine = self.engine

        def task_fn(inputs: dict) -> Any:
            from llm_pipeline.sandbox import create_single_step_pipeline

            pipeline = create_single_step_pipeline(
                step_def=step_def,
                input_data_cls=input_data_cls,
                prod_engine=prod_engine,
                model=step_model,
                run_id="eval",
            )

            try:
                pipeline.execute(input_data=inputs)
                output = pipeline.instructions.get(step_def.step_name)
                if output and isinstance(output, list) and len(output) == 1:
                    return output[0]
                return output
            finally:
                try:
                    pipeline.close()
                except Exception:
                    pass

        return task_fn

    def _build_pipeline_task_fn(
        self, pipeline_name: str, model: str | None
    ) -> Callable:
        """Return callable(inputs) -> dict[step_name, output] for full pipeline."""
        factory = self.pipeline_registry[pipeline_name]
        prod_engine = self.engine

        def task_fn(inputs: dict) -> dict:
            from llm_pipeline.sandbox import create_sandbox_from_factory

            pipeline = create_sandbox_from_factory(
                factory=factory,
                prod_engine=prod_engine,
                model=model,
                run_id="eval",
            )

            try:
                pipeline.execute(input_data=inputs)

                outputs: dict[str, Any] = {}
                for key, val in pipeline._instructions.items():
                    if hasattr(val, "model_dump"):
                        outputs[key] = val.model_dump()
                    elif isinstance(val, dict):
                        outputs[key] = val
                    else:
                        outputs[key] = str(val)
                return outputs
            finally:
                try:
                    pipeline.close()
                except Exception:
                    pass

        return task_fn


__all__ = ["EvalRunner"]
