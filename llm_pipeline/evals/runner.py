"""Eval runner: drive a Phoenix dataset through ``pydantic-evals``.

The flow:

1. Fetch the dataset metadata + examples from Phoenix.
2. Inspect ``dataset.metadata.target_type`` (``step`` or ``pipeline``)
   + ``target_name`` to decide which task wrapper to build.
3. Compose ``pydantic_evals.Dataset`` from the Phoenix examples,
   attaching auto evaluators (per INSTRUCTIONS field) plus any custom
   evaluators a case's metadata names.
4. ``await dataset.evaluate(task)`` — concurrent execution.
5. Post a Phoenix experiment + per-case runs + evaluation scores so
   the UI's experiment view stays the source of truth.
6. Return the :class:`EvaluationReport` so callers can bind it
   directly into their own UI / logs.

Pipelines are looked up via the user-supplied ``pipeline_registry``
(matching the rest of the framework's plumbing). Steps are resolved
by class name on ``pipeline_cls.nodes``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic_evals import Case, Dataset

from llm_pipeline.evals.evaluators import build_case_evaluators
from llm_pipeline.evals.phoenix_client import PhoenixDatasetClient
from llm_pipeline.evals.runtime import build_pipeline_task, build_step_task
from llm_pipeline.evals.variants import Variant

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from llm_pipeline.graph.nodes import LLMStepNode
    from llm_pipeline.graph.pipeline import Pipeline
    from pydantic_evals.reporting import EvaluationReport


__all__ = [
    "run_dataset",
    "create_experiment_record",
    "EvalTargetError",
]


logger = logging.getLogger(__name__)


class EvalTargetError(ValueError):
    """Dataset metadata's target_type / target_name doesn't resolve."""


async def run_dataset(
    dataset_id: str,
    variant: Variant,
    *,
    pipeline_registry: dict[str, type["Pipeline"]],
    model: str,
    engine: "Engine",
    run_name: str | None = None,
    max_concurrency: int | None = None,
    client: PhoenixDatasetClient | None = None,
    experiment_id: str | None = None,
) -> "EvaluationReport":
    """Run ``dataset_id`` end-to-end and post results to Phoenix.

    Args:
        dataset_id: Phoenix dataset identifier.
        variant: ``Variant()`` overrides for this run; baseline uses
            production settings (``Variant()`` with no fields set).
        pipeline_registry: ``pipeline_name -> Pipeline subclass`` map.
            Same shape the UI uses; the runner resolves the dataset's
            ``target_name`` against it.
        model: Production model string (used when ``variant.model`` is
            ``None``).
        engine: SQLAlchemy engine the per-case sessions open against.
            Use a per-eval in-memory SQLite engine to keep DB writes
            scoped to the run.
        run_name: Phoenix experiment name. Defaults to a
            ``{variant_summary}-{timestamp}`` string.
        max_concurrency: Forwarded to ``Dataset.evaluate``.
        client: Optional pre-built Phoenix client (tests inject a stub).
        experiment_id: Optional pre-existing Phoenix experiment id.
            When supplied (e.g. by the UI route after pre-creating the
            experiment so it can return the id immediately), skip the
            inner ``create_experiment`` call and post per-case runs +
            evaluations to the existing experiment. ``None`` keeps the
            legacy behaviour of creating an experiment after the report
            is built.
    """
    client = client or PhoenixDatasetClient()

    dataset_record = client.get_dataset(dataset_id)
    examples_payload = client.list_examples(dataset_id)
    examples = _normalise_examples(examples_payload)

    target_type, target_name = _resolve_target(dataset_record)
    pipeline_cls, step_cls = _resolve_pipeline_and_step(
        pipeline_registry=pipeline_registry,
        target_type=target_type,
        target_name=target_name,
    )

    if target_type == "step":
        task = build_step_task(
            pipeline_cls, step_cls, variant, model=model, engine=engine,
        )
        instructions_cls_for_evaluators = step_cls.INSTRUCTIONS
    else:  # pipeline
        task = build_pipeline_task(
            pipeline_cls, variant, model=model, engine=engine,
        )
        instructions_cls_for_evaluators = None

    cases = [
        _build_case(
            example,
            instructions_cls=instructions_cls_for_evaluators,
        )
        for example in examples
    ]

    eval_dataset: Dataset[Any, Any, Any] = Dataset(cases=cases)

    report = await eval_dataset.evaluate(
        task,
        name=run_name or _default_run_name(variant),
        max_concurrency=max_concurrency,
        progress=False,
    )

    _post_results_to_phoenix(
        client=client,
        dataset_id=dataset_id,
        variant=variant,
        target_type=target_type,
        target_name=target_name,
        report=report,
        examples=examples,
        experiment_id=experiment_id,
    )

    return report


def create_experiment_record(
    *,
    client: PhoenixDatasetClient,
    dataset_id: str,
    variant: Variant,
    target_type: str,
    target_name: str,
    run_name: str | None = None,
) -> dict[str, Any]:
    """Create a Phoenix experiment row up-front so the UI can navigate immediately.

    The UI route uses this before backgrounding the per-case loop:
    pre-create the experiment, return its id to the client, then spawn
    a background task that calls :func:`run_dataset` with the same
    ``experiment_id`` so we don't create a duplicate experiment.

    Returns the Phoenix experiment record (with ``id``); the caller
    threads the id through to ``run_dataset(..., experiment_id=...)``.
    """
    return client.create_experiment(
        dataset_id,
        name=run_name or _default_run_name(variant),
        metadata={
            "variant": variant.model_dump(),
            "target_type": target_type,
            "target_name": target_name,
        },
    )


# ---------------------------------------------------------------------------
# Phoenix payload normalisation
# ---------------------------------------------------------------------------


def _normalise_examples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Coerce Phoenix's ``list_examples`` payload to the runner's case shape.

    Phoenix's ``GET /v1/datasets/{id}/examples`` returns
    ``{"data": {"examples": [...]}}`` (or similar — the wrapper
    accommodates both flat and nested layouts that have shipped over
    the project's lifetime).
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        examples = data.get("examples") or data.get("items") or []
    elif isinstance(data, list):
        examples = data
    else:
        examples = payload.get("examples") if isinstance(payload, dict) else []
    return list(examples or [])


def _resolve_target(dataset_record: dict[str, Any]) -> tuple[str, str]:
    """Read ``target_type`` and ``target_name`` from dataset metadata."""
    metadata = (dataset_record or {}).get("metadata") or {}
    target_type = metadata.get("target_type")
    target_name = metadata.get("target_name")
    if target_type not in {"step", "pipeline"}:
        raise EvalTargetError(
            f"dataset metadata.target_type must be 'step' or 'pipeline'; "
            f"got {target_type!r}.",
        )
    if not isinstance(target_name, str) or not target_name:
        raise EvalTargetError(
            f"dataset metadata.target_name must be a non-empty string; "
            f"got {target_name!r}.",
        )
    return target_type, target_name


def _resolve_pipeline_and_step(
    *,
    pipeline_registry: dict[str, type["Pipeline"]],
    target_type: str,
    target_name: str,
) -> tuple[type["Pipeline"], type["LLMStepNode"] | None]:
    """Walk the pipeline registry to find the target."""
    if target_type == "pipeline":
        pipeline_cls = pipeline_registry.get(target_name)
        if pipeline_cls is None:
            raise EvalTargetError(
                f"pipeline {target_name!r} not in registry. "
                f"Available: {sorted(pipeline_registry)}",
            )
        return pipeline_cls, None

    # target_type == "step": target_name is the step class name. We
    # locate the owning pipeline by scanning registry entries — usually
    # exactly one match; ambiguity is a registration bug callers should
    # see surfaced.
    matches: list[tuple[type["Pipeline"], type]] = []
    for pipeline_cls in pipeline_registry.values():
        for node_cls in pipeline_cls.nodes:
            if node_cls.__name__ == target_name:
                matches.append((pipeline_cls, node_cls))
    if not matches:
        raise EvalTargetError(
            f"step {target_name!r} not found in any registered pipeline. "
            f"Registered pipelines: {sorted(pipeline_registry)}",
        )
    if len(matches) > 1:
        owners = sorted({p.__name__ for p, _ in matches})
        raise EvalTargetError(
            f"step {target_name!r} appears in multiple pipelines: {owners}. "
            f"Disambiguate by giving the step a unique class name.",
        )
    return matches[0]


def _build_case(
    example: dict[str, Any],
    *,
    instructions_cls: type | None,
) -> Case[Any, Any, Any]:
    """Translate a Phoenix example record to a ``pydantic-evals`` Case."""
    custom_names = (example.get("metadata") or {}).get("evaluators") or []
    evaluators = tuple(
        build_case_evaluators(instructions_cls, list(custom_names)),
    )
    return Case(
        name=example.get("id") or example.get("name"),
        inputs=example.get("input") or example.get("inputs") or {},
        expected_output=example.get("output") or example.get("expected_output"),
        metadata=example.get("metadata") or None,
        evaluators=evaluators,
    )


# ---------------------------------------------------------------------------
# Phoenix write-back
# ---------------------------------------------------------------------------


def _post_results_to_phoenix(
    *,
    client: PhoenixDatasetClient,
    dataset_id: str,
    variant: Variant,
    target_type: str,
    target_name: str,
    report: "EvaluationReport",
    examples: list[dict[str, Any]],
    experiment_id: str | None = None,
) -> None:
    """Create an experiment (if not pre-supplied), then post per-case runs + scores."""
    if experiment_id is None:
        experiment = client.create_experiment(
            dataset_id,
            name=report.name,
            metadata={
                "variant": variant.model_dump(),
                "target_type": target_type,
                "target_name": target_name,
                # Full report as a backup for fields we don't map onto
                # Phoenix's structured evaluation surface (failures,
                # analyses, etc.).
                "full_report": _safe_dump_report(report),
            },
        )
        experiment_id = experiment.get("id") or experiment.get("experiment_id")
        if not experiment_id:
            logger.warning(
                "Phoenix create_experiment returned no id; "
                "skipping per-case write-back. payload=%r",
                experiment,
            )
            return

    name_to_id = {
        ex.get("id") or ex.get("name"): ex.get("id")
        for ex in examples
    }

    for case in report.cases:
        example_id = name_to_id.get(case.name)
        if example_id is None:
            logger.warning(
                "Could not match report case %r to a dataset example id; "
                "skipping run record.",
                case.name,
            )
            continue

        try:
            run = client.record_run(
                experiment_id,
                dataset_example_id=example_id,
                output=_dump_output(case.output),
                start_time=_iso_now(),
                end_time=_iso_now(),
            )
        except Exception:
            logger.exception("Phoenix record_run failed for case=%r", case.name)
            continue

        run_id = run.get("id") or run.get("run_id")
        if not run_id:
            continue

        for label, result in (case.assertions or {}).items():
            _attach_evaluation(
                client, experiment_id, run_id,
                name=label,
                score=1.0 if result.value else 0.0,
                label="match" if result.value else "no_match",
                explanation=str(result.reason) if getattr(result, "reason", None) else None,
            )
        for label, result in (case.scores or {}).items():
            _attach_evaluation(
                client, experiment_id, run_id,
                name=label, score=float(result.value),
            )
        for label, result in (case.labels or {}).items():
            _attach_evaluation(
                client, experiment_id, run_id,
                name=label, label=str(result.value),
            )


def _attach_evaluation(
    client: PhoenixDatasetClient,
    experiment_id: str,
    run_id: str,
    **kwargs: Any,
) -> None:
    try:
        client.attach_evaluation(experiment_id, run_id, **kwargs)
    except Exception:
        logger.exception(
            "Phoenix attach_evaluation failed for run=%s name=%s",
            run_id, kwargs.get("name"),
        )


def _dump_output(output: Any) -> Any:
    if hasattr(output, "model_dump"):
        return output.model_dump(mode="json")
    return output


def _safe_dump_report(report: "EvaluationReport") -> dict[str, Any]:
    """Serialise the full report to a JSON-safe dict; swallows failures."""
    try:
        if hasattr(report, "model_dump"):
            return report.model_dump(mode="json")  # type: ignore[no-any-return]
    except Exception:
        logger.warning("EvaluationReport.model_dump failed; using minimal fallback.")
    return {"name": getattr(report, "name", None), "cases": len(report.cases)}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_run_name(variant: Variant) -> str:
    if variant.is_baseline():
        prefix = "baseline"
    else:
        prefix = "variant"
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
