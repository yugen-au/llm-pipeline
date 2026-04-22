"""Evaluation system endpoints - dataset and case CRUD."""
import logging
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy import func
from sqlmodel import select

from llm_pipeline.db.versioning import get_latest, save_new_version, soft_delete_latest
from llm_pipeline.evals import apply_instruction_delta, get_type_whitelist
from llm_pipeline.evals.models import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationRun,
    EvaluationVariant,
)
from llm_pipeline.ui.deps import DBSession, WritableDBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evals", tags=["evals"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class DatasetListItem(BaseModel):
    id: int
    name: str
    target_type: str
    target_name: str
    description: Optional[str] = None
    case_count: int
    last_run_pass_rate: Optional[float] = None
    created_at: str
    updated_at: str


class DatasetListResponse(BaseModel):
    items: List[DatasetListItem]
    total: int


class CaseItem(BaseModel):
    id: int
    name: str
    inputs: dict
    expected_output: Optional[dict] = None
    metadata_: Optional[dict] = None


class DatasetDetail(BaseModel):
    id: int
    name: str
    target_type: str
    target_name: str
    description: Optional[str] = None
    case_count: int
    last_run_pass_rate: Optional[float] = None
    created_at: str
    updated_at: str
    cases: List[CaseItem]


class DatasetCreateRequest(BaseModel):
    name: str
    target_type: Literal["step", "pipeline"]
    target_name: str
    description: Optional[str] = None


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CaseCreateRequest(BaseModel):
    name: str
    inputs: dict
    expected_output: Optional[dict] = None
    metadata_: Optional[dict] = None


class CaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    inputs: Optional[dict] = None
    expected_output: Optional[dict] = None


# ---------------------------------------------------------------------------
# Run response / request models
# ---------------------------------------------------------------------------


class CaseResultItem(BaseModel):
    id: int
    # case_id is None when the runner could not resolve the case name to a DB id
    # (see runner.py lines 222, 237: name_to_id.get(..., 0) sentinel). The ORM
    # column is non-null int; the route handler maps the 0 sentinel to None so
    # clients receive an explicit null instead of a magic 0.
    case_id: Optional[int] = None
    case_name: str
    passed: bool
    evaluator_scores: dict
    output_data: Optional[dict] = None
    error_message: Optional[str] = None


class RunListItem(BaseModel):
    id: int
    dataset_id: int
    status: str
    total_cases: int
    passed: int
    failed: int
    errored: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    variant_id: Optional[int] = None
    delta_snapshot: Optional[dict] = None
    case_versions: Optional[dict] = None
    prompt_versions: Optional[dict] = None
    model_snapshot: Optional[dict] = None
    instructions_schema_snapshot: Optional[dict] = None


class RunListResponse(BaseModel):
    items: List[RunListItem]


class RunDetail(RunListItem):
    case_results: List[CaseResultItem]


class TriggerRunRequest(BaseModel):
    model: Optional[str] = None
    variant_id: Optional[int] = None


class TriggerRunResponse(BaseModel):
    status: str


class SchemaResponse(BaseModel):
    target_type: str
    target_name: str
    json_schema: dict
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None


# ---------------------------------------------------------------------------
# Variant request / response models
# ---------------------------------------------------------------------------


class VariantItem(BaseModel):
    id: int
    dataset_id: int
    name: str
    description: Optional[str] = None
    delta: dict
    created_at: str
    updated_at: str


class VariantCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    delta: dict


class VariantUpdateRequest(BaseModel):
    # all optional — partial update via PUT
    name: Optional[str] = None
    description: Optional[str] = None
    delta: Optional[dict] = None


class VariantListResponse(BaseModel):
    items: List[VariantItem]
    total: int


class TypeWhitelistResponse(BaseModel):
    """Canonical list of allowed ``type_str`` values for instruction deltas.

    Served by ``GET /evals/delta-type-whitelist`` so the frontend variant
    editor can source the type dropdown from the backend — single source
    of truth, no drift with ``llm_pipeline.evals.delta._TYPE_WHITELIST``.
    """

    types: List[str]


class ProdPromptContent(BaseModel):
    """Resolved prod prompt payload surfaced to the variant editor."""

    prompt_key: str
    content: str
    variable_definitions: Optional[dict | list] = None
    version: Optional[str] = None


class ProdPromptsResponse(BaseModel):
    """Prod system + user prompts resolved for a dataset's step target.

    Either side may be ``null`` when the corresponding key is not declared
    (tier 1/2) and no matching active ``Prompt`` row exists (tier 3).
    """

    system: Optional[ProdPromptContent] = None
    user: Optional[ProdPromptContent] = None


