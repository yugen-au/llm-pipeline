"""
Sandboxed pipeline execution for evals and experimentation.

Runs pipelines (or single steps) in an isolated in-memory database so
production state is never modified. The execution path is identical to
production — same PipelineConfig.execute() code runs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import Engine, create_engine
from sqlmodel import Session, select

from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.strategy import PipelineStrategy, StepDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sandbox pipeline class (static, reusable)
# ---------------------------------------------------------------------------

class SandboxRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class SandboxPipeline(PipelineConfig, registry=SandboxRegistry):
    """Minimal pipeline for sandboxed execution. Strategies + INPUT_DATA set at runtime."""
    pass


# ---------------------------------------------------------------------------
# Sandbox engine factory
# ---------------------------------------------------------------------------

def create_sandbox_engine(prod_engine: Engine) -> Engine:
    """Create an in-memory SQLite engine seeded with prompts from prod DB."""
    from llm_pipeline.db import init_pipeline_db
    from llm_pipeline.db.prompt import Prompt
    from llm_pipeline.db.step_config import StepModelConfig

    sandbox_engine = create_engine("sqlite:///:memory:")
    init_pipeline_db(sandbox_engine)

    with Session(prod_engine) as src, Session(sandbox_engine) as dst:
        for prompt in src.exec(select(Prompt)).all():
            dst.add(Prompt(
                prompt_key=prompt.prompt_key,
                prompt_name=prompt.prompt_name,
                prompt_type=prompt.prompt_type,
                category=prompt.category,
                step_name=prompt.step_name,
                content=prompt.content,
                required_variables=prompt.required_variables,
                variable_definitions=prompt.variable_definitions,
                description=prompt.description,
                version=prompt.version,
                is_active=prompt.is_active,
                created_at=prompt.created_at,
                updated_at=prompt.updated_at,
            ))

        for cfg in src.exec(select(StepModelConfig)).all():
            dst.add(StepModelConfig(
                pipeline_name=cfg.pipeline_name,
                step_name=cfg.step_name,
                model=cfg.model,
                request_limit=cfg.request_limit,
            ))

        dst.commit()

    return sandbox_engine


# ---------------------------------------------------------------------------
# Single-step strategy
# ---------------------------------------------------------------------------

class _SingleStepStrategy(PipelineStrategy):
    """Strategy wrapping a single StepDefinition."""

    def __init__(self, step_def: StepDefinition):
        self._step_def = step_def

    def can_handle(self, context: Dict[str, Any]) -> bool:
        return True

    def get_steps(self) -> List[StepDefinition]:
        return [self._step_def]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_single_step_pipeline(
    step_def: StepDefinition,
    input_data_cls: Optional[Type] = None,
    engine: Optional[Engine] = None,
    prod_engine: Optional[Engine] = None,
    model: str = "",
    run_id: Optional[str] = None,
    event_emitter: Any = None,
) -> SandboxPipeline:
    """Create a sandboxed pipeline wrapping a single step.

    Args:
        step_def: the step to execute
        input_data_cls: PipelineInputData subclass for input validation (optional)
        engine: pre-built sandbox engine (if None, created from prod_engine)
        prod_engine: production engine to seed prompts from (used if engine is None)
        model: LLM model string
        run_id: optional run identifier
        event_emitter: optional event handler (None disables events)
    """
    if engine is None:
        if prod_engine is not None:
            engine = create_sandbox_engine(prod_engine)
        else:
            engine = create_engine("sqlite:///:memory:")
            from llm_pipeline.db import init_pipeline_db
            init_pipeline_db(engine)

    SandboxPipeline.INPUT_DATA = input_data_cls

    strategy = _SingleStepStrategy(step_def)

    return SandboxPipeline(
        model=model,
        engine=engine,
        strategies=[strategy],
        event_emitter=event_emitter,
        run_id=run_id,
    )


def create_sandbox_from_factory(
    factory,
    prod_engine: Engine,
    model: Optional[str] = None,
    run_id: Optional[str] = None,
    event_emitter: Any = None,
) -> PipelineConfig:
    """Create a sandboxed instance of a registered pipeline.

    Uses the existing factory function (from pipeline_registry) but
    swaps in a sandbox engine so writes are isolated.

    Args:
        factory: pipeline factory callable (from app.state.pipeline_registry)
        prod_engine: production engine to seed from
        model: optional model override
        run_id: optional run identifier
        event_emitter: optional event handler
    """
    sandbox_engine = create_sandbox_engine(prod_engine)

    kwargs = {
        "run_id": run_id or "sandbox",
        "engine": sandbox_engine,
        "event_emitter": event_emitter,
    }

    pipeline = factory(**kwargs)

    if model:
        pipeline._model = model

    return pipeline


__all__ = [
    "SandboxPipeline",
    "create_sandbox_engine",
    "create_single_step_pipeline",
    "create_sandbox_from_factory",
]
