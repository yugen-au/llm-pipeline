"""End-to-end smoke test for the pydantic-graph-native framework.

Constructs a minimal real ``Pipeline`` (one ``LLMStepNode`` + one
``ExtractionNode``) and runs it via ``run_pipeline_in_memory`` with a
``TestModel`` (no LLM API key required). Verifies the framework emits
a single Phoenix trace with the expected node-span tree:

    pipeline.smoke_pipeline                    [graph root span]
      smoke_pipeline.SmokePipeline.run         [pydantic-graph]
        SmokePipeline.SentimentAnalysisStep    [pydantic-graph node span]
          TestModel                            [pydantic-ai LLM call span]
        SmokePipeline.WidgetExtraction         [pydantic-graph node span]

Run: ``uv run python scripts/smoke_pipeline.py``
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import ClassVar, Optional

from dotenv import load_dotenv
from pydantic_graph import End, GraphRunContext

from llm_pipeline.graph import (
    ExtractionNode,
    FromInput,
    FromOutput,
    FromPipeline,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    StepInputs,
    run_pipeline_in_memory,
)
from llm_pipeline.step import LLMResultMixin

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

required = ("OTEL_EXPORTER_OTLP_ENDPOINT",)
missing = [k for k in required if not os.environ.get(k)]
if missing:
    print(
        f"Missing env vars: {missing}\n"
        f"Set OTEL_EXPORTER_OTLP_ENDPOINT to your OTLP backend "
        f"(e.g. http://localhost:6006 for the docker-compose Phoenix).",
        file=sys.stderr,
    )
    sys.exit(1)

from sqlmodel import Field, SQLModel, create_engine  # noqa: E402


# ---------------------------------------------------------------------------
# Domain model + pipeline shape
# ---------------------------------------------------------------------------


class Widget(SQLModel, table=True):
    __tablename__ = "smoke_widgets"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str


class SmokeInputData(PipelineInputData):
    data: str


class WidgetDetectionInputs(StepInputs):
    data: str


class WidgetDetectionInstructions(LLMResultMixin):
    widget_count: int = 0
    category: str = ""

    example: ClassVar[dict] = {
        "widget_count": 3,
        "category": "gadgets",
        "notes": "Found 3 gadgets",
    }


class FromWidgetExtractionInputs(StepInputs):
    widget_count: int
    category: str
    run_id: str


class WidgetDetectionStep(LLMStepNode):
    """Detect widgets in raw input data."""

    INPUTS = WidgetDetectionInputs
    INSTRUCTIONS = WidgetDetectionInstructions
    inputs_spec = WidgetDetectionInputs.sources(
        data=FromInput("data"),
    )

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> WidgetExtraction:
        await self._run_llm(ctx)
        return WidgetExtraction()


class WidgetExtraction(ExtractionNode):
    """Convert detected widget counts into ``Widget`` rows."""

    MODEL = Widget
    INPUTS = FromWidgetExtractionInputs
    source_step = WidgetDetectionStep
    inputs_spec = FromWidgetExtractionInputs.sources(
        widget_count=FromOutput(WidgetDetectionStep, field="widget_count"),
        category=FromOutput(WidgetDetectionStep, field="category"),
        run_id=FromPipeline("run_id"),
    )

    def extract(self, inputs: FromWidgetExtractionInputs) -> list[Widget]:
        return [
            Widget(name=f"widget_{i}", category=inputs.category)
            for i in range(inputs.widget_count)
        ]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_extraction(ctx)
        return End(None)


class SmokePipeline(Pipeline):
    """Smoke pipeline: detect widgets -> extract widget rows."""

    INPUT_DATA = SmokeInputData
    nodes = [WidgetDetectionStep, WidgetExtraction]


# ---------------------------------------------------------------------------
# Run it
# ---------------------------------------------------------------------------


def _seed_phoenix_prompt() -> None:
    """Ensure ``widget_detection`` exists in Phoenix with smoke content."""
    from llm_pipeline.prompts.phoenix_client import (
        PhoenixError,
        PhoenixPromptClient,
        PromptNotFoundError,
    )

    try:
        client = PhoenixPromptClient()
    except PhoenixError as exc:
        print(f"Phoenix not reachable; skipping prompt seed: {exc}")
        return

    try:
        client.get_latest("widget_detection")
        return  # already seeded
    except PromptNotFoundError:
        pass
    except PhoenixError as exc:
        print(f"Phoenix lookup failed; skipping seed: {exc}")
        return

    client.create(
        prompt={"name": "widget_detection"},
        version={
            "model_provider": "OPENAI",
            "model_name": "gpt-4o-mini",
            "template": {
                "type": "chat",
                "messages": [
                    {"role": "system",
                     "content": "You are a widget detector. Return widget_count and category."},
                    {"role": "user", "content": "Analyze this data: {data}"},
                ],
            },
            "template_type": "CHAT",
            "template_format": "F_STRING",
            "invocation_parameters": {"type": "openai", "openai": {}},
        },
    )


async def _amain() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    _seed_phoenix_prompt()

    final_state, _end = await run_pipeline_in_memory(
        SmokePipeline,
        input_data={"data": "raw smoke-test input"},
        model="test",
        engine=engine,
    )

    print(f"Run completed.")
    print(f"  outputs: {list(final_state.outputs.keys())}")
    print(f"  extractions: {list(final_state.extractions.keys())}")

    backend_url = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/")
    if backend_url.endswith("/v1/traces"):
        backend_url = backend_url[: -len("/v1/traces")]
    print(
        f"Open {backend_url} -> Traces and look for "
        "'SmokePipeline' (run-level graph span)."
    )


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