class ProdModelResponse(BaseModel):
    """Resolved prod model for a dataset's step target.

    ``model`` is the effective string (e.g. ``openai:gpt-5``) after the
    three-tier resolution. ``source`` indicates which tier produced it:
    ``"db"`` (StepModelConfig override), ``"step_definition"``
    (step_def.model), ``"pipeline_default"`` (pipeline-level default),
    or ``"none"`` (no model configured at any tier — ``model`` is null).
    """

    model: Optional[str] = None
    source: str


# ---------------------------------------------------------------------------
# Variant helpers
# ---------------------------------------------------------------------------


def _variant_to_item(v: EvaluationVariant) -> VariantItem:
    return VariantItem(
        id=v.id,
        dataset_id=v.dataset_id,
        name=v.name,
        description=v.description,
        delta=v.delta or {},
        created_at=v.created_at.isoformat(),
        updated_at=v.updated_at.isoformat(),
    )


def _dry_run_validate_delta(delta: Optional[dict]) -> None:
    """Dry-run validation of a variant delta via apply_instruction_delta.

    Runs the same whitelist/field/op/type/default checks as runtime delta
    application to prevent persisting invalid deltas. Raises HTTPException
    422 if validation fails.

    Note: uses pydantic BaseModel as the dry-run base class since the real
    step_def.instructions is not known at variant-authoring time. The
    whitelist/field-name/length/op/type checks all fire regardless of base
    class, so ACE protection is complete. The only edge case uncovered at
    dry-run is `op=modify` of a field inherited from the real step_def's
    instructions without a type_str — that is only checkable against the
    actual base class at run-time and will surface as a ValueError when
    the runner executes.
    """
    if not delta:
        return
    instructions_delta = delta.get("instructions_delta")
    if not instructions_delta:
        return
    from pydantic import BaseModel as _DryRunBase

    try:
        apply_instruction_delta(_DryRunBase, instructions_delta)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trigger_evals_writeback(request: Request, dataset_id: int) -> None:
    """Fire DB -> YAML writeback for a dataset if evals_dir is configured."""
    from pathlib import Path
    from llm_pipeline.evals.yaml_sync import write_dataset_to_yaml

    evals_dir = getattr(request.app.state, "evals_dir", None)
    if evals_dir is None:
        return
    try:
        write_dataset_to_yaml(
            request.app.state.engine, dataset_id, Path(evals_dir)
        )
    except Exception:
        logger.warning(
            "Evals YAML writeback failed for dataset %d", dataset_id,
            exc_info=True,
        )


def _find_step_def_by_target(
    target_step: str, introspection_registry: dict
) -> tuple[Optional[Any], Optional[str], Optional[str]]:
    """Walk registered pipelines for a step_def matching ``target_step``.

    Returns ``(step_def, strategy_name, pipeline_name)`` — all ``None`` if
    no match. First-match semantics (registry insertion order) mirror
    ``EvalRunner._find_step_def``. ``strategy_name`` is surfaced for
    tier-3 prompt auto-discovery; ``pipeline_name`` feeds the tier-2
    model-resolver DB lookup.

    Extracted so prod-prompts and prod-model share one iteration —
    both endpoints need step_def + pipeline_name, and prod-prompts
    additionally needs strategy_name.
    """
    for pipeline_name, pipeline_cls in introspection_registry.items():
        strategies_cls = getattr(pipeline_cls, "STRATEGIES", None)
        if strategies_cls is None:
            continue
        strategy_classes = getattr(strategies_cls, "STRATEGIES", []) or []
        for strategy_cls in strategy_classes:
            try:
                strategy_inst = strategy_cls()
                for sd in strategy_inst.get_steps():
                    if sd.step_name == target_step:
                        return (
                            sd,
                            getattr(strategy_inst, "name", None),
                            pipeline_name,
                        )
            except Exception:
                logger.debug(
                    "Failed to introspect strategy %s for step '%s'",
                    strategy_cls.__name__, target_step, exc_info=True,
                )
                continue
    return None, None, None


def _last_run_pass_rate(db, dataset_id: int) -> Optional[float]:
    """Compute pass rate from the latest completed EvaluationRun for a dataset."""
    latest_run = db.exec(
        select(EvaluationRun)
        .where(EvaluationRun.dataset_id == dataset_id)
        .where(EvaluationRun.status == "completed")
        .order_by(EvaluationRun.started_at.desc())
        .limit(1)
    ).first()
    if latest_run is None or latest_run.total_cases == 0:
        return None
    return round(latest_run.passed / latest_run.total_cases, 4)


