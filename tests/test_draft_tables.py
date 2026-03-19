"""Integration tests for DraftStep and DraftPipeline table creation, CRUD, and constraints."""
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.state import DraftStep, DraftPipeline


class TestDraftStepTableCreation:
    """Verify init_pipeline_db() creates the draft_steps table correctly."""

    def test_table_creation(self):
        """init_pipeline_db() with in-memory engine creates draft_steps table."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            assert "draft_steps" in tables
        finally:
            engine.dispose()

    def test_index_creation(self):
        """draft_steps table has ix_draft_steps_status and ix_draft_steps_name indexes."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            indexes = inspector.get_indexes("draft_steps")
            index_names = {idx["name"] for idx in indexes}
            assert "ix_draft_steps_status" in index_names
            assert "ix_draft_steps_name" in index_names
        finally:
            engine.dispose()

    def test_unique_constraint_on_name(self):
        """Inserting two DraftStep rows with same name raises IntegrityError."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            code = {"instructions": "x", "step": "x", "extractions": {}, "prompts": {}}
            with Session(engine) as session:
                session.add(DraftStep(name="duplicate", generated_code=code))
                session.commit()
            with pytest.raises(IntegrityError):
                with Session(engine) as session:
                    session.add(DraftStep(name="duplicate", generated_code=code))
                    session.commit()
        finally:
            engine.dispose()


class TestDraftPipelineTableCreation:
    """Verify init_pipeline_db() creates the draft_pipelines table correctly."""

    def test_table_creation(self):
        """init_pipeline_db() with in-memory engine creates draft_pipelines table."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            assert "draft_pipelines" in tables
        finally:
            engine.dispose()

    def test_index_creation(self):
        """draft_pipelines table has ix_draft_pipelines_status index."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            indexes = inspector.get_indexes("draft_pipelines")
            index_names = {idx["name"] for idx in indexes}
            assert "ix_draft_pipelines_status" in index_names
        finally:
            engine.dispose()

    def test_unique_constraint_on_name(self):
        """Inserting two DraftPipeline rows with same name raises IntegrityError."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            structure = {"steps": ["step_a"], "strategy": "sequential"}
            with Session(engine) as session:
                session.add(DraftPipeline(name="duplicate", structure=structure))
                session.commit()
            with pytest.raises(IntegrityError):
                with Session(engine) as session:
                    session.add(DraftPipeline(name="duplicate", structure=structure))
                    session.commit()
        finally:
            engine.dispose()


