"""Tests for EvalRunner: mock step returning fixed output, verify run counts."""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals.models import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationRun,
)
from llm_pipeline.evals.runner import EvalRunner


@pytest.fixture()
def engine():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(e)
    return e


@pytest.fixture()
def seeded_dataset(engine):
    """Insert a dataset with 2 cases: one that matches expected, one that doesn't."""
    with Session(engine) as session:
        ds = EvaluationDataset(
            name="test_ds",
            target_type="step",
            target_name="mock_step",
        )
        session.add(ds)
        session.flush()

        session.add(EvaluationCase(
            dataset_id=ds.id,
            name="pass_case",
            inputs={"text": "good"},
            expected_output={"sentiment": "positive"},
        ))
        session.add(EvaluationCase(
            dataset_id=ds.id,
            name="fail_case",
            inputs={"text": "bad"},
            expected_output={"sentiment": "positive"},  # will mismatch
        ))
        session.commit()
        return ds.id


class TestEvalRunner:
    def test_run_dataset_creates_run_with_correct_counts(self, engine, seeded_dataset):
        """Mock _resolve_task to return a simple task_fn + no evaluators."""

        def mock_task_fn(inputs: dict) -> dict:
            # "good" -> positive, anything else -> negative
            if inputs.get("text") == "good":
                return {"sentiment": "positive"}
            return {"sentiment": "negative"}

        runner = EvalRunner(engine=engine)

        with patch.object(runner, "_resolve_task", return_value=(mock_task_fn, None)):
            run_id = runner.run_dataset(seeded_dataset)

        with Session(engine) as session:
            run = session.exec(
                select(EvaluationRun).where(EvaluationRun.id == run_id)
            ).first()
            assert run is not None
            assert run.status == "completed"
            assert run.total_cases == 2
            # Without evaluators, all cases pass (no assertions to fail)
            assert run.passed == 2

    def test_run_dataset_with_evaluators(self, engine, seeded_dataset):
        """Custom evaluator that checks sentiment field."""
        from pydantic_evals.evaluators import Evaluator

        class SentimentEval(Evaluator):
            def evaluate(self, ctx):
                if ctx.expected_output and "sentiment" in ctx.expected_output:
                    match = ctx.output.get("sentiment") == ctx.expected_output["sentiment"]
                    return {"sentiment_match": match}
                return {}

        def mock_task_fn(inputs: dict) -> dict:
            if inputs.get("text") == "good":
                return {"sentiment": "positive"}
            return {"sentiment": "negative"}

        runner = EvalRunner(engine=engine)

        with patch.object(
            runner, "_resolve_task",
            return_value=(mock_task_fn, [SentimentEval()]),
        ):
            run_id = runner.run_dataset(seeded_dataset)

        with Session(engine) as session:
            run = session.exec(
                select(EvaluationRun).where(EvaluationRun.id == run_id)
            ).first()
            assert run.status == "completed"
            assert run.total_cases == 2
            assert run.passed == 1
            assert run.failed == 1

            results = session.exec(
                select(EvaluationCaseResult)
                .where(EvaluationCaseResult.run_id == run_id)
            ).all()
            assert len(results) == 2

            by_name = {r.case_name: r for r in results}
            assert by_name["pass_case"].passed is True
            assert by_name["fail_case"].passed is False

    def test_run_dataset_by_name(self, engine, seeded_dataset):
        def mock_task_fn(inputs: dict) -> dict:
            return {"sentiment": "positive"}

        runner = EvalRunner(engine=engine)

        with patch.object(runner, "_resolve_task", return_value=(mock_task_fn, None)):
            run_id = runner.run_dataset_by_name("test_ds")

        with Session(engine) as session:
            run = session.exec(
                select(EvaluationRun).where(EvaluationRun.id == run_id)
            ).first()
            assert run.status == "completed"

    def test_run_dataset_by_name_not_found(self, engine):
        runner = EvalRunner(engine=engine)
        with pytest.raises(ValueError, match="not found"):
            runner.run_dataset_by_name("nonexistent")

    def test_run_dataset_no_cases_raises(self, engine):
        with Session(engine) as session:
            ds = EvaluationDataset(
                name="empty_ds", target_type="step", target_name="x",
            )
            session.add(ds)
            session.commit()
            ds_id = ds.id

        runner = EvalRunner(engine=engine)
        with pytest.raises(ValueError, match="no cases"):
            runner.run_dataset(ds_id)

    def test_resolve_task_failure_marks_status_failed(self, engine, seeded_dataset):
        """When _resolve_task itself raises, run is marked failed."""
        runner = EvalRunner(engine=engine)

        with patch.object(
            runner, "_resolve_task",
            side_effect=ValueError("step not found"),
        ):
            with pytest.raises(ValueError, match="step not found"):
                runner.run_dataset(seeded_dataset)

        with Session(engine) as session:
            run = session.exec(select(EvaluationRun)).first()
            assert run.status == "failed"
            assert "step not found" in run.error_message


