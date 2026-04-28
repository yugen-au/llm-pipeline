"""End-to-end smoke test for the framework's full Langfuse instrumentation.

Constructs a minimal real ``PipelineConfig`` (with ``Bind`` + ``StepInputs``,
a real step + extraction, prompts seeded into SQLite) and runs ``execute()``
with a ``TestModel`` so no LLM API key is required. Verifies that the
PipelineObserver emits the full trace structure end-to-end:

    pipeline.smoke_pipeline                     [root span]
      pipeline-run input/output, session_id=run_id, tags=[smoke_pipeline]
    +- step.widget_detection                    [step span]
       +- (cache.lookup, cache.miss span events if use_cache=True)
       +- TestModel                             [LLM generation, pydantic-ai auto]
       +- extraction.WidgetExtraction           [extraction span]

Run: uv run python scripts/smoke_pipeline.py

Then in Langfuse UI find the trace ``pipeline.smoke_pipeline`` and confirm
the nesting + span events.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import ClassVar, List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

required = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
missing = [k for k in required if not os.environ.get(k)]
if missing:
    print(f"Missing env vars: {missing}", file=sys.stderr)
    sys.exit(1)

from sqlmodel import Field, Session, SQLModel, create_engine  # noqa: E402

from llm_pipeline import (  # noqa: E402
    LLMResultMixin,
    LLMStep,
    PipelineConfig,
    PipelineDatabaseRegistry,
    PipelineExtraction,
    PipelineStrategies,
    PipelineStrategy,
    step_definition,
)
from llm_pipeline.db.prompt import Prompt  # noqa: E402
from llm_pipeline.inputs import PipelineInputData, StepInputs  # noqa: E402
from llm_pipeline.types import StepCallParams  # noqa: E402
from llm_pipeline.wiring import Bind, FromInput, FromOutput  # noqa: E402


# ---------------------------------------------------------------------------
# Domain model + pipeline shape
# ---------------------------------------------------------------------------


class Widget(SQLModel, table=True):
    __tablename__ = "smoke_widgets"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str


class WidgetPipelineInput(PipelineInputData):
    data: str


class WidgetDetectionInputs(StepInputs):
    data: str


class WidgetDetectionInstructions(LLMResultMixin):
    widget_count: int
    category: str

    example: ClassVar[dict] = {
        "widget_count": 3,
        "category": "gadgets",
        "notes": "Found 3 gadgets",
    }


class WidgetExtraction(PipelineExtraction, model=Widget):
    class FromWidgetDetectionInputs(StepInputs):
        widget_count: int
        category: str

    def from_widget_detection(
        self, inputs: FromWidgetDetectionInputs,
    ) -> list[Widget]:
        return [
            Widget(name=f"widget_{i}", category=inputs.category)
            for i in range(inputs.widget_count)
        ]


@step_definition(
    inputs=WidgetDetectionInputs,
    instructions=WidgetDetectionInstructions,
    default_system_key="widget_detection.system_instruction",
    default_user_key="widget_detection.user_prompt",
)
class WidgetDetectionStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [StepCallParams(variables={"data": self.inputs.data})]


class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_bindings(self) -> List[Bind]:
        return [
            Bind(
                step=WidgetDetectionStep,
                inputs=WidgetDetectionInputs.sources(
                    data=FromInput("data"),
                ),
                extractions=[
                    Bind(
                        extraction=WidgetExtraction,
                        inputs=WidgetExtraction.FromWidgetDetectionInputs.sources(
                            widget_count=FromOutput(
                                WidgetDetectionStep, field="widget_count",
                            ),
                            category=FromOutput(
                                WidgetDetectionStep, field="category",
                            ),
                        ),
                    ),
                ],
            ),
        ]


class SmokeRegistry(PipelineDatabaseRegistry, models=[Widget]):
    pass


class SmokeStrategies(PipelineStrategies, strategies=[DefaultStrategy]):
    pass


class SmokePipeline(
    PipelineConfig,
    registry=SmokeRegistry,
    strategies=SmokeStrategies,
):
    INPUT_DATA = WidgetPipelineInput


# ---------------------------------------------------------------------------
# Run it
# ---------------------------------------------------------------------------


def _seed_prompts(session: Session) -> None:
    session.add(Prompt(
        prompt_key="widget_detection.system_instruction",
        prompt_name="Widget Detection System",
        prompt_type="system",
        category="smoke",
        step_name="widget_detection",
        content="You are a widget detector. Return widget_count and category.",
        version="1.0",
    ))
    session.add(Prompt(
        prompt_key="widget_detection.user_prompt",
        prompt_name="Widget Detection User",
        prompt_type="user",
        category="smoke",
        step_name="widget_detection",
        content="Analyze this data: {data}",
        version="1.0",
    ))
    session.commit()


def main() -> None:
    # check_same_thread=False so the in-memory SQLite engine works with
    # the framework's threaded execution path (pydantic-ai instrumentation
    # + flush logic touches the connection from a different thread than
    # the one that created it).
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as seed_session:
        _seed_prompts(seed_session)

    # The 'test' model string is resolved by pydantic-ai to TestModel,
    # which returns synthetic structured output matching Instructions
    # schema (no LLM API key required). pydantic-ai's instrumentation
    # still produces the generation observation in Langfuse, and the
    # string is what gets persisted into PipelineStepState.model_name
    # so SQLite serialization works.
    pipeline = SmokePipeline(
        model="test",
        engine=engine,
    )
    pipeline.execute(input_data={"data": "raw smoke-test input"})

    print(f"Run completed. run_id={pipeline.run_id}")
    print(
        f"Open {os.environ['LANGFUSE_BASE_URL']} -> Traces and look for "
        "'pipeline.smoke_pipeline' (filter by tag = smoke_pipeline)."
    )


if __name__ == "__main__":
    main()
