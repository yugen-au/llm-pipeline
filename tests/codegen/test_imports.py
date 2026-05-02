"""Tests for ``edit_imports`` / ``write_imports`` / ``render_import_block``.

Imports are captured structurally (module + artifacts), so spec → code
regenerates them in canonical form rather than preserving verbatim
formatting. Tests cover:

- Canonical-form rendering of every import shape we support.
- Edit-tool contract (``edit_imports`` verifies caller's view of
  current imports before swapping).
- Write-tool contract (``write_imports`` overwrites unconditionally).
- Path-guarding, missing-file errors.
- Round-trip on the demo: captured ``ImportBlock``s, written back,
  semantically equivalent to original (canonical form matches the
  demo's already-canonical formatting except for blank-line grouping).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_pipeline.codegen import (
    CodegenError,
    edit_imports,
    render_import_block,
    write_imports,
)
from llm_pipeline.cst_analysis import analyze_imports
from llm_pipeline.specs import ImportArtifact, ImportBlock


def _write(root: Path, name: str, content: str) -> Path:
    path = root / f"{name}.py"
    path.write_text(content, encoding="utf-8")
    return path


def _noop(_module: str, _symbol: str):
    return None


# ---------------------------------------------------------------------------
# render_import_block — pure rendering
# ---------------------------------------------------------------------------


class TestRenderImportBlock:
    def test_from_x_import_y(self):
        block = ImportBlock(
            module="llm_pipeline.graph",
            artifacts=[ImportArtifact(name="LLMStepNode")],
        )
        assert render_import_block(block) == (
            "from llm_pipeline.graph import LLMStepNode\n"
        )

    def test_from_x_import_multiple(self):
        block = ImportBlock(
            module="typing",
            artifacts=[
                ImportArtifact(name="ClassVar"),
                ImportArtifact(name="TYPE_CHECKING"),
            ],
        )
        assert render_import_block(block) == (
            "from typing import ClassVar, TYPE_CHECKING\n"
        )

    def test_from_x_import_with_alias(self):
        block = ImportBlock(
            module="numpy",
            artifacts=[ImportArtifact(name="ndarray", alias="NDArray")],
        )
        assert render_import_block(block) == (
            "from numpy import ndarray as NDArray\n"
        )

    def test_bare_import(self):
        block = ImportBlock(
            module=None,
            artifacts=[ImportArtifact(name="os")],
        )
        assert render_import_block(block) == "import os\n"

    def test_bare_import_with_alias(self):
        block = ImportBlock(
            module=None,
            artifacts=[ImportArtifact(name="numpy", alias="np")],
        )
        assert render_import_block(block) == "import numpy as np\n"

    def test_bare_import_multi_artifact_splits_to_lines(self):
        # Canonicalisation: ``import a, b`` becomes two lines.
        block = ImportBlock(
            module=None,
            artifacts=[
                ImportArtifact(name="os"),
                ImportArtifact(name="sys"),
            ],
        )
        assert render_import_block(block) == "import os\nimport sys\n"


# ---------------------------------------------------------------------------
# write_imports — unconditional swap
# ---------------------------------------------------------------------------


_FIXTURE = (
    '"""docstring"""\n'
    "\n"
    "from __future__ import annotations\n"
    "\n"
    "from typing import ClassVar\n"
    "from llm_pipeline.graph import LLMStepNode\n"
    "\n"
    "\n"
    "class Foo:\n"
    "    pass\n"
)


class TestWriteImports:
    def test_swaps_imports_section(self, tmp_path: Path):
        src = _write(tmp_path, "fix", _FIXTURE)
        new_blocks = [
            ImportBlock(
                module="__future__",
                artifacts=[ImportArtifact(name="annotations")],
            ),
            ImportBlock(
                module="typing",
                artifacts=[ImportArtifact(name="Any")],
            ),
        ]
        write_imports(
            source_file=src,
            new_imports=new_blocks,
            root=tmp_path,
            write_backup=False,
        )
        new = src.read_text(encoding="utf-8")
        # New imports rendered canonically
        assert "from __future__ import annotations\n" in new
        assert "from typing import Any\n" in new
        # Old imports gone
        assert "ClassVar" not in new
        assert "LLMStepNode" not in new
        # Body untouched
        assert "class Foo:" in new
        assert '"""docstring"""' in new

    def test_canonicalises_blank_lines_between_groups(self, tmp_path: Path):
        # Original has a blank line between import groups; canonical
        # form collapses them.
        src = _write(tmp_path, "fix", _FIXTURE)
        blocks = analyze_imports(source=_FIXTURE, resolver=_noop)
        write_imports(
            source_file=src,
            new_imports=blocks,
            root=tmp_path,
            write_backup=False,
        )
        new = src.read_text(encoding="utf-8")
        # All three imports, contiguous (no blank lines between them
        # in the imports section)
        section = (
            "from __future__ import annotations\n"
            "from typing import ClassVar\n"
            "from llm_pipeline.graph import LLMStepNode\n"
        )
        assert section in new


# ---------------------------------------------------------------------------
# edit_imports — verified swap
# ---------------------------------------------------------------------------


class TestEditImports:
    def test_matching_old_imports_succeeds(self, tmp_path: Path):
        src = _write(tmp_path, "fix", _FIXTURE)
        blocks = analyze_imports(source=_FIXTURE, resolver=_noop)
        # Round-trip: pass blocks as both old and new
        edit_imports(
            source_file=src,
            old_imports=blocks,
            new_imports=blocks,
            root=tmp_path,
            write_backup=False,
        )
        # File ends up canonical (blanks collapsed in section)
        new = src.read_text(encoding="utf-8")
        # Body still here
        assert "class Foo:" in new

    def test_mismatched_old_imports_raises(self, tmp_path: Path):
        src = _write(tmp_path, "fix", _FIXTURE)
        # Caller's "view" disagrees with what's actually in the file.
        wrong_blocks = [
            ImportBlock(
                module="something_else",
                artifacts=[ImportArtifact(name="Whatever")],
            ),
        ]
        new_blocks = [
            ImportBlock(
                module="typing",
                artifacts=[ImportArtifact(name="Any")],
            ),
        ]
        with pytest.raises(CodegenError, match="does not match"):
            edit_imports(
                source_file=src,
                old_imports=wrong_blocks,
                new_imports=new_blocks,
                root=tmp_path,
                write_backup=False,
            )
        # File untouched
        assert src.read_text(encoding="utf-8") == _FIXTURE

    def test_structural_match_ignores_refs_and_issues(self, tmp_path: Path):
        # The match is structural: module + artifact name + alias.
        # Refs (resolver-derived) and issues differ between
        # null-resolver pass and full-resolver pass — must not
        # cause a mismatch.
        src = _write(tmp_path, "fix", _FIXTURE)

        def fake_resolver(module, sym):
            if module == "llm_pipeline.graph" and sym == "LLMStepNode":
                return ("step", "fake")
            return None

        # The "old" view as the analyser produced it with one resolver.
        old_blocks = analyze_imports(source=_FIXTURE, resolver=fake_resolver)
        # The "new" view captured under a different resolver — same
        # source so structurally identical, but refs differ.
        new_blocks = analyze_imports(source=_FIXTURE, resolver=_noop)
        # Should NOT raise.
        edit_imports(
            source_file=src,
            old_imports=old_blocks,
            new_imports=new_blocks,
            root=tmp_path,
            write_backup=False,
        )


# ---------------------------------------------------------------------------
# Negative paths
# ---------------------------------------------------------------------------


class TestNegativePaths:
    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(CodegenError, match="does not exist"):
            write_imports(
                source_file=tmp_path / "nonexistent.py",
                new_imports=[],
                root=tmp_path,
            )

    def test_no_existing_imports_section(self, tmp_path: Path):
        # File has no imports — V1 doesn't auto-insert at the top.
        src = _write(tmp_path, "no_imports", "class Foo:\n    pass\n")
        with pytest.raises(CodegenError, match="no top-level imports"):
            write_imports(
                source_file=src,
                new_imports=[
                    ImportBlock(
                        module="typing",
                        artifacts=[ImportArtifact(name="Any")],
                    ),
                ],
                root=tmp_path,
                write_backup=False,
            )

    def test_path_outside_root(self, tmp_path: Path):
        outside = tmp_path / "outside"
        inside = tmp_path / "inside"
        outside.mkdir()
        inside.mkdir()
        src = _write(outside, "fix", _FIXTURE)
        with pytest.raises(CodegenError):
            write_imports(
                source_file=src,
                new_imports=[],
                root=inside,
                write_backup=False,
            )


# ---------------------------------------------------------------------------
# Demo round-trip — semantic equivalence (NOT byte-equal; canonicalisation
# collapses blank lines between import groups)
# ---------------------------------------------------------------------------


class TestDemoRoundTrip:
    DEMO_FILES = [
        "steps/sentiment_analysis.py",
        "steps/topic_extraction.py",
        "steps/summary.py",
        "extractions/text_analyzer.py",
        "pipelines/text_analyzer.py",
    ]

    @pytest.mark.parametrize("rel_path", DEMO_FILES)
    def test_round_trip_preserves_imports_semantically(
        self, tmp_path: Path, rel_path: str,
    ):
        """Capture imports → write back → re-analyse → same structure.

        Canonicalisation may collapse blank-line groupings in the
        rendered text, but the SET of imports (module + artifact
        names + aliases) must be identical before and after.
        """
        demo_root = (
            Path(__file__).resolve().parent.parent.parent / "llm_pipelines"
        )
        demo_file = demo_root / rel_path
        assert demo_file.exists(), f"demo source not found: {demo_file}"

        # Sandbox
        sandbox_root = tmp_path / "llm_pipelines"
        sandbox_file = sandbox_root / rel_path
        sandbox_file.parent.mkdir(parents=True, exist_ok=True)
        original = demo_file.read_text(encoding="utf-8")
        sandbox_file.write_text(original, encoding="utf-8")

        before_blocks = analyze_imports(source=original, resolver=_noop)
        write_imports(
            source_file=sandbox_file,
            new_imports=before_blocks,
            root=sandbox_root,
            write_backup=False,
        )
        after_blocks = analyze_imports(
            source=sandbox_file.read_text(encoding="utf-8"),
            resolver=_noop,
        )

        # Same number of blocks
        assert len(before_blocks) == len(after_blocks), (
            f"block count changed for {rel_path}: "
            f"{len(before_blocks)} -> {len(after_blocks)}"
        )

        # Same structure (module + artifact names + aliases)
        for i, (b, a) in enumerate(zip(before_blocks, after_blocks)):
            assert b.module == a.module, (
                f"block {i} module changed in {rel_path}: "
                f"{b.module!r} -> {a.module!r}"
            )
            assert len(b.artifacts) == len(a.artifacts), (
                f"block {i} artifact count changed in {rel_path}"
            )
            for j, (ba, aa) in enumerate(zip(b.artifacts, a.artifacts)):
                assert ba.name == aa.name, (
                    f"block {i} artifact {j} name changed in {rel_path}"
                )
                assert ba.alias == aa.alias, (
                    f"block {i} artifact {j} alias changed in {rel_path}"
                )
