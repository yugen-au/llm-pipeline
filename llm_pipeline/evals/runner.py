"""Eval runner: executes pydantic-evals Dataset against pipeline steps/pipelines.

Builds pydantic-evals Dataset from DB cases, runs via evaluate_sync(),
persists results back to EvaluationRun + EvaluationCaseResult rows.

Variants (v2): when a variant_id is passed, a frozen JSON delta is loaded
and applied to the step definition before evaluator resolution and sandbox
execution. See PLAN.md "Security Constraints" — delta data is JSON only,
no Python class objects cross the variant boundary, no host paths baked
into delta records (Docker-sandbox-readiness invariants).
"""
from __future__ import annotations

import copy
import dataclasses
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
    EvaluationVariant,
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

    def run_dataset(
        self,
        dataset_id: int,
        model: str | None = None,
        variant_id: int | None = None,
    ) -> int:
        """Run all cases in a dataset, persist results. Returns EvaluationRun.id.

        Args:
            dataset_id: target dataset.
            model: optional model override (applied only when no variant or when
                variant does not supply a model).
            variant_id: optional EvaluationVariant.id to apply delta overrides.
                Must belong to ``dataset_id`` — otherwise ValueError.
        """
        from pydantic_evals import Case, Dataset

        # Load dataset + cases + optional variant
        with Session(self.engine) as session:
            dataset = session.exec(
                select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
            ).first()
            if dataset is None:
                raise ValueError(f"Dataset {dataset_id} not found")

            variant_delta: dict | None = None
            variant_snapshot: dict | None = None
            if variant_id is not None:
                variant = session.exec(
                    select(EvaluationVariant).where(
                        EvaluationVariant.id == variant_id
                    )
                ).first()
                if variant is None:
                    raise ValueError(f"Variant {variant_id} not found")
                if variant.dataset_id != dataset_id:
                    raise ValueError(
                        f"Variant {variant_id} does not belong to dataset "
                        f"{dataset_id}"
                    )
                # Deep-copy so caller mutations to the ORM row cannot leak
                # through into runner logic or the persisted snapshot.
                variant_delta = copy.deepcopy(variant.delta) if variant.delta else {}
                variant_snapshot = copy.deepcopy(variant_delta)

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
                variant_id=variant_id,
                delta_snapshot=variant_snapshot,
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
                ds_target_type,
                ds_target_name,
                model,
                variant_delta=variant_delta,
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

    def run_dataset_by_name(
        self,
        name: str,
        model: str | None = None,
        variant_id: int | None = None,
    ) -> int:
        """Lookup dataset by name, delegate to run_dataset."""
        with Session(self.engine) as session:
            dataset = session.exec(
                select(EvaluationDataset).where(EvaluationDataset.name == name)
            ).first()
            if dataset is None:
                raise ValueError(f"Dataset '{name}' not found")
            dataset_id = dataset.id

        return self.run_dataset(dataset_id, model=model, variant_id=variant_id)

    # ------------------------------------------------------------------
    # Internal: resolve task function + evaluators from target
    # ------------------------------------------------------------------

    def _resolve_task(
        self,
        target_type: str,
        target_name: str,
        model: str | None,
        variant_delta: dict | None = None,
    ) -> tuple[Callable, list | None]:
        """Return (task_fn, evaluators) for a given target.

        For target_type=step: finds step definition across all registered
        pipelines, builds a task_fn that runs just that step.

        For target_type=pipeline: finds pipeline factory, builds a task_fn
        that runs the full pipeline.

        ``variant_delta`` (JSON-only) propagates through to _resolve_step_task
        and _build_step_task_fn when provided. Pipeline-target variant runs
        are not supported in v2 (variants are step-scoped).
        """
        if target_type == "step":
            return self._resolve_step_task(
                target_name, model, variant_delta=variant_delta
            )
        elif target_type == "pipeline":
            if variant_delta:
                logger.warning(
                    "variant_delta provided for pipeline target %r — ignored "
                    "(variants are step-scoped in v2)",
                    target_name,
                )
            return self._resolve_pipeline_task(target_name, model)
        else:
            raise ValueError(f"Unknown target_type: {target_type}")

    def _resolve_step_task(
        self,
        step_name: str,
        model: str | None,
        variant_delta: dict | None = None,
    ) -> tuple[Callable, list | None]:
        """Build task_fn for a single step evaluation.

        When ``variant_delta`` has ``instructions_delta``, the base
        instructions class is replaced with the delta-modified class BEFORE
        evaluator resolution so auto-evaluators cover variant-added fields.
        """
        from llm_pipeline.evals.delta import apply_instruction_delta

        step_def, input_data_cls, default_model = self._find_step_def(step_name)
        if step_def is None:
            raise ValueError(
                f"Step '{step_name}' not found in any registered pipeline"
            )

        # Apply instructions_delta first so evaluator resolution (and downstream
        # agent output_type wiring) see the modified schema. Reordering per
        # CEO decision — variant-added fields must be visible to auto-evaluator
        # generation.
        if variant_delta:
            instructions_delta = variant_delta.get("instructions_delta")
            if instructions_delta and step_def.instructions is not None:
                modified_cls = apply_instruction_delta(
                    step_def.instructions, instructions_delta
                )
                # dataclasses.replace returns a new StepDefinition instance —
                # never mutate the registered step_def (prod path must stay
                # pristine across concurrent eval runs).
                step_def = dataclasses.replace(step_def, instructions=modified_cls)

        # Variant model override takes precedence over `model` kwarg; then
        # step_def default.
        variant_model = None
        if variant_delta:
            vm = variant_delta.get("model")
            if isinstance(vm, str) and vm.strip():
                variant_model = vm
        step_model = variant_model or model or default_model
        if not step_model:
            raise ValueError(
                f"No model configured for step '{step_name}'. "
                "Pass model= to run_dataset() or configure a default model."
            )

        evaluators = self._resolve_evaluators(step_def)
        task_fn = self._build_step_task_fn(
            step_def, input_data_cls, step_model, variant_delta=variant_delta
        )
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
        self,
        step_def: Any,
        input_data_cls: Optional[Type],
        step_model: str,
        variant_delta: dict | None = None,
    ) -> Callable:
        """Return callable(inputs) -> output for single step execution.

        Uses sandbox pipeline so the step runs through the identical
        execution path as production (prompt rendering, model resolution, etc).

        When ``variant_delta`` is provided, the sandbox DB is patched AFTER
        ``create_sandbox_engine`` seeds it from prod:

        1. If ``variant_delta["system_prompt"]`` is set AND the step has a
           ``system_instruction_key``, the sandbox Prompt row for that key
           is updated with the variant content. Same for user_prompt_key +
           ``user_prompt``.
        2. ``variable_definitions`` on the sandbox Prompt rows are replaced
           with the merge of (prod defs, variant defs) where variant wins on
           name collision. Expressions are NOT evaluated here — registry-based
           resolution happens later at prompt render time.
        3. ``variant_delta["model"]`` upserts a StepModelConfig row for the
           sandbox pipeline (pipeline_name="sandbox"), overriding any default
           for this step.

        When ``system_instruction_key`` / ``user_prompt_key`` is None (prompt
        auto-discovery path on the step def), the corresponding override is
        skipped and a warning is logged — v2 limitation, documented in the
        variant editor UI.
        """
        prod_engine = self.engine
        # Snapshot variant payload as JSON-safe dict (deepcopy — pure data,
        # no Python class objects cross the sandbox boundary).
        delta_snapshot = copy.deepcopy(variant_delta) if variant_delta else None

        def task_fn(inputs: dict) -> Any:
            from llm_pipeline.sandbox import (
                create_sandbox_engine,
                create_single_step_pipeline,
            )

            # Build sandbox engine up-front so we can patch it before the
            # pipeline instantiates and loads prompts.
            sandbox_engine = create_sandbox_engine(prod_engine)

            if delta_snapshot:
                try:
                    _apply_variant_to_sandbox(
                        sandbox_engine=sandbox_engine,
                        step_def=step_def,
                        variant_delta=delta_snapshot,
                    )
                except Exception:  # pragma: no cover — defensive
                    logger.exception(
                        "Failed to apply variant delta to sandbox; "
                        "proceeding with un-patched sandbox"
                    )

            pipeline = create_single_step_pipeline(
                step_def=step_def,
                input_data_cls=input_data_cls,
                engine=sandbox_engine,
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


# ---------------------------------------------------------------------------
# Internal helper: apply variant delta to sandbox engine
# ---------------------------------------------------------------------------

def _apply_variant_to_sandbox(
    sandbox_engine: Engine,
    step_def: Any,
    variant_delta: dict,
) -> None:
    """Patch sandbox DB with variant prompt overrides, merged variable
    definitions, and a StepModelConfig row for the model override.

    Called after ``create_sandbox_engine`` has seeded the sandbox with a copy
    of production prompts + step configs. Mutates only the sandbox DB — prod
    is never touched.

    All inputs that cross into the sandbox layer are JSON-serialisable strings
    / lists / dicts (no host paths, no Python class objects). See PLAN.md
    Docker-sandbox-readiness invariants.
    """
    from llm_pipeline.db.prompt import Prompt
    from llm_pipeline.db.step_config import StepModelConfig

    system_key = getattr(step_def, "system_instruction_key", None)
    user_key = getattr(step_def, "user_prompt_key", None)
    system_content_override = variant_delta.get("system_prompt")
    user_content_override = variant_delta.get("user_prompt")
    variant_model = variant_delta.get("model")
    variant_var_defs = variant_delta.get("variable_definitions")

    # Step name (snake_case) for the StepModelConfig upsert.
    try:
        step_name = step_def.step_name
    except Exception:
        step_name = None

    with Session(sandbox_engine) as session:
        # --- Prompt overrides (system) ---------------------------------
        if system_key:
            prompt = session.exec(
                select(Prompt).where(
                    Prompt.prompt_key == system_key,
                    Prompt.prompt_type == "system",
                )
            ).first()
            if prompt is not None:
                _merge_variant_defs_into_prompt(
                    session,
                    prompt,
                    system_content_override,
                    variant_var_defs,
                )
            elif isinstance(system_content_override, str):
                logger.warning(
                    "variant system_prompt override: no Prompt row for key "
                    "%r in sandbox; override skipped",
                    system_key,
                )
        elif isinstance(system_content_override, str):
            logger.warning(
                "variant system_prompt override: step has no "
                "system_instruction_key (auto-discovery path); override "
                "skipped — v2 limitation"
            )

        # --- Prompt overrides (user) -----------------------------------
        if user_key:
            prompt = session.exec(
                select(Prompt).where(
                    Prompt.prompt_key == user_key,
                    Prompt.prompt_type == "user",
                )
            ).first()
            if prompt is not None:
                _merge_variant_defs_into_prompt(
                    session,
                    prompt,
                    user_content_override,
                    variant_var_defs,
                )
            elif isinstance(user_content_override, str):
                logger.warning(
                    "variant user_prompt override: no Prompt row for key "
                    "%r in sandbox; override skipped",
                    user_key,
                )
        elif isinstance(user_content_override, str):
            logger.warning(
                "variant user_prompt override: step has no user_prompt_key "
                "(auto-discovery path); override skipped — v2 limitation"
            )

        # --- StepModelConfig upsert ------------------------------------
        if isinstance(variant_model, str) and variant_model.strip() and step_name:
            existing = session.exec(
                select(StepModelConfig).where(
                    StepModelConfig.pipeline_name == "sandbox",
                    StepModelConfig.step_name == step_name,
                )
            ).first()
            if existing is not None:
                existing.model = variant_model
                session.add(existing)
            else:
                session.add(
                    StepModelConfig(
                        pipeline_name="sandbox",
                        step_name=step_name,
                        model=variant_model,
                    )
                )

        session.commit()


def _merge_variant_defs_into_prompt(
    session: Session,
    prompt: Any,
    content_override: Any,
    variant_var_defs: Any,
) -> None:
    """Merge variant variable_definitions into a sandbox Prompt row.

    Module-private helper shared by the system/user prompt branches of
    ``_apply_variant_to_sandbox``. Applies content override (if a string),
    merges ``variant_var_defs`` over existing ``prompt.variable_definitions``
    (variant wins on name conflict via ``merge_variable_definitions``),
    preserves the original column shape, and stages the row on the session.
    """
    from llm_pipeline.evals.delta import merge_variable_definitions

    if isinstance(content_override, str):
        prompt.content = content_override
    merged = merge_variable_definitions(
        _coerce_var_defs(prompt.variable_definitions),
        _coerce_var_defs(variant_var_defs),
    )
    prompt.variable_definitions = _encode_var_defs(
        prompt.variable_definitions, merged
    )
    session.add(prompt)


def _coerce_var_defs(raw: Any) -> list:
    """Normalise a Prompt.variable_definitions column value to a list-of-dicts.

    The column is typed as ``dict`` in the ORM but prompts in the wild store
    either a list or a {name: spec} dict. Returns [] for None/unexpected
    shapes so merge_variable_definitions can operate uniformly.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        out: list[dict] = []
        for name, spec in raw.items():
            if isinstance(spec, dict):
                # Inject name if the nested spec lacks it.
                entry = dict(spec)
                entry.setdefault("name", name)
                out.append(entry)
        return out
    return []


def _encode_var_defs(original: Any, merged: list) -> Any:
    """Preserve the original column shape (list-of-dicts vs {name: spec} dict)
    when writing merged definitions back.
    """
    if isinstance(original, dict):
        return {item["name"]: item for item in merged if "name" in item}
    return merged


__all__ = ["EvalRunner"]
