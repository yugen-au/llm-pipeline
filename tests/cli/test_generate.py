"""Tests for ``llm_pipeline.cli.generate``.

Covers both the pure ``run(config) -> Result`` surface (importable
from anywhere) and the ``cli_main(argv) -> int`` standalone entry
(invoked by the dispatcher). The Config/Result/run/cli_main protocol
is the contract every subcommand under ``cli/`` will follow, so
these tests double as a reference for the pattern.
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


# ---------------------------------------------------------------------------
# run(): happy paths
# ---------------------------------------------------------------------------


class TestRunHappyPaths:
    def test_generates_one_file_per_yaml(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "alpha.yaml", _minimal_yaml("alpha"))
        _write_yaml(prompts / "beta.yaml", _minimal_yaml("beta"))

        result = run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        assert sorted(p.name for p in result.files_written) == [
            "_alpha.py", "_beta.py",
        ]
        assert result.files_unchanged == []
        assert result.files_failed == []
        assert (out / "_alpha.py").exists()
        assert (out / "_beta.py").exists()

    def test_creates_init_file_in_output_dir(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        init = out / "__init__.py"
        assert init.exists()

    def test_idempotent_second_run_marks_files_unchanged(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        first = run(GenerateConfig(prompts_dir=prompts, output_dir=out))
        second = run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        assert len(first.files_written) == 1
        assert second.files_written == []
        assert len(second.files_unchanged) == 1

    def test_existing_init_file_not_overwritten(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        out.mkdir()
        # User-authored marker in __init__.py
        (out / "__init__.py").write_text(
            "# user content\n", encoding="utf-8",
        )
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        assert (out / "__init__.py").read_text() == "# user content\n"

    def test_empty_prompts_dir_returns_empty_result(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"

        result = run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        assert result.files_written == []
        assert result.files_unchanged == []
        assert result.files_failed == []

    def test_yaml_without_variable_definitions_emits_pass_class(
        self, tmp_path,
    ):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(
            prompts / "bare.yaml",
            "name: bare\n"
            "description: Bare prompt with no vars\n"
            "messages:\n"
            "  - role: user\n"
            "    content: hi\n",
        )

        result = run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        assert len(result.files_written) == 1
        body = (out / "_bare.py").read_text()
        assert "class BarePrompt(PromptVariables):" in body
        assert "pass" in body


# ---------------------------------------------------------------------------
# run(): error collection (per-file)
# ---------------------------------------------------------------------------


class TestRunErrorCollection:
    """Per-file errors land in ``files_failed`` — they do not raise."""

    def test_invalid_yaml_appended_to_failed(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "ok.yaml", _minimal_yaml("ok"))
        _write_yaml(prompts / "bad.yaml", "name: [unterminated\n")

        result = run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        # Good file generated
        assert any("_ok.py" in str(p) for p in result.files_written)
        # Bad file recorded as failed
        assert len(result.files_failed) == 1
        bad_path, reason = result.files_failed[0]
        assert bad_path.name == "bad.yaml"
        assert "YAML parse" in reason

    def test_yaml_missing_name_field_recorded_as_failed(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(
            prompts / "no_name.yaml",
            "description: no name field\n",
        )

        result = run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        assert len(result.files_failed) == 1
        _, reason = result.files_failed[0]
        assert "name" in reason

    def test_yaml_root_not_dict_recorded_as_failed(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "list.yaml", "- item1\n- item2\n")

        result = run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        assert len(result.files_failed) == 1


# ---------------------------------------------------------------------------
# run(): top-level errors
# ---------------------------------------------------------------------------


class TestRunTopLevelErrors:
    def test_missing_prompts_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run(
                GenerateConfig(
                    prompts_dir=tmp_path / "does_not_exist",
                    output_dir=tmp_path / "_v",
                ),
            )


# ---------------------------------------------------------------------------
# cli_main(): standalone CLI entry
# ---------------------------------------------------------------------------


class TestDryRun:
    """``dry_run`` short-circuits the disk write but still reports drift."""

    def test_dry_run_does_not_write_when_file_missing(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        result = run(
            GenerateConfig(
                prompts_dir=prompts, output_dir=out, dry_run=True,
            ),
        )

        # Reports "would-write" but the file was never created.
        assert len(result.files_written) == 1
        target = out / "_x.py"
        assert not target.exists()

    def test_dry_run_does_not_overwrite_existing(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        out.mkdir()
        sentinel = "# user-modified content (must survive dry-run)\n"
        target = out / "_x.py"
        target.write_text(sentinel, encoding="utf-8")
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        result = run(
            GenerateConfig(
                prompts_dir=prompts, output_dir=out, dry_run=True,
            ),
        )

        # Generator says "would-write" because content differs.
        assert len(result.files_written) == 1
        # But the file is unchanged on disk.
        assert target.read_text(encoding="utf-8") == sentinel

    def test_dry_run_no_op_when_already_clean(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        # Real run first to settle disk state.
        run(GenerateConfig(prompts_dir=prompts, output_dir=out))

        # Dry-run on the now-clean tree should report no changes.
        result = run(
            GenerateConfig(
                prompts_dir=prompts, output_dir=out, dry_run=True,
            ),
        )
        assert result.files_written == []
        assert len(result.files_unchanged) == 1

    def test_cli_dry_run_returns_one_when_drift_present(
        self, tmp_path, capsys,
    ):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        rc = cli_main(
            [
                "--prompts-dir", str(prompts),
                "--output-dir", str(out),
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
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "x.yaml", _minimal_yaml("x"))

        rc = cli_main(
            ["--prompts-dir", str(prompts), "--output-dir", str(out)],
        )

        assert rc == 0
        captured = capsys.readouterr()
        assert "Generated" in captured.out or "_x.py" in captured.out

    def test_cli_main_returns_one_on_failure(self, tmp_path, capsys):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        out = tmp_path / "_variables"
        _write_yaml(prompts / "bad.yaml", "name: [unterminated\n")

        rc = cli_main(
            ["--prompts-dir", str(prompts), "--output-dir", str(out)],
        )

        assert rc == 1
        captured = capsys.readouterr()
        assert "FAIL" in captured.err

    def test_cli_main_returns_one_when_prompts_dir_missing(
        self, tmp_path, capsys,
    ):
        rc = cli_main(
            [
                "--prompts-dir", str(tmp_path / "missing"),
                "--output-dir", str(tmp_path / "_v"),
            ],
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