# ---------------------------------------------------------------------------
# Dataset endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    db: DBSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DatasetListResponse:
    """List evaluation datasets with case counts and last run pass rates."""
    # case count subquery (active + latest only)
    case_count_sq = (
        select(
            EvaluationCase.dataset_id,
            func.count(EvaluationCase.id).label("case_count"),
        )
        .where(
            EvaluationCase.is_active == True,  # noqa: E712
            EvaluationCase.is_latest == True,  # noqa: E712
        )
        .group_by(EvaluationCase.dataset_id)
        .subquery()
    )

    # pass rate subquery: latest completed run per dataset
    latest_run_sq = (
        select(
            EvaluationRun.dataset_id,
            func.max(EvaluationRun.id).label("latest_run_id"),
        )
        .where(EvaluationRun.status == "completed")
        .group_by(EvaluationRun.dataset_id)
        .subquery()
    )
    pass_rate_sq = (
        select(
            latest_run_sq.c.dataset_id,
            (
                func.cast(EvaluationRun.passed, sa.Float)
                / func.nullif(EvaluationRun.total_cases, 0)
            ).label("pass_rate"),
        )
        .join(EvaluationRun, EvaluationRun.id == latest_run_sq.c.latest_run_id)
        .subquery()
    )

    stmt = (
        select(EvaluationDataset, case_count_sq.c.case_count, pass_rate_sq.c.pass_rate)
        .outerjoin(case_count_sq, EvaluationDataset.id == case_count_sq.c.dataset_id)
        .outerjoin(pass_rate_sq, EvaluationDataset.id == pass_rate_sq.c.dataset_id)
        .order_by(EvaluationDataset.updated_at.desc())
    )

    count_stmt = select(func.count()).select_from(EvaluationDataset)
    total = db.exec(count_stmt).one()

    rows = db.exec(stmt.offset(offset).limit(limit)).all()

    items = []
    for row in rows:
        ds, cc, pr = row[0], row[1], row[2]
        items.append(
            DatasetListItem(
                id=ds.id,
                name=ds.name,
                target_type=ds.target_type,
                target_name=ds.target_name,
                description=ds.description,
                case_count=cc or 0,
                last_run_pass_rate=round(pr, 4) if pr is not None else None,
                created_at=ds.created_at.isoformat(),
                updated_at=ds.updated_at.isoformat(),
            )
        )

    return DatasetListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# Schema introspection (registered before /{dataset_id} to avoid shadowing)
# ---------------------------------------------------------------------------


@router.get("/schema", response_model=SchemaResponse)
def get_input_schema(
    request: Request,
    target_type: str = Query(..., pattern="^(step|pipeline)$"),
    target_name: str = Query(..., min_length=1),
) -> SchemaResponse:
    """Return JSON Schema for a step or pipeline input type."""
    introspection_registry: dict = getattr(
        request.app.state, "introspection_registry", {}
    )

    if target_type == "pipeline":
        return _pipeline_schema(target_name, introspection_registry)
    elif target_type == "step":
        return _step_schema(target_name, introspection_registry)
    else:
        raise HTTPException(status_code=400, detail="Invalid target_type")


@router.get(
    "/delta-type-whitelist",
    response_model=TypeWhitelistResponse,
)
def get_delta_type_whitelist() -> TypeWhitelistResponse:
    """Return the canonical list of allowed ``type_str`` values.

    Frontend variant editor consumes this so the type dropdown cannot drift
    from ``llm_pipeline.evals.delta._TYPE_WHITELIST``. Static list, no auth,
    no params. Registered before ``/{dataset_id}`` to avoid path-param
    shadowing (int coercion would reject it, but explicit ordering is
    clearer — matches the ``/schema`` convention).
    """
    return TypeWhitelistResponse(types=get_type_whitelist())


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: int, db: DBSession) -> DatasetDetail:
    """Get dataset detail with all cases."""
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    cases = db.exec(
        select(EvaluationCase)
        .where(
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.is_active == True,  # noqa: E712
            EvaluationCase.is_latest == True,  # noqa: E712
        )
        .order_by(EvaluationCase.id)
    ).all()

    return DatasetDetail(
        id=ds.id,
        name=ds.name,
        target_type=ds.target_type,
        target_name=ds.target_name,
        description=ds.description,
        case_count=len(cases),
        last_run_pass_rate=_last_run_pass_rate(db, ds.id),
        created_at=ds.created_at.isoformat(),
        updated_at=ds.updated_at.isoformat(),
        cases=[
            CaseItem(
                id=c.id,
                name=c.name,
                inputs=c.inputs,
                expected_output=c.expected_output,
                metadata_=c.metadata_,
            )
            for c in cases
        ],
    )


