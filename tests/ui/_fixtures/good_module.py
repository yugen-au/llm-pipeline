"""Fixture module: one concrete PipelineConfig subclass."""
from llm_pipeline.pipeline import PipelineConfig


class AlphaPipeline(PipelineConfig):
    """Concrete subclass defined locally."""

    @classmethod
    def seed_prompts(cls, engine):
        pass
