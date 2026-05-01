"""Tests for ``edit_code_body`` / ``write_code_body``.

Both APIs replace ``{class_name}.{method_name}``'s body in a source
file. ``edit_code_body`` verifies the current body matches an
expected ``old_source`` first (Edit-tool contract); ``write_code_body``
overwrites unconditionally (Write-tool contract). Both leave the
surrounding signature, decorators, neighbouring methods, and
file-level imports untouched.

Round-trip property: capturing a body via
:func:`llm_pipeline.cst_analysis.analyze_code_body` and writing
it straight back via these APIs must produce a byte-identical
file. That property is the architectural validation of the
spec ↔ source pipeline — proven at the bottom of this module
against every demo step / extraction.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_pipeline.codegen.api import (
    CodegenError,
    edit_code_body,
    write_code_body,
)
from llm_pipeline.cst_analysis import analyze_code_body


def _write_source(root: Path, name: str, content: str) -> Path:
    """Helper: write a Python source file under ``root``."""
    path = root / f"{name}.py"
    path.write_text(content, encoding="utf-8")
    return path


def _noop_resolver(_module: str, _symbol: str):
    return None


# A tiny class with two methods, used by most unit tests below. Putting
# it in a string constant keeps each test self-contained — the test
# writes the file fresh, so changes don't leak between cases.
_FIXTURE_SOURCE = (
    "class Calc:\n"
    "    def add(self, a, b):\n"
    "        # leading comment\n"
    "        return a + b\n"
    "\n"
    "    def mul(self, a, b):\n"
    "        return a * b\n"
)


# ---------------------------------------------------------------------------
# write_code_body — unconditional swap
# ---------------------------------------------------------------------------


class TestWriteCodeBody:
    def test_swaps_body_in_place(self, tmp_path: Path):
        src = _write_source(tmp_path, "calc", _FIXTURE_SOURCE)
        report = write_code_body(
            source_file=src,
            class_name="Calc",
            method_name="add",
            new_source="        return a - b  # swapped\n",
            root=tmp_path,
            write_backup=False,
        )
        new = src.read_text(encoding="utf-8")
        # Body replaced
        assert "return a - b  # swapped" in new
        # Other method untouched
        assert "return a * b" in new
        # Signature and class def preserved
        assert "def add(self, a, b):" in new
        assert "class Calc:" in new
        assert report["class"] == "Calc"
        assert report["method"] == "add"

    def test_handles_multi_line_replacement(self, tmp_path: Path):
        # The body of ``add`` is just the ``return a + b`` line —
        # the leading comment is libcst trivia attached to the next
        # statement, not part of the body proper. Replacing the
        # body removes ``return a + b`` but the comment stays.
        src = _write_source(tmp_path, "calc", _FIXTURE_SOURCE)
        new_body = (
            "        x = a + 1\n"
            "        y = b + 1\n"
            "        return x + y\n"
        )
        write_code_body(
            source_file=src,
            class_name="Calc",
            method_name="add",
            new_source=new_body,
            root=tmp_path,
            write_backup=False,
        )
        new = src.read_text(encoding="utf-8")
        assert "x = a + 1" in new
        assert "y = b + 1" in new
        assert "return x + y" in new
        # Original body's statement is gone
        assert "return a + b" not in new
        # Sibling method untouched
        assert "return a * b" in new

    def test_writes_backup_by_default(self, tmp_path: Path):
        src = _write_source(tmp_path, "calc", _FIXTURE_SOURCE)
        write_code_body(
            source_file=src,
            class_name="Calc",
            method_name="add",
            new_source="        return 0\n",
            root=tmp_path,
            # write_backup default = True
        )
        bak = src.with_suffix(src.suffix + ".bak")
        assert bak.exists()
        assert bak.read_text(encoding="utf-8") == _FIXTURE_SOURCE


# ---------------------------------------------------------------------------
# edit_code_body — verified swap
# ---------------------------------------------------------------------------


class TestEditCodeBody:
    def test_matching_old_source_succeeds(self, tmp_path: Path):
        src = _write_source(tmp_path, "calc", _FIXTURE_SOURCE)
        spec = analyze_code_body(
            source=_FIXTURE_SOURCE,
            function_qualname="Calc.add",
            resolver=_noop_resolver,
        )
        # Round-trip with the captured body — file should be unchanged.
        edit_code_body(
            source_file=src,
            class_name="Calc",
            method_name="add",
            old_source=spec.source,
            new_source=spec.source,
            root=tmp_path,
            write_backup=False,
        )
        assert src.read_text(encoding="utf-8") == _FIXTURE_SOURCE

    def test_mismatch_raises_without_writing(self, tmp_path: Path):
        src = _write_source(tmp_path, "calc", _FIXTURE_SOURCE)
        with pytest.raises(CodegenError, match="old_source does not match"):
            edit_code_body(
                source_file=src,
                class_name="Calc",
                method_name="add",
                old_source="        return 999\n",  # not the actual body
                new_source="        return 0\n",
                root=tmp_path,
                write_backup=False,
            )
        # File untouched
        assert src.read_text(encoding="utf-8") == _FIXTURE_SOURCE

    def test_replaces_when_match(self, tmp_path: Path):
        src = _write_source(tmp_path, "calc", _FIXTURE_SOURCE)
        spec = analyze_code_body(
            source=_FIXTURE_SOURCE,
            function_qualname="Calc.add",
            resolver=_noop_resolver,
        )
        edit_code_body(
            source_file=src,
            class_name="Calc",
            method_name="add",
            old_source=spec.source,
            new_source="        return a * 2 + b * 2\n",
            root=tmp_path,
            write_backup=False,
        )
        new = src.read_text(encoding="utf-8")
        assert "return a * 2 + b * 2" in new
        # Other method unaffected
        assert "return a * b" in new


# ---------------------------------------------------------------------------
# Negative paths shared by both APIs
# ---------------------------------------------------------------------------


class TestNegativePaths:
    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(CodegenError, match="does not exist"):
            write_code_body(
                source_file=tmp_path / "nonexistent.py",
                class_name="Calc",
                method_name="add",
                new_source="        return 0\n",
                root=tmp_path,
            )

    def test_missing_class_raises(self, tmp_path: Path):
        src = _write_source(tmp_path, "calc", _FIXTURE_SOURCE)
        with pytest.raises(CodegenError, match="could not locate"):
            write_code_body(
                source_file=src,
                class_name="NotARealClass",
                method_name="add",
                new_source="        return 0\n",
                root=tmp_path,
                write_backup=False,
            )

    def test_missing_method_raises(self, tmp_path: Path):
        src = _write_source(tmp_path, "calc", _FIXTURE_SOURCE)
        with pytest.raises(CodegenError, match="could not locate"):
            write_code_body(
                source_file=src,
                class_name="Calc",
                method_name="not_a_method",
                new_source="        return 0\n",
                root=tmp_path,
                write_backup=False,
            )

    def test_path_outside_root_raises(self, tmp_path: Path):
        # Two separate dirs — the source file is in dir_a, but root
        # passed to the API is dir_b. Path-guard should reject.
        dir_a = tmp_path / "outside"
        dir_b = tmp_path / "inside"
        dir_a.mkdir()
        dir_b.mkdir()
        src = _write_source(dir_a, "calc", _FIXTURE_SOURCE)
        with pytest.raises(CodegenError):
            write_code_body(
                source_file=src,
                class_name="Calc",
                method_name="add",
                new_source="        return 0\n",
                root=dir_b,
                write_backup=False,
            )


# ---------------------------------------------------------------------------
# Demo round-trip — the architectural validation
# ---------------------------------------------------------------------------


class TestDemoRoundTrip:
    """For every ``(class, method)`` we extract a CodeBodySpec from
    in the demo, write it straight back via ``edit_code_body`` and
    assert the source file is byte-identical.

    If this fails on any pair, the analyser is dropping data (or the
    splice helper has a bug) — the spec is not faithful to source
    and the broader spec ↔ code translation has a hole. Tests like
    this are why the round-trip was the architectural-validation
    test we wanted from D.3.a.
    """

    DEMO_TARGETS: list[tuple[str, str, str]] = [
        # (relative_path, class_name, method_name)
        ("steps/sentiment_analysis.py", "SentimentAnalysisStep", "prepare"),
        ("steps/sentiment_analysis.py", "SentimentAnalysisStep", "run"),
        ("steps/topic_extraction.py", "TopicExtractionStep", "prepare"),
        ("steps/topic_extraction.py", "TopicExtractionStep", "run"),
        ("steps/summary.py", "SummaryStep", "prepare"),
        ("steps/summary.py", "SummaryStep", "run"),
        ("extractions/text_analyzer.py", "TopicExtraction", "extract"),
        ("extractions/text_analyzer.py", "TopicExtraction", "run"),
    ]

    @pytest.mark.parametrize("rel_path,class_name,method_name", DEMO_TARGETS)
    def test_round_trip_preserves_demo_source(
        self,
        tmp_path: Path,
        rel_path: str,
        class_name: str,
        method_name: str,
    ):
        # Locate the real demo file relative to the project tree.
        demo_root = (
            Path(__file__).resolve().parent.parent.parent / "llm_pipelines"
        )
        demo_file = demo_root / rel_path
        assert demo_file.exists(), f"demo source not found: {demo_file}"

        # Copy into tmp so the test can't accidentally touch the real
        # demo files. Mirror the relative path so the path-guard
        # against ``llm_pipelines`` semantics is honoured (we point
        # ``root`` at our tmp ``llm_pipelines`` clone).
        sandbox_root = tmp_path / "llm_pipelines"
        sandbox_file = sandbox_root / rel_path
        sandbox_file.parent.mkdir(parents=True, exist_ok=True)
        original_text = demo_file.read_text(encoding="utf-8")
        sandbox_file.write_text(original_text, encoding="utf-8")

        # Capture the body via the analyser …
        spec = analyze_code_body(
            source=original_text,
            function_qualname=f"{class_name}.{method_name}",
            resolver=_noop_resolver,
        )

        # … and write it straight back via edit_code_body.
        edit_code_body(
            source_file=sandbox_file,
            class_name=class_name,
            method_name=method_name,
            old_source=spec.source,
            new_source=spec.source,
            root=sandbox_root,
            write_backup=False,
        )

        round_tripped = sandbox_file.read_text(encoding="utf-8")
        assert round_tripped == original_text, (
            f"round-trip changed source for {class_name}.{method_name} "
            f"in {rel_path}. The analyser's CodeBodySpec.source isn't "
            f"a faithful slice of the file (or _splice_body is wrong)."
        )