@router.get(
    "/{dataset_id}/prod-prompts", response_model=ProdPromptsResponse
)
def get_dataset_prod_prompts(
    dataset_id: int,
    request: Request,
    db: DBSession,
) -> ProdPromptsResponse:
    """Return resolved prod (system, user) prompts for a dataset's step target.

    Step-targeted only — pipeline-target variants are not supported in v2.
    Uses the shared resolver so tier 1/2/3 keys are all surfaced, then
    fetches Prompt rows for each non-None key. Either side returns null
    when the key is unresolved OR the Prompt row doesn't exist.

    Strategy resolution: walks registered pipelines in registry order and
    returns on the first match (same convention as ``EvalRunner._find_step_def``).
    Datasets don't store strategy_name, so the first-match strategy name
    is what drives tier-3 lookup.
    """
    from llm_pipeline.db.prompt import Prompt
    from llm_pipeline.prompts.resolver import resolve_with_auto_discovery

    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if ds.target_type != "step":
        raise HTTPException(
            status_code=422,
            detail=(
                "prod-prompts endpoint supports step-targets only "
                "(pipeline target variants are not supported in v2)"
            ),
        )

    introspection_registry: dict = getattr(
        request.app.state, "introspection_registry", {}
    )

    target_step = ds.target_name
    step_def, strategy_name, _pipeline_name = _find_step_def_by_target(
        target_step, introspection_registry
    )

    if step_def is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Step '{target_step}' not found in any registered pipeline"
            ),
        )

    system_key, user_key = resolve_with_auto_discovery(
        step_def, db, strategy_name
    )

    def _fetch(key: Optional[str], ptype: str) -> Optional[ProdPromptContent]:
        if key is None:
            return None
        row = db.exec(
            select(Prompt).where(
                Prompt.prompt_key == key,
                Prompt.prompt_type == ptype,
                Prompt.is_active == True,  # noqa: E712
                Prompt.is_latest == True,  # noqa: E712
            )
        ).first()
        if row is None:
            return None
        return ProdPromptContent(
            prompt_key=row.prompt_key,
            content=row.content,
            variable_definitions=row.variable_definitions,
            version=row.version,
        )

    return ProdPromptsResponse(
        system=_fetch(system_key, "system"),
        user=_fetch(user_key, "user"),
    )


@router.get(
    "/{dataset_id}/prod-model", response_model=ProdModelResponse
)
def get_dataset_prod_model(
    dataset_id: int,
    request: Request,
    db: DBSession,
) -> ProdModelResponse:
    """Return resolved prod model for a dataset's step target.

    Step-targeted only — pipeline-target variants are not supported in v2.
    Uses the shared model resolver so tier 1/2/3 all contribute. The
    ``source`` field surfaces which tier produced the value; ``"none"``
    means no model is configured at any tier.
    """
    from llm_pipeline.model.resolver import resolve_model_with_fallbacks

    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if ds.target_type != "step":
        raise HTTPException(
            status_code=422,
            detail=(
                "prod-model endpoint supports step-targets only "
                "(pipeline target variants are not supported in v2)"
            ),
        )

    introspection_registry: dict = getattr(
        request.app.state, "introspection_registry", {}
    )

    target_step = ds.target_name
    step_def, _strategy_name, pipeline_name = _find_step_def_by_target(
        target_step, introspection_registry
    )

    if step_def is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Step '{target_step}' not found in any registered pipeline"
            ),
        )

    pipeline_cls = introspection_registry.get(pipeline_name)
    pipeline_default_model = getattr(pipeline_cls, "_default_model", None)

    model, source = resolve_model_with_fallbacks(
        step_def, db, pipeline_name or "", pipeline_default_model
    )

    return ProdModelResponse(model=model, source=source)


@router.post("", response_model=DatasetDetail, status_code=201)
def create_dataset(
    body: DatasetCreateRequest,
    db: WritableDBSession,
) -> DatasetDetail:
    """Create a new evaluation dataset."""
    existing = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.name == body.name)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Dataset name already exists")

    now = datetime.now(timezone.utc)
    ds = EvaluationDataset(
        name=body.name,
        target_type=body.target_type,
        target_name=body.target_name,
        description=body.description,
        created_at=now,
        updated_at=now,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)

    return DatasetDetail(
        id=ds.id,
        name=ds.name,
        target_type=ds.target_type,
        target_name=ds.target_name,
        description=ds.description,
        case_count=0,
        last_run_pass_rate=None,
        created_at=ds.created_at.isoformat(),
        updated_at=ds.updated_at.isoformat(),
        cases=[],
    )


