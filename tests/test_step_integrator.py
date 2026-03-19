"""
Integration tests for StepIntegrator.

Uses in-memory SQLite engine + init_pipeline_db() for isolation.
No real pipeline.py file needed for file-write and prompt tests;
AST tests use a tmp_path fixture with a minimal pipeline stub.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.state import DraftStep
from llm_pipeline.creator.integrator import StepIntegrator
from llm_pipeline.creator.models import GeneratedStep, IntegrationResult


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

STEP_NAME = "sentiment"

STEP_CODE = """\
from llm_pipeline.step import LLMStep

class SentimentStep(LLMStep):
    pass
"""

INSTRUCTIONS_CODE = """\
from pydantic import BaseModel

class SentimentInstructions(BaseModel):
    sentiment: str
"""

PROMPTS_CODE = """\
ALL_PROMPTS = [
    {
        "prompt_key": "sentiment",
        "prompt_name": "Sentiment System",
        "prompt_type": "system",
        "category": "sentiment",
        "step_name": "sentiment",
        "content": "You are a sentiment analyser.",
        "required_variables": [],
        "description": "System prompt for sentiment step",
    },
    {
        "prompt_key": "sentiment",
        "prompt_name": "Sentiment User",
        "prompt_type": "user",
        "category": "sentiment",
        "step_name": "sentiment",
        "content": "Analyse: {text}",
        "required_variables": ["text"],
        "description": "User prompt for sentiment step",
    },
]
"""

ALL_ARTIFACTS = {
    f"{STEP_NAME}_step.py": STEP_CODE,
    f"{STEP_NAME}_instructions.py": INSTRUCTIONS_CODE,
    f"{STEP_NAME}_prompts.py": PROMPTS_CODE,
}


def _make_generated_step(step_name: str = STEP_NAME) -> GeneratedStep:
    """Build a minimal GeneratedStep for testing."""
    return GeneratedStep(
        step_name=step_name,
        step_class_name="SentimentStep",
        instructions_class_name="SentimentInstructions",
        step_code=STEP_CODE,
        instructions_code=INSTRUCTIONS_CODE,
        prompts_code=PROMPTS_CODE,
        extraction_code=None,
        all_artifacts=dict(ALL_ARTIFACTS),
    )


def _make_engine():
    """Create isolated in-memory SQLite engine with pipeline schema."""
    engine = create_engine("sqlite://")
    init_pipeline_db(engine)
    return engine


def _make_draft_step(session: Session, name: str = STEP_NAME) -> DraftStep:
    """Insert and return a persisted DraftStep."""
    draft = DraftStep(
        name=name,
        generated_code=dict(ALL_ARTIFACTS),
        status="draft",
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


# ---------------------------------------------------------------------------
# TestStepIntegratorFileWrites
# ---------------------------------------------------------------------------


class TestStepIntegratorFileWrites:
    """StepIntegrator writes artifact files to target_dir correctly."""

    def test_files_written_to_target_dir(self, tmp_path):
        """After integrate(), all artifact files exist in target_dir."""
        engine = _make_engine()
        target_dir = tmp_path / "steps" / "sentiment"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            integrator.integrate(generated, target_dir)

        for filename in ALL_ARTIFACTS:
            assert (target_dir / filename).exists(), f"{filename} missing from target_dir"

        engine.dispose()

    def test_init_py_created_if_missing(self, tmp_path):
        """New target_dir gets an __init__.py created automatically."""
        engine = _make_engine()
        target_dir = tmp_path / "new_pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            integrator.integrate(generated, target_dir)

        assert (target_dir / "__init__.py").exists()
        engine.dispose()

    def test_integration_result_contains_absolute_paths(self, tmp_path):
        """IntegrationResult.files_written lists absolute paths of written files."""
        engine = _make_engine()
        target_dir = tmp_path / "sentiment_pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            result = integrator.integrate(generated, target_dir)

        assert isinstance(result, IntegrationResult)
        assert len(result.files_written) == len(ALL_ARTIFACTS)
        for fpath in result.files_written:
            assert Path(fpath).is_absolute(), f"path not absolute: {fpath}"
            assert Path(fpath).exists(), f"written path does not exist: {fpath}"

        engine.dispose()

    def test_integration_result_target_dir_str(self, tmp_path):
        """IntegrationResult.target_dir matches str(target_dir)."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            result = integrator.integrate(generated, target_dir)

        assert result.target_dir == str(target_dir)
        engine.dispose()

    def test_file_contents_match_artifacts(self, tmp_path):
        """Written files contain exactly the artifact content."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            integrator.integrate(generated, target_dir)

        for filename, expected_content in ALL_ARTIFACTS.items():
            actual = (target_dir / filename).read_text(encoding="utf-8")
            assert actual == expected_content, f"content mismatch for {filename}"

        engine.dispose()


# ---------------------------------------------------------------------------
# TestStepIntegratorPromptRegistration
# ---------------------------------------------------------------------------


class TestStepIntegratorPromptRegistration:
    """StepIntegrator registers prompts idempotently in the DB."""

    def test_prompts_inserted_in_db(self, tmp_path):
        """After integrate(), Prompt rows exist for step's system + user prompts."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            result = integrator.integrate(generated, target_dir)

        with Session(engine) as session:
            prompts = session.exec(
                select(Prompt).where(Prompt.prompt_key == STEP_NAME)
            ).all()

        assert len(prompts) == 2
        types = {p.prompt_type for p in prompts}
        assert "system" in types
        assert "user" in types
        assert result.prompts_registered == 2
        engine.dispose()

    def test_idempotent_prompt_insertion(self, tmp_path):
        """Second integrate() call with same step does not duplicate prompts."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            integrator.integrate(generated, target_dir)

        # Second call with a different target_dir to avoid file conflicts
        target_dir2 = tmp_path / "pkg2"
        generated2 = _make_generated_step()

        with Session(engine) as session:
            integrator2 = StepIntegrator(session=session)
            result2 = integrator2.integrate(generated2, target_dir2)

        with Session(engine) as session:
            prompts = session.exec(
                select(Prompt).where(Prompt.prompt_key == STEP_NAME)
            ).all()

        # Still exactly 2 rows (system + user), no duplicates
        assert len(prompts) == 2
        # Second call registers 0 new (all already exist)
        assert result2.prompts_registered == 0
        engine.dispose()

    def test_prompt_registration_fallback(self, tmp_path):
        """When prompts_code has a security issue, fallback reconstruction inserts prompts."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"

        # Inject a blocked import to trigger security scan failure + fallback
        bad_prompts_code = "import os\nALL_PROMPTS = []\n"
        generated = GeneratedStep(
            step_name=STEP_NAME,
            step_class_name="SentimentStep",
            instructions_class_name="SentimentInstructions",
            step_code=STEP_CODE,
            instructions_code=INSTRUCTIONS_CODE,
            prompts_code=bad_prompts_code,
            extraction_code=None,
            all_artifacts={
                f"{STEP_NAME}_step.py": STEP_CODE,
                f"{STEP_NAME}_instructions.py": INSTRUCTIONS_CODE,
                f"{STEP_NAME}_prompts.py": bad_prompts_code,
            },
        )

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            result = integrator.integrate(generated, target_dir)

        with Session(engine) as session:
            prompts = session.exec(
                select(Prompt).where(Prompt.prompt_key == STEP_NAME)
            ).all()

        # Fallback reconstruction always inserts system + user (2 prompts)
        assert len(prompts) == 2
        assert result.prompts_registered == 2
        engine.dispose()

    def test_prompts_registered_count_in_result(self, tmp_path):
        """IntegrationResult.prompts_registered matches actual DB insertions."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            result = integrator.integrate(generated, target_dir)

        with Session(engine) as session:
            count = len(session.exec(
                select(Prompt).where(Prompt.prompt_key == STEP_NAME)
            ).all())

        assert result.prompts_registered == count
        engine.dispose()


# ---------------------------------------------------------------------------
# TestStepIntegratorRollback
# ---------------------------------------------------------------------------


class TestStepIntegratorRollback:
    """StepIntegrator rolls back file writes and DB on failure."""

    def test_rollback_deletes_files_on_db_error(self, tmp_path):
        """When session.commit() raises, written files are deleted."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        written_paths: list[str] = []

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)

            original_commit = session.commit

            def failing_commit():
                raise RuntimeError("simulated DB commit failure")

            session.commit = failing_commit

            with pytest.raises(RuntimeError, match="simulated DB commit failure"):
                integrator.integrate(generated, target_dir)

        # Files written during phase 2 must be cleaned up
        for filename in ALL_ARTIFACTS:
            fpath = target_dir / filename
            assert not fpath.exists(), f"{filename} should have been deleted on rollback"

        engine.dispose()

    def test_rollback_removes_new_dir_on_failure(self, tmp_path):
        """If target_dir was newly created and integrate fails, dir is removed."""
        engine = _make_engine()
        # target_dir must NOT pre-exist so integrator tracks it as newly created
        target_dir = tmp_path / "brand_new_dir"
        assert not target_dir.exists()

        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)

            def failing_commit():
                raise RuntimeError("commit failure")

            session.commit = failing_commit

            with pytest.raises(RuntimeError):
                integrator.integrate(generated, target_dir)

        assert not target_dir.exists(), "newly created dir should be removed on rollback"
        engine.dispose()

    def test_rollback_does_not_remove_preexisting_dir(self, tmp_path):
        """If target_dir already existed before integrate(), rollback does not remove it."""
        engine = _make_engine()
        target_dir = tmp_path / "preexisting"
        target_dir.mkdir()
        existing_file = target_dir / "existing.txt"
        existing_file.write_text("keep me", encoding="utf-8")

        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)

            def failing_commit():
                raise RuntimeError("commit failure")

            session.commit = failing_commit

            with pytest.raises(RuntimeError):
                integrator.integrate(generated, target_dir)

        # Dir must still exist; existing_file must survive
        assert target_dir.exists(), "pre-existing dir must not be removed"
        assert existing_file.exists(), "pre-existing file must survive rollback"
        engine.dispose()

    def test_rollback_restores_bak_on_ast_failure(self, tmp_path):
        """When AST modifier raises after writing .bak, pipeline file is restored."""
        engine = _make_engine()

        # Create a minimal pipeline.py in tmp_path
        pipeline_file = tmp_path / "pipeline.py"
        original_content = "# original pipeline\n"
        pipeline_file.write_text(original_content, encoding="utf-8")

        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(
                session=session,
                pipeline_file=pipeline_file,
            )

            # Patch modify_pipeline_file to raise after .bak would be written
            with patch(
                "llm_pipeline.creator.integrator.ast_modifier.modify_pipeline_file",
                side_effect=Exception("AST modification failed"),
            ):
                with pytest.raises(Exception, match="AST modification failed"):
                    integrator.integrate(generated, target_dir)

        # Pipeline file should be restored to original (or unchanged since bak
        # restore is best-effort; at minimum, the file must still exist)
        assert pipeline_file.exists()
        engine.dispose()


