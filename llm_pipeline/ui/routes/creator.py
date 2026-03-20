"""Creator workflow route module -- generate, test, accept, list drafts."""
import importlib.util
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from llm_pipeline.events.emitter import CompositeEmitter
from llm_pipeline.events.handlers import BufferedEventHandler
from llm_pipeline.state import DraftStep, PipelineRun, utc_now
from llm_pipeline.ui.bridge import UIBridge
from llm_pipeline.ui.deps import DBSession
from llm_pipeline.ui.routes.websocket import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/creator", tags=["creator"])

# ---------------------------------------------------------------------------
# Request / response models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    description: str
    target_pipeline: str | None = None
    include_extraction: bool = True
    include_transformation: bool = False


class GenerateResponse(BaseModel):
    run_id: str
    draft_name: str
    status: str


class TestRequest(BaseModel):
    code_overrides: dict[str, str] | None = None
    sample_data: dict | None = None


class TestResponse(BaseModel):
    import_ok: bool
    security_issues: list[str]
    sandbox_skipped: bool
    output: str
    errors: list[str]
    modules_found: list[str]
    draft_status: str


class AcceptRequest(BaseModel):
    pipeline_file: str | None = None


class AcceptResponse(BaseModel):
    files_written: list[str]
    prompts_registered: int
    pipeline_file_updated: bool
    target_dir: str


class DraftItem(BaseModel):
    id: int
    name: str
    description: str | None
    status: str
    run_id: str | None
    created_at: datetime
    updated_at: datetime


class DraftDetail(DraftItem):
    """Full draft including generated code and test results (for single-draft view)."""
    generated_code: dict
    test_results: dict | None


class RenameRequest(BaseModel):
    name: str


class DraftListResponse(BaseModel):
    items: list[DraftItem]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_seed_done: bool = False


def _ensure_seeded(engine) -> None:
    """Lazily seed StepCreatorPipeline prompts once per process."""
    global _seed_done
    if _seed_done:
        return
    try:
        from llm_pipeline.creator.pipeline import StepCreatorPipeline

        StepCreatorPipeline.seed_prompts(engine)
        _seed_done = True
    except Exception:
        logger.warning(
            "seed_prompts failed for StepCreatorPipeline, continuing anyway",
            exc_info=True,
        )
        _seed_done = True  # don't retry on every request