class TestDraftStepCRUD:
    """Verify DraftStep insert, retrieve, JSON serialization, and status transitions."""

    def test_insert_and_retrieve(self):
        """DraftStep inserted with required fields is retrievable with correct values."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            code = {
                "instructions": "Parse input",
                "step": "class ParseStep(LLMStep): ...",
                "extractions": {"field": "str"},
                "prompts": {"system": "You are...", "user": "Parse: {input}"},
            }
            record = DraftStep(name="parse_step", generated_code=code, description="Parses input")

            with Session(engine) as session:
                session.add(record)
                session.commit()

            with Session(engine) as session:
                retrieved = session.exec(
                    select(DraftStep).where(DraftStep.name == "parse_step")
                ).one()

            assert retrieved.name == "parse_step"
            assert retrieved.description == "Parses input"
            assert retrieved.generated_code == code
            assert retrieved.status == "draft"
            assert retrieved.id is not None
        finally:
            engine.dispose()

    def test_json_serialization(self):
        """generated_code, test_results, validation_errors store and retrieve nested dicts."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            code = {
                "instructions": "top",
                "step": "class X: pass",
                "extractions": {"nested": {"a": 1}},
                "prompts": {"system": "sys", "user": "usr"},
            }
            test_results = {"passed": True, "cases": [{"name": "t1", "ok": True}]}
            validation_errors = {"errors": ["err1"], "warnings": []}

            with Session(engine) as session:
                session.add(DraftStep(
                    name="json_step",
                    generated_code=code,
                    test_results=test_results,
                    validation_errors=validation_errors,
                ))
                session.commit()

            with Session(engine) as session:
                retrieved = session.exec(
                    select(DraftStep).where(DraftStep.name == "json_step")
                ).one()

            assert retrieved.generated_code["extractions"]["nested"]["a"] == 1
            assert retrieved.test_results["cases"][0]["name"] == "t1"
            assert retrieved.validation_errors["errors"] == ["err1"]
        finally:
            engine.dispose()

    def test_optional_json_fields_nullable(self):
        """DraftStep with only name and generated_code inserts; optional JSON fields are None."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            code = {"instructions": "x", "step": "x", "extractions": {}, "prompts": {}}

            with Session(engine) as session:
                session.add(DraftStep(name="minimal_step", generated_code=code))
                session.commit()

            with Session(engine) as session:
                retrieved = session.exec(
                    select(DraftStep).where(DraftStep.name == "minimal_step")
                ).one()

            assert retrieved.test_results is None
            assert retrieved.validation_errors is None
            assert retrieved.description is None
            assert retrieved.run_id is None
        finally:
            engine.dispose()

    def test_run_id_optional(self):
        """DraftStep accepts run_id=None and run_id set to a UUID string."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            code = {"instructions": "x", "step": "x", "extractions": {}, "prompts": {}}
            uuid_str = "550e8400-e29b-41d4-a716-446655440000"

            with Session(engine) as session:
                session.add(DraftStep(name="no_run_id", generated_code=code, run_id=None))
                session.add(DraftStep(name="with_run_id", generated_code=code, run_id=uuid_str))
                session.commit()

            with Session(engine) as session:
                no_run = session.exec(
                    select(DraftStep).where(DraftStep.name == "no_run_id")
                ).one()
                with_run = session.exec(
                    select(DraftStep).where(DraftStep.name == "with_run_id")
                ).one()

            assert no_run.run_id is None
            assert with_run.run_id == uuid_str
        finally:
            engine.dispose()

    def test_status_transitions(self):
        """DraftStep status updates from draft to tested to accepted persist correctly."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            code = {"instructions": "x", "step": "x", "extractions": {}, "prompts": {}}

            with Session(engine) as session:
                session.add(DraftStep(name="transition_step", generated_code=code, status="draft"))
                session.commit()

            with Session(engine) as session:
                step = session.exec(
                    select(DraftStep).where(DraftStep.name == "transition_step")
                ).one()
                step.status = "tested"
                session.add(step)
                session.commit()

            with Session(engine) as session:
                step = session.exec(
                    select(DraftStep).where(DraftStep.name == "transition_step")
                ).one()
                step.status = "accepted"
                session.add(step)
                session.commit()

            with Session(engine) as session:
                final = session.exec(
                    select(DraftStep).where(DraftStep.name == "transition_step")
                ).one()

            assert final.status == "accepted"
        finally:
            engine.dispose()


class TestDraftPipelineCRUD:
    """Verify DraftPipeline insert, retrieve, JSON serialization, and status transitions."""

    def test_insert_and_retrieve(self):
        """DraftPipeline inserted with required fields is retrievable with correct values."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            structure = {
                "steps": ["parse_step", "validate_step"],
                "strategy": "sequential",
                "config": {"timeout": 30},
            }
            record = DraftPipeline(name="my_pipeline", structure=structure)

            with Session(engine) as session:
                session.add(record)
                session.commit()

            with Session(engine) as session:
                retrieved = session.exec(
                    select(DraftPipeline).where(DraftPipeline.name == "my_pipeline")
                ).one()

            assert retrieved.name == "my_pipeline"
            assert retrieved.structure == structure
            assert retrieved.status == "draft"
            assert retrieved.id is not None
        finally:
            engine.dispose()

    def test_json_serialization(self):
        """structure and compilation_errors store and retrieve nested dicts correctly."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            structure = {
                "steps": ["a", "b"],
                "strategy": "sequential",
                "meta": {"author": "test", "version": 2},
            }
            compilation_errors = {
                "errors": [{"step": "a", "msg": "missing field"}],
                "count": 1,
            }

            with Session(engine) as session:
                session.add(DraftPipeline(
                    name="json_pipeline",
                    structure=structure,
                    compilation_errors=compilation_errors,
                ))
                session.commit()

            with Session(engine) as session:
                retrieved = session.exec(
                    select(DraftPipeline).where(DraftPipeline.name == "json_pipeline")
                ).one()

            assert retrieved.structure["meta"]["version"] == 2
            assert retrieved.compilation_errors["errors"][0]["step"] == "a"
            assert retrieved.compilation_errors["count"] == 1
        finally:
            engine.dispose()

    def test_optional_json_fields_nullable(self):
        """DraftPipeline with only name and structure inserts; compilation_errors is None."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            structure = {"steps": ["only_step"], "strategy": "sequential"}

            with Session(engine) as session:
                session.add(DraftPipeline(name="minimal_pipeline", structure=structure))
                session.commit()

            with Session(engine) as session:
                retrieved = session.exec(
                    select(DraftPipeline).where(DraftPipeline.name == "minimal_pipeline")
                ).one()

            assert retrieved.compilation_errors is None
        finally:
            engine.dispose()

    def test_status_transitions(self):
        """DraftPipeline status update to error stores compilation_errors simultaneously."""
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            structure = {"steps": ["bad_step"], "strategy": "sequential"}

            with Session(engine) as session:
                session.add(DraftPipeline(name="error_pipeline", structure=structure))
                session.commit()

            errors = {"errors": [{"step": "bad_step", "msg": "undefined reference"}]}
            with Session(engine) as session:
                pipeline = session.exec(
                    select(DraftPipeline).where(DraftPipeline.name == "error_pipeline")
                ).one()
                pipeline.status = "error"
                pipeline.compilation_errors = errors
                session.add(pipeline)
                session.commit()

            with Session(engine) as session:
                final = session.exec(
                    select(DraftPipeline).where(DraftPipeline.name == "error_pipeline")
                ).one()

            assert final.status == "error"
            assert final.compilation_errors["errors"][0]["msg"] == "undefined reference"
        finally:
            engine.dispose()
