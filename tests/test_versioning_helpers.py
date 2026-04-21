"""Unit tests for versioning utilities and db helpers."""
import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select

from llm_pipeline.utils.versioning import compare_versions
from llm_pipeline.db.versioning import (
    _bump_minor,
    _utc_now,
    get_latest,
    save_new_version,
    soft_delete_latest,
)
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.evals.models import EvaluationCase, EvaluationDataset


@pytest.fixture
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """Session bound to in-memory engine; rolls back on teardown."""
    with Session(engine) as sess:
        yield sess


class TestCompareVersions:
    """Tests for compare_versions — covers _bump_minor edge cases from PLAN Step 1."""

    def test_less_than(self):
        assert compare_versions("1.0", "1.1") == -1

    def test_greater_than(self):
        assert compare_versions("1.1", "1.0") == 1

    def test_equal(self):
        assert compare_versions("1.0", "1.0") == 0

    def test_numeric_not_lexicographic(self):
        # "1.10" > "1.9" numerically, but lexicographic would say otherwise
        assert compare_versions("1.10", "1.9") == 1

    def test_major_dominates(self):
        assert compare_versions("2.0", "1.99") == 1

    def test_unequal_depth_greater(self):
        assert compare_versions("1.0.1", "1.0") == 1

    def test_unequal_depth_equal(self):
        # Trailing zeros are equivalent
        assert compare_versions("1.0.0", "1.0") == 0

    def test_single_segment(self):
        assert compare_versions("2", "1") == 1
        assert compare_versions("1", "2") == -1
        assert compare_versions("1", "1") == 0

    def test_three_segments(self):
        assert compare_versions("1.2.3", "1.2.4") == -1
        assert compare_versions("1.2.4", "1.2.3") == 1
        assert compare_versions("1.2.3", "1.2.3") == 0

    def test_zero_padded_depth(self):
        # "1.0.0.0" == "1"
        assert compare_versions("1.0.0.0", "1") == 0

    def test_large_minor(self):
        assert compare_versions("1.100", "1.99") == 1


class TestBumpMinor:
    """Test #7: _bump_minor edge cases."""

    def test_one_nine(self):
        assert _bump_minor("1.9") == "1.10"

    def test_single_segment(self):
        assert _bump_minor("1") == "1.1"

    def test_three_segments(self):
        assert _bump_minor("1.2.3") == "1.2.4"

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError, match="Non-numeric"):
            _bump_minor("1.x")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Non-numeric"):
            _bump_minor("")


class TestSaveNewVersion:
    """Tests #1, #5, #6, #8 from VALIDATED_RESEARCH 9.1."""

    def _make_prompt_fields(self, **overrides):
        base = {
            "prompt_name": "Test Prompt",
            "content": "Hello {name}",
        }
        base.update(overrides)
        return base

    def test_save_new_version_bumps_and_flips_prior(self, session):
        """Test #1: v1=1.0, v2=1.1; old is_latest=False, is_active=True."""
        v1 = save_new_version(
            session, Prompt,
            key_filters={"prompt_key": "greet", "prompt_type": "system"},
            new_fields=self._make_prompt_fields(),
        )
        session.commit()
        assert v1.version == "1.0"
        assert v1.is_latest is True

        v2 = save_new_version(
            session, Prompt,
            key_filters={"prompt_key": "greet", "prompt_type": "system"},
            new_fields=self._make_prompt_fields(content="Hello v2"),
        )
        session.commit()

        assert v2.version == "1.1"
        assert v2.is_latest is True
        assert v2.is_active is True

        # Refresh v1
        session.refresh(v1)
        assert v1.is_latest is False
        assert v1.is_active is True

    def test_save_new_version_forbids_managed_cols(self, session):
        """Test #5: ValueError on managed cols in new_fields."""
        with pytest.raises(ValueError, match="versioning-managed"):
            save_new_version(
                session, Prompt,
                key_filters={"prompt_key": "x", "prompt_type": "system"},
                new_fields={"prompt_name": "X", "content": "c", "is_latest": True},
            )
        with pytest.raises(ValueError, match="versioning-managed"):
            save_new_version(
                session, Prompt,
                key_filters={"prompt_key": "x", "prompt_type": "system"},
                new_fields={"prompt_name": "X", "content": "c", "version": "2.0"},
            )

    def test_explicit_version_must_be_greater(self, session):
        """Test #6: ValueError when explicit version <= prior."""
        save_new_version(
            session, Prompt,
            key_filters={"prompt_key": "v", "prompt_type": "system"},
            new_fields=self._make_prompt_fields(),
        )
        session.commit()
        # Now prior is "1.0"; try to insert "1.0" explicitly
        with pytest.raises(ValueError, match="not greater than prior"):
            save_new_version(
                session, Prompt,
                key_filters={"prompt_key": "v", "prompt_type": "system"},
                new_fields=self._make_prompt_fields(),
                version="1.0",
            )

    def test_soft_delete_writes_updated_at(self, session):
        """Test #8: updated_at populated on soft-delete."""
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        row = save_new_version(
            session, Prompt,
            key_filters={"prompt_key": "del", "prompt_type": "user"},
            new_fields=self._make_prompt_fields(),
        )
        session.commit()

        deleted = soft_delete_latest(session, Prompt, prompt_key="del", prompt_type="user")
        session.commit()

        assert deleted is not None
        assert deleted.is_active is False
        # SQLite strips tzinfo; compare naive
        updated = deleted.updated_at.replace(tzinfo=None) if deleted.updated_at.tzinfo else deleted.updated_at
        assert updated >= before