@router.put("/{dataset_id}", response_model=DatasetDetail)
def update_dataset(
    dataset_id: int,
    body: DatasetUpdateRequest,
    request: Request,
    db: WritableDBSession,
) -> DatasetDetail:
    """Update dataset name and/or description."""
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if body.name is not None:
        dup = db.exec(
            select(EvaluationDataset)
            .where(EvaluationDataset.name == body.name)
            .where(EvaluationDataset.id != dataset_id)
        ).first()
        if dup:
            raise HTTPException(status_code=409, detail="Dataset name already exists")
        ds.name = body.name

    if body.description is not None:
        ds.description = body.description

    ds.updated_at = datetime.now(timezone.utc)
    db.add(ds)
    db.commit()
    db.refresh(ds)

    cases = db.exec(
        select(EvaluationCase)
        .where(
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.is_active == True,  # noqa: E712
            EvaluationCase.is_latest == True,  # noqa: E712
        )
        .order_by(EvaluationCase.id)
    ).all()

    # DB -> YAML writeback
    _trigger_evals_writeback(request, dataset_id)

    return DatasetDetail(
        id=ds.id,
        name=ds.name,
        target_type=ds.target_type,
        target_name=ds.target_name,
        description=ds.description,
        case_count=len(cases),
        last_run_pass_rate=_last_run_pass_rate(db, ds.id),
        created_at=ds.created_at.isoformat(),
        updated_at=ds.updated_at.isoformat(),
        cases=[
            CaseItem(
                id=c.id,
                name=c.name,
                inputs=c.inputs,
                expected_output=c.expected_output,
                metadata_=c.metadata_,
            )
            for c in cases
        ],
    )


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int, db: WritableDBSession) -> None:
    """Delete dataset with cascading deletion of cases, runs, and case results."""
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # cascade: case results -> runs -> cases -> dataset
    run_ids = db.exec(
        select(EvaluationRun.id).where(EvaluationRun.dataset_id == dataset_id)
    ).all()
    if run_ids:
        for rid in run_ids:
            results = db.exec(
                select(EvaluationCaseResult).where(EvaluationCaseResult.run_id == rid)
            ).all()
            for r in results:
                db.delete(r)
        runs = db.exec(
            select(EvaluationRun).where(EvaluationRun.dataset_id == dataset_id)
        ).all()
        for run in runs:
            db.delete(run)

    cases = db.exec(
        select(EvaluationCase).where(EvaluationCase.dataset_id == dataset_id)
    ).all()
    for c in cases:
        db.delete(c)

    # cascade: variants for this dataset
    variants = db.exec(
        select(EvaluationVariant).where(EvaluationVariant.dataset_id == dataset_id)
    ).all()
    for v in variants:
        db.delete(v)

    db.delete(ds)
    db.commit()


# ---------------------------------------------------------------------------
# Case endpoints
# ---------------------------------------------------------------------------


@router.post("/{dataset_id}/cases", response_model=CaseItem, status_code=201)
def create_case(
    dataset_id: int,
    body: CaseCreateRequest,
    request: Request,
    db: WritableDBSession,
) -> CaseItem:
    """Add a case to a dataset."""
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    case = save_new_version(
        db, EvaluationCase,
        key_filters={"dataset_id": dataset_id, "name": body.name},
        new_fields={
            "inputs": body.inputs,
            "expected_output": body.expected_output,
            "metadata_": body.metadata_,
        },
    )
    # bump dataset updated_at
    ds.updated_at = datetime.now(timezone.utc)
    db.add(ds)
    db.commit()
    db.refresh(case)

    # DB -> YAML writeback
    _trigger_evals_writeback(request, dataset_id)

    return CaseItem(
        id=case.id,
        name=case.name,
        inputs=case.inputs,
        expected_output=case.expected_output,
        metadata_=case.metadata_,
    )


