"""Tests for ``yaml_sync`` leaf mutators honoring ``dry_run_mode``.

The CLI integration tests in tests/cli/test_pull.py and
tests/cli/test_push.py mock ``startup_sync`` / ``pull_phoenix_to_yaml``
wholesale and just check the dry-run flag is set when those entry
points are invoked. These tests validate the OTHER half of the
contract: the leaf mutators (write_prompt_yaml, write_dataset_yaml,
_push_new_version) actually short-circuit when called inside a
dry-run scope.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_pipeline._dry_run import dry_run_mode
from llm_pipeline.prompts.models import (
    Prompt,
    PromptMessage,
    PromptMetadata,
)


def _make_prompt(name: str = "demo") -> Prompt:
    return Prompt(
        name=name,
        description="test",
        model="openai:gpt-4o-mini",
        messages=[
            PromptMessage(role="system", content="sys"),
            PromptMessage(role="user", content="user"),
        ],
        metadata=PromptMetadata(),
    )


class TestWritePromptYamlDryRun:
    def test_dry_run_skips_disk_write_for_new_file(self, tmp_path: Path):
        from llm_pipeline.yaml_sync import write_prompt_yaml

        prompt = _make_prompt("brand_new")
        target = tmp_path / "brand_new.yaml"

        with dry_run_mode():
            wrote = write_prompt_yaml(prompt, tmp_path)

        # Reports "would-write" but no file landed on disk.
        assert wrote is True
        assert not target.exists()

    def test_dry_run_skips_disk_write_for_changed_file(self, tmp_path: Path):
        from llm_pipeline.yaml_sync import write_prompt_yaml

        prompt = _make_prompt("changed")
        target = tmp_path / "changed.yaml"
        # Seed an unrelated YAML so write_prompt_yaml's hash compare
        # decides the contents differ.
        target.write_text("name: changed\nmessages: []\n", encoding="utf-8")
        sentinel = target.read_text(encoding="utf-8")

        with dry_run_mode():
            wrote = write_prompt_yaml(prompt, tmp_path)

        assert wrote is True
        # Original on-disk content survives.
        assert target.read_text(encoding="utf-8") == sentinel

    def test_dry_run_no_op_when_already_clean(self, tmp_path: Path):
        from llm_pipeline.yaml_sync import write_prompt_yaml

        prompt = _make_prompt("clean")
        # Seed via a real run.
        write_prompt_yaml(prompt, tmp_path)
        before = (tmp_path / "clean.yaml").read_text(encoding="utf-8")

        with dry_run_mode():
            wrote = write_prompt_yaml(prompt, tmp_path)

        assert wrote is False
        assert (tmp_path / "clean.yaml").read_text(encoding="utf-8") == before


class TestPushNewVersionDryRun:
    def test_dry_run_does_not_call_phoenix(self):
        from llm_pipeline.yaml_sync import _push_new_version

        client = MagicMock()
        prompt = _make_prompt("noop")

        with dry_run_mode():
            _push_new_version(client, prompt)

        # No Phoenix interaction at all in dry-run mode.
        client.create.assert_not_called()
        client.add_tag.assert_not_called()
        client.get_latest.assert_not_called()
