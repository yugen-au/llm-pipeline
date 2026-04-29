"""``llm_pipeline.creator`` — meta-pipeline (stubbed pending Phase 3b rewrite).

The legacy creator generated ``@step_definition``-decorated step
files plus a ``PipelineConfig`` + ``PipelineStrategy`` integration.
The pydantic-graph migration retired all three; the creator's
generation templates + integrator need to be rebuilt against
``LLMStepNode`` + ``Pipeline.nodes`` shape. Tracked as Phase 3b.

Until then the public surface
(``StepCreatorPipeline``, ``StepIntegrator``) raises
``NotImplementedError`` on instantiation so the framework imports
clean while creator endpoints (``POST /api/creator/...``) surface
a clear error.
"""
from __future__ import annotations

try:
    import jinja2  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "llm_pipeline.creator requires jinja2. Install with: pip install llm-pipeline[creator]"
    ) from exc


_NOT_IMPLEMENTED = (
    "Creator (meta-pipeline) rewrite pending. The pydantic-graph "
    "migration retired @step_definition / PipelineConfig / "
    "PipelineStrategy that the creator generated against. Phase 3b "
    "rebuilds against LLMStepNode + Pipeline.nodes."
)


class StepCreatorPipeline:
    """Stub. Phase 3b reimplements against the graph shape."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise NotImplementedError(_NOT_IMPLEMENTED)


class StepIntegrator:
    """Stub. Phase 3b reimplements against the graph shape."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise NotImplementedError(_NOT_IMPLEMENTED)


__all__ = ["StepCreatorPipeline", "StepIntegrator"]
