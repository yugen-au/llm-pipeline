"""Tests for :class:`EnumWriter` — write / edit / apply."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from llm_pipeline.artifacts.enums import EnumMemberSpec, EnumSpec, EnumWriter


def _spec(*, members: list[tuple[str, object]], name: str = "Sentiment") -> EnumSpec:
    member_specs = [EnumMemberSpec(name=n, value=v) for n, v in members]
    value_type = type(members[0][1]).__name__ if members else "str"
    return EnumSpec(
        name=name.lower(),
        cls=f"llm_pipelines.enums.foo.{name}",
        source_path="/tmp/foo.py",
        value_type=value_type,
        members=member_specs,
    )


# ---------------------------------------------------------------------------
# write() — greenfield
# ---------------------------------------------------------------------------


class TestWrite:
    def test_basic_string_enum(self):
        spec = _spec(members=[("POSITIVE", "pos"), ("NEGATIVE", "neg")])
        result = EnumWriter(spec=spec).write()
        assert "from enum import Enum" in result
        assert "class Sentiment(Enum):" in result
        assert "POSITIVE = 'pos'" in result
        assert "NEGATIVE = 'neg'" in result

    def test_int_enum(self):
        spec = _spec(members=[("LOW", 1), ("HIGH", 10)])
        result = EnumWriter(spec=spec).write()
        assert "LOW = 1" in result
        assert "HIGH = 10" in result

    def test_empty_enum_renders_pass(self):
        spec = _spec(members=[])
        result = EnumWriter(spec=spec).write()
        assert "pass" in result


# ---------------------------------------------------------------------------
# edit() — bulk replace
# ---------------------------------------------------------------------------


_EXISTING = textwrap.dedent('''\
    """Sentiment enum module."""
    from enum import Enum


    class Sentiment(Enum):
        POSITIVE = "pos"
        NEGATIVE = "neg"


    class Other(Enum):
        A = 1
''')


class TestEdit:
    def test_replaces_only_target_class(self):
        spec = _spec(members=[
            ("POSITIVE", "positive"),
            ("NEGATIVE", "negative"),
            ("NEUTRAL", "neutral"),
        ])
        result = EnumWriter(spec=spec).edit(_EXISTING)
        # Updated values + new member.
        assert "POSITIVE = 'positive'" in result
        assert "NEUTRAL = 'neutral'" in result
        # Other class untouched.
        assert "class Other(Enum):" in result
        assert "A = 1" in result

    def test_preserves_module_docstring(self):
        spec = _spec(members=[("X", "x")])
        result = EnumWriter(spec=spec).edit(_EXISTING)
        assert '"""Sentiment enum module."""' in result

    def test_no_match_leaves_source_unchanged(self):
        spec = _spec(members=[("X", "x")], name="DoesNotExist")
        result = EnumWriter(spec=spec).edit(_EXISTING)
        # Original sentiment members stay verbatim.
        assert 'POSITIVE = "pos"' in result
        assert "DoesNotExist" not in result


# ---------------------------------------------------------------------------
# apply() — path-guarded write
# ---------------------------------------------------------------------------


class TestApply:
    def test_writes_to_disk(self, tmp_path: Path):
        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = root / "enums" / "foo.py"

        spec = EnumSpec(
            name="sentiment",
            cls="llm_pipelines.enums.foo.Sentiment",
            source_path=str(target),
            value_type="str",
            members=[EnumMemberSpec(name="POSITIVE", value="pos")],
        )
        writer = EnumWriter(spec=spec)
        wrote = writer.apply(writer.write(), root=root)
        assert wrote is True
        assert "POSITIVE = 'pos'" in target.read_text()

    def test_blocks_writes_outside_root(self, tmp_path: Path):
        from llm_pipeline.codegen.io import CodegenPathError

        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = tmp_path / "elsewhere" / "foo.py"

        spec = EnumSpec(
            name="sentiment",
            cls="llm_pipelines.enums.foo.Sentiment",
            source_path=str(target),
            value_type="str",
            members=[EnumMemberSpec(name="X", value="x")],
        )
        writer = EnumWriter(spec=spec)
        with pytest.raises(CodegenPathError):
            writer.apply(writer.write(), root=root)