class TestResolveStepTaskHonoursDBOverride:
    """Regression coverage for the runner honouring StepModelConfig.

    Previously ``_resolve_step_task`` only consulted ``step_def.model`` and
    the pipeline default. After the shared resolver refactor, a DB row
    for the step's (pipeline, step_name) must win — same as prod runtime.
    """

    def _fake_step_def(self, model: str | None):
        from dataclasses import dataclass, field
        from typing import Optional as _Opt

        @dataclass
        class _SD:
            step_class: type = type("MyStep", (), {"__name__": "MyStep"})
            prompt_name: _Opt[str] = None
            instructions: _Opt[type] = None
            evaluators: list = field(default_factory=list)
            model: _Opt[str] = None

            @property
            def step_name(self) -> str:
                return "my_step"

            @property
            def resolved_prompt_name(self) -> str:
                return self.prompt_name or self.step_name

        sd = _SD()
        sd.model = model
        return sd

    def test_db_override_beats_step_def_model(self, engine):
        """StepModelConfig row for the step pipeline+name wins."""
        from llm_pipeline.db.step_config import StepModelConfig
        from llm_pipeline.evals.runner import EvalRunner

        with Session(engine) as session:
            session.add(
                StepModelConfig(
                    pipeline_name="my_pipeline",
                    step_name="my_step",
                    model="db-override-model",
                )
            )
            session.commit()

        runner = EvalRunner(engine=engine)

        captured: dict = {}

        def stub_find(step_name):
            return (
                self._fake_step_def(model="step-def-model"),
                None,
                "pipeline-default",
                "my_pipeline",
            )

        def stub_build(step_def, input_data_cls, step_model, variant_delta=None):
            captured["step_model"] = step_model

            def task(inputs):  # pragma: no cover — not invoked here
                return {}

            return task

        with patch.object(runner, "_find_step_def", side_effect=stub_find), \
             patch.object(runner, "_build_step_task_fn", side_effect=stub_build):
            runner._resolve_step_task("my_step", model=None, variant_delta=None)

        assert captured["step_model"] == "db-override-model"

    def test_no_db_row_uses_step_def_model(self, engine):
        """No DB override → still falls through to step_def.model."""
        from llm_pipeline.evals.runner import EvalRunner

        runner = EvalRunner(engine=engine)
        captured: dict = {}

        def stub_find(step_name):
            return (
                self._fake_step_def(model="step-def-model"),
                None,
                "pipeline-default",
                "my_pipeline",
            )

        def stub_build(step_def, input_data_cls, step_model, variant_delta=None):
            captured["step_model"] = step_model

            def task(inputs):  # pragma: no cover
                return {}

            return task

        with patch.object(runner, "_find_step_def", side_effect=stub_find), \
             patch.object(runner, "_build_step_task_fn", side_effect=stub_build):
            runner._resolve_step_task("my_step", model=None, variant_delta=None)

        assert captured["step_model"] == "step-def-model"

    def test_variant_model_beats_db_override(self, engine):
        """Variant override is applied on top of the resolved base."""
        from llm_pipeline.db.step_config import StepModelConfig
        from llm_pipeline.evals.runner import EvalRunner

        with Session(engine) as session:
            session.add(
                StepModelConfig(
                    pipeline_name="my_pipeline",
                    step_name="my_step",
                    model="db-override-model",
                )
            )
            session.commit()

        runner = EvalRunner(engine=engine)
        captured: dict = {}

        def stub_find(step_name):
            return (
                self._fake_step_def(model="step-def-model"),
                None,
                "pipeline-default",
                "my_pipeline",
            )

        def stub_build(step_def, input_data_cls, step_model, variant_delta=None):
            captured["step_model"] = step_model

            def task(inputs):  # pragma: no cover
                return {}

            return task

        with patch.object(runner, "_find_step_def", side_effect=stub_find), \
             patch.object(runner, "_build_step_task_fn", side_effect=stub_build):
            runner._resolve_step_task(
                "my_step",
                model=None,
                variant_delta={"model": "variant-model"},
            )

        assert captured["step_model"] == "variant-model"