@router.put("/{dataset_id}/cases/{case_id}", response_model=CaseItem)
def update_case(
    dataset_id: int,
    case_id: int,
    body: CaseUpdateRequest,
    request: Request,
    db: WritableDBSession,
) -> CaseItem:
    """Update a case's fields by creating a new version."""
    old_case = db.exec(
        select(EvaluationCase)
        .where(
            EvaluationCase.id == case_id,
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.is_active == True,  # noqa: E712
            EvaluationCase.is_latest == True,  # noqa: E712
        )
    ).first()
    if not old_case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Build new fields from existing + overrides
    new_name = body.name if body.name is not None else old_case.name
    new_inputs = body.inputs if body.inputs is not None else old_case.inputs
    new_expected = body.expected_output if body.expected_output is not None else old_case.expected_output

    case = save_new_version(
        db, EvaluationCase,
        key_filters={"dataset_id": dataset_id, "name": old_case.name},
        new_fields={
            "inputs": new_inputs,
            "expected_output": new_expected,
            "metadata_": old_case.metadata_,
        },
    )
    # If name changed, check for conflicts before renaming.
    if body.name is not None and body.name != old_case.name:
        existing = get_latest(db, EvaluationCase, dataset_id=dataset_id, name=body.name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A case named '{body.name}' already exists in this dataset.",
            )
        case.name = body.name
        db.add(case)
        db.flush()

    # bump dataset updated_at
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds:
        ds.updated_at = datetime.now(timezone.utc)
        db.add(ds)
    db.commit()
    db.refresh(case)

    # DB -> YAML writeback
    _trigger_evals_writeback(request, dataset_id)

    return CaseItem(
        id=case.id,
        name=case.name,
        inputs=case.inputs,
        expected_output=case.expected_output,
        metadata_=case.metadata_,
    )


@router.delete("/{dataset_id}/cases/{case_id}", status_code=204)
def delete_case(
    dataset_id: int,
    case_id: int,
    request: Request,
    db: WritableDBSession,
) -> None:
    """Soft-delete a case from a dataset."""
    # Verify the case exists and is active+latest
    case = db.exec(
        select(EvaluationCase)
        .where(
            EvaluationCase.id == case_id,
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.is_active == True,  # noqa: E712
            EvaluationCase.is_latest == True,  # noqa: E712
        )
    ).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    soft_delete_latest(
        db, EvaluationCase, dataset_id=dataset_id, name=case.name
    )
    # bump dataset updated_at
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds:
        ds.updated_at = datetime.now(timezone.utc)
        db.add(ds)
    db.commit()

    # DB -> YAML writeback
    _trigger_evals_writeback(request, dataset_id)


# ---------------------------------------------------------------------------
# Run endpoints
# ---------------------------------------------------------------------------


@router.get("/{dataset_id}/runs", response_model=RunListResponse)
def list_eval_runs(
    dataset_id: int,
    db: DBSession,
) -> RunListResponse:
    """List runs for a dataset, ordered by started_at desc."""
    stmt = (
        select(EvaluationRun)
        .where(EvaluationRun.dataset_id == dataset_id)
        .order_by(EvaluationRun.started_at.desc())
    )
    rows = db.exec(stmt).all()

    return RunListResponse(
        items=[
            RunListItem(
                id=r.id,
                dataset_id=r.dataset_id,
                status=r.status,
                total_cases=r.total_cases,
                passed=r.passed,
                failed=r.failed,
                errored=r.errored,
                started_at=r.started_at,
                completed_at=r.completed_at,
                variant_id=r.variant_id,
                delta_snapshot=r.delta_snapshot,
                case_versions=r.case_versions,
                prompt_versions=r.prompt_versions,
                model_snapshot=r.model_snapshot,
                instructions_schema_snapshot=r.instructions_schema_snapshot,
            )
            for r in rows
        ]
    )


@router.get("/{dataset_id}/runs/{run_id}", response_model=RunDetail)
def get_eval_run(
    dataset_id: int,
    run_id: int,
    db: DBSession,
) -> RunDetail:
    """Run detail with per-case results."""
    run = db.exec(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id,
            EvaluationRun.dataset_id == dataset_id,
        )
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    case_results = db.exec(
        select(EvaluationCaseResult)
        .where(EvaluationCaseResult.run_id == run_id)
        .order_by(EvaluationCaseResult.id)
    ).all()

    return RunDetail(
        id=run.id,
        dataset_id=run.dataset_id,
        status=run.status,
        total_cases=run.total_cases,
        passed=run.passed,
        failed=run.failed,
        errored=run.errored,
        started_at=run.started_at,
        completed_at=run.completed_at,
        variant_id=run.variant_id,
        delta_snapshot=run.delta_snapshot,
        case_versions=run.case_versions,
        prompt_versions=run.prompt_versions,
        model_snapshot=run.model_snapshot,
        instructions_schema_snapshot=run.instructions_schema_snapshot,
        case_results=[
            CaseResultItem(
                id=cr.id,
                # Map runner's 0 sentinel (unresolved case name) to None for clients
                case_id=cr.case_id if cr.case_id else None,
                case_name=cr.case_name,
                passed=cr.passed,
                evaluator_scores=cr.evaluator_scores or {},
                output_data=cr.output_data,
                error_message=cr.error_message,
            )
            for cr in case_results
        ],
    )


