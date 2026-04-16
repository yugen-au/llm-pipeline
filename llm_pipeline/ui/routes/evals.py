"""Evaluation system endpoints - dataset and case CRUD."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from llm_pipeline.evals.models import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationRun,
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
    target_type: str
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
# Helpers
# ---------------------------------------------------------------------------


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
    # case count subquery
    case_count_sq = (
        select(
            EvaluationCase.dataset_id,
            func.count(EvaluationCase.id).label("case_count"),
        )
        .group_by(EvaluationCase.dataset_id)
        .subquery()
    )

    stmt = (
        select(EvaluationDataset, case_count_sq.c.case_count)
        .outerjoin(case_count_sq, EvaluationDataset.id == case_count_sq.c.dataset_id)
        .order_by(EvaluationDataset.updated_at.desc())
    )

    count_stmt = select(func.count()).select_from(EvaluationDataset)
    total = db.exec(count_stmt).one()

    rows = db.exec(stmt.offset(offset).limit(limit)).all()

    items = []
    for row in rows:
        ds = row[0] if isinstance(row, tuple) else row
        cc = row[1] if isinstance(row, tuple) else 0
        items.append(
            DatasetListItem(
                id=ds.id,
                name=ds.name,
                target_type=ds.target_type,
                target_name=ds.target_name,
                description=ds.description,
                case_count=cc or 0,
                last_run_pass_rate=_last_run_pass_rate(db, ds.id),
                created_at=ds.created_at.isoformat(),
                updated_at=ds.updated_at.isoformat(),
            )
        )

    return DatasetListResponse(items=items, total=total)


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
        .where(EvaluationCase.dataset_id == dataset_id)
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
        .where(EvaluationCase.dataset_id == dataset_id)
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

    db.delete(ds)
    db.commit()


# ---------------------------------------------------------------------------
# Case endpoints
# ---------------------------------------------------------------------------


@router.post("/{dataset_id}/cases", response_model=CaseItem, status_code=201)
def create_case(
    dataset_id: int,
    body: CaseCreateRequest,
    db: WritableDBSession,
) -> CaseItem:
    """Add a case to a dataset."""
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    case = EvaluationCase(
        dataset_id=dataset_id,
        name=body.name,
        inputs=body.inputs,
        expected_output=body.expected_output,
        metadata_=body.metadata_,
    )
    db.add(case)
    # bump dataset updated_at
    ds.updated_at = datetime.now(timezone.utc)
    db.add(ds)
    db.commit()
    db.refresh(case)

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
    db: WritableDBSession,
) -> CaseItem:
    """Update a case's fields."""
    case = db.exec(
        select(EvaluationCase)
        .where(EvaluationCase.id == case_id)
        .where(EvaluationCase.dataset_id == dataset_id)
    ).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if body.name is not None:
        case.name = body.name
    if body.inputs is not None:
        case.inputs = body.inputs
    if body.expected_output is not None:
        case.expected_output = body.expected_output

    db.add(case)
    # bump dataset updated_at
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds:
        ds.updated_at = datetime.now(timezone.utc)
        db.add(ds)
    db.commit()
    db.refresh(case)

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
    db: WritableDBSession,
) -> None:
    """Delete a case from a dataset."""
    case = db.exec(
        select(EvaluationCase)
        .where(EvaluationCase.id == case_id)
        .where(EvaluationCase.dataset_id == dataset_id)
    ).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    db.delete(case)
    # bump dataset updated_at
    ds = db.exec(
        select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
    ).first()
    if ds:
        ds.updated_at = datetime.now(timezone.utc)
        db.add(ds)
    db.commit()


# --- Run + introspection endpoints added by Step 5 ---