class TestPartialUniqueIndex:
    """Test #2: partial unique index prevents two active-latest rows with same key."""

    def test_partial_unique_index_prevents_two_latest_active(self, engine):
        """Bypass helper to directly insert two active+latest rows — IntegrityError."""
        with Session(engine) as sess:
            now = datetime.now(timezone.utc)
            p1 = Prompt(
                prompt_key="dup", prompt_type="system",
                prompt_name="P1", content="a",
                version="1.0", is_active=True, is_latest=True,
                created_at=now, updated_at=now,
            )
            sess.add(p1)
            sess.commit()

        with Session(engine) as sess:
            now = datetime.now(timezone.utc)
            p2 = Prompt(
                prompt_key="dup", prompt_type="system",
                prompt_name="P2", content="b",
                version="1.1", is_active=True, is_latest=True,
                created_at=now, updated_at=now,
            )
            sess.add(p2)
            with pytest.raises(IntegrityError):
                sess.commit()


class TestSoftDeleteAndRecreate:
    """Test #3: soft-delete then recreate resets version to 1.0."""

    def _make_prompt_fields(self, **overrides):
        base = {"prompt_name": "Test", "content": "c"}
        base.update(overrides)
        return base

    def test_soft_delete_then_recreate_resets_version(self, session):
        key = {"prompt_key": "cyc", "prompt_type": "system"}
        # Create 3 versions
        save_new_version(session, Prompt, key, self._make_prompt_fields())
        session.commit()
        save_new_version(session, Prompt, key, self._make_prompt_fields())
        session.commit()
        save_new_version(session, Prompt, key, self._make_prompt_fields())
        session.commit()

        # Soft-delete
        soft_delete_latest(session, Prompt, **key)
        session.commit()

        # get_latest returns None (soft-deleted vacates active slot)
        assert get_latest(session, Prompt, **key) is None

        # Recreate — should start at 1.0
        new = save_new_version(session, Prompt, key, self._make_prompt_fields())
        session.commit()
        assert new.version == "1.0"

        # Total rows = 4 (3 historical + 1 new)
        all_rows = session.exec(
            select(Prompt).where(
                Prompt.prompt_key == "cyc", Prompt.prompt_type == "system"
            )
        ).all()
        assert len(all_rows) == 4


class TestGetLatest:
    """Test #4: get_latest ignores inactive and non-latest rows."""

    def test_get_latest_ignores_inactive_and_non_latest(self, session):
        now = datetime.now(timezone.utc)
        # Insert non-latest row (historical)
        p_old = Prompt(
            prompt_key="gl", prompt_type="system",
            prompt_name="Old", content="old",
            version="1.0", is_active=True, is_latest=False,
            created_at=now, updated_at=now,
        )
        # Insert inactive row (soft-deleted, still is_latest=True per semantics)
        p_inactive = Prompt(
            prompt_key="gl2", prompt_type="system",
            prompt_name="Inactive", content="del",
            version="1.0", is_active=False, is_latest=True,
            created_at=now, updated_at=now,
        )
        # Insert the actual active+latest
        p_live = Prompt(
            prompt_key="gl", prompt_type="system",
            prompt_name="Live", content="live",
            version="1.1", is_active=True, is_latest=True,
            created_at=now, updated_at=now,
        )
        session.add_all([p_old, p_inactive, p_live])
        session.commit()

        result = get_latest(session, Prompt, prompt_key="gl", prompt_type="system")
        assert result is not None
        assert result.version == "1.1"
        assert result.content == "live"

        # Inactive excluded
        result2 = get_latest(session, Prompt, prompt_key="gl2", prompt_type="system")
        assert result2 is None


class TestSandboxSeedFilters:
    """Test #11: sandbox seed only copies active+latest prompts."""

    def test_sandbox_seed_filters_is_latest_is_active(self):
        """Seed DB with 3 versions of same prompt; sandbox gets only live+latest."""
        from llm_pipeline.sandbox import create_sandbox_engine

        prod_engine = create_engine("sqlite:///:memory:", echo=False)
        SQLModel.metadata.create_all(prod_engine)

        now = datetime.now(timezone.utc)

        with Session(prod_engine) as sess:
            # Row 1: active + latest (should be copied)
            sess.add(Prompt(
                prompt_key="sand", prompt_type="system",
                prompt_name="Sand", content="latest",
                version="1.2", is_active=True, is_latest=True,
                created_at=now, updated_at=now,
            ))
            # Row 2: active + non-latest (historical, should NOT be copied)
            sess.add(Prompt(
                prompt_key="sand", prompt_type="system",
                prompt_name="Sand", content="old",
                version="1.1", is_active=True, is_latest=False,
                created_at=now, updated_at=now,
            ))
            # Row 3: inactive + latest (soft-deleted, should NOT be copied)
            sess.add(Prompt(
                prompt_key="sand2", prompt_type="system",
                prompt_name="Sand2", content="deleted",
                version="1.0", is_active=False, is_latest=True,
                created_at=now, updated_at=now,
            ))
            sess.commit()

        sandbox_engine = create_sandbox_engine(prod_engine)

        with Session(sandbox_engine) as sess:
            rows = sess.exec(select(Prompt)).all()
            assert len(rows) == 1
            assert rows[0].prompt_key == "sand"
            assert rows[0].version == "1.2"
            assert rows[0].content == "latest"
            assert rows[0].is_latest is True
            assert rows[0].is_active is True
