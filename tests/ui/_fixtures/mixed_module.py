"""Fixture module: one local subclass + one re-exported subclass."""
from llm_pipeline.pipeline import PipelineConfig
from tests.ui._fixtures.good_module import AlphaPipeline  # noqa: F401 - re-export


class BetaPipeline(PipelineConfig):
    """Locally defined -- should be registered."""
    pass