class TestRunSnapshotPopulation:
    """Tests for _build_run_snapshot and snapshot fields on EvaluationRun."""

    def _make_step_def(self, step_name="mock_step", model=None, instructions=None):
        """Create a minimal fake StepDefinition."""
        from dataclasses import dataclass, field
        from typing import Optional as _Opt

        captured_step_name = step_name

        @dataclass
        class _SD:
            step_class: type = type("MockStep", (), {"__name__": "MockStep"})
            prompt_name: _Opt[str] = None
            instructions: _Opt[type] = None
            evaluators: list = field(default_factory=list)
            model: _Opt[str] = None

            @property
            def step_name(self) -> str:
                return captured_step_name

            @property
            def resolved_prompt_name(self) -> str:
                return self.prompt_name or self.step_name

        sd = _SD()
        sd.model = model
        sd.instructions = instructions
        return sd

    def test_run_populates_snapshots_step_target(self, engine):
        """Step-target run populates all four snapshot columns with correct shapes."""
        from pydantic import BaseModel

        # Create instructions model
        class MockInstructions(BaseModel):
            sentiment: str = ""
            confidence: float = 0.0

        # Seed dataset + cases
        with Session(engine) as session:
            ds = EvaluationDataset(
                name="snap_step_ds",
                target_type="step",
                target_name="mock_step",
            )
            session.add(ds)
            session.flush()
            session.add(EvaluationCase(
                dataset_id=ds.id,
                name="case_a",
                inputs={"text": "hello"},
                version="1.0",
            ))
            session.add(EvaluationCase(
                dataset_id=ds.id,
                name="case_b",
                inputs={"text": "world"},
                version="1.1",
            ))
            session.commit()
            ds_id = ds.id

        step_def = self._make_step_def(
            step_name="mock_step",
            model="gpt-4o",
            instructions=MockInstructions,
        )
        step_def.prompt_name = "mock_step"

        def mock_task_fn(inputs: dict) -> dict:
            return {"sentiment": "positive"}

        runner = EvalRunner(engine=engine)

        # Patch _find_step_def to return our fake step def, and stub
        # the Phoenix version-id lookup so the snapshot stamps a
        # deterministic value without needing a live Phoenix.
        with patch.object(
            runner, "_find_step_def",
            return_value=(step_def, None, "gpt-4o", "test_pipeline"),
        ), patch.object(
            runner, "_resolve_task",
            return_value=(mock_task_fn, None),
        ), patch(
            "llm_pipeline.evals.runner._phoenix_latest_version_id",
            return_value="phx_v_stub",
        ):
            run_id = runner.run_dataset(ds_id)

        with Session(engine) as session:
            run = session.exec(
                select(EvaluationRun).where(EvaluationRun.id == run_id)
            ).first()

            # case_versions: {str_id: version_str}
            assert run.case_versions is not None
            assert all(isinstance(k, str) for k in run.case_versions.keys())
            assert all("." in v for v in run.case_versions.values())
            assert len(run.case_versions) == 2

            # prompt_versions: legacy split-key shape now stamped with
            # the same Phoenix version_id for both system + user roles.
            assert run.prompt_versions is not None
            assert run.prompt_versions["mock_step.system_instruction"]["system"] == "phx_v_stub"
            assert run.prompt_versions["mock_step.user_prompt"]["user"] == "phx_v_stub"

            # model_snapshot: {step_name: model_id} single-entry
            assert run.model_snapshot is not None
            assert run.model_snapshot == {"mock_step": "gpt-4o"}

            # instructions_schema_snapshot: flat schema dict
            assert run.instructions_schema_snapshot is not None
            assert "properties" in run.instructions_schema_snapshot
            assert "sentiment" in run.instructions_schema_snapshot["properties"]

    def test_run_populates_snapshots_pipeline_target(self, engine):
        """Pipeline-target run populates snapshots keyed by step_name."""
        from pydantic import BaseModel

        class StepAInstructions(BaseModel):
            result_a: str = ""

        class StepBInstructions(BaseModel):
            result_b: int = 0

        # Seed dataset + case
        with Session(engine) as session:
            ds = EvaluationDataset(
                name="snap_pipe_ds",
                target_type="pipeline",
                target_name="test_pipeline",
            )
            session.add(ds)
            session.flush()
            session.add(EvaluationCase(
                dataset_id=ds.id,
                name="pipe_case",
                inputs={"x": 1},
                version="1.0",
            ))
            session.commit()
            ds_id = ds.id

        # Build fake step defs
        step_def_a = self._make_step_def(
            step_name="step_a", model="gpt-4o", instructions=StepAInstructions
        )
        step_def_b = self._make_step_def(
            step_name="step_b", model="claude-3", instructions=StepBInstructions
        )
        # Patch step_class.__name__ for auto-discovery
        step_def_a.step_class = type("StepAStep", (), {"__name__": "StepAStep"})
        step_def_b.step_class = type("StepBStep", (), {"__name__": "StepBStep"})

        # Build a fake pipeline class with STRATEGIES
        class FakeStrategy:
            def get_steps(self):
                return [step_def_a, step_def_b]

        class FakeStrategies:
            STRATEGIES = [FakeStrategy]

        class FakePipelineCls:
            STRATEGIES = FakeStrategies
            _default_model = "default-model"

        runner = EvalRunner(
            engine=engine,
            introspection_registry={"test_pipeline": FakePipelineCls},
        )

        def mock_task_fn(inputs: dict) -> dict:
            return {"step_a": {"result_a": "ok"}, "step_b": {"result_b": 42}}

        with patch.object(
            runner, "_resolve_task", return_value=(mock_task_fn, None),
        ), patch(
            "llm_pipeline.evals.runner._phoenix_latest_version_id",
            return_value="phx_v_stub",
        ):
            run_id = runner.run_dataset(ds_id)

        with Session(engine) as session:
            run = session.exec(
                select(EvaluationRun).where(EvaluationRun.id == run_id)
            ).first()

            # case_versions
            assert run.case_versions is not None
            assert len(run.case_versions) == 1

            # prompt_versions: per-step legacy split-key shape stamped
            # with the same Phoenix version_id for both roles.
            assert run.prompt_versions is not None
            assert (
                run.prompt_versions["step_a"]["step_a.system_instruction"]["system"]
                == "phx_v_stub"
            )
            assert (
                run.prompt_versions["step_b"]["step_b.system_instruction"]["system"]
                == "phx_v_stub"
            )

            # model_snapshot: {step_name: model_id} one entry per step
            assert run.model_snapshot is not None
            assert len(run.model_snapshot) == 2
            assert run.model_snapshot["step_a"] == "gpt-4o"
            assert run.model_snapshot["step_b"] == "claude-3"

            # instructions_schema_snapshot: {step_name: schema_dict}
            assert run.instructions_schema_snapshot is not None
            assert "step_a" in run.instructions_schema_snapshot
            assert "properties" in run.instructions_schema_snapshot["step_a"]
            assert "result_a" in run.instructions_schema_snapshot["step_a"]["properties"]
            assert "step_b" in run.instructions_schema_snapshot
            assert "result_b" in run.instructions_schema_snapshot["step_b"]["properties"]
