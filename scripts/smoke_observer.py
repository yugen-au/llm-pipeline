"""End-to-end smoke test for PipelineObserver + pydantic-ai instrumentation.

Verifies the full chain:
  1. ``observability.configure()`` initializes Langfuse + ``Agent.instrument_all()``
  2. ``PipelineObserver.pipeline_run()`` opens a root trace span
  3. ``PipelineObserver.step()`` opens a child step span
  4. Inside the step, a ``pydantic_ai.Agent.run_sync()`` produces a generation
     observation that auto-nests under the step span (via OTEL context).
  5. Span events (``cache.hit`` etc.) attach to the active span as metadata.

Uses ``TestModel`` so the script doesn't require an LLM API key — the
generation observation still gets created with the model name and
synthetic response.

Run: uv run python scripts/smoke_observer.py

Then in the Langfuse UI you should see one trace ``pipeline.observer_smoke``
with this structure::

    pipeline.observer_smoke    [trace span]
      step.demo                [child span; cache.hit event attached]
        TestModel              [child generation, auto-instrumented]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

required = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
missing = [k for k in required if not os.environ.get(k)]
if missing:
    print(f"Missing env vars: {missing}", file=sys.stderr)
    sys.exit(1)

from llm_pipeline.observability import PipelineObserver, configure  # noqa: E402
from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402

# Bootstrap Langfuse + pydantic-ai instrumentation.
assert configure(environment="smoke-test") is True, "configure() returned False unexpectedly"

agent = Agent(model=TestModel(), system_prompt="You are a smoke test agent.")

obs = PipelineObserver(run_id="observer-smoke-run", pipeline_name="observer_smoke")

with obs.pipeline_run(
    input_data={"reason": "exercising observer + pydantic-ai instrumentation"},
    tags=["smoke-test", "observer"],
):
    with obs.step(step_name="demo", step_number=1, instructions_class="DemoInstructions"):
        # Span event attaches to the demo step span as metadata
        obs.cache_hit(input_hash="deadbeef")
        # The Agent.run_sync call produces a generation that auto-nests
        # under the demo step span via OTEL context propagation.
        result = agent.run_sync("Say hello.")
        print(f"Agent output: {result.output}")

obs.shutdown()

print("Observer smoke test complete.")
print(
    f"Open {os.environ['LANGFUSE_BASE_URL']} -> Traces and look for "
    "'pipeline.observer_smoke' with a nested 'step.demo' span and a "
    "TestModel generation under it."
)