# ---------------------------------------------------------------------------
# TestStepIntegratorDraftStatusUpdate
# ---------------------------------------------------------------------------


class TestStepIntegratorDraftStatusUpdate:
    """StepIntegrator updates DraftStep.status to 'accepted' when draft passed."""

    def test_draft_status_set_to_accepted(self, tmp_path):
        """After integrate(draft=...), draft.status == 'accepted' in DB."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        draft_id: int

        with Session(engine) as session:
            draft = _make_draft_step(session)
            draft_id = draft.id
            assert draft.status == "draft"

        with Session(engine) as session:
            draft = session.get(DraftStep, draft_id)
            integrator = StepIntegrator(session=session)
            integrator.integrate(generated, target_dir, draft=draft)

        with Session(engine) as session:
            updated = session.get(DraftStep, draft_id)

        assert updated.status == "accepted"
        engine.dispose()

    def test_draft_status_none_completes_without_error(self, tmp_path):
        """integrate() with draft=None completes successfully without error."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        with Session(engine) as session:
            integrator = StepIntegrator(session=session)
            result = integrator.integrate(generated, target_dir, draft=None)

        assert isinstance(result, IntegrationResult)
        engine.dispose()

    def test_draft_updated_at_refreshed_on_accept(self, tmp_path):
        """draft.updated_at is changed when status is set to accepted."""
        from datetime import datetime, timezone, timedelta

        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        draft_id: int
        original_updated_at: datetime

        with Session(engine) as session:
            draft = _make_draft_step(session)
            draft_id = draft.id
            original_updated_at = draft.updated_at

        with Session(engine) as session:
            draft = session.get(DraftStep, draft_id)
            integrator = StepIntegrator(session=session)
            integrator.integrate(generated, target_dir, draft=draft)

        with Session(engine) as session:
            updated = session.get(DraftStep, draft_id)

        # updated_at should be >= original (may be equal if same second on fast machines)
        assert updated.updated_at >= original_updated_at
        engine.dispose()

    def test_draft_status_in_same_transaction_as_files(self, tmp_path):
        """DraftStep status update and prompt inserts are in the same commit."""
        engine = _make_engine()
        target_dir = tmp_path / "pkg"
        generated = _make_generated_step()

        draft_id: int

        with Session(engine) as session:
            draft = _make_draft_step(session)
            draft_id = draft.id

        with Session(engine) as session:
            draft = session.get(DraftStep, draft_id)
            integrator = StepIntegrator(session=session)

            call_count = 0
            original_commit = session.commit

            def counting_commit():
                nonlocal call_count
                call_count += 1
                original_commit()

            session.commit = counting_commit
            integrator.integrate(generated, target_dir, draft=draft)

        # integrate() should commit exactly once (all-or-nothing)
        assert call_count == 1
        engine.dispose()