@router.post(
    "/{dataset_id}/runs",
    response_model=TriggerRunResponse,
    status_code=202,
)
def trigger_eval_run(
    dataset_id: int,
    body: TriggerRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: DBSession,
) -> TriggerRunResponse:
    """Trigger eval run in background. Runner creates its own run row."""
    from llm_pipeline.evals.runner import EvalRunner

    # Validate dataset exists
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Validate variant belongs to dataset (422 if mismatched)
    if body.variant_id is not None:
        variant = db.exec(
            select(EvaluationVariant).where(EvaluationVariant.id == body.variant_id)
        ).first()
        if variant is None or variant.dataset_id != dataset_id:
            raise HTTPException(
                status_code=422,
                detail="variant_id does not belong to this dataset",
            )

    engine = request.app.state.engine
    pipeline_registry = getattr(request.app.state, "pipeline_registry", {})
    introspection_registry = getattr(request.app.state, "introspection_registry", {})

    runner = EvalRunner(
        engine=engine,
        pipeline_registry=pipeline_registry,
        introspection_registry=introspection_registry,
    )

    eval_model = body.model or getattr(request.app.state, "default_model", None)
    eval_variant_id = body.variant_id

    def _execute() -> None:
        try:
            runner.run_dataset(
                dataset_id, model=eval_model, variant_id=eval_variant_id
            )
        except Exception:
            logger.exception("Eval run failed for dataset_id=%d", dataset_id)

    background_tasks.add_task(_execute)

    return TriggerRunResponse(status="accepted")


# ---------------------------------------------------------------------------
# Variant endpoints
# ---------------------------------------------------------------------------


@router.get("/{dataset_id}/variants", response_model=VariantListResponse)
def list_variants(dataset_id: int, db: DBSession) -> VariantListResponse:
    """List variants for a dataset, ordered by created_at desc."""
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    rows = db.exec(
        select(EvaluationVariant)
        .where(EvaluationVariant.dataset_id == dataset_id)
        .order_by(EvaluationVariant.created_at.desc())
    ).all()

    items = [_variant_to_item(v) for v in rows]
    return VariantListResponse(items=items, total=len(items))


@router.post(
    "/{dataset_id}/variants",
    response_model=VariantItem,
    status_code=201,
)
def create_variant(
    dataset_id: int,
    body: VariantCreateRequest,
    db: WritableDBSession,
) -> VariantItem:
    """Create a variant scoped to a dataset.

    Dry-run validates instructions_delta via apply_instruction_delta; returns
    422 with the ValueError message on failure.
    """
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _dry_run_validate_delta(body.delta)

    now = datetime.now(timezone.utc)
    variant = EvaluationVariant(
        dataset_id=dataset_id,
        name=body.name,
        description=body.description,
        delta=body.delta or {},
        created_at=now,
        updated_at=now,
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)

    return _variant_to_item(variant)


@router.get(
    "/{dataset_id}/variants/{variant_id}",
    response_model=VariantItem,
)
def get_variant(
    dataset_id: int,
    variant_id: int,
    db: DBSession,
) -> VariantItem:
    """Get a single variant; 404 if not found or not belonging to dataset."""
    variant = db.exec(
        select(EvaluationVariant)
        .where(EvaluationVariant.id == variant_id)
        .where(EvaluationVariant.dataset_id == dataset_id)
    ).first()
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return _variant_to_item(variant)


@router.put(
    "/{dataset_id}/variants/{variant_id}",
    response_model=VariantItem,
)
def update_variant(
    dataset_id: int,
    variant_id: int,
    body: VariantUpdateRequest,
    db: WritableDBSession,
) -> VariantItem:
    """Partial update of a variant. Dry-run validates delta when provided."""
    variant = db.exec(
        select(EvaluationVariant)
        .where(EvaluationVariant.id == variant_id)
        .where(EvaluationVariant.dataset_id == dataset_id)
    ).first()
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")

    if body.delta is not None:
        _dry_run_validate_delta(body.delta)
        variant.delta = body.delta

    if body.name is not None:
        variant.name = body.name
    if body.description is not None:
        variant.description = body.description

    variant.updated_at = datetime.now(timezone.utc)
    db.add(variant)
    db.commit()
    db.refresh(variant)

    return _variant_to_item(variant)


