"""Legacy ``PipelineConfig.execute`` tests — retired pending Phase 3 rewrite.

The original module exercised ``PipelineConfig`` / ``PipelineStrategy``
/ ``Bind``-list pipeline execution against ``PipelineStepState``. The
pydantic-graph migration replaces all three: pipelines are graph
objects (``llm_pipeline.graph.Pipeline``), the legacy state table is
gone (``PipelineNodeSnapshot`` replaces it), and execution flows
through ``llm_pipeline.graph.runtime.run_pipeline``.

Phase 3 deletes the legacy classes and rewrites these tests against
the new runtime. Until then this module is a no-op.
"""
import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Legacy PipelineConfig.execute path retired in pydantic-graph "
        "migration Phase 2. Tests rewrite lands in Phase 3 against "
        "llm_pipeline.graph.runtime.run_pipeline."
    ),
)
