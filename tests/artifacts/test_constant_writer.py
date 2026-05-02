"""Tests for :class:`ConstantWriter` — write / edit / apply.

End-to-end coverage of the per-kind writer pattern using the
simplest kind (``Constant``). Other writers follow the same shape.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from llm_pipeline.artifacts.constants import ConstantSpec, ConstantWriter


def _spec(*, class_name: str, value, name: str | None = None) -> ConstantSpec:
    """Build a constant spec with sensible defaults."""
    return ConstantSpec(
        name=name or class_name.lower(),
        cls=f"llm_pipelines.constants.foo.{class_name}",
        source_path="/tmp/foo.py",
        value_type=type(value).__name__,
        value=value,
    )


# ---------------------------------------------------------------------------
# write() — greenfield
# ---------------------------------------------------------------------------


class TestWrite:
    def test_int_constant(self):
        spec = _spec(class_name="MAX_RETRIES", value=3)
        result = ConstantWriter(spec=spec).write()
        assert "from llm_pipeline.constants import Constant" in result
        assert "class MAX_RETRIES(Constant):" in result
        assert "value = 3" in result

    def test_string_constant_quotes_via_repr(self):
        spec = _spec(class_name="LABEL", value="hello")
        result = ConstantWriter(spec=spec).write()
        assert "value = 'hello'" in result

    def test_list_constant(self):
        spec = _spec(class_name="DEFAULTS", value=[1, 2, 3])
        result = ConstantWriter(spec=spec).write()
        assert "value = [1, 2, 3]" in result

    def test_dict_constant(self):
        spec = _spec(class_name="CONFIG", value={"a": 1, "b": 2})
        result = ConstantWriter(spec=spec).write()
        # repr of a dict — exact spacing may vary by Python version
        assert "value = {" in result
        assert "'a': 1" in result


# ---------------------------------------------------------------------------
# edit() — round-trip
# ---------------------------------------------------------------------------


_EXISTING = textwrap.dedent('''\
    """Constants module."""
    from llm_pipeline.constants import Constant


    class MAX_RETRIES(Constant):
        """Max retry count."""
        value = 3


    class DEFAULT_LABEL(Constant):
        value = "unknown"
''')


class TestEdit:
    def test_changes_target_class_only(self):
        spec = _spec(class_name="MAX_RETRIES", value=5)
        result = ConstantWriter(spec=spec).edit(_EXISTING)
        assert "value = 5" in result
        # Other class untouched.
        assert 'value = "unknown"' in result

    def test_preserves_docstring_and_formatting(self):
        spec = _spec(class_name="MAX_RETRIES", value=5)
        result = ConstantWriter(spec=spec).edit(_EXISTING)
        assert '"""Max retry count."""' in result
        assert '"""Constants module."""' in result
        assert "from llm_pipeline.constants import Constant" in result

    def test_changes_string_constant(self):
        spec = _spec(class_name="DEFAULT_LABEL", value="positive")
        result = ConstantWriter(spec=spec).edit(_EXISTING)
        assert "value = 'positive'" in result
        # Other class's value untouched.
        assert "value = 3" in result

    def test_no_match_leaves_source_unchanged(self):
        # Spec targets a class not present in the source.
        spec = _spec(class_name="NEVER_DEFINED", value=99)
        result = ConstantWriter(spec=spec).edit(_EXISTING)
        # libcst round-trip preserves byte-for-byte; both classes stay.
        assert "value = 3" in result
        assert 'value = "unknown"' in result
        assert "NEVER_DEFINED" not in result

    def test_handles_class_pass_body(self):
        # Class with no value yet — writer appends one.
        source = textwrap.dedent('''\
            from llm_pipeline.constants import Constant

            class FOO(Constant):
                pass
        ''')
        spec = _spec(class_name="FOO", value=42)
        result = ConstantWriter(spec=spec).edit(source)
        assert "value = 42" in result


# ---------------------------------------------------------------------------
# apply() — path-guarded write
# ---------------------------------------------------------------------------


class TestApply:
    def test_writes_to_disk(self, tmp_path: Path):
        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = root / "constants" / "foo.py"

        spec = ConstantSpec(
            name="max_retries",
            cls="llm_pipelines.constants.foo.MAX_RETRIES",
            source_path=str(target),
            value_type="int",
            value=3,
        )
        writer = ConstantWriter(spec=spec)
        content = writer.write()
        wrote = writer.apply(content, root=root)
        assert wrote is True
        assert target.exists()
        assert "value = 3" in target.read_text()

    def test_idempotent_skips_when_unchanged(self, tmp_path: Path):
        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = root / "constants" / "foo.py"

        spec = ConstantSpec(
            name="max_retries",
            cls="llm_pipelines.constants.foo.MAX_RETRIES",
            source_path=str(target),
            value_type="int",
            value=3,
        )
        writer = ConstantWriter(spec=spec)
        content = writer.write()
        assert writer.apply(content, root=root) is True
        # Second apply with same content — file already matches.
        assert writer.apply(content, root=root) is False

    def test_blocks_writes_outside_root(self, tmp_path: Path):
        from llm_pipeline.codegen.io import CodegenPathError

        root = tmp_path / "llm_pipelines"
        root.mkdir()
        # Target outside the configured root — should raise.
        target = tmp_path / "elsewhere" / "foo.py"

        spec = ConstantSpec(
            name="max_retries",
            cls="llm_pipelines.constants.foo.MAX_RETRIES",
            source_path=str(target),
            value_type="int",
            value=3,
        )
        writer = ConstantWriter(spec=spec)
        content = writer.write()
        import pytest
        with pytest.raises(CodegenPathError):
            writer.apply(content, root=root)
