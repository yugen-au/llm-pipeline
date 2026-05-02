"""Tests for ``llm_pipeline.cli.generate``.

Covers both the pure ``run(config) -> Result`` surface (importable
from anywhere) and the ``cli_main(argv) -> int`` standalone entry
(invoked by the dispatcher). The Config/Result/run/cli_main protocol
is the contract every subcommand under ``cli/`` will follow, so
these tests double as a reference for the pattern.

The generate command upserts each YAML's ``XPrompt`` class into the
matching ``<steps_dir>/<name>.py`` file. Tests pre-create the step
file as a minimal stub; assertions inspect the upserted class
inside it after the run.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_pipeline.cli.generate import (
    GenerateConfig,
    GenerateResult,
    cli_main,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _minimal_yaml(name: str, *, var_name: str = "text") -> str:
    return (
        f"name: {name}\n"
        f"description: Test prompt\n"
        f"metadata:\n"
        f"  variable_definitions:\n"
        f"    {var_name}:\n"
        f"      type: str\n"
        f"      description: Input {var_name}\n"
        f"messages:\n"
        f"  - role: user\n"
        f"    content: '{{{var_name}}}'\n"
    )


def _step_stub(name: str = "x") -> str:
    """Minimal step file body — enough for generate to upsert into.

    Generate doesn't require any specific structure in the file (no
    Step class, no imports). The upsert appends the XPrompt class
    at the end and adds required imports at the top.
    """
    return f"# stub step file for '{name}' — generated tests upsert here\n"


def _make_dirs(tmp_path: Path) -> tuple[Path, Path]:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    steps = tmp_path / "steps"
    steps.mkdir()
    return prompts, steps


# ---------------------------------------------------------------------------
# run(): happy paths
# ---------------------------------------------------------------------------


class TestRunHappyPaths:
    def test_upserts_into_one_step_per_yaml(self, tmp_path):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "alpha.yaml", _minimal_yaml("alpha"))
        _write_yaml(prompts / "beta.yaml", _minimal_yaml("beta"))
        (steps / "alpha.py").write_text(_step_stub("alpha"), encoding="utf-8")
        (steps / "beta.py").write_text(_step_stub("beta"), encoding="utf-8")

        result = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert sorted(p.name for p in result.files_written) == [
            "alpha.py", "beta.py",
        ]
        assert result.files_unchanged == []
        assert result.files_failed == []
        assert "AlphaPrompt(PromptVariables):" in (steps / "alpha.py").read_text()
        assert "BetaPrompt(PromptVariables):" in (steps / "beta.py").read_text()

    def test_idempotent_second_run_marks_files_unchanged(self, tmp_path):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))
        (steps / "x.py").write_text(_step_stub(), encoding="utf-8")

        first = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))
        second = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert len(first.files_written) == 1
        assert second.files_written == []
        assert len(second.files_unchanged) == 1

    def test_empty_prompts_dir_returns_empty_result(self, tmp_path):
        prompts, steps = _make_dirs(tmp_path)

        result = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert result.files_written == []
        assert result.files_unchanged == []
        assert result.files_failed == []

    def test_yaml_without_variable_definitions_emits_pass_class(
        self, tmp_path,
    ):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(
            prompts / "bare.yaml",
            "name: bare\n"
            "description: Bare prompt with no vars\n"
            "messages:\n"
            "  - role: user\n"
            "    content: hi\n",
        )
        (steps / "bare.py").write_text(_step_stub("bare"), encoding="utf-8")

        result = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert len(result.files_written) == 1
        body = (steps / "bare.py").read_text()
        assert "class BarePrompt(PromptVariables):" in body
        assert "pass" in body

    def test_existing_xprompt_class_is_replaced(self, tmp_path):
        # Step file already has an XPrompt class with stale fields;
        # generate should rewrite the class body but leave the rest
        # of the file alone.
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))
        (steps / "x.py").write_text(
            "from pydantic import Field\n"
            "from llm_pipeline.prompts import PromptVariables\n"
            "\n"
            "\n"
            "class XPrompt(PromptVariables):\n"
            "    \"\"\"stale\"\"\"\n"
            "    old_field: str = Field(description='gone')\n"
            "\n"
            "\n"
            "# trailing user content\n",
            encoding="utf-8",
        )

        result = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert len(result.files_written) == 1
        body = (steps / "x.py").read_text()
        assert "old_field" not in body
        assert "text: str = Field(description='Input text')" in body
        # Surrounding content survives.
        assert "# trailing user content" in body


# ---------------------------------------------------------------------------
# run(): error collection (per-file)
# ---------------------------------------------------------------------------


class TestRunErrorCollection:
    """Per-file errors land in ``files_failed`` — they do not raise."""

    def test_invalid_yaml_appended_to_failed(self, tmp_path):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "ok.yaml", _minimal_yaml("ok"))
        _write_yaml(prompts / "bad.yaml", "name: [unterminated\n")
        (steps / "ok.py").write_text(_step_stub("ok"), encoding="utf-8")

        result = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert any(p.name == "ok.py" for p in result.files_written)
        assert len(result.files_failed) == 1
        bad_path, reason = result.files_failed[0]
        assert bad_path.name == "bad.yaml"
        assert "YAML parse" in reason

    def test_yaml_missing_name_field_recorded_as_failed(self, tmp_path):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(
            prompts / "no_name.yaml", "description: no name field\n",
        )

        result = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert len(result.files_failed) == 1
        _, reason = result.files_failed[0]
        assert "name" in reason

    def test_yaml_root_not_dict_recorded_as_failed(self, tmp_path):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "list.yaml", "- item1\n- item2\n")

        result = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert len(result.files_failed) == 1

    def test_yaml_without_paired_step_file_recorded_as_failed(self, tmp_path):
        # YAML exists but the matching step file doesn't — generate
        # surfaces that as a per-file failure (stale YAML).
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "orphan.yaml", _minimal_yaml("orphan"))

        result = run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        assert len(result.files_failed) == 1
        path, reason = result.files_failed[0]
        assert path.name == "orphan.py"
        assert "does not exist" in reason


# ---------------------------------------------------------------------------
# run(): top-level errors
# ---------------------------------------------------------------------------


class TestRunTopLevelErrors:
    def test_missing_prompts_dir_raises(self, tmp_path):
        steps = tmp_path / "steps"
        steps.mkdir()
        with pytest.raises(FileNotFoundError):
            run(
                GenerateConfig(
                    prompts_dir=tmp_path / "does_not_exist",
                    steps_dir=steps,
                ),
            )

    def test_missing_steps_dir_raises(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        with pytest.raises(FileNotFoundError):
            run(
                GenerateConfig(
                    prompts_dir=prompts,
                    steps_dir=tmp_path / "does_not_exist",
                ),
            )


# ---------------------------------------------------------------------------
# cli_main(): dry-run + standalone CLI entry
# ---------------------------------------------------------------------------


class TestDryRun:
    """``dry_run`` short-circuits the disk write but still reports drift."""

    def test_dry_run_does_not_overwrite_existing(self, tmp_path):
        prompts, steps = _make_dirs(tmp_path)
        sentinel = "# user-modified content (must survive dry-run)\n"
        target = steps / "x.py"
        target.write_text(sentinel, encoding="utf-8")
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        result = run(
            GenerateConfig(
                prompts_dir=prompts, steps_dir=steps, dry_run=True,
            ),
        )

        # Generator says "would-write" because the upsert would
        # change the file.
        assert len(result.files_written) == 1
        # But the file is unchanged on disk.
        assert target.read_text(encoding="utf-8") == sentinel

    def test_dry_run_no_op_when_already_clean(self, tmp_path):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))
        (steps / "x.py").write_text(_step_stub(), encoding="utf-8")

        # Real run first to settle disk state.
        run(GenerateConfig(prompts_dir=prompts, steps_dir=steps))

        # Dry-run on the now-clean tree should report no changes.
        result = run(
            GenerateConfig(
                prompts_dir=prompts, steps_dir=steps, dry_run=True,
            ),
        )
        assert result.files_written == []
        assert len(result.files_unchanged) == 1

    def test_cli_dry_run_returns_one_when_drift_present(
        self, tmp_path, capsys,
    ):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))
        (steps / "x.py").write_text(_step_stub(), encoding="utf-8")

        rc = cli_main(
            [
                "--prompts-dir", str(prompts),
                "--steps-dir", str(steps),
                "--dry-run",
            ],
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "Would generate" in captured.out
        assert "WOULD" in captured.out


class TestCliMain:
    """Invokes the same code path the dispatcher uses for ``llm-pipeline generate``."""

    def test_cli_main_returns_zero_on_success(self, tmp_path, capsys):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))
        (steps / "x.py").write_text(_step_stub(), encoding="utf-8")

        rc = cli_main(
            ["--prompts-dir", str(prompts), "--steps-dir", str(steps)],
        )

        assert rc == 0
        captured = capsys.readouterr()
        assert "Generated" in captured.out or "x.py" in captured.out

    def test_cli_main_returns_one_on_failure(self, tmp_path, capsys):
        prompts, steps = _make_dirs(tmp_path)
        _write_yaml(prompts / "bad.yaml", "name: [unterminated\n")

        rc = cli_main(
            ["--prompts-dir", str(prompts), "--steps-dir", str(steps)],
        )

        assert rc == 1
        captured = capsys.readouterr()
        assert "FAIL" in captured.err

    def test_cli_main_returns_one_when_prompts_dir_missing(
        self, tmp_path, capsys,
    ):
        steps = tmp_path / "steps"
        steps.mkdir()
        rc = cli_main(
            [
                "--prompts-dir", str(tmp_path / "missing"),
                "--steps-dir", str(steps),
            ],
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