def _derive_target_dir(step_name: str) -> Path:
    """Compute target directory for accepted step files.

    Uses LLM_PIPELINE_STEPS_DIR env var if set, otherwise derives base
    from the llm_pipeline package parent directory.
    """
    env_dir = os.environ.get("LLM_PIPELINE_STEPS_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        spec = importlib.util.find_spec("llm_pipeline")
        if spec and spec.submodule_search_locations:
            base = Path(spec.submodule_search_locations[0]).parent
        else:
            base = Path.cwd()
    return base / "steps" / step_name


# ---------------------------------------------------------------------------
# Endpoints (all sync def -- FastAPI wraps in threadpool)
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=GenerateResponse, status_code=202)
def generate_step(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> GenerateResponse:
    """Trigger step generation in the background. Returns 202 immediately."""
    default_model = getattr(request.app.state, "default_model", None)
    if default_model is None:
        raise HTTPException(
            status_code=422,
            detail="No model configured. Set LLM_PIPELINE_MODEL env var or pass --model flag.",
        )

    engine = request.app.state.engine
    _ensure_seeded(engine)

    run_id = str(uuid.uuid4())
    draft_name = f"draft_{run_id[:8]}"

    # Pre-create PipelineRun + DraftStep so frontend can poll immediately
    with Session(engine) as pre_session:
        pre_session.add(PipelineRun(
            run_id=run_id,
            pipeline_name="step_creator",
            status="running",
        ))
        pre_session.add(DraftStep(
            name=draft_name,
            description=body.description,
            generated_code={},
            status="draft",
            run_id=run_id,
        ))
        pre_session.commit()

    ws_manager.broadcast_global({
        "type": "run_created",
        "run_id": run_id,
        "pipeline_name": "step_creator",
        "started_at": datetime.now(timezone.utc).isoformat(),
    })

    def run_creator() -> None:
        bridge = UIBridge(run_id=run_id)
        db_buffer = BufferedEventHandler(engine)
        emitter = CompositeEmitter([bridge, db_buffer])
        pipeline = None
        try:
            from llm_pipeline.creator.pipeline import StepCreatorPipeline

            pipeline = StepCreatorPipeline(
                model=default_model,
                run_id=run_id,
                engine=engine,
                event_emitter=emitter,
            )
            pipeline.execute(data=None, input_data=body.model_dump())
            pipeline.save()

            # Update DraftStep with actual generated name + code
            from llm_pipeline.creator.models import GenerationRecord

            with Session(engine) as post_session:
                gen_rec = post_session.exec(
                    select(GenerationRecord).where(
                        GenerationRecord.run_id == run_id
                    )
                ).first()
                draft = post_session.exec(
                    select(DraftStep).where(DraftStep.run_id == run_id)
                ).first()
                if draft and gen_rec:
                    # Collect generated_code from pipeline context
                    ctx = getattr(pipeline, "_context", None)
                    if ctx and hasattr(ctx, "get"):
                        code_dict = ctx.get("all_artifacts", {})
                        if code_dict:
                            draft.generated_code = code_dict
                    draft.status = "draft"
                    draft.updated_at = utc_now()

                    # Name assignment with collision retry (_2 .. _9)
                    base_name = gen_rec.step_name_generated
                    candidates = [base_name] + [f"{base_name}_{i}" for i in range(2, 10)]
                    for candidate_name in candidates:
                        draft.name = candidate_name
                        post_session.add(draft)
                        try:
                            post_session.commit()
                            break
                        except IntegrityError:
                            post_session.rollback()
                            # re-fetch after rollback (session state cleared)
                            draft = post_session.exec(
                                select(DraftStep).where(DraftStep.run_id == run_id)
                            ).first()
                            if draft is None:
                                break
                            logger.warning(
                                "Name collision for '%s', trying next suffix (run_id=%s)",
                                candidate_name,
                                run_id,
                            )
        except Exception:
            logger.exception(
                "Background step creator failed for run_id=%s", run_id
            )
            if pipeline is not None:
                try:
                    pipeline.close()
                except Exception:
                    pass
            try:
                with Session(engine) as err_session:
                    draft = err_session.exec(
                        select(DraftStep).where(DraftStep.run_id == run_id)
                    ).first()
                    if draft:
                        draft.status = "error"
                        draft.updated_at = utc_now()
                        err_session.add(draft)
                        err_session.commit()
                    run = err_session.exec(
                        select(PipelineRun).where(PipelineRun.run_id == run_id)
                    ).first()
                    if run:
                        run.status = "failed"
                        run.completed_at = datetime.now(timezone.utc)
                        err_session.add(run)
                        err_session.commit()
            except Exception:
                logger.exception(
                    "Failed to update error status for run_id=%s", run_id
                )
        finally:
            bridge.complete()
            try:
                count = db_buffer.flush()
                logger.info("Flushed %d events to DB for run_id=%s", count, run_id)
            except Exception:
                logger.exception("Failed to flush events for run_id=%s", run_id)

    background_tasks.add_task(run_creator)

    return GenerateResponse(run_id=run_id, draft_name=draft_name, status="accepted")


@router.post("/test/{draft_id}", response_model=TestResponse)
def test_draft(
    draft_id: int,
    body: TestRequest,
    request: Request,
) -> TestResponse:
    """Run sandbox validation on a draft step. Persists code_overrides before running."""
    engine = request.app.state.engine
    with Session(engine) as session:
        draft = session.get(DraftStep, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Merge code_overrides into generated_code and persist
        if body.code_overrides:
            merged = dict(draft.generated_code)
            merged.update(body.code_overrides)
            draft.generated_code = merged
            draft.updated_at = utc_now()
            session.add(draft)
            session.commit()
            session.refresh(draft)

        artifacts = dict(draft.generated_code)

    # Run sandbox outside session (may block up to 60s)
    from llm_pipeline.creator.sandbox import StepSandbox

    sandbox_result = StepSandbox().run(artifacts=artifacts, sample_data=body.sample_data)

    # Persist test results and update status
    with Session(engine) as session:
        draft = session.get(DraftStep, draft_id)
        if draft:
            draft.test_results = sandbox_result.model_dump()
            draft.status = "tested" if sandbox_result.import_ok else "error"
            draft.updated_at = utc_now()
            session.add(draft)
            session.commit()
            final_status = draft.status
        else:
            final_status = "error"

    return TestResponse(**sandbox_result.model_dump(), draft_status=final_status)


@router.post("/accept/{draft_id}", response_model=AcceptResponse)
def accept_draft(
    draft_id: int,
    body: AcceptRequest,
    request: Request,
) -> AcceptResponse:
    """Accept a draft step: write files, register prompts, optionally modify pipeline."""
    engine = request.app.state.engine
    session = Session(engine)
    try:
        draft = session.get(DraftStep, draft_id)
        if draft is None:
            session.close()
            raise HTTPException(status_code=404, detail="Draft not found")

        from llm_pipeline.creator.models import GeneratedStep

        try:
            generated = GeneratedStep.from_draft(draft)
        except KeyError as exc:
            session.close()
            raise HTTPException(
                status_code=422,
                detail=f"Malformed generated_code: missing key {exc}",
            )

        target_dir = _derive_target_dir(draft.name)

        from llm_pipeline.creator.integrator import StepIntegrator

        integrator = StepIntegrator(
            session=session,
            pipeline_file=Path(body.pipeline_file) if body.pipeline_file else None,
        )

        try:
            result = integrator.integrate(
                generated=generated,
                target_dir=target_dir,
                draft=draft,
            )
        except Exception as exc:
            logger.exception("StepIntegrator failed for draft_id=%s", draft_id)
            raise HTTPException(
                status_code=500,
                detail=f"Integration failed: {type(exc).__name__}: {exc}",
            )

        return AcceptResponse(**result.model_dump())
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        session.close()
        raise
    finally:
        # Integrator owns commit; session may already be closed on error paths
        try:
            session.close()
        except Exception:
            pass


@router.get("/drafts", response_model=DraftListResponse)
def list_drafts(db: DBSession) -> DraftListResponse:
    """List all draft steps, ordered by created_at desc."""
    stmt = select(DraftStep).order_by(DraftStep.created_at.desc())
    rows = db.exec(stmt).all()
    return DraftListResponse(
        items=[
            DraftItem(
                id=d.id,
                name=d.name,
                description=d.description,
                status=d.status,
                run_id=d.run_id,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in rows
        ],
        total=len(rows),
    )


@router.get("/drafts/{draft_id}", response_model=DraftDetail)
def get_draft(draft_id: int, db: DBSession) -> DraftDetail:
    """Get a single draft step by ID (includes generated_code + test_results)."""
    draft = db.exec(
        select(DraftStep).where(DraftStep.id == draft_id)
    ).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return DraftDetail(
        id=draft.id,
        name=draft.name,
        description=draft.description,
        status=draft.status,
        run_id=draft.run_id,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        generated_code=draft.generated_code,
        test_results=draft.test_results,
    )


@router.patch("/drafts/{draft_id}", response_model=DraftDetail, responses={409: {"description": "Name conflict"}})
def rename_draft(
    draft_id: int,
    body: RenameRequest,
    request: Request,
) -> DraftDetail | JSONResponse:
    """Rename a draft step. Returns 409 with suggested_name on name collision."""
    engine = request.app.state.engine
    with Session(engine) as session:
        draft = session.exec(
            select(DraftStep).where(DraftStep.id == draft_id)
        ).first()
        if draft is None:
            raise HTTPException(status_code=404, detail="Draft not found")

        draft.name = body.name
        draft.updated_at = utc_now()
        try:
            session.add(draft)
            session.commit()
            session.refresh(draft)
        except IntegrityError:
            session.rollback()
            # find a free suffix
            suggested = body.name
            for i in range(2, 10):
                candidate = f"{body.name}_{i}"
                existing = session.exec(
                    select(DraftStep).where(DraftStep.name == candidate)
                ).first()
                if existing is None:
                    suggested = candidate
                    break
            return JSONResponse(
                status_code=409,
                content={"detail": "name_conflict", "suggested_name": suggested},
            )

        return DraftDetail(
            id=draft.id,
            name=draft.name,
            description=draft.description,
            status=draft.status,
            run_id=draft.run_id,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            generated_code=draft.generated_code,
            test_results=draft.test_results,
        )
