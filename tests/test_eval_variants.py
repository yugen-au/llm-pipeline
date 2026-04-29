"""Legacy test file — pending Phase 3b rewrite or retirement.

The pydantic-graph migration retired the PipelineConfig / PipelineStrategy / @step_definition / PipelineExtraction / creator / eval-runner stack this module exercised. Tests get rewritten or deleted as Phase 3b lands.
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="Pending Phase 3b rewrite — exercised legacy stack retired in pydantic-graph migration.",
)
