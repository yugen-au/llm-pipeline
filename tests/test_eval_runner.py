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