@router.delete(
    "/{dataset_id}/variants/{variant_id}",
    status_code=204,
)
def delete_variant(
    dataset_id: int,
    variant_id: int,
    db: WritableDBSession,
) -> None:
    """Delete a variant, nulling out ``EvaluationRun.variant_id`` references.

    Application-level cascade: SQLite does not enforce foreign keys without
    ``PRAGMA foreign_keys=ON``, so dangling ``variant_id`` pointers on
    historical ``EvaluationRun`` rows would otherwise persist. We null them
    out in the same transaction as the variant delete for atomicity.

    Note: ``EvaluationRun.delta_snapshot`` is intentionally left untouched.
    It is a deep-copied JSON snapshot captured at run time so a run stays
    reproducible even after its source variant is deleted. Nulling it would
    destroy historical audit data.
    """
    variant = db.exec(
        select(EvaluationVariant)
        .where(EvaluationVariant.id == variant_id)
        .where(EvaluationVariant.dataset_id == dataset_id)
    ).first()
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")

    # Null out variant_id on historical runs referencing this variant.
    # delta_snapshot is preserved — see docstring.
    runs_referencing = db.exec(
        select(EvaluationRun).where(EvaluationRun.variant_id == variant_id)
    ).all()
    for run in runs_referencing:
        run.variant_id = None
        db.add(run)

    db.delete(variant)
    db.commit()


# ---------------------------------------------------------------------------
# Schema introspection helpers
# ---------------------------------------------------------------------------


def _pipeline_schema(
    pipeline_name: str, introspection_registry: dict
) -> SchemaResponse:
    """Resolve input schema for a pipeline via PipelineIntrospector."""
    from llm_pipeline.introspection import PipelineIntrospector

    pipeline_cls = introspection_registry.get(pipeline_name)
    if pipeline_cls is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline '{pipeline_name}' not found",
        )

    # Check for INPUT_DATA (validated_input type) first
    input_data_cls = getattr(pipeline_cls, "INPUT_DATA", None)
    if input_data_cls is not None and hasattr(input_data_cls, "model_json_schema"):
        return SchemaResponse(
            target_type="pipeline",
            target_name=pipeline_name,
            json_schema=input_data_cls.model_json_schema(),
        )

    # Fallback: use PipelineIntrospector metadata
    introspector = PipelineIntrospector(pipeline_cls)
    metadata = introspector.get_metadata()
    schema = metadata.get("pipeline_input_schema")
    if schema is None:
        raise HTTPException(
            status_code=404,
            detail=f"No input schema found for pipeline '{pipeline_name}'",
        )
    return SchemaResponse(
        target_type="pipeline",
        target_name=pipeline_name,
        json_schema=schema,
    )


def _step_schema(
    step_name: str, introspection_registry: dict
) -> SchemaResponse:
    """Resolve input + output schemas for a step by searching all registered pipelines."""
    for _pipeline_name, pipeline_cls in introspection_registry.items():
        strategies_cls = getattr(pipeline_cls, "STRATEGIES", None)
        if strategies_cls is None:
            continue
        strategy_classes = getattr(strategies_cls, "STRATEGIES", []) or []
        for s_cls in strategy_classes:
            try:
                instance = s_cls()
                for sd in instance.get_steps():
                    if sd.step_name != step_name:
                        continue

                    input_schema = None
                    output_schema = None

                    input_cls = getattr(pipeline_cls, "INPUT_DATA", None)
                    if input_cls is not None and hasattr(input_cls, "model_json_schema"):
                        input_schema = input_cls.model_json_schema()

                    instr_cls = sd.instructions
                    if instr_cls is not None and hasattr(instr_cls, "model_json_schema"):
                        output_schema = instr_cls.model_json_schema()

                    if input_schema is None and output_schema is None:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Step '{step_name}' has no typed schema",
                        )

                    return SchemaResponse(
                        target_type="step",
                        target_name=step_name,
                        json_schema=output_schema or input_schema or {},
                        input_schema=input_schema,
                        output_schema=output_schema,
                    )
            except HTTPException:
                raise
            except Exception:
                logger.debug(
                    "Failed to introspect for step '%s'",
                    step_name,
                    exc_info=True,
                )
                continue

    raise HTTPException(
        status_code=404,
        detail=f"Step '{step_name}' not found in any registered pipeline",
    )
