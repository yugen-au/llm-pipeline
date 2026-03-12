"""
TextAnalyzer demo pipeline for the llm-pipeline framework.

Demonstrates a 3-step sequential pipeline: sentiment analysis,
topic extraction, and summary generation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_pipeline.demo.pipeline import TextAnalyzerPipeline

__all__ = ["TextAnalyzerPipeline"]
