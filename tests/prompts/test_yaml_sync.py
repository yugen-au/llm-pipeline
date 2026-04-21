"""Tests for YAML prompt discovery and bidirectional sync."""
import pytest
import yaml
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.utils.versioning import compare_versions
from llm_pipeline.prompts.yaml_sync import (
    parse_prompt_yaml,
    discover_yaml_prompts,
    sync_yaml_to_db,
    write_prompt_to_yaml,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return init_pipeline_db(e)


VALID_YAML_BOTH = """\
prompt_key: test_prompt
prompt_name: Test Prompt
category: testing
step_name: test_step

system:
  content: |
    You are {role}. Do {task}.
  description: System instruction
  version: "1.2"
  variable_definitions:
    role:
      type: str
      description: The role

user:
  content: |
    Input: {data}
  description: User prompt
  version: "1.0"
"""

VALID_YAML_SYSTEM_ONLY = """\
prompt_key: sys_only
prompt_name: System Only

system:
  content: Just a system prompt.
  version: "2.0"
"""


def _write_yaml(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# compare_versions
# ---------------------------------------------------------------------------


class TestCompareVersions:
    def test_less_than(self):
        assert compare_versions("1.0", "1.1") == -1

    def test_greater_than(self):
        assert compare_versions("1.1", "1.0") == 1

    def test_equal(self):
        assert compare_versions("1.0", "1.0") == 0

    def test_numeric_comparison(self):
        assert compare_versions("1.10", "1.9") == 1

    def test_major_wins(self):
        assert compare_versions("2.0", "1.99") == 1

    def test_different_lengths(self):
        assert compare_versions("1.0.1", "1.0") == 1

    def test_different_lengths_equal(self):
        assert compare_versions("1.0.0", "1.0") == 0


# ---------------------------------------------------------------------------
# parse_prompt_yaml
# ---------------------------------------------------------------------------


class TestParsePromptYaml:
    def test_both_variants(self, tmp_path):
        p = _write_yaml(tmp_path, "test.yaml", VALID_YAML_BOTH)
        variants = parse_prompt_yaml(p)
        assert len(variants) == 2
        sys_v = next(v for v in variants if v["prompt_type"] == "system")
        usr_v = next(v for v in variants if v["prompt_type"] == "user")
        assert sys_v["prompt_key"] == "test_prompt"
        assert sys_v["version"] == "1.2"
        assert sys_v["category"] == "testing"
        assert sys_v["created_by"] == "yaml"
        assert sys_v["variable_definitions"]["role"]["type"] == "str"
        assert usr_v["version"] == "1.0"
        assert usr_v["required_variables"] == ["data"]

    def test_system_only(self, tmp_path):
        p = _write_yaml(tmp_path, "sys.yaml", VALID_YAML_SYSTEM_ONLY)
        variants = parse_prompt_yaml(p)
        assert len(variants) == 1
        assert variants[0]["prompt_type"] == "system"
        assert variants[0]["version"] == "2.0"

    def test_missing_prompt_key(self, tmp_path):
        p = _write_yaml(tmp_path, "bad.yaml", "system:\n  content: hello\n")
        with pytest.raises(ValueError, match="Missing prompt_key"):
            parse_prompt_yaml(p)

    def test_missing_variants(self, tmp_path):
        p = _write_yaml(tmp_path, "empty.yaml", "prompt_key: foo\n")
        with pytest.raises(ValueError, match="No system or user"):
            parse_prompt_yaml(p)

    def test_default_version(self, tmp_path):
        p = _write_yaml(tmp_path, "noversion.yaml", """\
prompt_key: nover
system:
  content: hello
""")
        variants = parse_prompt_yaml(p)
        assert variants[0]["version"] == "1.0"

    def test_default_prompt_name(self, tmp_path):
        p = _write_yaml(tmp_path, "noname.yaml", """\
prompt_key: no_name
system:
  content: hello
""")
        variants = parse_prompt_yaml(p)
        assert variants[0]["prompt_name"] == "no_name"


# ---------------------------------------------------------------------------
# discover_yaml_prompts
# ---------------------------------------------------------------------------


class TestDiscoverYamlPrompts:
    def test_discovers_valid_files(self, tmp_path):
        _write_yaml(tmp_path, "a.yaml", VALID_YAML_BOTH)
        _write_yaml(tmp_path, "b.yaml", VALID_YAML_SYSTEM_ONLY)
        results = discover_yaml_prompts(tmp_path)
        assert len(results) == 3  # 2 from a + 1 from b

    def test_skips_bad_files(self, tmp_path):
        _write_yaml(tmp_path, "good.yaml", VALID_YAML_SYSTEM_ONLY)
        _write_yaml(tmp_path, "bad.yaml", "not: valid: yaml: [")
        results = discover_yaml_prompts(tmp_path)
        assert len(results) == 1

    def test_empty_dir(self, tmp_path):
        assert discover_yaml_prompts(tmp_path) == []


# ---------------------------------------------------------------------------
# sync_yaml_to_db
# ---------------------------------------------------------------------------


class TestSyncYamlToDb:
    def test_inserts_new(self, tmp_path, engine):
        _write_yaml(tmp_path, "test.yaml", VALID_YAML_BOTH)
        sync_yaml_to_db(engine, tmp_path)

        with Session(engine) as s:
            prompts = s.exec(select(Prompt)).all()
            assert len(prompts) == 2
            sys_p = next(p for p in prompts if p.prompt_type == "system")
            assert sys_p.prompt_key == "test_prompt"
            assert sys_p.version == "1.2"
            assert sys_p.created_by == "yaml"

    def test_yaml_newer_updates_db(self, tmp_path, engine):
        # Seed DB with older version
        with Session(engine) as s:
            s.add(Prompt(
                prompt_key="test_prompt", prompt_type="system",
                prompt_name="Old", content="old content",
                version="1.0",
            ))
            s.commit()

        _write_yaml(tmp_path, "test_prompt.yaml", VALID_YAML_BOTH)
        sync_yaml_to_db(engine, tmp_path)

        with Session(engine) as s:
            # New version-aware sync inserts a new row; query latest
            p = s.exec(select(Prompt).where(
                Prompt.prompt_key == "test_prompt",
                Prompt.prompt_type == "system",
                Prompt.is_latest == True,  # noqa: E712
            )).first()
            assert p.version == "1.2"
            assert "role" in p.content

    def test_db_newer_skips(self, tmp_path, engine):
        with Session(engine) as s:
            s.add(Prompt(
                prompt_key="test_prompt", prompt_type="system",
                prompt_name="Newer", content="db content",
                version="2.0",
            ))
            s.commit()

        _write_yaml(tmp_path, "test_prompt.yaml", VALID_YAML_BOTH)
        sync_yaml_to_db(engine, tmp_path)

        with Session(engine) as s:
            p = s.exec(select(Prompt).where(
                Prompt.prompt_key == "test_prompt",
                Prompt.prompt_type == "system",
            )).first()
            assert p.version == "2.0"
            assert p.content == "db content"

    def test_same_version_skips(self, tmp_path, engine):
        with Session(engine) as s:
            s.add(Prompt(
                prompt_key="test_prompt", prompt_type="system",
                prompt_name="Same", content="db content",
                version="1.2",
            ))
            s.commit()

        _write_yaml(tmp_path, "test_prompt.yaml", VALID_YAML_BOTH)
        sync_yaml_to_db(engine, tmp_path)

        with Session(engine) as s:
            p = s.exec(select(Prompt).where(
                Prompt.prompt_key == "test_prompt",
                Prompt.prompt_type == "system",
            )).first()
            assert p.content == "db content"

    def test_inserts_variable_definitions(self, tmp_path, engine):
        _write_yaml(tmp_path, "test.yaml", VALID_YAML_BOTH)
        sync_yaml_to_db(engine, tmp_path)

        with Session(engine) as s:
            p = s.exec(select(Prompt).where(
                Prompt.prompt_key == "test_prompt",
                Prompt.prompt_type == "system",
            )).first()
            assert p.variable_definitions is not None
            assert "role" in p.variable_definitions

    def test_yaml_newer_inserts_version_and_flips_prior(self, tmp_path, engine):
        """Test #13: YAML newer version creates new row and flips prior is_latest."""
        with Session(engine) as s:
            s.add(Prompt(
                prompt_key="test_prompt", prompt_type="system",
                prompt_name="Old", content="old content",
                version="1.0", is_active=True, is_latest=True,
            ))
            s.commit()

        _write_yaml(tmp_path, "test_prompt.yaml", VALID_YAML_BOTH)
        sync_yaml_to_db(engine, tmp_path)

        with Session(engine) as s:
            all_rows = s.exec(select(Prompt).where(
                Prompt.prompt_key == "test_prompt",
                Prompt.prompt_type == "system",
            )).all()
            # Should have 2 rows: old (is_latest=False) + new (is_latest=True)
            assert len(all_rows) == 2
            latest = [r for r in all_rows if r.is_latest]
            not_latest = [r for r in all_rows if not r.is_latest]
            assert len(latest) == 1
            assert len(not_latest) == 1
            assert latest[0].version == "1.2"
            assert not_latest[0].version == "1.0"

    def test_yaml_older_or_equal_logs_warning_noop(self, tmp_path, engine, caplog):
        """Test #14: YAML same/older version logs WARNING and does nothing."""
        import logging

        with Session(engine) as s:
            s.add(Prompt(
                prompt_key="test_prompt", prompt_type="system",
                prompt_name="Newer", content="db content",
                version="2.0", is_active=True, is_latest=True,
            ))
            s.commit()

        _write_yaml(tmp_path, "test_prompt.yaml", VALID_YAML_BOTH)

        with caplog.at_level(logging.WARNING, logger="llm_pipeline.prompts.yaml_sync"):
            sync_yaml_to_db(engine, tmp_path)

        # Verify WARNING was logged
        assert any("skipping" in r.message.lower() for r in caplog.records)
        assert any("test_prompt" in r.message for r in caplog.records)

        # Verify DB unchanged - still single row
        with Session(engine) as s:
            rows = s.exec(select(Prompt).where(
                Prompt.prompt_key == "test_prompt",
                Prompt.prompt_type == "system",
            )).all()
            assert len(rows) == 1
            assert rows[0].version == "2.0"
            assert rows[0].content == "db content"


# ---------------------------------------------------------------------------
# write_prompt_to_yaml
# ---------------------------------------------------------------------------


class TestWritePromptToYaml:
    def test_updates_existing_section(self, tmp_path):
        _write_yaml(tmp_path, "test_prompt.yaml", VALID_YAML_BOTH)

        result = write_prompt_to_yaml(tmp_path, "test_prompt", "system", {
            "content": "Updated system content.\n",
            "description": "Updated desc",
            "version": "1.3",
            "variable_definitions": None,
            "prompt_name": "Test Prompt",
            "category": "testing",
            "step_name": "test_step",
        })
        assert result is True

        with open(tmp_path / "test_prompt.yaml", "r") as f:
            doc = yaml.safe_load(f)
        assert doc["system"]["version"] == "1.3"
        assert doc["system"]["content"] == "Updated system content.\n"
        # User section preserved
        assert "user" in doc
        assert doc["user"]["version"] == "1.0"

    def test_creates_new_file(self, tmp_path):
        result = write_prompt_to_yaml(tmp_path, "new_prompt", "system", {
            "content": "hello\n",
            "version": "1.0",
            "prompt_name": "New Prompt",
            "category": "test",
            "step_name": "test_step",
        })
        assert result is True
        with open(tmp_path / "new_prompt.yaml", "r") as f:
            doc = yaml.safe_load(f)
        assert doc["prompt_key"] == "new_prompt"
        assert doc["system"]["version"] == "1.0"

    def test_creates_dir_if_missing(self, tmp_path):
        new_dir = tmp_path / "subdir"
        result = write_prompt_to_yaml(new_dir, "test", "system", {
            "content": "hello",
            "version": "1.0",
        })
        assert result is True
        assert (new_dir / "test.yaml").exists()

    def test_preserves_shared_fields(self, tmp_path):
        _write_yaml(tmp_path, "test_prompt.yaml", VALID_YAML_BOTH)

        write_prompt_to_yaml(tmp_path, "test_prompt", "user", {
            "content": "New user content.\n",
            "version": "1.1",
            "prompt_name": "Test Prompt Updated",
            "category": "testing",
            "step_name": "test_step",
        })

        with open(tmp_path / "test_prompt.yaml", "r") as f:
            doc = yaml.safe_load(f)
        assert doc["prompt_key"] == "test_prompt"
        assert doc["prompt_name"] == "Test Prompt Updated"
        assert doc["user"]["version"] == "1.1"
        # System untouched
        assert doc["system"]["version"] == "1.2"
