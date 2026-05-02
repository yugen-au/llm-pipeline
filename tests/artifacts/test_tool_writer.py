"""Tests for :class:`ToolWriter` — write / edit / apply.

A tool file holds three classes: paired ``Inputs`` (StepInputs) +
``Args`` (BaseModel) + the ``AgentTool`` subclass with INPUTS /
ARGS classvars and a ``run`` classmethod.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from llm_pipeline.artifacts.base.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.artifacts.tools import ToolSpec, ToolWriter


def _spec(
    *,
    inputs_props: dict | None = None,
    inputs_field_source: dict[str, str] | None = None,
    args_props: dict | None = None,
    args_field_source: dict[str, str] | None = None,
    body_source: str | None = None,
    name: str = "WordCountTool",
) -> ToolSpec:
    return ToolSpec(
        name=name.replace("Tool", "").lower(),
        cls=f"llm_pipelines.tools.foo.{name}",
        source_path="/tmp/foo.py",
        inputs=JsonSchemaWithRefs(
            json_schema={
                "properties": inputs_props or {},
                "required": list((inputs_props or {}).keys()),
            },
            field_source=inputs_field_source or {},
        ),
        args=JsonSchemaWithRefs(
            json_schema={
                "properties": args_props or {},
                "required": list((args_props or {}).keys()),
            },
            field_source=args_field_source or {},
        ),
        body=(
            CodeBodySpec(source=body_source) if body_source is not None else None
        ),
    )


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------


class TestWrite:
    def test_basic_tool(self):
        spec = _spec(
            args_props={"text": {"type": "string"}},
            args_field_source={"text": "str"},
            body_source="        return len(args.text.split())\n",
        )
        result = ToolWriter(spec=spec).write()
        # Imports
        assert "from llm_pipeline.agent_tool import AgentTool" in result
        assert "from llm_pipeline.inputs import StepInputs" in result
        # Paired classes
        assert "class WordCountInputs(StepInputs):" in result
        assert "class WordCountArgs(BaseModel):" in result
        assert "text: str" in result
        # Tool class
        assert "class WordCountTool(AgentTool):" in result
        assert "INPUTS = WordCountInputs" in result
        assert "ARGS = WordCountArgs" in result
        assert "@classmethod" in result
        assert "return len(args.text.split())" in result

    def test_output_parses_as_valid_python(self):
        import libcst as cst

        spec = _spec(
            args_props={"text": {"type": "string"}},
            args_field_source={"text": "str"},
            body_source="        return 0\n",
        )
        cst.parse_module(ToolWriter(spec=spec).write())

    def test_missing_body_emits_not_implemented(self):
        spec = _spec(
            args_props={"text": {"type": "string"}},
            args_field_source={"text": "str"},
            body_source=None,
        )
        result = ToolWriter(spec=spec).write()
        assert "raise NotImplementedError" in result


# ---------------------------------------------------------------------------
# edit()
# ---------------------------------------------------------------------------


_EXISTING = textwrap.dedent('''\
    """Word count tool."""
    from pydantic import BaseModel

    from llm_pipeline.agent_tool import AgentTool
    from llm_pipeline.inputs import StepInputs


    class WordCountInputs(StepInputs):
        """No pipeline-side data needed."""


    class WordCountArgs(BaseModel):
        text: str


    class WordCountTool(AgentTool):
        INPUTS = WordCountInputs
        ARGS = WordCountArgs

        @classmethod
        def run(cls, inputs, args, ctx) -> int:
            return len(args.text.split())
''')


class TestEdit:
    def test_replaces_args_class_fields(self):
        spec = _spec(
            args_props={
                "text": {"type": "string"},
                "lang": {"type": "string", "default": "en"},
            },
            args_field_source={"text": "str", "lang": "str"},
            body_source="        return len(args.text.split())\n",
        )
        result = ToolWriter(spec=spec).edit(_EXISTING)
        assert "lang: str = 'en'" in result
        # Inputs class untouched (no fields to add).
        assert "class WordCountInputs(StepInputs):" in result
        # Module docstring preserved.
        assert '"""Word count tool."""' in result

    def test_replaces_run_body(self):
        spec = _spec(
            args_props={"text": {"type": "string"}},
            args_field_source={"text": "str"},
            body_source="        words = args.text.split()\n        return len(words) * 2\n",
        )
        result = ToolWriter(spec=spec).edit(_EXISTING)
        assert "return len(words) * 2" in result
        # Old body gone.
        assert "return len(args.text.split())" not in result


# ---------------------------------------------------------------------------
# apply()
# ---------------------------------------------------------------------------


class TestApply:
    def test_writes_to_disk(self, tmp_path: Path):
        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = root / "tools" / "word_count.py"

        spec = _spec(
            args_props={"text": {"type": "string"}},
            args_field_source={"text": "str"},
            body_source="        return 0\n",
        )
        # Override the spec's source_path now that we have a real path.
        spec = spec.model_copy(update={"source_path": str(target)})
        writer = ToolWriter(spec=spec)
        wrote = writer.apply(writer.write(), root=root)
        assert wrote is True
        assert "class WordCountTool(AgentTool):" in target.read_text()

    def test_blocks_writes_outside_root(self, tmp_path: Path):
        from llm_pipeline.codegen.io import CodegenPathError

        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = tmp_path / "elsewhere" / "word_count.py"

        spec = _spec(
            args_props={"text": {"type": "string"}},
            args_field_source={"text": "str"},
            body_source="        return 0\n",
        )
        spec = spec.model_copy(update={"source_path": str(target)})
        writer = ToolWriter(spec=spec)
        with pytest.raises(CodegenPathError):
            writer.apply(writer.write(), root=root)
