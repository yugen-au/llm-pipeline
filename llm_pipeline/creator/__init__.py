"""
llm_pipeline.creator - Meta-pipeline for generating step scaffold code.

Requires jinja2: pip install llm-pipeline[creator]
"""

try:
    import jinja2  # noqa: F401
except ImportError:
    raise ImportError(
        "llm_pipeline.creator requires jinja2. Install with: pip install llm-pipeline[creator]"
    )

from llm_pipeline.creator.pipeline import StepCreatorPipeline

__all__ = ["StepCreatorPipeline"]
