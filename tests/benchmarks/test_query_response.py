"""Legacy ``PipelineStepState`` benchmarks — retired in pydantic-graph migration.

The original benchmark seeded 10k ``PipelineRun`` + 30k
``PipelineStepState`` rows and measured query latencies on the run /
step list endpoints. ``PipelineStepState`` is gone (replaced by
``PipelineNodeSnapshot``); the equivalent benchmark is rewritten
against the new schema in a Phase 3 follow-up.
"""
import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Legacy PipelineStepState benchmarks retired in pydantic-graph "
        "migration Phase 2. To be rewritten against PipelineNodeSnapshot "
        "in a Phase 3 follow-up."
    ),
)
